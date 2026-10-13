"""文档服务：文本提取 + 分块 + 入库。

支持 PDF / Word(.docx) / TXT / Markdown。
链路：读取文件 → 提取纯文本 → 归一化 → 按段落聚合分块（带重叠） → 写 Chunk 表。
向量索引由 ai_service.refresh_embeddings 负责（本模块只落文本，向量可后续补）。
"""
from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy.orm import Session

from .config import settings
from .models import Chunk, Document

SUPPORTED_EXTS = {".pdf", ".docx", ".txt", ".md", ".markdown"}
DOC_TYPE_BY_EXT = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".md": "md",
    ".markdown": "md",
}


def ext_to_doc_type(ext: str) -> str:
    return DOC_TYPE_BY_EXT.get(ext.lower(), "txt")


# ---------------------------------------------------------------- 文本提取
def extract_text(path: Path, doc_type: str) -> str:
    if doc_type == "pdf":
        return _extract_pdf(path)
    if doc_type == "docx":
        return _extract_docx(path)
    return _extract_plain(path)


def _extract_pdf(path: Path) -> str:
    """提 PDF 文字。

    优先用 PyMuPDF 的「排版顺序」模式（sort=True）：
    表单型 PDF 里，填写的值（姓名/日期/月数等）在内容流中常与标签分离，
    pypdf 逐页提取会把它们抛到文末，导致「乙方姓名」「试用期为___月」丢值；
    sort=True 按视觉坐标重排，能把值贴回标签后面。
    失败则回退 pypdf。
    """
    try:
        import pymupdf  # PyMuPDF

        with pymupdf.open(str(path)) as doc:
            parts = [page.get_text("text", sort=True) for page in doc]
        return _cleanup_pdf_text("\n".join(parts))
    except Exception:  # noqa: BLE001
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001
                continue
        return "\n".join(parts)


def _cleanup_pdf_text(text: str) -> str:
    """清理 PDF 文本：压缩表单下划线填充、去掉零宽字符、压掉多余空白。"""
    text = text.replace("\u200b", "").replace("\ufeff", "")
    # 长下划线填充（表单空位）压成 3 个，减少噪声但保留「这里有值」的语义
    text = re.sub(r"_{3,}", "___", text)
    # 行内多余空格
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def _extract_docx(path: Path) -> str:
    """提 Word 文字：按文档真实顺序遍历「段落 + 表格」交错结构。

    旧做法先收集所有段落、再把所有表格追加到末尾，会打乱顺序
    （标题全挤到开头、正文全堆在后面）。这里按 body 子元素顺序输出；
    表格按行导出，并去掉合并单元格造成的相邻重复列。
    """
    from docx import Document as DocxDocument
    from docx.oxml.ns import qn

    doc = DocxDocument(str(path))
    parts: list[str] = []
    for child in doc.element.body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            txt = "".join(node.text or "" for node in child.iter(qn("w:t"))).strip()
            if txt:
                parts.append(txt)
        elif tag == "tbl":
            parts.extend(_docx_table_lines(child, qn))
    return "\n".join(parts)


def _docx_table_lines(tbl, qn) -> list[str]:
    """把一个 w:tbl 元素导出为若干行文本（每行单元格用 " | " 连接）。"""
    lines: list[str] = []
    for tr in tbl.findall(qn("w:tr")):
        cells: list[str] = []
        for tc in tr.findall(qn("w:tc")):
            cell = " ".join(
                "".join(node.text or "" for node in p.iter(qn("w:t"))).strip()
                for p in tc.findall(qn("w:p"))
            ).strip()
            cells.append(cell)
        # 合并单元格会把同一段文字重复到相邻列，去掉相邻重复
        dedup = [c for i, c in enumerate(cells) if i == 0 or c != cells[i - 1]]
        line = " | ".join(dedup).strip(" |")
        if line:
            lines.append(line)
    return lines


