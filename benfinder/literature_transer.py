"""格式转化统一：将期刊 XML/HTML/PDF 解析为可读的 JSON/Markdown。"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Iterable, Optional

from benfinder.config import BLOCKS_OUTPUT_DIR, XML_SOURCE_DIR
from benfinder.transer_tools import (
    DocumentBlock,
    StructuredDocument,
    available_parsers,
    build_blocks,
    describe_parsers,
    resolve_parser,
)
from benfinder import config as project_config


def _supported_suffixes() -> set[str]:
    suffixes: set[str] = set()
    for meta in describe_parsers().values():
        for suffix in (meta.get("suffixes") or "").split(","):
            suffix = suffix.strip()
            if suffix:
                if not suffix.startswith("."):
                    suffix = f".{suffix}"
                suffixes.add(suffix.lower())
    return suffixes or {".xml"}


def parse_document(
    xml_path: Path,
    parser_name: Optional[str] = None,
    *,
    embed_base64: bool = True,
) -> StructuredDocument:
    raw_text = xml_path.read_text(encoding="utf-8", errors="ignore")
    parser_cls = resolve_parser(xml_path, name=parser_name, raw_text=raw_text)
    soup = parser_cls.open_file(str(xml_path))
    metadata = parser_cls.get_metadata(soup)
    paragraphs = parser_cls.parsing(soup)
    blocks = build_blocks(
        paragraphs,
        source_path=xml_path,
        embed_base64=embed_base64,
    )
    return StructuredDocument(metadata=metadata, blocks=blocks)


def _render_markdown(document: StructuredDocument) -> str:
    meta = document.metadata.to_dict()
    authors = meta.get("author_list") or []
    if isinstance(authors, list):
        author_text = "; ".join(str(a) for a in authors if str(a).strip())
    else:
        author_text = str(authors)

    lines = [
        "---",
        f"title: {meta.get('title') or ''}",
        f"doi: {meta.get('doi') or ''}",
        f"journal: {meta.get('journal') or ''}",
        f"date: {meta.get('date') or ''}",
        f"authors: {author_text}",
        "---",
        "",
    ]

    title = (meta.get("title") or "").strip()
    title_written = False
    if title:
        lines.append(f"# {title}")
        lines.append("")
        title_written = True

    meta_lines: list[str] = []
    if meta.get("doi"):
        meta_lines.append(f"- DOI: {meta.get('doi')}")
    if meta.get("journal"):
        meta_lines.append(f"- Journal: {meta.get('journal')}")
    if meta.get("date"):
        meta_lines.append(f"- Date: {meta.get('date')}")
    if author_text:
        meta_lines.append(f"- Authors: {author_text}")
    if meta_lines:
        lines.extend(meta_lines)
        lines.append("")

    for block in document.blocks:
        heading_level = _block_heading_level(block)
        if heading_level and block.type == "text":
            heading_text = (block.content or "").strip()
            if not heading_text:
                continue
            if (
                title_written
                and heading_level == 1
                and title
                and heading_text.casefold() == title.casefold()
            ):
                continue
            lines.append(f"{'#' * heading_level} {heading_text}")
            lines.append("")
            continue

        if block.type == "text":
            text = (block.content or "").strip()
            if text:
                lines.append(text)
                lines.append("")
            continue

        if block.type == "table":
            table_lines = _render_table_markdown(block)
            if table_lines:
                lines.extend(table_lines)
                lines.append("")
            continue

        if block.type == "figure":
            figure_lines = _render_figure_markdown(block)
            if figure_lines:
                lines.extend(figure_lines)
                lines.append("")
            continue

        # fallback
        text = (block.content or "").strip()
        if text:
            lines.append(text)
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def _block_heading_level(block: DocumentBlock) -> Optional[int]:
    metadata = getattr(block, "metadata", {}) or {}
    raw_level = metadata.get("heading_level")
    if isinstance(raw_level, str) and raw_level.isdigit():
        raw_level = int(raw_level)
    if isinstance(raw_level, int):
        return max(1, min(raw_level, 6))
    role = str(metadata.get("role") or "").lower()
    if role in {"heading", "title", "section_title"}:
        return 2
    return None


def _render_table_markdown(block: DocumentBlock) -> list[str]:
    table = block.table or {}
    lines: list[str] = []
    caption = (table.get("caption") or "").strip()
    if caption:
        lines.append(f"**Table:** {caption}")

    header = [str(cell).strip() for cell in (table.get("header") or []) if cell is not None]
    rows = table.get("rows") or []

    if header:
        columns = len(header)
        lines.append(_render_row(header, columns))
        lines.append("| " + " | ".join(["---"] * columns) + " |")
        for row in rows:
            values = [str(cell).strip() for cell in row]
            lines.append(_render_row(values, columns))
        return lines

    if rows:
        for row in rows:
            values = [str(cell).strip() for cell in row if cell is not None]
            if values:
                lines.append(" | ".join(values))
        return lines

    fallback = (block.content or "").strip()
    if fallback:
        lines.append(fallback)
    return lines


def _render_row(values: list[str], columns: int) -> str:
    padded = list(values) + [""] * max(0, columns - len(values))
    return "| " + " | ".join(padded[:columns]) + " |"


def _render_figure_markdown(block: DocumentBlock) -> list[str]:
    figure = block.figure or {}
    caption = (figure.get("caption") or "").strip()
    label = (figure.get("label") or "").strip()
    if label and caption and not caption.startswith(label):
        caption = f"{label}: {caption}"
    caption = caption or (block.content or "").strip()
    if not caption:
        return []
    return [f"*Figure:* {caption}"]


def convert_file(
    xml_path: Path,
    output_dir: Path,
    parser_name: Optional[str] = None,
    output_format: str = "json",
) -> list[Path]:
    fmt = (output_format or "json").lower()
    embed_base64 = bool(
        getattr(project_config, "TRANSER_EMBED_TABLE_FIGURE_BASE64", True)
    ) and fmt in {"json", "both"}
    document = parse_document(xml_path, parser_name, embed_base64=embed_base64)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []

    if fmt in {"json", "both"}:
        output_path = output_dir / f"{xml_path.stem}.json"
        document.to_json(output_path)
        outputs.append(output_path)
    if fmt in {"md", "markdown", "both"}:
        output_path = output_dir / f"{xml_path.stem}.md"
        output_path.write_text(_render_markdown(document), encoding="utf-8")
        outputs.append(output_path)
    return outputs


def iter_xml_files(path: Path) -> Iterable[Path]:
    suffixes = _supported_suffixes()

    if path.is_file():
        if path.suffix.lower() in suffixes:
            yield path
        return

    for suffix in suffixes:
        for file_path in sorted(path.rglob(f"*{suffix}")):
            if file_path.is_file():
                yield file_path


def convert_path(
    input_path: Path,
    output_dir: Path,
    parser_name: Optional[str] = None,
    output_format: str = "json",
) -> None:
    xml_files = list(iter_xml_files(input_path))
    if not xml_files:
        raise FileNotFoundError(f"未找到 XML 文件：{input_path}")

    print(f"[格式转化统一] 开始转换 {len(xml_files)} 个文件")
    for xml_file in xml_files:
        try:
            outputs = convert_file(xml_file, output_dir, parser_name, output_format)
            for output in outputs:
                print(f"[格式转化统一] ok -> {output.name}")
        except Exception as exc:  # noqa: BLE001
            print(f"[格式转化统一] 失败 {xml_file.name}: {exc}")
    print(f"[格式转化统一] 输出目录：{output_dir.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="格式转化统一：将期刊 XML/HTML/PDF 解析为 JSON/Markdown"
    )
    parser.add_argument(
        "--input",
        default=str(XML_SOURCE_DIR),
        help="XML 文件或目录，默认使用 config.XML_SOURCE_DIR",
    )
    parser.add_argument(
        "--output",
        default=str(BLOCKS_OUTPUT_DIR),
        help="输出目录（JSON/MD），默认使用 config.BLOCKS_OUTPUT_DIR",
    )
    parser.add_argument(
        "--parser",
        choices=available_parsers(),
        help="指定解析器名称，默认自动检测",
    )
    parser.add_argument(
        "--output-format",
        choices=["json", "md", "both"],
        default=getattr(project_config, "TRANSER_OUTPUT_FORMAT", "json"),
        help="输出格式：json/md/both",
    )
    parser.add_argument(
        "--ocr-engine",
        choices=["auto", "tesseract", "paddle", "easyocr", "rapidocr", "pypdf2"],
        help="PDF OCR 引擎选择",
    )
    parser.add_argument(
        "--ocr-lang",
        help="OCR 语言（Tesseract 例如 eng/chi_sim；PaddleOCR 例如 en/ch）",
    )
    parser.add_argument(
        "--ocr-dpi",
        type=int,
        help="OCR 转图 DPI（默认读取 config.OCR_DPI）",
    )
    parser.add_argument(
        "--ocr-preprocess",
        choices=["none", "grayscale", "binarize", "sharpen"],
        help="OCR 图像预处理方式",
    )
    parser.add_argument(
        "--ocr-tesseract-config",
        help="Tesseract 额外参数（例如 --psm 6）",
    )
    parser.add_argument(
        "--ocr-easyocr-langs",
        help="EasyOCR 语言列表（逗号分隔，例如 en,ch_sim）",
    )
    parser.add_argument(
        "--ocr-easyocr-gpu",
        choices=["true", "false"],
        help="EasyOCR 是否启用 GPU",
    )
    parser.add_argument(
        "--ocr-paddle-lang",
        help="PaddleOCR 语言（例如 en/ch）",
    )
    parser.add_argument(
        "--ocr-paddle-use-angle-cls",
        choices=["true", "false"],
        help="PaddleOCR 是否启用方向分类",
    )
    parser.add_argument(
        "--ocr-paddle-use-gpu",
        choices=["true", "false"],
        help="PaddleOCR 是否启用 GPU",
    )
    args = parser.parse_args()

    if args.ocr_engine:
        os.environ["BENF_OCR_ENGINE"] = args.ocr_engine
    if args.ocr_lang:
        os.environ["BENF_OCR_LANG"] = args.ocr_lang
    if args.ocr_dpi is not None:
        os.environ["BENF_OCR_DPI"] = str(args.ocr_dpi)
    if args.ocr_preprocess:
        os.environ["BENF_OCR_PREPROCESS"] = args.ocr_preprocess
    if args.ocr_tesseract_config:
        os.environ["BENF_OCR_TESSERACT_CONFIG"] = args.ocr_tesseract_config
    if args.ocr_easyocr_langs:
        os.environ["BENF_OCR_EASYOCR_LANGS"] = args.ocr_easyocr_langs
    if args.ocr_easyocr_gpu:
        os.environ["BENF_OCR_EASYOCR_GPU"] = (
            "1" if args.ocr_easyocr_gpu == "true" else "0"
        )
    if args.ocr_paddle_lang:
        os.environ["BENF_OCR_PADDLE_LANG"] = args.ocr_paddle_lang
    if args.ocr_paddle_use_angle_cls:
        os.environ["BENF_OCR_PADDLE_USE_ANGLE_CLS"] = (
            "1" if args.ocr_paddle_use_angle_cls == "true" else "0"
        )
    if args.ocr_paddle_use_gpu:
        os.environ["BENF_OCR_PADDLE_USE_GPU"] = (
            "1" if args.ocr_paddle_use_gpu == "true" else "0"
        )

    input_path = Path(args.input)
    output_dir = Path(args.output)

    if not input_path.exists():
        raise FileNotFoundError(f"输入路径不存在：{input_path}")

    convert_path(input_path, output_dir, args.parser, args.output_format)


if __name__ == "__main__":
    main()
