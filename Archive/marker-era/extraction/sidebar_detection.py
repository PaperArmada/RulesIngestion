"""
Stage A sidebar detection (Option A bbox zones + Option B lexical cue).

Classify blocks in a narrow left or right zone as sidebar so they can be
dropped before chunking. Left: x1 <= threshold; right: x0 >= threshold.
Option B: when enabled, also require block text to match a sidebar pattern
(short, all-caps, or in allow-list) to reduce false positives.
See Stage-A-Sidebar-Pruning-Plan.md.
"""

from __future__ import annotations

from extraction.schemas import MarkerBlock

# Left sidebar: block's right edge x1 <= this fraction of page width (when using fraction).
DEFAULT_SIDEBAR_WIDTH_FRACTION = 0.18
# Fallback fixed pt when page width cannot be inferred.
DEFAULT_SIDEBAR_X_MAX_PT = 92.0
# Right sidebar: block's left edge x0 >= page_width * (1 - fraction). Fixed pt fallback when no page width.
DEFAULT_SIDEBAR_X_MIN_PT = 540.0  # letter ~612, main ends ~540
# Option B: max character length for "short" sidebar text (strip).
DEFAULT_MAX_SIDEBAR_TEXT_LEN = 50

# Option B: known TOC/sidebar labels (exact match after strip).
DEFAULT_SIDEBAR_ALLOW_LIST = (
    "INTRODUCTION",
    "ANCESTRIES & BACKGROUNDS",
    "CLASSES",
    "SKITTERMANDER",
    "5TH LEVEL",
    "9TH LEVEL",
    "13TH LEVEL",
    "14TH LEVEL",
    "ENVOY",
    "ENVOY MENTAL",
    "Mystic",
    "Android",
    "Barathu",
    "Human",
    "Kasatha",
    "Lashunta",
    "Pahtra",
    "Shirren",
    "Skittermander",
)


def _infer_page_widths(blocks: list[MarkerBlock]) -> dict[int, float]:
    """Infer page width per page as max x1 over blocks on that page. Empty/zero bbox skipped."""
    widths: dict[int, float] = {}
    for b in blocks:
        if not b.bbox or b.bbox == (0.0, 0.0, 0.0, 0.0):
            continue
        x1 = b.bbox[2]
        page = b.page_index
        widths[page] = max(widths.get(page, 0.0), x1)
    return widths


def _text_matches_sidebar_pattern(
    text: str | None,
    *,
    allow_list: tuple[str, ...] = DEFAULT_SIDEBAR_ALLOW_LIST,
    max_len: int = DEFAULT_MAX_SIDEBAR_TEXT_LEN,
) -> bool:
    """
    Return True if text looks like sidebar/TOC content (Option B).
    Match: exact strip in allow_list, or short (<= max_len) and all-caps or title-case.
    """
    t = (text or "").strip()
    if not t:
        return False
    if t in allow_list:
        return True
    if len(t) > max_len:
        return False
    # Short and all-caps (common for TOC/sidebar labels)
    if t.isupper():
        return True
    return False


def is_sidebar_block(
    block: MarkerBlock,
    *,
    page_width_pt: float | None = None,
    sidebar_x_max_pt: float | None = None,
    sidebar_x_min_pt: float | None = None,
    sidebar_width_fraction: float = DEFAULT_SIDEBAR_WIDTH_FRACTION,
    use_lexical: bool = False,
    sidebar_allow_list: tuple[str, ...] = DEFAULT_SIDEBAR_ALLOW_LIST,
    max_sidebar_text_len: int = DEFAULT_MAX_SIDEBAR_TEXT_LEN,
) -> bool:
    """
    Classify block as sidebar by bbox zones (left and/or right) and optionally lexical cue (Option B).

    - No usable bbox → False.
    - Left zone: x1 <= left_threshold (sidebar_x_max_pt, or page_width_pt * fraction, or default pt).
    - Right zone: x0 >= right_threshold (page_width_pt * (1 - fraction), or sidebar_x_min_pt when no page width).
    - If use_lexical: block must also match sidebar text pattern (allow_list, short all-caps/title-case).
    """
    if not block.bbox or block.bbox == (0.0, 0.0, 0.0, 0.0):
        return False
    x0, _y0, x1, _y1 = block.bbox
    if x1 <= x0:
        return False

    # Left zone threshold
    if sidebar_x_max_pt is not None:
        left_threshold = sidebar_x_max_pt
    elif page_width_pt is not None and page_width_pt > 0:
        left_threshold = page_width_pt * sidebar_width_fraction
    else:
        left_threshold = DEFAULT_SIDEBAR_X_MAX_PT
    in_left = x1 <= left_threshold

    # Right zone threshold
    if page_width_pt is not None and page_width_pt > 0:
        right_threshold = page_width_pt * (1.0 - sidebar_width_fraction)
    elif sidebar_x_min_pt is not None:
        right_threshold = sidebar_x_min_pt
    else:
        right_threshold = DEFAULT_SIDEBAR_X_MIN_PT
    in_right = x0 >= right_threshold

    in_zone = in_left or in_right
    if not in_zone:
        return False
    if use_lexical:
        return _text_matches_sidebar_pattern(
            block.text,
            allow_list=sidebar_allow_list,
            max_len=max_sidebar_text_len,
        )
    return True


def classify_sidebar_blocks(
    content_stream: list[MarkerBlock],
    *,
    sidebar_x_max_pt: float | None = None,
    sidebar_x_min_pt: float | None = None,
    sidebar_width_fraction: float | None = None,
    use_lexical: bool = False,
    sidebar_allow_list: tuple[str, ...] = DEFAULT_SIDEBAR_ALLOW_LIST,
    max_sidebar_text_len: int = DEFAULT_MAX_SIDEBAR_TEXT_LEN,
) -> tuple[list[MarkerBlock], list[MarkerBlock]]:
    """
    Split content stream into main-column blocks and sidebar blocks.

    Uses per-page inferred width for left and right zone thresholds when
    fixed-pt overrides are not set. Option B: set use_lexical=True to require
    sidebar text pattern (reduces false positives). Returns (content_no_sidebar, sidebar_blocks).
    """
    fraction = sidebar_width_fraction if sidebar_width_fraction is not None else DEFAULT_SIDEBAR_WIDTH_FRACTION
    page_widths = _infer_page_widths(content_stream)
    main: list[MarkerBlock] = []
    sidebar: list[MarkerBlock] = []
    for b in content_stream:
        page_width = page_widths.get(b.page_index)
        if is_sidebar_block(
            b,
            page_width_pt=page_width,
            sidebar_x_max_pt=sidebar_x_max_pt,
            sidebar_x_min_pt=sidebar_x_min_pt,
            sidebar_width_fraction=fraction,
            use_lexical=use_lexical,
            sidebar_allow_list=sidebar_allow_list,
            max_sidebar_text_len=max_sidebar_text_len,
        ):
            sidebar.append(b)
        else:
            main.append(b)
    return main, sidebar
