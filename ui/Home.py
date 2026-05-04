"""Lumeo Campaign Studio — landing page.

Full-page gradient hero with the product wordmark, tagline, and three clickable
workflow cards floating below in a layered grid layout. Multi-page UI is configured
via files in `ui/pages/` (Streamlit auto-discovers them).
"""
from __future__ import annotations

import streamlit as st

from ui.styles import (
    PRODUCT_NAME,
    inject_global_css,
    top_header,
)


# Streamlit auto-generates URL slugs from page filenames by stripping the leading
# numeric prefix and underscore. `pages/1_Plan_from_Brief.py` → `/Plan_from_Brief`.
# The anchors below let the entire workflow card act as a clickable surface;
# Streamlit's multipage router handles the in-app navigation.
_WORKFLOW_CARDS = [
    {
        "icon": "📋",
        "title": "Plan from Brief",
        "body": (
            "Paste a campaign brief, resolve gaps with the AI, review the generated "
            "plan, and approve. The headline workflow."
        ),
        "href": "/Plan_from_Brief",
    },
    {
        "icon": "🛡️",
        "title": "Brief QA",
        "body": (
            "Verify a campaign brief's quality before plan generation. The system "
            "extracts a structured brief, runs completeness rules, and surfaces "
            "ambiguity gaps."
        ),
        "href": "/Brief_QA",
    },
    {
        "icon": "🔍",
        "title": "Asset Consistency",
        "body": (
            "Drop in marketing assets. The system clusters terminology variants, "
            "flags CTA drift, and recommends canonicals from your brand dictionary."
        ),
        "href": "/Asset_Consistency",
    },
]


def main() -> None:
    st.set_page_config(
        page_title=f"{PRODUCT_NAME} · Campaign Studio",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_global_css()
    top_header()

    # ---- Hero ------------------------------------------------------------
    st.markdown(
        "<div class='lumeo-hero'>"
        "<span class='hero-eyebrow'>AI Campaign Workflow</span>"
        f"<h1>{PRODUCT_NAME} Campaign Studio</h1>"
        "<p>Turn rough campaign briefs into reviewable plans, audit existing plans against "
        "their briefs, and check marketing assets for terminology drift before they ship — "
        "from one clean workspace.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    # ---- Workflow cards (each entire card is a clickable link) ----------
    cards_html = "".join(
        f"<a class='workflow-card-link' href='{c['href']}' target='_self'>"
        "<div class='workflow-card'>"
        f"<div class='workflow-icon'>{c['icon']}</div>"
        f"<h3>{c['title']}</h3>"
        f"<p>{c['body']}</p>"
        "</div>"
        "</a>"
        for c in _WORKFLOW_CARDS
    )
    st.markdown(
        f"<div class='workflow-grid'>{cards_html}</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<p style='color:var(--text-secondary); margin-top:32px; text-align:center; "
        "font-size:0.95rem'>"
        "Click any card above to open that workflow. <strong>Get Started</strong> "
        "(in the sidebar) opens pre-filled sample workflows you can run end-to-end "
        "in five minutes."
        "</p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
