"""Helpers to turn enriched JSON into LLM-friendly semi-structured text."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Sequence


def normalize_keywords(raw: Any) -> List[str]:
    if isinstance(raw, str):
        return [kw.strip() for kw in raw.split(",") if kw.strip()]
    if isinstance(raw, Iterable):
        return [str(kw).strip() for kw in raw if str(kw).strip()]
    return []


def _compress_text(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def select_relevant_blocks(
    blocks: Sequence[Mapping[str, Any]],
    *,
    limit: int,
    key_terms: Sequence[str],
) -> List[Dict[str, Any]]:
    if not blocks:
        return []

    key_terms_lower = {term.lower() for term in key_terms}
    scored: List[tuple[int, int, Dict[str, Any]]] = []
    fallback: List[tuple[int, Dict[str, Any]]] = []

    for idx, block in enumerate(blocks):
        text = str(block.get("content", ""))
        lowered = text.lower()
        metadata = block.get("metadata") or {}
        score = 0
        keywords = [kw.lower() for kw in normalize_keywords(block.get("keywords"))]
        if keywords:
            score += 2
        if any(kw in key_terms_lower for kw in keywords):
            score += 4
        score += sum(1 for kw in key_terms_lower if kw in lowered)
        if block.get("type") == "table":
            score += 2
        if block.get("type") == "figure":
            score += 1
        if isinstance(metadata, Mapping):
            role = str(metadata.get("role") or "").lower()
            heading_level = metadata.get("heading_level")
            if role in {"heading", "title", "section_title"}:
                score += 1
            if isinstance(heading_level, int) and heading_level <= 3:
                score += 1
        if any(ch.isdigit() for ch in text):
            score += 1
        if any(unit in text for unit in ("%", "±", "°", "K", "bar", "Pa", "MPa", "mA", "V")):
            score += 1
        if score:
            scored.append((score, idx, dict(block)))
        else:
            fallback.append((idx, dict(block)))

    ranked = [entry for _, _, entry in sorted(scored, key=lambda item: (-item[0], item[1]))]
    if len(ranked) < limit:
        needed = limit - len(ranked)
        ranked.extend(entry for _, entry in sorted(fallback, key=lambda item: item[0])[:needed])

    return ranked[:limit]


def render_semistructured_metadata(metadata: Mapping[str, Any]) -> str:
    authors = metadata.get("author_list") or []
    if isinstance(authors, list):
        author_text = "; ".join(authors)
    else:
        author_text = str(authors)

    parts = [
        f"标题: {metadata.get('title', '未知标题')}",
        f"DOI: {metadata.get('doi', '未知 DOI')}",
        f"期刊: {metadata.get('journal', '未知期刊')}",
        f"发表时间: {metadata.get('date', '未知日期')}",
        f"作者: {author_text or '未提供'}",
    ]
    abstract = metadata.get("abstract")
    if abstract:
        parts.append("摘要概览: " + _compress_text(str(abstract), 380))
    return "\n".join(parts)


def render_semistructured_blocks(
    blocks: Sequence[Mapping[str, Any]],
    *,
    snippet_length: int = 380,
    max_chars: int | None = None,
) -> str:
    if not blocks:
        return "(无候选片段)"

    rendered: List[str] = []
    total_chars = 0
    if isinstance(max_chars, int) and max_chars <= 0:
        max_chars = None
    for block in blocks:
        idx = block.get("idx", "?")
        type_ = block.get("type", "text")
        keywords = normalize_keywords(block.get("keywords"))
        label = f"块 {idx} | 类型: {type_}"
        keyword_line = f"关键词: {', '.join(keywords) if keywords else '无'}"
        content = str(block.get("content", "") or "")
        snippet = _compress_text(content, snippet_length)
        block_text = "\n".join([label, keyword_line, "内容: " + snippet])
        if max_chars is not None:
            separator = 2 if rendered else 0
            projected = total_chars + separator + len(block_text)
            if projected > max_chars:
                remaining = max_chars - total_chars - separator
                if remaining <= 0:
                    break
                truncated = block_text[:remaining].rstrip()
                if truncated != block_text:
                    truncated = truncated.rstrip() + "…"
                rendered.append(truncated)
                total_chars = max_chars
                break
            total_chars = projected
        rendered.append(block_text)

    return "\n\n".join(rendered)
