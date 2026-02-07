"""Tests for extraction.sidebar_detection: Option A bbox zones + Option B lexical."""

from extraction.schemas import MarkerBlock
from extraction.sidebar_detection import (
    DEFAULT_SIDEBAR_ALLOW_LIST,
    _text_matches_sidebar_pattern,
    classify_sidebar_blocks,
    is_sidebar_block,
)


def _block(
    page: int = 0,
    text: str = "text",
    bbox: tuple[float, float, float, float] = (50.0, 10.0, 200.0, 25.0),
    ordinal: int = 0,
) -> MarkerBlock:
    return MarkerBlock(
        doc_id="d1",
        page_index=page,
        text=text,
        bbox=bbox,
        raw_block_type="Text",
        block_ordinal=ordinal,
        section_hierarchy={},
    )


# --- is_sidebar_block ---


def test_is_sidebar_block_left_zone_with_fixed_pt() -> None:
    """Block with x1 <= sidebar_x_max_pt is sidebar."""
    # x1=80 <= 92 → sidebar
    b = _block(bbox=(10.0, 0.0, 80.0, 12.0))
    assert is_sidebar_block(b, sidebar_x_max_pt=92.0) is True
    # x1=100 > 92 → not sidebar
    b2 = _block(bbox=(10.0, 0.0, 100.0, 12.0))
    assert is_sidebar_block(b2, sidebar_x_max_pt=92.0) is False


def test_is_sidebar_block_with_page_width_fraction() -> None:
    """Threshold = page_width_pt * fraction (612 * 0.18 ≈ 110.16)."""
    # x1=100 < 110.16 → sidebar
    b = _block(bbox=(5.0, 0.0, 100.0, 12.0))
    assert is_sidebar_block(b, page_width_pt=612.0) is True
    # x1=150 > 110.16 → not sidebar
    b2 = _block(bbox=(10.0, 0.0, 150.0, 12.0))
    assert is_sidebar_block(b2, page_width_pt=612.0) is False


def test_is_sidebar_block_no_bbox_returns_false() -> None:
    """Block with zero/empty bbox is not classified as sidebar."""
    b = _block(bbox=(0.0, 0.0, 0.0, 0.0))
    assert is_sidebar_block(b, sidebar_x_max_pt=92.0) is False


def test_is_sidebar_block_main_column_not_sidebar() -> None:
    """Typical main-column bbox (e.g. x0=72, x1=540 on letter) is not sidebar."""
    # Letter width 612pt; main column often ~72–540. Left zone x1<=110, right zone x0>=502.
    b = _block(bbox=(72.0, 100.0, 540.0, 115.0))
    assert is_sidebar_block(b, sidebar_x_max_pt=92.0) is False
    assert is_sidebar_block(b, page_width_pt=612.0) is False


def test_is_sidebar_block_right_zone() -> None:
    """Right sidebar: x0 >= page_width * (1 - fraction)."""
    # 612 * 0.82 = 501.84. Block in right column x0=540, x1=600.
    b = _block(bbox=(540.0, 50.0, 600.0, 65.0), text="INTRODUCTION")
    assert is_sidebar_block(b, page_width_pt=612.0) is True
    # Main column x0=72 not in right zone
    b2 = _block(bbox=(72.0, 100.0, 500.0, 115.0))
    assert is_sidebar_block(b2, page_width_pt=612.0) is False


def test_is_sidebar_block_right_zone_fixed_pt() -> None:
    """Right sidebar with sidebar_x_min_pt (no page width)."""
    b = _block(bbox=(550.0, 0.0, 600.0, 12.0))
    assert is_sidebar_block(b, sidebar_x_min_pt=540.0) is True
    b2 = _block(bbox=(400.0, 0.0, 530.0, 12.0))
    assert is_sidebar_block(b2, sidebar_x_min_pt=540.0) is False


def test_is_sidebar_block_option_b_lexical_required_when_on() -> None:
    """With use_lexical=True, block in zone must match text pattern."""
    # In right zone but body text → not sidebar when Option B on
    b = _block(bbox=(550.0, 0.0, 600.0, 12.0), text="You never let the inability to communicate stop you.")
    assert is_sidebar_block(b, page_width_pt=612.0, use_lexical=True) is False
    # In right zone and allow-list match → sidebar
    b2 = _block(bbox=(550.0, 0.0, 600.0, 12.0), text="INTRODUCTION")
    assert is_sidebar_block(b2, page_width_pt=612.0, use_lexical=True) is True
    # Short all-caps in zone → sidebar
    b3 = _block(bbox=(10.0, 0.0, 80.0, 12.0), text="13TH LEVEL")
    assert is_sidebar_block(b3, sidebar_x_max_pt=92.0, use_lexical=True) is True


def test_text_matches_sidebar_pattern_allow_list() -> None:
    """Exact strip match in allow-list."""
    assert _text_matches_sidebar_pattern("INTRODUCTION") is True
    assert _text_matches_sidebar_pattern("  ANCESTRIES & BACKGROUNDS  ") is True
    assert _text_matches_sidebar_pattern("Unknown Label") is False


def test_text_matches_sidebar_pattern_short_all_caps() -> None:
    """Short all-caps matches."""
    assert _text_matches_sidebar_pattern("SKITTERMANDER") is True
    assert _text_matches_sidebar_pattern("A long sentence that is not short.") is False


def test_text_matches_sidebar_pattern_title_case() -> None:
    """Only allow-list and short all-caps match; generic title-case does not."""
    assert _text_matches_sidebar_pattern("Introduction") is False  # not in allow_list, not all-caps
    assert _text_matches_sidebar_pattern("INTRODUCTION") is True   # in allow_list
    assert _text_matches_sidebar_pattern("Unknown Label") is False


# --- classify_sidebar_blocks ---


def test_classify_sidebar_blocks_splits_by_inferred_width() -> None:
    """Inferred page width from max x1; left 18% is sidebar."""
    # Page width inferred as 600 from second block. Threshold 600*0.18=108.
    left_narrow = _block(ordinal=0, bbox=(10.0, 0.0, 90.0, 12.0))   # x1=90 → sidebar
    main_col = _block(ordinal=1, bbox=(120.0, 0.0, 600.0, 12.0))   # x1=600 → main
    stream = [left_narrow, main_col]
    main, sidebar = classify_sidebar_blocks(stream)
    assert len(sidebar) == 1
    assert sidebar[0].block_ordinal == 0
    assert len(main) == 1
    assert main[0].block_ordinal == 1


def test_classify_sidebar_blocks_deterministic_order() -> None:
    """Main and sidebar lists preserve original order within each group."""
    a = _block(ordinal=0, bbox=(10, 0, 50, 10))
    b = _block(ordinal=1, bbox=(200, 0, 400, 10))
    c = _block(ordinal=2, bbox=(15, 20, 60, 32))
    stream = [a, b, c]
    main, sidebar = classify_sidebar_blocks(stream)
    assert [x.block_ordinal for x in sidebar] == [0, 2]
    assert [x.block_ordinal for x in main] == [1]


def test_classify_sidebar_blocks_fixed_threshold() -> None:
    """When sidebar_x_max_pt is set, it overrides inferred width."""
    left = _block(bbox=(5.0, 0.0, 85.0, 10.0))
    stream = [left]
    main, sidebar = classify_sidebar_blocks(stream, sidebar_x_max_pt=90.0)
    assert len(sidebar) == 1
    assert len(main) == 0
