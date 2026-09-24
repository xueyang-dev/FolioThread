"""Unified Translation Interaction Workspace Fragment.

Ensures that the CAT Grid table and the Agent Inspector share ONE single
@st.fragment boundary. When a user selects a segment, navigates viewports,
or saves an inline edit, this fragment re-renders atomically in a single cycle.
Both columns consume the updated state synchronously with ZERO state drift,
while PDF Preview and Runtime Polling remain completely isolated outside.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple
import streamlit as st

from transpraxis import profiler
from transpraxis.ui.workspace import cat_grid
from transpraxis.ui.workspace import inspector


@st.fragment
def render_translation_workspace_fragment(
    job_id: str,
    state: Dict[str, Any],
    overview: Optional[Dict[str, Any]] = None,
    ratios: Tuple[float, float] = (4.25, 1.55),
    *,
    render_main_fn: Optional[Callable[..., Any]] = None,
    render_inspector_fn: Optional[Callable[..., Any]] = None,
) -> None:
    """Render the CAT translation grid and Inspector in a single atomic fragment."""
    with profiler.span("translation_workspace_fragment", job_id=job_id):
        main_col, inspector_col = st.columns(ratios, gap="medium")
        with main_col:
            with st.container(key="workspace_main_col"):
                if render_main_fn:
                    render_main_fn(job_id, state, overview)
                else:
                    st.info("Translation workspace main area")
        with inspector_col:
            with st.container(key="workspace_context_col"):
                with st.container(key="translation_inspector"):
                    if render_inspector_fn:
                        render_inspector_fn(job_id, state, overview)
                    else:
                        inspector.render_workspace_translation_context(job_id, state, overview)
