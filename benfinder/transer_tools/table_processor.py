"""
Elsevier 表格解析工具。

把解析器返回的 `<table>` 节点转成结构化 JSON，可供 LLM 提示或后续数据处理使用。

要点：
1. 保留 caption、表头、行数据的纯文本，同时记录原始 HTML（以 Base64 形式避免编码损失）。
2. 生成 CSV 字符串，方便直接送入 LLM 或导出表格。
3. 仅保留表级别的原始 HTML；单元格级别的 HTML 通过 CSV/文本表示。
"""

from __future__ import annotations

import base64
import csv
import io
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from bs4 import BeautifulSoup

from benfinder.config import TRANSER_EMBED_TABLE_FIGURE_BASE64
from .text_cleaning import clean_text

ROW_TAGS: Sequence[str] = ("ce:row", "row", "tr")
SECTION_TAGS: Sequence[str] = ("ce:tbody", "tbody")
CELL_TAGS: Sequence[str] = ("ce:cell", "cell", "entry", "td", "th")


def _encode_base64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def extract_table_nodes(xml_path: Path) -> List[Any]:
    """从 XML 文件中提取原始表格节点。"""

    if not xml_path.exists():
        raise FileNotFoundError(f"找不到 XML 文件：{xml_path}")

    with xml_path.open("r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "lxml-xml")

    tables = soup.find_all(["ce:table", "table"])
    return tables


def parse_table_html_block(html: str) -> Optional[Any]:
    """将段落中的 table HTML 片段转成 BeautifulSoup 节点。"""

    if not html.strip():
        return None
    soup = BeautifulSoup(html, "lxml-xml")
    table = soup.find(["ce:table", "table"])
    return table


def normalize_table_structure(
    table_nodes: Iterable[Any],
    *,
    context: Optional[Dict[str, Any]] = None,
    embed_base64: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """将 BeautifulSoup 节点转成统一结构。"""

    if embed_base64 is None:
        embed_base64 = TRANSER_EMBED_TABLE_FIGURE_BASE64

    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(table_nodes, start=1):
        if isinstance(item, tuple):
            node, node_context = item
        else:
            node, node_context = item, {}

        node_context = {**(context or {}), **node_context}
        caption = _extract_caption(node, embed_base64=embed_base64)
        header = _extract_header(node)
        rows = _extract_rows(node)
        csv_content = _render_csv(header, rows)

        entry: Dict[str, Any] = {
            "table_idx": idx,
            "source_id": node.get("id"),
            "caption": caption["text"],
            "caption_html": caption["html"],
            "header": header,
            "rows": rows,
            "csv": csv_content,
            "context": node_context,
        }
        if caption.get("html_base64"):
            entry["caption_html_base64"] = caption["html_base64"]
        if embed_base64:
            entry["raw_html_base64"] = _encode_base64(str(node))
        normalized.append(entry)
    return normalized


def serialize_tables(json_dir: Path, tables: List[Dict[str, Any]]) -> Optional[Path]:
    """把标准化表格写入 JSON 文件，便于调试。"""

    if not tables:
        return None

    json_dir.mkdir(parents=True, exist_ok=True)
    output_path = json_dir / "tables.json"
    import json

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(tables, f, ensure_ascii=False, indent=2)
    return output_path


def table_to_plain_text(table: Dict[str, Any], *, max_rows: Optional[int] = None) -> str:
    """
    将标准化表格转成纯文本，遵循“idx/type/content”格式的 content 字段需求。

    - caption（如果存在）会作为首行。
    - header 与数据行使用 " | " 连接，保持结构。
    - max_rows 为 None 时输出全部行，否则限制行数以避免冗长。
    """

    lines: List[str] = []
    caption = table.get("caption")
    if caption:
        lines.append(f"Caption: {caption}")

    header = table.get("header") or []
    if header:
        header_line = " | ".join(cell.strip() for cell in header if cell)
        if header_line:
            lines.append(header_line)

    rows = table.get("rows") or []
    limit = len(rows) if max_rows is None else max_rows
    for row in rows[:limit]:
        row_line = " | ".join(cell.strip() for cell in row if cell)
        if row_line:
            lines.append(row_line)

    return "\n".join(line for line in lines if line).strip()


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------


def _extract_caption(node: Any, *, embed_base64: bool) -> Dict[str, Any]:
    caption_tag = node.find(["ce:caption", "caption"])
    if not caption_tag:
        return {"text": "", "html": "", "html_base64": None}
    raw_html = caption_tag.decode()
    texts = [clean_text(text) for text in caption_tag.stripped_strings]
    text = " ".join(texts)
    html_base64 = _encode_base64(raw_html) if embed_base64 else None
    return {
        "text": text,
        "html": raw_html,
        "html_base64": html_base64,
    }


def _extract_header(node: Any) -> List[str]:
    header_rows = None
    thead = node.find(["ce:thead", "thead"])
    if thead:
        header_rows = thead.find_all(ROW_TAGS, recursive=False) or thead.find_all(ROW_TAGS)
    if not header_rows:
        first_row = node.find(ROW_TAGS)
        header_rows = [first_row] if first_row else []

    if not header_rows:
        return []

    return _extract_row_cells(header_rows[0])


def _extract_rows(node: Any) -> List[List[str]]:
    rows: List[List[str]] = []
    body_sections = node.find_all(SECTION_TAGS)
    if not body_sections:
        tgroup = node.find("tgroup")
        if tgroup:
            body_sections = tgroup.find_all(SECTION_TAGS)
            if not body_sections:
                body_sections = [tgroup]
    if not body_sections:
        body_sections = [node]
    for section in body_sections:
        row_tags = section.find_all(ROW_TAGS)
        for row in row_tags:
            cells = _extract_row_cells(row)
            if cells:
                rows.append(cells)
    return rows


def _extract_row_cells(row: Any) -> List[str]:
    values: List[str] = []
    for cell in row.find_all(CELL_TAGS, recursive=False):
        texts = [clean_text(text) for text in cell.stripped_strings]
        value = " ".join(texts).strip()
        values.append(value)
    return values


def _render_csv(header: List[str], rows: List[List[str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    if header:
        writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().strip()
