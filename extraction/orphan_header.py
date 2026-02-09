"""
Orphan page detection and header assignment.

Deterministic checks:
  - is_orphan_ast(ast_dict) — AST has no heading nodes.
  - is_image_and_caption_only_ast(ast_dict) — Just image + caption; no header needed.

LLM-based assignment (requires OPENAI_API_KEY):
  - run_orphan_header_pass(eval_dir, ...) — Discover orphans, skip image+caption,
    call gpt-5-nano for rest (async, concurrent); returns per-page results.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

# Canonical prompt location (source-controlled); any eval_dir can override with local ORPHAN_HEADER_PROMPT.md
_ORPHAN_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "ORPHAN_HEADER_PROMPT.md"


def ast_has_heading(obj: object) -> bool:
    """Return True if AST (or subtree) contains any node with node_type 'heading'."""
    if isinstance(obj, dict):
        if obj.get("node_type") == "heading":
            return True
        for v in obj.values():
            if ast_has_heading(v):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if ast_has_heading(item):
                return True
    return False


def is_orphan_ast(ast_dict: dict[str, Any]) -> bool:
    """Return True if the page AST has no heading nodes."""
    return not ast_has_heading(ast_dict)


def is_image_and_caption_only_ast(ast_dict: dict[str, Any]) -> bool:
    """Return True if the orphan page is just an image and a caption — no header needed."""
    root = ast_dict.get("root") or {}
    children = root.get("children") or []
    if len(children) > 2:
        return False
    types = {c.get("node_type") for c in children if isinstance(c, dict)}
    if not (types <= {"paragraph", "image_ref"}):
        return False
    return "image_ref" in types


def parse_page_number(dir_name: str) -> int | None:
    """Extract page number from dir name like DnD5eBrutalChapters_p15."""
    m = re.search(r"_p(\d+)$", dir_name)
    return int(m.group(1)) if m else None


def discover_orphans(eval_dir: Path) -> list[tuple[int, Path]]:
    """Discover orphan page dirs (no headings) in eval dir. Returns [(page_num, page_dir), ...] sorted."""
    page_dirs: list[tuple[int, Path]] = []
    for d in eval_dir.iterdir():
        if not d.is_dir():
            continue
        n = parse_page_number(d.name)
        if n is not None and (d / "stageA.surface.ast.json").exists():
            page_dirs.append((n, d))
    page_dirs.sort(key=lambda x: x[0])

    orphans: list[tuple[int, Path]] = []
    for n, page_dir in page_dirs:
        ast_path = page_dir / "stageA.surface.ast.json"
        data = json.loads(ast_path.read_text(encoding="utf-8"))
        if is_orphan_ast(data):
            orphans.append((n, page_dir))
    return orphans


def load_prompt_template(prompt_path: Path) -> str:
    """Load template from ORPHAN_HEADER_PROMPT.md with {{PRIOR_PAGE_SURFACE}} and {{ORPHAN_PAGE_SURFACE}}."""
    text = prompt_path.read_text(encoding="utf-8")
    start = text.find("You are given two inputs for one document page")
    if start == -1:
        raise ValueError("Template section not found in prompt file")
    end_marker = "\n---\n"
    end = text.find(end_marker, start)
    if end == -1:
        end = len(text)
    block = text[start:end]
    lines = block.split("\n")
    out = []
    for line in lines:
        if line.startswith("    "):
            out.append(line[4:])
        else:
            out.append(line)
    return "\n".join(out)


def _parse_llm_response(content: str) -> tuple[str, str]:
    """Parse heading and reason from LLM response."""
    heading = ""
    reason = ""
    for line in content.split("\n"):
        if line.strip().lower().startswith("heading:"):
            heading = line.split(":", 1)[1].strip().strip('"')
        elif line.strip().lower().startswith("reason:"):
            reason = line.split(":", 1)[1].strip().strip('"')
    return heading, reason


async def _call_orphan_llm(
    client: Any,
    model: str,
    prompt: str,
    label: str,
) -> dict[str, Any]:
    """Single async LLM call for orphan header assignment."""
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    content = resp.choices[0].message.content or ""
    heading, reason = _parse_llm_response(content)
    return {
        "label": label,
        "status": "assigned",
        "heading": heading,
        "reason": reason,
        "raw_response": content,
    }


def run_orphan_header_pass(
    eval_dir: Path,
    *,
    prompt_path: Path | None = None,
    openai_client: Any | None = None,
    model: str = "gpt-5-nano",
) -> list[dict[str, Any]]:
    """Run orphan header assignment on eval dir.

    Uses async OpenAI client to call the LLM concurrently for all orphans that
    need assignment. Returns list of dicts:
      - label: page label (e.g. DnD5eBrutalChapters_p15)
      - status: "skipped_no_prior" | "skipped_image_caption" | "skipped_missing_md" | "assigned"
      - heading: assigned heading (if status == "assigned")
      - reason: LLM reason (if status == "assigned")
    """
    return asyncio.run(
        _run_orphan_header_pass_async(
            eval_dir=eval_dir,
            prompt_path=prompt_path,
            openai_client=openai_client,
            model=model,
        )
    )


async def _run_orphan_header_pass_async(
    eval_dir: Path,
    *,
    prompt_path: Path | None = None,
    openai_client: Any | None = None,
    model: str = "gpt-5-nano",
) -> list[dict[str, Any]]:
    """Async implementation of orphan header pass."""
    from openai import AsyncOpenAI

    eval_dir = Path(eval_dir)
    if prompt_path is None:
        prompt_path = eval_dir / "ORPHAN_HEADER_PROMPT.md"
    if not prompt_path.exists():
        if _ORPHAN_PROMPT_PATH.exists():
            prompt_path = _ORPHAN_PROMPT_PATH
        else:
            raise FileNotFoundError(
                f"ORPHAN_HEADER_PROMPT.md not found: {prompt_path} or {_ORPHAN_PROMPT_PATH}"
            )

    template = load_prompt_template(prompt_path)
    orphans = discover_orphans(eval_dir)
    page_dirs: list[tuple[int, Path]] = []
    for d in eval_dir.iterdir():
        if not d.is_dir():
            continue
        n = parse_page_number(d.name)
        if n is not None and (d / "stageA.surface.ast.json").exists():
            page_dirs.append((n, d))
    page_dirs.sort(key=lambda x: x[0])

    # Build items in orphan order: either {"skipped": result} or {"llm": prompt}
    items: list[tuple[str, dict[str, Any]]] = []
    for page_num, page_dir in orphans:
        label = page_dir.name
        prior_num = page_num - 1
        prior_dir = next((pd for pn, pd in page_dirs if pn == prior_num), None)

        if prior_dir is None:
            items.append((label, {"skipped": {"label": label, "status": "skipped_no_prior"}}))
            continue

        ast_path = page_dir / "stageA.surface.ast.json"
        ast_data = json.loads(ast_path.read_text(encoding="utf-8"))
        if is_image_and_caption_only_ast(ast_data):
            items.append((label, {"skipped": {"label": label, "status": "skipped_image_caption"}}))
            continue

        prior_md_path = prior_dir / "stageA.surface.md"
        orphan_md_path = page_dir / "stageA.surface.md"
        if not prior_md_path.exists() or not orphan_md_path.exists():
            items.append((label, {"skipped": {"label": label, "status": "skipped_missing_md"}}))
            continue

        prior_surface = prior_md_path.read_text(encoding="utf-8")
        orphan_surface = orphan_md_path.read_text(encoding="utf-8")
        prompt = template.replace("{{PRIOR_PAGE_SURFACE}}", prior_surface).replace(
            "{{ORPHAN_PAGE_SURFACE}}", orphan_surface
        )
        items.append((label, {"llm": prompt}))

    client = openai_client or AsyncOpenAI()
    llm_items = [(label, d["llm"]) for label, d in items if "llm" in d]
    if not llm_items:
        return [d["skipped"] for _, d in items]

    # Run all LLM calls concurrently
    coros = [_call_orphan_llm(client, model, prompt, label) for label, prompt in llm_items]
    llm_results = list(await asyncio.gather(*coros))
    llm_iter = iter(llm_results)

    # Build final results in orphan order
    results: list[dict[str, Any]] = []
    for _, d in items:
        if "skipped" in d:
            results.append(d["skipped"])
        else:
            results.append(next(llm_iter))
    return results