def _extract_plain(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "gbk", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


# ---------------------------------------------------------------- 归一化 + 分块
def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_units(text: str, reflow: bool = True) -> list[str]:
    """把正文切成「语义单元」。

    reflow=True（PDF）：先合并 PDF 视觉折行（每行都换行，一句话被拆成多行），
    再按句末标点/换行切。
    reflow=False（Word/TXT/MD 等已结构化文本）：保留原有换行/段落边界，
    每个段落/表格行自成一个或多个单元，不被错误地跨行拼接。
    """
    if reflow:
        # 合并被折行的句子：换行前后都不是句末/标题特征时，删掉该换行
        text = re.sub(r"(?<=[^\n。！？；;.!?：:])\n(?=[^\n])", "", text)
    # 连续空行压成一个换行
    text = re.sub(r"\n{2,}", "\n", text)
    # 按句末标点 / 换行切（保留标点）
    parts = re.split(r"(?<=[。！？；;!?])\s*|\n+", text)
    units: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(p) > settings.chunk_size:
            # 超长单元再按逗号/顿号切
            for s in re.split(r"(?<=[，,、])", p):
                s = s.strip()
                if s:
                    units.append(s)
        else:
            units.append(p)
    return units


def _overlap_tail(text: str, limit: int) -> str:
    """取 text 末尾若干「完整句子」作为下一块的重叠前缀，总长尽量 ≤ limit。

    关键：即使整段没有句末标点（如词汇/短语表，每行一条），也必须把重叠
    长度硬性封顶到 limit，否则会把整个上一块当成尾巴，导致后续块滚雪球式重复。
    """
    if limit <= 0:
        return ""
    sents = [s.strip() for s in re.split(r"(?<=[。！？；;!?])", text) if s.strip()]
    tail = ""
    for s in reversed(sents):
        if tail and len(s) + len(tail) + 1 > limit:
            break
        tail = f"{s} {tail}".strip()
    # 封顶：重叠永不超限（无句末标点时取末尾 limit 字）
    if len(tail) > limit:
        tail = tail[-limit:]
    return tail


def chunk_text(text: str, reflow: bool = True) -> list[str]:
    """把正文按语义单元聚合分块：块尽量填满 chunk_size，块间按整句重叠。

    保证：每个单元至少出现在一个块里（不丢内容）；块以完整句子/条款开头。
    """
    units = split_units(normalize(text), reflow)
    if not units:
        return []

    chunks: list[str] = []
    buf = ""
    for u in units:
        candidate = f"{buf} {u}".strip() if buf else u
        if not buf or len(candidate) <= settings.chunk_size:
            buf = candidate
        else:
            chunks.append(buf)
            tail = _overlap_tail(buf, settings.chunk_overlap)
            buf = f"{tail} {u}".strip() if tail else u
    if buf.strip():
        chunks.append(buf.strip())
    return chunks


# ---------------------------------------------------------------- 入库
def build_chunks(db: Session, document: Document, text: str, reflow: bool = True) -> int:
    """把文本分块写入 Chunk 表，返回块数。"""
    pieces = chunk_text(text, reflow)
    # 先清掉旧分块（重建/重新解析场景），避免重复累积
    db.query(Chunk).filter(Chunk.document_id == document.id).delete()
    db.flush()
    for i, piece in enumerate(pieces):
        db.add(
            Chunk(
                document_id=document.id,
                tenant_id=document.tenant_id,
                seq=i,
                content=piece,
                dim=settings.ai_embed_dim,
            )
        )
    document.chunk_count = len(pieces)
    document.char_count = len(text)
    db.commit()
    return len(pieces)


def process_document(db: Session, document: Document, path: Path) -> None:
    """完整处理：提取 → 分块。异常时把文档标记 failed。"""
    try:
        text = normalize(extract_text(path, document.doc_type))
        if not text:
            raise ValueError("未能从文件中提取到文本（可能是扫描版 PDF 或空文件）")
        # 仅 PDF 需要「合并视觉折行」；其他格式保留原有段落/行结构
        reflow = document.doc_type == "pdf"
        build_chunks(db, document, text, reflow)
        document.status = "ready"
        document.error = None
    except Exception as exc:  # noqa: BLE001
        document.status = "failed"
        document.error = str(exc)[:480]
    db.commit()
