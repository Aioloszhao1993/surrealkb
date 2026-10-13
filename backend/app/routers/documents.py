"""文档：上传 / 列表 / 详情 / 重命名 / 删除 / 重建索引。"""
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
from ..models import Chunk, Document, User
from ..schemas import (
    ChunkOut,
    DocumentContent,
    DocumentOut,
    DocumentPage,
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


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    title: str | None = Form(None, max_length=200),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentOut:
    tenant_id = _require_tenant(user)

    ext = Path(file.filename or "").suffix.lower()
    if ext not in doc_service.SUPPORTED_EXTS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "仅支持 PDF / Word(.docx) / TXT / Markdown 文档"
        )

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

    doc = Document(
        tenant_id=tenant_id,
        title=(title or Path(file.filename or "未命名").stem)[:200],
        filename=stored,
        original_name=file.filename,
        doc_type=doc_service.ext_to_doc_type(ext),
        size=size,
        status="pending",
        owner_id=user.id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # 同步解析 + 分块（文档一般不大，直接同步，失败标记 failed）
    doc_service.process_document(db, doc, dest)
    db.refresh(doc)

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
    tenant_id = _require_tenant(user)
    doc = db.get(Document, doc_id)
    if not doc or doc.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文档不存在")
    return DocumentOut.model_validate(doc)


@router.get("/{doc_id}/chunks", response_model=list[ChunkOut])
def get_document_chunks(
    doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[ChunkOut]:
    tenant_id = _require_tenant(user)
    doc = db.get(Document, doc_id)
    if not doc or doc.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文档不存在")
    rows = db.scalars(
        select(Chunk).where(Chunk.document_id == doc_id).order_by(Chunk.seq.asc())
    ).all()
    return [ChunkOut.model_validate(r) for r in rows]


@router.get("/{doc_id}/content", response_model=DocumentContent)
def get_document_content(
    doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> DocumentContent:
    """文档提取出的纯文本全文（供「原文」阅读视图）。"""
    tenant_id = _require_tenant(user)
    doc = db.get(Document, doc_id)
    if not doc or doc.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文档不存在")
    return DocumentContent(
        id=doc.id,
        title=doc.title,
        content=doc.content or "",
        char_count=doc.char_count or 0,
    )


@router.get("/{doc_id}/raw")
def get_document_raw(
    doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> FileResponse:
    """下载/预览原始上传文件（PDF 可内嵌、Word/TXT 下载）。"""
    tenant_id = _require_tenant(user)
    doc = db.get(Document, doc_id)
    if not doc or doc.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文档不存在")
    path = settings.upload_path / doc.filename
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "原始文件已丢失")
    ext = Path(doc.filename).suffix.lower()
    mime = DOC_MIME.get(ext, "application/octet-stream")
    name = doc.original_name or path.name
    return FileResponse(path, media_type=mime, filename=name)


@router.patch("/{doc_id}", response_model=DocumentOut)
def update_document(
    doc_id: int,
    payload: DocumentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentOut:
    tenant_id = _require_tenant(user)
    doc = db.get(Document, doc_id)
    if not doc or doc.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文档不存在")
    if payload.title is not None:
        doc.title = payload.title
    db.commit()
    db.refresh(doc)
    return DocumentOut.model_validate(doc)


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> None:
    tenant_id = _require_tenant(user)
    doc = db.get(Document, doc_id)
    if not doc or doc.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文档不存在")
    # 仅上传者或管理员可删
    if doc.owner_id != user.id and user.role not in ("owner", "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只能删除自己上传的文档")
    path = settings.upload_path / doc.filename
    db.delete(doc)  # cascade 会一并删 chunks
    db.commit()
    path.unlink(missing_ok=True)


@router.post("/{doc_id}/reindex", response_model=DocumentOut)
def reindex_document(
    doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> DocumentOut:
    """重新解析并重建该文档的向量索引。"""
    tenant_id = _require_tenant(user)
    doc = db.get(Document, doc_id)
    if not doc or doc.tenant_id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文档不存在")
    path = settings.upload_path / doc.filename
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "原始文件已丢失，无法重建")
    doc_service.process_document(db, doc, path)
    if ai_service.ai_ready():
        ai_service.refresh_embeddings(db, force=True, tenant_id=tenant_id)
    db.refresh(doc)
    return DocumentOut.model_validate(doc)
