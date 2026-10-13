"""文档：上传（含同名覆盖）/ 列表 / 详情 / 在线编辑 / 版本历史 / 重命名 / 删除 / 重建索引。"""
import shutil
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import ai_service, doc_service
from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Chunk, Document, DocumentRevision, User
from ..schemas import (
    ChunkOut,
    DocumentConflict,
    DocumentContent,
    DocumentEdit,
    DocumentOut,
    DocumentPage,
    DocumentRevisionOut,
    DocumentUpdate,
)

router = APIRouter(prefix="/api/documents", tags=["documents"])

# 原始文件的 MIME（用于直接下载/内嵌预览）
DOC_MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".markdown": "text/markdown; charset=utf-8",
}


def _require_tenant(user: User) -> int:
    if not user.tenant_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "你还没有加入任何知识库")
    return user.tenant_id


def _can_edit(doc: Document, user: User) -> bool:
    """上传者本人，或知识库创建者/管理员，可编辑。"""
    return doc.owner_id == user.id or user.role in ("owner", "admin")


def _get_doc(doc_id: int, db: Session, user: User) -> Document:
    tenant_id = _require_tenant(user)
    doc = db.get(Document, doc_id)
    if not doc or doc.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文档不存在")
    return doc


def _snapshot(db: Session, doc: Document, user: User) -> None:
    """把文档『当前』正文存为一个历史版本（编辑/回滚前调用）。"""
    db.add(
        DocumentRevision(
            document_id=doc.id,
            revision_no=doc.revision or 1,
            title=doc.title,
            content=doc.content,
            created_by=user.id,
        )
    )


