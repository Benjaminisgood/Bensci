"""OCR-based parser for PDF articles."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from bensci import config as project_config

from ...models import Metadata, Paragraph
from ...parser_base import BaseParser
from ...registry import register_parser
from ...text_cleaning import clean_text
from .common import (
    chunk_text,
    classify_paragraph,
    guess_authors,
    guess_date,
    guess_doi,
    guess_journal,
    guess_title,
)

LOGGER = logging.getLogger(__name__)

try:
    from pdf2image import convert_from_path  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    convert_from_path = None

try:
    import pytesseract  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    pytesseract = None

try:
    from paddleocr import PaddleOCR  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    PaddleOCR = None

try:
    import easyocr  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    easyocr = None

try:
    from rapidocr_onnxruntime import RapidOCR  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    RapidOCR = None

try:
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    np = None

try:
    from PIL import ImageFilter  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    ImageFilter = None

try:
    from PyPDF2 import PdfReader  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    PdfReader = None


@dataclass(slots=True)
class OCRPage:
    """Container for a single OCR-ed PDF page."""

    number: int
    text: str


@dataclass(slots=True)
class OCRDocument:
    """Aggregated OCR result for a PDF file."""

    path: Path
    pages: List[OCRPage]
    raw_metadata: Dict[str, str]

    @property
    def full_text(self) -> str:
        return "\n".join(page.text for page in self.pages)


def ocr(
    pdf_path: str | Path,
    *,
    engine: Optional[str] = None,
    lang: Optional[str] = None,
    dpi: Optional[int] = None,
    preprocess: Optional[str] = None,
    tesseract_config: Optional[str] = None,
    easyocr_langs: Optional[Sequence[str] | str] = None,
    easyocr_gpu: Optional[bool] = None,
    paddle_lang: Optional[str] = None,
    paddle_use_angle_cls: Optional[bool] = None,
    paddle_use_gpu: Optional[bool] = None,
) -> OCRDocument:
    """
    对 PDF 执行 OCR，返回按页归档的文本结果。

    支持 tesseract / paddle / pypdf2，多引擎可通过配置或环境变量切换。
    """

    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"未找到 PDF 文件：{path}")

    options = _resolve_ocr_options(
        engine=engine,
        lang=lang,
        dpi=dpi,
        preprocess=preprocess,
        tesseract_config=tesseract_config,
        easyocr_langs=easyocr_langs,
        easyocr_gpu=easyocr_gpu,
        paddle_lang=paddle_lang,
        paddle_use_angle_cls=paddle_use_angle_cls,
        paddle_use_gpu=paddle_use_gpu,
    )
    engine = options["engine"]
    pages: List[OCRPage] = []

    if engine == "paddle":
        pages = _ocr_with_paddle(path, options)
    elif engine == "easyocr":
        pages = _ocr_with_easyocr(path, options)
    elif engine == "rapidocr":
        pages = _ocr_with_rapidocr(path, options)
    elif engine == "tesseract":
        pages = _ocr_with_tesseract(path, options)
    elif engine == "pypdf2":
        pages = _ocr_with_pypdf2(path)
    elif engine == "auto":
        pages = _ocr_auto(path, options)
    else:
        raise RuntimeError(f"未知 OCR 引擎：{engine}")

    raw_metadata = _read_pdf_metadata(path)
    return OCRDocument(path=path, pages=pages, raw_metadata=raw_metadata)


def _resolve_ocr_options(
    *,
    engine: Optional[str],
    lang: Optional[str],
    dpi: Optional[int],
    preprocess: Optional[str],
    tesseract_config: Optional[str],
    easyocr_langs: Optional[Sequence[str] | str],
    easyocr_gpu: Optional[bool],
    paddle_lang: Optional[str],
    paddle_use_angle_cls: Optional[bool],
    paddle_use_gpu: Optional[bool],
) -> Dict[str, object]:
    def _env(key: str) -> Optional[str]:
        value = os.getenv(key)
        if value is None or str(value).strip() == "":
            return None
        return str(value)

    def _resolve_bool(value: Optional[str], default: bool) -> bool:
        if value is None:
            return default
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y"}:
            return True
        if lowered in {"0", "false", "no", "n"}:
            return False
        return default

    def _resolve_int(value: Optional[str], default: int) -> int:
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    engine = engine or _env("BENF_OCR_ENGINE") or getattr(project_config, "OCR_ENGINE", "auto")
    engine = str(engine).lower().strip() or "auto"

    preprocess = preprocess or _env("BENF_OCR_PREPROCESS") or getattr(project_config, "OCR_PREPROCESS", "none")
    preprocess = str(preprocess).lower().strip() or "none"

    resolved_lang = lang or _env("BENF_OCR_LANG") or getattr(project_config, "OCR_LANG", "eng")
    resolved_dpi = dpi if dpi is not None else _resolve_int(_env("BENF_OCR_DPI"), int(getattr(project_config, "OCR_DPI", 300)))

    tesseract_config = (
        tesseract_config
        or _env("BENF_OCR_TESSERACT_CONFIG")
        or getattr(project_config, "OCR_TESSERACT_CONFIG", "")
    )

    if easyocr_langs is None:
        easyocr_langs_raw = (
            _env("BENF_OCR_EASYOCR_LANGS")
            or (",".join(getattr(project_config, "OCR_EASYOCR_LANGS", []) or []))
        )
    else:
        easyocr_langs_raw = easyocr_langs
    if isinstance(easyocr_langs_raw, (list, tuple)):
        easyocr_langs_list = [str(item).strip() for item in easyocr_langs_raw if str(item).strip()]
    else:
        easyocr_langs_list = [
            item.strip()
            for item in str(easyocr_langs_raw).split(",")
            if item.strip()
        ]
    if easyocr_gpu is None:
        easyocr_gpu = _resolve_bool(
            _env("BENF_OCR_EASYOCR_GPU"),
            bool(getattr(project_config, "OCR_EASYOCR_GPU", False)),
        )
    easyocr_gpu = bool(easyocr_gpu) if easyocr_langs_list else False

    paddle_lang = (
        paddle_lang
        or _env("BENF_OCR_PADDLE_LANG")
        or getattr(project_config, "OCR_PADDLE_LANG", "en")
    )
    paddle_use_angle_cls = (
        paddle_use_angle_cls
        if paddle_use_angle_cls is not None
        else _resolve_bool(
            _env("BENF_OCR_PADDLE_USE_ANGLE_CLS"),
            bool(getattr(project_config, "OCR_PADDLE_USE_ANGLE_CLS", True)),
        )
    )
    paddle_use_gpu = (
        paddle_use_gpu
        if paddle_use_gpu is not None
        else _resolve_bool(
            _env("BENF_OCR_PADDLE_USE_GPU"),
            bool(getattr(project_config, "OCR_PADDLE_USE_GPU", False)),
        )
    )
    priority = getattr(project_config, "OCR_ENGINE_PRIORITY", ["paddle", "tesseract", "pypdf2"])

    return {
        "engine": engine,
        "lang": resolved_lang,
        "dpi": resolved_dpi,
        "preprocess": preprocess,
        "tesseract_config": tesseract_config,
        "easyocr_langs": easyocr_langs_list,
        "easyocr_gpu": easyocr_gpu,
        "paddle_lang": paddle_lang,
        "paddle_use_angle_cls": paddle_use_angle_cls,
        "paddle_use_gpu": paddle_use_gpu,
        "priority": [str(item).lower() for item in (priority or [])],
    }


def _preprocess_image(image, mode: str):
    if mode == "none":
        return image
    try:
        if mode == "grayscale":
            return image.convert("L")
        if mode == "binarize":
            gray = image.convert("L")
            return gray.point(lambda x: 0 if x < 180 else 255, "1")
        if mode == "sharpen" and ImageFilter is not None:
            return image.filter(ImageFilter.SHARPEN)
    except Exception:  # noqa: BLE001
        return image
    return image


def _images_from_pdf(path: Path, dpi: int):
    if not convert_from_path:
        raise RuntimeError("缺少 pdf2image，无法将 PDF 转为图片。")
    return convert_from_path(str(path), dpi=dpi)


def _ocr_with_tesseract(path: Path, options: Dict[str, object]) -> List[OCRPage]:
    if not convert_from_path or not pytesseract:
        raise RuntimeError("缺少 pdf2image 或 pytesseract，无法使用 Tesseract OCR。")
    lang = str(options["lang"])
    dpi = int(options["dpi"])
    tesseract_config = str(options.get("tesseract_config") or "")
    preprocess = str(options.get("preprocess") or "none")

    LOGGER.info("OCR(Tesseract): %s | dpi=%s | lang=%s | preprocess=%s", path.name, dpi, lang, preprocess)
    images = _images_from_pdf(path, dpi)
    pages: List[OCRPage] = []
    for idx, image in enumerate(images, start=1):
        processed = _preprocess_image(image, preprocess)
        text = pytesseract.image_to_string(processed, lang=lang, config=tesseract_config or None)
        pages.append(OCRPage(number=idx, text=text or ""))
    return pages


def _easyocr_extract_text(result) -> str:
    lines: List[str] = []
    if not result:
        return ""
    for item in result:
        if not item or len(item) < 2:
            continue
        text = str(item[1]).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def _ocr_with_easyocr(path: Path, options: Dict[str, object]) -> List[OCRPage]:
    if not convert_from_path or not easyocr or np is None:
        raise RuntimeError("缺少 easyocr/pdf2image/numpy，无法使用 EasyOCR。")
    langs = options.get("easyocr_langs") or ["en"]
    dpi = int(options["dpi"])
    preprocess = str(options.get("preprocess") or "none")
    use_gpu = bool(options.get("easyocr_gpu"))

    LOGGER.info(
        "OCR(EasyOCR): %s | dpi=%s | langs=%s | use_gpu=%s | preprocess=%s",
        path.name,
        dpi,
        langs,
        use_gpu,
        preprocess,
    )
    reader = easyocr.Reader(list(langs), gpu=use_gpu)
    images = _images_from_pdf(path, dpi)
    pages: List[OCRPage] = []
    for idx, image in enumerate(images, start=1):
        processed = _preprocess_image(image, preprocess)
        result = reader.readtext(np.array(processed))
        text = _easyocr_extract_text(result)
        pages.append(OCRPage(number=idx, text=text or ""))
    return pages


def _rapidocr_extract_text(result) -> str:
    lines: List[str] = []
    if not result:
        return ""
    for item in result:
        if not item or len(item) < 2:
            continue
        text = str(item[1]).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def _ocr_with_rapidocr(path: Path, options: Dict[str, object]) -> List[OCRPage]:
    if not convert_from_path or RapidOCR is None or np is None:
        raise RuntimeError("缺少 rapidocr-onnxruntime/pdf2image/numpy，无法使用 RapidOCR。")
    dpi = int(options["dpi"])
    preprocess = str(options.get("preprocess") or "none")

    LOGGER.info(
        "OCR(RapidOCR): %s | dpi=%s | preprocess=%s",
        path.name,
        dpi,
        preprocess,
    )
    ocr_engine = RapidOCR()
    images = _images_from_pdf(path, dpi)
    pages: List[OCRPage] = []
    for idx, image in enumerate(images, start=1):
        processed = _preprocess_image(image, preprocess)
        result, _ = ocr_engine(np.array(processed))
        text = _rapidocr_extract_text(result)
        pages.append(OCRPage(number=idx, text=text or ""))
    return pages


def _paddle_extract_text(result) -> str:
    lines: List[str] = []
    if not result:
        return ""
    if len(result) == 1 and isinstance(result[0], list) and result and result[0] and isinstance(result[0][0], list):
        result = result[0]
    for item in result:
        if not item or len(item) < 2:
            continue
        text_info = item[1]
        if isinstance(text_info, (list, tuple)) and text_info:
            text = str(text_info[0]).strip()
            if text:
                lines.append(text)
    return "\n".join(lines)


def _ocr_with_paddle(path: Path, options: Dict[str, object]) -> List[OCRPage]:
    if not convert_from_path or not PaddleOCR or np is None:
        raise RuntimeError("缺少 paddleocr/pdf2image/numpy，无法使用 PaddleOCR。")
    lang = str(options["paddle_lang"])
    dpi = int(options["dpi"])
    preprocess = str(options.get("preprocess") or "none")
    use_angle_cls = bool(options.get("paddle_use_angle_cls"))
    use_gpu = bool(options.get("paddle_use_gpu"))

    LOGGER.info(
        "OCR(PaddleOCR): %s | dpi=%s | lang=%s | angle_cls=%s | use_gpu=%s | preprocess=%s",
        path.name,
        dpi,
        lang,
        use_angle_cls,
        use_gpu,
        preprocess,
    )
    ocr_engine = PaddleOCR(use_angle_cls=use_angle_cls, lang=lang, use_gpu=use_gpu)
    images = _images_from_pdf(path, dpi)
    pages: List[OCRPage] = []
    for idx, image in enumerate(images, start=1):
        processed = _preprocess_image(image, preprocess)
        result = ocr_engine.ocr(np.array(processed), cls=use_angle_cls)
        text = _paddle_extract_text(result)
        pages.append(OCRPage(number=idx, text=text or ""))
    return pages


def _ocr_with_pypdf2(path: Path) -> List[OCRPage]:
    if not PdfReader:
        raise RuntimeError("缺少 PyPDF2，无法使用 pypdf2 文本抽取。")
    LOGGER.debug("OCR 回退：PyPDF2 %s", path.name)
    reader = PdfReader(str(path))
    pages: List[OCRPage] = []
    for idx, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("读取 PDF 第 %d 页失败：%s", idx, exc)
            text = ""
        pages.append(OCRPage(number=idx, text=text))
    return pages


def _is_engine_available(engine: str) -> bool:
    if engine == "paddle":
        return bool(convert_from_path and PaddleOCR and np is not None)
    if engine == "easyocr":
        return bool(convert_from_path and easyocr and np is not None)
    if engine == "rapidocr":
        return bool(convert_from_path and RapidOCR and np is not None)
    if engine == "tesseract":
        return bool(convert_from_path and pytesseract)
    if engine == "pypdf2":
        return bool(PdfReader)
    return False


def _ocr_auto(path: Path, options: Dict[str, object]) -> List[OCRPage]:
    priority = options.get("priority") or []
    candidates = [item for item in priority if _is_engine_available(item)]
    if not candidates:
        if PdfReader:
            return _ocr_with_pypdf2(path)
        raise RuntimeError("未找到可用 OCR 引擎，请检查依赖安装情况。")

    for engine in candidates:
        try:
            if engine == "paddle":
                return _ocr_with_paddle(path, options)
            if engine == "easyocr":
                return _ocr_with_easyocr(path, options)
            if engine == "rapidocr":
                return _ocr_with_rapidocr(path, options)
            if engine == "tesseract":
                return _ocr_with_tesseract(path, options)
            if engine == "pypdf2":
                return _ocr_with_pypdf2(path)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("OCR(%s) 失败，尝试下一个引擎：%s", engine, exc)
            continue

    raise RuntimeError("OCR 自动流程失败，请检查日志。")


def _read_pdf_metadata(path: Path) -> Dict[str, str]:
    if not PdfReader:
        return {}
    try:
        reader = PdfReader(str(path))
    except Exception:  # noqa: BLE001
        return {}
    info = reader.metadata or {}
    metadata: Dict[str, str] = {}
    for key, value in info.items():
        if not value:
            continue
        normalized_key = key.lstrip("/").lower()
        metadata[normalized_key] = str(value)
    return metadata


class WileyPDFParser(BaseParser):
    """Parser implementation that normalises Wiley PDF files via OCR."""

    suffixes: Sequence[str] = (".pdf",)
    parser = "pdf"
    content_type = "pdf"
    para_tags: List[str] = []
    table_tags: List[str] = []
    figure_tags: List[str] = []

    @classmethod
    def supports(cls, path, raw_text: str) -> bool:  # type: ignore[override]
        return path.suffix.lower() == ".pdf" and "wiley" in path.stem.lower()

    @classmethod
    def open_file(cls, filepath: str) -> OCRDocument:  # type: ignore[override]
        return ocr(filepath)

    @classmethod
    def parsing(cls, document: OCRDocument) -> List[Paragraph]:  # type: ignore[override]
        paragraphs: List[Paragraph] = []
        for page in document.pages:
            for local_idx, chunk in enumerate(chunk_text(page.text), start=1):
                cleaned = clean_text(chunk)
                if not cleaned:
                    continue
                para_type = classify_paragraph(cleaned)
                paragraphs.append(
                    Paragraph(
                        idx=f"{page.number}.{local_idx}",
                        type=para_type,
                        content=chunk,
                        clean_text=cleaned,
                        intermediate_step={"page": page.number},
                    )
                )
        return paragraphs

    @classmethod
    def get_metadata(cls, document: OCRDocument) -> Metadata:  # type: ignore[override]
        metadata = document.raw_metadata
        first_page_text = document.pages[0].text if document.pages else ""
        title = guess_title(first_page_text, metadata)
        authors = guess_authors(metadata)
        journal = guess_journal(metadata)
        date = guess_date(document.full_text, metadata)
        doi = guess_doi(document.full_text)

        return Metadata(
            doi=doi or None,
            title=title or None,
            journal=journal or None,
            date=date or None,
            author_list=authors,
        )


register_parser("wiley_pdf", WileyPDFParser, priority=80)

__all__ = ["ocr", "WileyPDFParser"]
