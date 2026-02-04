from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Sequence, Tuple


logger = logging.getLogger(__name__)


def parse_summary_lengths(value: str) -> List[Tuple[str, int]]:
    results: List[Tuple[str, int]] = []
    for item in (value or "").split(","):
        entry = item.strip()
        if not entry:
            continue
        if "=" in entry:
            key, raw = entry.split("=", 1)
            key = key.strip()
            raw = raw.strip()
        else:
            key = f"len{entry}"
            raw = entry
        try:
            max_chars = int(raw)
        except ValueError:
            continue
        if max_chars > 0:
            results.append((key, max_chars))
    return results


def split_text_for_llm(text: str, max_chars: int) -> List[str]:
    if len(text) <= max_chars:
        return [text]
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            for start in range(0, len(paragraph), max_chars):
                chunks.append(paragraph[start : start + max_chars])
            continue
        if current_len + len(paragraph) + 2 > max_chars and current:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
        current.append(paragraph)
        current_len += len(paragraph) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def call_llm_text(prompt: str, model: str, api_key: str, temperature: float) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - runtime dependency guard
        raise RuntimeError("openai package is required for LLM summaries.") from exc

    logger.info(
        "🤖 [LLM] Calling model=%s temp=%.2f prompt_chars=%d",
        model,
        temperature,
        len(prompt),
    )
    start_time = time.time()
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Return plain text only."},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
    )
    content = (response.choices[0].message.content or "").strip()
    elapsed = time.time() - start_time
    logger.info("✅ [LLM] Response received in %.2fs", elapsed)
    return content


def summarize_chapter_with_llm(
    *,
    title: Optional[str],
    text: str,
    model: str,
    api_key: str,
    temperature: float,
    max_input_chars: int,
    segment_max_chars: int,
    summary_lengths: Sequence[Tuple[str, int]],
) -> Dict[str, str]:
    logger.info("📚 [LLM] Summarizing chapter title=%s len=%d", title or "unknown", len(text))
    segments = split_text_for_llm(text, segment_max_chars)
    notes: List[str] = []
    for idx, segment in enumerate(segments, start=1):
        notes.append(f"Segment {idx}:\n{segment}")
    notes_text = "\n\n".join(notes)
    summaries: Dict[str, str] = {}
    for key, max_chars in summary_lengths:
        prompt = f"""Summarize the following chapter text for retrieval routing.\n\nThe summary should help a search system choose the right chapter for a query.\n\nOutput guidelines:\n- Keep it concise, under {max_chars} characters.\n- List key concepts and unique terms that appear.\n- Include any tables of contents or section names.\n\nAt the end, include a final line:\nKey terms: <comma-separated list of exact terms used>\n\nTitle: {title or 'Unknown'}\n\nSegment Notes:\n{notes_text}"""
        if len(prompt) > max_input_chars:
            prompt = prompt[:max_input_chars].rsplit(" ", 1)[0]
        summary = call_llm_text(prompt, model, api_key, temperature)
        if len(summary) > max_chars:
            summary = summary[:max_chars].rsplit(" ", 1)[0]
        summaries[key] = summary.strip()
    logger.info(
        "✅ [LLM] Chapter summary complete title=%s variants=%s",
        title or "unknown",
        ",".join(summaries.keys()),
    )
    return summaries


def summarize_chapters(
    *,
    chapter_texts: Dict[str, str],
    chapter_titles: Dict[str, Optional[str]],
    model: str,
    api_key: str,
    temperature: float,
    max_input_chars: int,
    segment_max_chars: int,
    summary_lengths: Sequence[Tuple[str, int]],
    max_workers: int = 6,
) -> Dict[str, Dict[str, str]]:
    summaries: Dict[str, Dict[str, str]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for chapter_id, text in chapter_texts.items():
            futures[
                executor.submit(
                    summarize_chapter_with_llm,
                    title=chapter_titles.get(chapter_id),
                    text=text,
                    model=model,
                    api_key=api_key,
                    temperature=temperature,
                    max_input_chars=max_input_chars,
                    segment_max_chars=segment_max_chars,
                    summary_lengths=summary_lengths,
                )
            ] = chapter_id
        for future in as_completed(futures):
            chapter_id = futures[future]
            summaries[chapter_id] = future.result()
    return summaries