def _trash(path: Path) -> None:
    """把文件移入 trash/ 而非直接删除（可恢复）。"""
    if not path.exists():
        return
    trash_dir = settings.upload_path / "trash"
    trash_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(path), str(trash_dir / f"{uuid.uuid4().hex}{path.suffix}"))
    except OSError:
        path.unlink(missing_ok=True)


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    title: str | None = Form(None, max_length=200),
    file: UploadFile = File(...),
    overwrite: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentOut:
    tenant_id = _require_tenant(user)
    new_title = (title or Path(file.filename or "未命名").stem)[:200]

    ext = Path(file.filename or "").suffix.lower()
    if ext not in doc_service.SUPPORTED_EXTS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "仅支持 PDF / Word(.docx) / TXT / Markdown 文档"
        )

    # 同名查重：默认不覆盖，返回冲突让前端确认；overwrite=true 则替换旧文档
    existing = db.scalars(
        select(Document).where(
            Document.tenant_id == tenant_id, Document.title == new_title
        )
    ).first()
    old = None
    if existing and not overwrite:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=DocumentConflict(
                document_id=existing.id,
                title=new_title,
                message=f"知识库中已存在同名文档《{new_title}》，选择覆盖或改名后再传。",
            ).model_dump(),
        )
    if existing and overwrite:
        old = existing  # 写完新文件、删掉旧行之后再移走旧文件，避免中途失败丢数据

    stored = f"docs/{uuid.uuid4().hex}{ext}"
    dest = settings.upload_path / stored
    dest.parent.mkdir(parents=True, exist_ok=True)

    max_bytes = settings.max_doc_mb * 1024 * 1024
    size = 0
    try:
        with dest.open("wb") as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        f"文档超过 {settings.max_doc_mb}MB 限制",
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"写入失败: {exc}") from exc

    old_path = None
    if old is not None:
        old_path = settings.upload_path / old.filename
        db.delete(old)  # cascade 删其 chunks 与历史版本
        db.flush()

    doc = Document(
        tenant_id=tenant_id,
        title=new_title,
        filename=stored,
        original_name=file.filename,
        doc_type=doc_service.ext_to_doc_type(ext),
        size=size,
        status="pending",
        owner_id=user.id,
        revision=1,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # 同步解析 + 分块（文档一般不大，直接同步，失败标记 failed）
    doc_service.process_document(db, doc, dest)
    db.refresh(doc)

    # 覆盖成功后，把旧文件移入 trash（可恢复），不再留在项目目录
    if old_path is not None:
        _trash(old_path)

    # 后台补向量（不阻塞响应）
    ai_service.index_document_bg(doc.id)

    out = DocumentOut.model_validate(doc)
    out.owner = None
    return out


@router.get("", response_model=DocumentPage)
def list_documents(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    q: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    owner_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=60),
) -> DocumentPage:
    tenant_id = _require_tenant(user)
    stmt = select(Document).where(Document.tenant_id == tenant_id)
    count_stmt = select(func.count()).select_from(Document).where(Document.tenant_id == tenant_id)
    if q:
        stmt = stmt.where(Document.title.like(f"%{q}%"))
        count_stmt = count_stmt.where(Document.title.like(f"%{q}%"))
    if status_filter:
        stmt = stmt.where(Document.status == status_filter)
        count_stmt = count_stmt.where(Document.status == status_filter)
    if owner_id:
        stmt = stmt.where(Document.owner_id == owner_id)
        count_stmt = count_stmt.where(Document.owner_id == owner_id)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return DocumentPage(
        items=[DocumentOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{doc_id}", response_model=DocumentOut)
def get_document(
    doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> DocumentOut:
    doc = _get_doc(doc_id, db, user)
    return DocumentOut.model_validate(doc)


@router.get("/{doc_id}/chunks", response_model=list[ChunkOut])
def get_document_chunks(
    doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[ChunkOut]:
    doc = _get_doc(doc_id, db, user)
    rows = db.scalars(
        select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.seq.asc())
    ).all()
    return [ChunkOut.model_validate(r) for r in rows]


@router.get("/{doc_id}/content", response_model=DocumentContent)
def get_document_content(
    doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> DocumentContent:
    """文档提取出的纯文本全文（供「原文」阅读视图）。"""
    doc = _get_doc(doc_id, db, user)
    return DocumentContent(
        id=doc.id,
        title=doc.title,
        content=doc.content or "",
        char_count=doc.char_count or 0,
        revision=doc.revision or 1,
    )


@router.get("/{doc_id}/raw")
def get_document_raw(
    doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> FileResponse:
    """下载/预览原始上传文件（PDF 可内嵌、Word/TXT 下载）。"""
    doc = _get_doc(doc_id, db, user)
    path = settings.upload_path / doc.filename
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "原始文件已丢失")
    ext = Path(doc.filename).suffix.lower()
    mime = DOC_MIME.get(ext, "application/octet-stream")
    name = doc.original_name or path.name
    return FileResponse(path, media_type=mime, filename=name)


@router.put("/{doc_id}", response_model=DocumentOut)
def edit_document(
    doc_id: int,
    payload: DocumentEdit,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentOut:
    """在线编辑正文（可选改名）：先存历史快照，再用新正文重建分块与向量。"""
    doc = _get_doc(doc_id, db, user)
    if not _can_edit(doc, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只能编辑自己上传的文档")
    text = payload.content.strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "正文不能为空")

    # 1) 保存编辑前的版本
    _snapshot(db, doc, user)
    # 2) 更新标题 / 版本号
    if payload.title and payload.title.strip() and payload.title.strip() != doc.title:
        doc.title = payload.title.strip()[:200]
    doc.revision = (doc.revision or 1) + 1
    doc.edited_at = func.now()
    # 3) 用新正文重建分块（内部会更新 content / char_count / chunk_count）
    doc_service.reindex_text(db, doc, text, reflow=False)
    doc.status = "ready"
    doc.error = None
    db.commit()
    db.refresh(doc)

    # 4) 后台为新的分块补向量
    ai_service.index_document_bg(doc.id)

    out = DocumentOut.model_validate(doc)
    out.owner = None
    return out


@router.get("/{doc_id}/revisions", response_model=list[DocumentRevisionOut])
def list_revisions(
    doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[DocumentRevisionOut]:
    """该文档的历史版本列表（不含全文）。"""
    doc = _get_doc(doc_id, db, user)
    rows = db.scalars(
        select(DocumentRevision)
        .where(DocumentRevision.document_id == doc.id)
        .order_by(DocumentRevision.revision_no.desc(), DocumentRevision.id.desc())
    ).all()
    out: list[DocumentRevisionOut] = []
    for r in rows:
        out.append(
            DocumentRevisionOut(
                id=r.id,
                revision_no=r.revision_no,
                title=r.title,
                char_count=len(r.content or ""),
                created_at=r.created_at,
            )
        )
    return out


@router.get("/{doc_id}/revisions/{rev_id}", response_model=DocumentContent)
def get_revision(
    doc_id: int,
    rev_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentContent:
    """查看某个历史版本的全文。"""
    doc = _get_doc(doc_id, db, user)
    rev = db.get(DocumentRevision, rev_id)
    if not rev or rev.document_id != doc.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "版本不存在")
    return DocumentContent(
        id=rev.id,
        title=rev.title,
        content=rev.content or "",
        char_count=len(rev.content or ""),
        revision=rev.revision_no,
    )


@router.post("/{doc_id}/revisions/{rev_id}/restore", response_model=DocumentOut)
def restore_revision(
    doc_id: int,
    rev_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentOut:
    """回滚到某个历史版本（当前内容会先存为新快照，回滚本身也可撤销）。"""
    doc = _get_doc(doc_id, db, user)
    if not _can_edit(doc, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只能编辑自己上传的文档")
    rev = db.get(DocumentRevision, rev_id)
    if not rev or rev.document_id != doc.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "版本不存在")

    _snapshot(db, doc, user)  # 先存当前版本
    doc.title = rev.title
    doc.revision = (doc.revision or 1) + 1
    doc.edited_at = func.now()
    doc_service.reindex_text(db, doc, rev.content or "", reflow=False)
    doc.status = "ready"
    doc.error = None
    db.commit()
    db.refresh(doc)

    ai_service.index_document_bg(doc.id)
    out = DocumentOut.model_validate(doc)
    out.owner = None
    return out


@router.patch("/{doc_id}", response_model=DocumentOut)
def update_document(
    doc_id: int,
    payload: DocumentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentOut:
    doc = _get_doc(doc_id, db, user)
    if not _can_edit(doc, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只能编辑自己上传的文档")
    if payload.title is not None:
        doc.title = payload.title
    db.commit()
    db.refresh(doc)
    return DocumentOut.model_validate(doc)


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> None:
    doc = _get_doc(doc_id, db, user)
    # 仅上传者或管理员可删
    if not _can_edit(doc, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只能删除自己上传的文档")
    path = settings.upload_path / doc.filename
    db.delete(doc)  # cascade 会一并删 chunks 与历史版本
    db.commit()
    path.unlink(missing_ok=True)


@router.post("/{doc_id}/reindex", response_model=DocumentOut)
def reindex_document(
    doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> DocumentOut:
    """重新解析原始文件并重建该文档的向量索引。"""
    doc = _get_doc(doc_id, db, user)
    if not _can_edit(doc, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只能重建自己上传的文档")
    path = settings.upload_path / doc.filename
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "原始文件已丢失，无法重建")
    _snapshot(db, doc, user)  # 重建前存快照
    doc.revision = (doc.revision or 1) + 1
    doc.edited_at = func.now()
    db.commit()
    doc_service.process_document(db, doc, path)
    if ai_service.ai_ready():
        # 只补『被清掉向量』的新分块（旧向量已随分块删除）
        ai_service.refresh_embeddings(db, tenant_id=doc.tenant_id)
    db.refresh(doc)
    return DocumentOut.model_validate(doc)
