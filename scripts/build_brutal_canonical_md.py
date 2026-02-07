#!/usr/bin/env python3
"""
Build canonical markdown from out/brutal_pages marker_stream.json.
One .md per page. Output: Archive/marker-era/blind_eval/brutal_pages/.
Source: extraction output (marker_stream reading order). Use with archived pipeline.
"""
from pathlib import Path
import json

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_BRUTAL = REPO_ROOT / "out" / "brutal_pages"
BLIND_BRUTAL = REPO_ROOT / "Archive" / "marker-era" / "blind_eval" / "brutal_pages"


def block_to_md(entry: dict) -> str:
    raw = entry.get("raw_block_type", "")
    text = (entry.get("text") or "").strip()
    if not text:
        return ""
    if raw == "SectionHeader":
        return f"\n## {text}\n"
    if raw == "ListItem":
        return f"- {text}\n"
    return f"{text}\n\n"


def marker_stream_to_md(stream: list) -> str:
    parts = ["# Canonical representation\n"]
    for entry in stream:
        part = block_to_md(entry)
        if part:
            parts.append(part)
    return "".join(parts).strip() + "\n"


def main() -> None:
    BLIND_BRUTAL.mkdir(parents=True, exist_ok=True)
    stems = sorted({p.parent.name for p in OUT_BRUTAL.glob("*/marker_stream.json")})
    for stem in stems:
        path = OUT_BRUTAL / stem / "marker_stream.json"
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            stream = json.load(f)
        md = marker_stream_to_md(stream)
        out_path = BLIND_BRUTAL / f"{stem}.md"
        out_path.write_text(md, encoding="utf-8")
        print(f"Wrote {out_path.relative_to(REPO_ROOT)}")
    print(f"Done: {len(stems)} canonical markdown files in {BLIND_BRUTAL.relative_to(REPO_ROOT)}/")


if __name__ == "__main__":
    main()
