"""Integration tests for PDF visual source provenance preview and workbench layout."""
from pathlib import Path
import pytest
import fitz
import streamlit as st

import app
import core
from transpraxis import pdf_preview


@pytest.fixture
def mock_pdf_workspace(tmp_path: Path):
    old_output = core.OUTPUT_DIR
    core.OUTPUT_DIR = tmp_path

    job_id = "test-pdf-ui-workspace"
    doc = fitz.open()
    p1 = doc.new_page(width=400, height=600)
    p1.insert_text(fitz.Point(50, 100), "Title on Page One", fontsize=16)

    p2 = doc.new_page(width=400, height=600)
    p2.insert_text(fitz.Point(50, 100), "First segment text on Page Two", fontsize=12)
    p2.insert_text(fitz.Point(50, 150), "Second segment text on Page Two", fontsize=12)

    core.save_source(job_id, doc.tobytes())
    doc.close()

    state = core.new_job_state("book.pdf")
    state["paras"] = [
        "Title on Page One",
        "First segment text on Page Two",
        "Second segment text on Page Two",
    ]
    state["pairs"] = [
        {"source": "Title on Page One", "target": "第一页标题"},
        {"source": "First segment text on Page Two", "target": "第二页第一段"},
        {"source": "Second segment text on Page Two", "target": "第二页第二段"},
    ]
    core.save_job_state(job_id, state)

    try:
        yield job_id, state
    finally:
        core.OUTPUT_DIR = old_output


def test_pdf_preview_has_source(mock_pdf_workspace):
    job_id, _ = mock_pdf_workspace
    assert pdf_preview.has_pdf_source(job_id) is True
    assert pdf_preview.get_pdf_page_count(job_id) == 2


def test_pdf_preview_finds_page_and_renders(mock_pdf_workspace):
    job_id, state = mock_pdf_workspace

    # Query text on Page 2 (0-indexed: 1)
    page_idx, rects = pdf_preview.find_segment_page_and_rects(
        job_id, "First segment text on Page Two", start_page_hint=0
    )
    assert page_idx == 1
    assert len(rects) >= 1

    png_bytes = pdf_preview.render_pdf_page_image(job_id, page_idx, highlight_rects=rects)
    assert png_bytes is not None
    assert png_bytes.startswith(b"\x89PNG")


def test_pdf_preview_toggle_state(mock_pdf_workspace):
    job_id, _ = mock_pdf_workspace
    preview_key = f"pdf_preview_open_{job_id}"

    # Default should be set to True if not present
    st.session_state.pop(preview_key, None)
    if preview_key not in st.session_state:
        st.session_state[preview_key] = True
    assert st.session_state[preview_key] is True

    # User toggles off
    st.session_state[preview_key] = False
    assert st.session_state[preview_key] is False

    # User toggles on
    st.session_state[preview_key] = True
    assert st.session_state[preview_key] is True


def test_navigate_to_segment_syncs_pdf_page(mock_pdf_workspace):
    job_id, state = mock_pdf_workspace
    st.session_state[f"pdf_preview_open_{job_id}"] = True
    st.session_state[f"pdf_preview_page_{job_id}"] = 0

    # Navigate to segment index 1 (which is on Page 2, 0-indexed: 1)
    success = app._navigate_to_segment(job_id, state, 1, reveal=False)
    assert success is True

    # PDF preview highlight should be set to index 1
    assert st.session_state[f"pdf_preview_hl_seg_{job_id}"] == 1
    # PDF preview page should be synced to page index 1
    assert st.session_state[f"pdf_preview_page_{job_id}"] == 1
