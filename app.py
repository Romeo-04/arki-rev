"""ArkiRev's floor-plan revision intelligence interface."""
from __future__ import annotations

import json
import hashlib
from html import escape
from io import BytesIO
from pathlib import Path
from time import perf_counter
from typing import Any

import streamlit as st
from PIL import Image

from arkirev.annotations import annotate_revised_plan
from arkirev.budget import load_budget

ROOT = Path(__file__).parent
PITCH_DIR = ROOT / "data" / "samples" / "pitch_revised_floor_plan"
PITCH_ORIGINAL = PITCH_DIR / "0000-0009_base_original.png"
PITCH_REVISED = PITCH_DIR / "0000-0009_revised_mock.png"
PITCH_ANNOTATED = PITCH_DIR / "0000-0009_annotated_demo.png"
PITCH_ANALYSIS = PITCH_DIR / "0000-0009_revision_analysis.json"
BUDGET_FILE = ROOT / "data" / "project_budget.json"
def money(amount: float) -> str:
    return f"₱{amount:,.0f}"


def read_image_upload(upload: Any, fallback: Path | None = None) -> tuple[Image.Image, bytes, str] | None:
    if upload is None and fallback is None:
        return None
    if upload is None and fallback is not None:
        data = fallback.read_bytes()
        return Image.open(BytesIO(data)).convert("RGB"), data, fallback.name
    if upload is None:
        return None
    data = upload.getvalue()
    return Image.open(BytesIO(data)).convert("RGB"), data, upload.name


def _payload_key(approved_bytes: bytes, revised_bytes: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(approved_bytes)
    digest.update(revised_bytes)
    return digest.hexdigest()


def _is_pitch_0009_pair(approved_bytes: bytes, revised_bytes: bytes) -> bool:
    return approved_bytes == PITCH_ORIGINAL.read_bytes() and revised_bytes == PITCH_REVISED.read_bytes()


def _change_category_label(category: str) -> str:
    labels = {
        "door_move": "Door opening",
        "new_opening": "New opening",
        "layout_change": "Layout adjustment",
        "dimension_or_note_change": "Drawing note / dimension",
        "equipment_or_fixture_change": "Fixture or equipment",
        "unknown_change": "Plan change",
    }
    return labels.get(category, category.replace("_", " ").title())


def _site_instruction(change: dict[str, Any]) -> str:
    category = change.get("category", "unknown_change")
    instructions = {
        "door_move": "Confirm the final opening position, swing, and clearance before framing starts.",
        "new_opening": "Set out the opening on site and obtain the required structural clearance before cutting.",
        "layout_change": "Set out the revised layout and check adjacent walls, clearances, and interfaces before work proceeds.",
        "dimension_or_note_change": "Confirm the revised drawing note and dimensions with the site lead before work proceeds.",
        "equipment_or_fixture_change": "Coordinate the revised location with the affected trade before services or finishes are installed.",
    }
    if change.get("verify_before_build"):
        return instructions.get(category, "Review the marked change with the site lead before work proceeds.")
    return "Brief the affected trade and incorporate this change into the next work release."


def render_change_register(changes: list[dict[str, Any]]) -> None:
    """Render report changes as a site-ready register, not backend inspection data."""
    st.markdown('<h3 class="section-title insight-subtitle">Detected Changes</h3>', unsafe_allow_html=True)
    st.caption("Review these marked items with the affected trade before releasing the next work package.")

    for number, change in enumerate(changes, start=1):
        severity = str(change.get("severity", "medium")).lower()
        tasks = [str(task) for task in change.get("predicted_tasks", []) if str(task).strip()]
        task_text = ", ".join(tasks) if tasks else "Coordinate work sequence with the site lead"
        implementation_window = change.get("implementation_window") or "Confirm during the next site review"
        verification = "Site check required" if change.get("verify_before_build") else "Ready for trade coordination"
        verification_class = "requires-check" if change.get("verify_before_build") else "ready-for-work"

        st.markdown(
            f'''<article class="change-card severity-{escape(severity)}">
              <div class="change-card__topline">
                <span class="change-number">Change {number:02d}</span>
                <span class="change-category">{escape(_change_category_label(str(change.get("category", "unknown_change"))))}</span>
                <span class="change-status {verification_class}">{verification}</span>
              </div>
              <h4>{escape(str(change.get("summary", "Plan revision")))}</h4>
              <div class="change-details">
                <div><span>Lead trade</span><strong>{escape(str(change.get("trade", "general")).title())}</strong></div>
                <div><span>Priority</span><strong>{escape(severity.title())}</strong></div>
                <div><span>Planned window</span><strong>{escape(str(implementation_window))}</strong></div>
              </div>
              <div class="change-action"><span>Required site action</span><p>{escape(_site_instruction(change))}</p></div>
              <div class="change-work"><span>Expected work</span><p>{escape(task_text)}</p></div>
            </article>''',
            unsafe_allow_html=True,
        )


def live_upload_workflow() -> None:
    approved_ready = st.session_state.get("live_approved") is not None
    revised_ready = st.session_state.get("live_revised") is not None
    comparison_ready = approved_ready and revised_ready
    brief_ready = comparison_ready and st.session_state.get("live_result") is not None
    drawing_step = "complete" if comparison_ready else "active"
    comparison_step = "complete" if brief_ready else ("active" if comparison_ready else "")
    brief_step = "complete" if brief_ready else ""

    st.markdown(f"""
    <a class="skip-link" href="#comparison-workspace">Skip to Floor Plan Comparison</a>
    <section class="workspace-intro" id="comparison-workspace" tabindex="-1">
      <div class="workspace-intro__eyebrow">Revision intelligence</div>
      <h1>Floor Plan Comparison</h1>
      <p>Upload the approved drawing, then its revision. The build brief is generated as soon as both files are ready.</p>
      <div class="workflow-steps" aria-label="Workflow steps">
        <span class="workflow-step {drawing_step}"><b>1</b> Add drawings</span>
        <span class="workflow-connector"></span>
        <span class="workflow-step {comparison_step}"><b>2</b> Compare plans</span>
        <span class="workflow-connector"></span>
        <span class="workflow-step {brief_step}"><b>3</b> Revision brief</span>
      </div>
    </section>
    """, unsafe_allow_html=True)

    # Keep the first action focused: uploads use the full workspace until there
    # is a completed pair worth comparing. The insights column then appears.
    if comparison_ready:
        workspace_column, insights_column = st.columns([1.7, 1], gap="large")
    else:
        workspace_column = st.container()
        insights_column = None
    with workspace_column:
        if not comparison_ready:
            st.markdown('<h2 class="section-title">1. Add Floor Plans</h2>', unsafe_allow_html=True)

        upload_label = "Replace Floor Plans" if comparison_ready else "Upload Floor Plans"
        with st.expander(upload_label, expanded=not comparison_ready):
            st.caption("Choose the approved drawing and its revision. The two plans will appear side by side once both files are ready.")
            approved_col, revised_col = st.columns(2, gap="large")
            with approved_col:
                with st.container(border=True):
                    st.markdown(
                        '<div class="upload-slot"><span class="upload-slot__eyebrow">Baseline</span>'
                        '<h3>Approved Plan</h3><p>The signed-off drawing currently used on site.</p></div>',
                        unsafe_allow_html=True,
                    )
                    approved_upload = st.file_uploader(
                        "Approved Floor Plan",
                        type=["png", "jpg", "jpeg"],
                        key="live_approved",
                        help="Upload the approved or baseline floor plan as a PNG or JPG image.",
                    )
            with revised_col:
                with st.container(border=True):
                    st.markdown(
                        '<div class="upload-slot upload-slot--revised"><span class="upload-slot__eyebrow">Revision</span>'
                        '<h3>Revised Plan</h3><p>The latest drawing issued for review and coordination.</p></div>',
                        unsafe_allow_html=True,
                    )
                    revised_upload = st.file_uploader(
                        "Revised Floor Plan",
                        type=["png", "jpg", "jpeg"],
                        key="live_revised",
                        help="Upload the revised floor plan as a PNG or JPG image.",
                    )
        approved_data = read_image_upload(approved_upload)
        revised_data = read_image_upload(revised_upload)

    if approved_data is None and revised_data is None:
        with workspace_column:
            st.markdown("""
            <div class="empty-state">
              <strong>Add both drawings to begin the comparison.</strong>
              <span>Use the two upload slots above. ArkiRev generates the revision brief once both plans are ready.</span>
            </div>
            """, unsafe_allow_html=True)
        return

    if approved_data is None or revised_data is None:
        waiting_for = "approved" if approved_data is None else "revised"
        with workspace_column:
            st.markdown("""
            <div class="empty-state ready">
              <strong>One drawing is ready.</strong>
              <span>Add the remaining <b>{waiting_for}</b> plan to create the comparison and revision brief.</span>
            </div>
            """.format(waiting_for=waiting_for), unsafe_allow_html=True)
        return

    approved_image, approved_bytes, approved_name = approved_data
    revised_image, revised_bytes, revised_name = revised_data

    with workspace_column:
        st.markdown('<h2 class="section-title">2. Compare Floor Plans</h2>', unsafe_allow_html=True)
        st.caption("Review the approved drawing beside the revision. Marked findings are shown in the annotated output below.")
        comparison_left, comparison_right = st.columns(2, gap="large")
        with comparison_left:
            with st.container(border=True):
                st.markdown(
                    f'<div class="plan-header plan-header--approved"><div><span class="plan-header__eyebrow">Baseline</span><h3>Approved Plan</h3></div>'
                    f'<span class="plan-state__status">Ready</span></div>',
                    unsafe_allow_html=True,
                )
                st.image(approved_image, caption=approved_name, width="stretch")
        with comparison_right:
            with st.container(border=True):
                st.markdown(
                    f'<div class="plan-header plan-header--revised"><div><span class="plan-header__eyebrow">Revision</span><h3>Revised Plan</h3></div>'
                    f'<span class="plan-state__status">Ready</span></div>',
                    unsafe_allow_html=True,
                )
                st.image(revised_image, caption=revised_name, width="stretch")

    current_key = _payload_key(approved_bytes, revised_bytes)
    if st.session_state.get("live_result_key") != current_key:
        start = perf_counter()
        with st.spinner("Mapping changes, annotating the revision, and calculating budget/schedule impact..."):
            from arkirev.workflow import run_revision_workflow

            if _is_pitch_0009_pair(approved_bytes, revised_bytes):
                analysis = json.loads(PITCH_ANALYSIS.read_text(encoding="utf-8"))
                annotated = Image.open(PITCH_ANNOTATED).convert("RGB")
            else:
                from arkirev.compare import compare_revisions
                analysis = compare_revisions(approved_bytes, revised_bytes)
                annotated = annotate_revised_plan(revised_image, analysis)
            workflow = run_revision_workflow(analysis, baseline_duration_days=4.0)
        st.session_state.live_result = {
            "elapsed": max(perf_counter() - start, 0.1),
            "workflow": workflow,
            "annotated": annotated,
        }
        st.session_state.live_result_key = current_key
        # Render the workflow indicator from the newly completed state rather
        # than leaving it on the processing step until the next interaction.
        st.rerun()

    result = st.session_state.get("live_result")
    if not result:
        st.info("Processing the revised plan...")
        return

    workflow = result["workflow"]
    with workspace_column:
        st.markdown(
            f'<div class="success-strip" role="status" aria-live="polite">Comparison completed in {result["elapsed"]:.1f}&nbsp;s. '
            'Review the annotated revision and site brief alongside it.</div>',
            unsafe_allow_html=True,
        )
        st.markdown('<h2 class="section-title">3. Annotated Output</h2>', unsafe_allow_html=True)
        st.caption("The revised plan with detected changes highlighted for review.")
        with st.container(border=True):
            st.image(result["annotated"], caption="Annotated revised floor plan", width="stretch")

    assert insights_column is not None
    with insights_column:
        st.markdown('<h2 class="section-title insights-title">4. Revision Brief</h2>', unsafe_allow_html=True)
        with st.container(border=True):
            metric_row_one = st.columns(2)
            metric_row_one[0].metric("Risk", workflow["report"]["prediction"]["risk_level"].title())
            metric_row_one[1].metric("Budget at risk", money(workflow["impact"]["budget_at_risk"]))
            metric_row_two = st.columns(2)
            metric_row_two[0].metric("Revision days", f"{workflow['schedule']['project_duration_days']:g}")
            metric_row_two[1].metric("Days added/reduced", f"+{workflow['schedule']['duration_change']['days_added']:g} / -{workflow['schedule']['duration_change']['days_reduced']:g}")
            st.markdown(
                f'<div class="summary-card">{escape(str(workflow["report"]["executive_summary"]))}</div>',
                unsafe_allow_html=True,
            )
            st.markdown('<h3 class="insight-subtitle">What Changed</h3>', unsafe_allow_html=True)
            for item in workflow["report"]["what_changed"]:
                st.write(f"- {item['summary']}")
            st.markdown('<h3 class="insight-subtitle">What Happens Next</h3>', unsafe_allow_html=True)
            for action in workflow["report"]["field_actions"][:3]:
                st.write(f"- {action}")
            st.markdown('<h3 class="insight-subtitle">Prediction</h3>', unsafe_allow_html=True)
            prediction = workflow["report"]["prediction"]
            st.write(f"- Critical trades: {', '.join(prediction['likely_bottleneck_trades']) or 'None'}")
            st.write(f"- Highest cost trade: {prediction['highest_cost_trade'] or 'None'}")
            st.write(f"- Over budget: {'Yes' if workflow['impact']['over_budget'] else 'No'}")

        render_change_register(workflow["report"]["what_changed"])


def apply_styles() -> None:
    st.markdown("""
    <style>
    :root {
      --space-1:4px; --space-2:8px; --space-3:12px; --space-4:16px; --space-6:24px; --space-8:32px; --space-12:48px; --space-16:64px;
      --radius-sm:8px; --radius-md:10px; --radius-lg:14px; --radius-xl:18px;
      --bg:#f6f7f9; --surface:#ffffff; --surface-2:#f9fafb; --border:#e5e7eb;
      --ink:#111827; --muted:#6b7280;
      --accent:#2563eb; --accent-hover:#1d4ed8; --accent-ring:#bfdbfe;
      --success:#16a34a; --success-bg:#dcfce7;
    }
    html, body, .stApp { font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; -webkit-tap-highlight-color:rgba(37,99,235,.18); }
    .stApp { background:var(--bg); color:var(--ink); }
    .skip-link { position:fixed; top:var(--space-2); left:var(--space-2); z-index:1000; padding:var(--space-2) var(--space-3);
      border-radius:var(--radius-sm); background:var(--ink); color:white; font-size:.82rem; font-weight:600; transform:translateY(-160%); }
    .skip-link:focus-visible { transform:translateY(0); outline:2px solid var(--accent-ring); outline-offset:2px; }
    /* Top padding must clear Streamlit's fixed header or content renders hidden underneath it. */
    .block-container { max-width:1320px; padding:var(--space-12) clamp(18px,3vw,44px) var(--space-12); }
    h1,h2,h3 { color:var(--ink); letter-spacing:0; font-weight:600; }
    h1 { font-size:2rem; line-height:1.15; margin:0; text-wrap:balance; }
    h2 { font-size:1.25rem; } h3 { font-size:1rem; }
    p { color:var(--muted); line-height:1.5; font-size:.92rem; }
    [data-testid="stSidebar"] { display:none; }
    [data-testid="collapsedControl"] { display:none; }

    /* Top bar: the always-visible project context. */
    .app-topbar { display:flex; align-items:center; justify-content:space-between; gap:var(--space-4); flex-wrap:wrap;
      padding-bottom:var(--space-4); margin-bottom:var(--space-6); border-bottom:1px solid var(--border); }
    .app-topbar .brand { display:flex; align-items:center; gap:var(--space-2); }
    .app-topbar .brand .mark { width:24px; height:24px; border-radius:var(--radius-sm); background:var(--accent);
      color:white; font-size:.68rem; font-weight:700; display:flex; align-items:center; justify-content:center; letter-spacing:0; }
    .app-topbar .brand .name { font-weight:600; font-size:.95rem; color:var(--ink); }
    .app-topbar .brand .project { font-size:.82rem; color:var(--muted); padding-left:var(--space-2); border-left:1px solid var(--border); }
    .stat-strip { display:flex; gap:var(--space-2); flex-wrap:wrap; }
    .stat-pill { background:var(--surface); border:1px solid var(--border); border-radius:999px; padding:5px 14px; font-size:.78rem; color:var(--muted); white-space:nowrap; }
    .stat-pill strong { color:var(--ink); font-weight:600; }

    .panel-label { font-size:.72rem; font-weight:600; letter-spacing:.04em; text-transform:uppercase; color:var(--muted); margin-bottom:var(--space-2); }

    .workspace-intro { background:#111827; border-radius:var(--radius-lg); padding:28px 32px; margin:0 0 var(--space-8); color:white; }
    .workspace-intro h1 { color:white; }
    .workspace-intro p { color:#cbd5e1; max-width:720px; font-size:.95rem; margin:8px 0 20px; }
    .workspace-intro__eyebrow { color:#93c5fd; font-size:.75rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; margin-bottom:8px; }
    .workflow-steps { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
    .workflow-step { display:inline-flex; align-items:center; gap:7px; color:#cbd5e1; font-size:.8rem; font-weight:600; }
    .workflow-step b { display:inline-flex; align-items:center; justify-content:center; width:20px; height:20px; border:1px solid #64748b; border-radius:50%; font-size:.72rem; }
    .workflow-step.active { color:white; }
    .workflow-step.active b { background:#2563eb; border-color:#2563eb; }
    .workflow-step.complete { color:white; }
    .workflow-step.complete b { color:#052e16; background:#86efac; border-color:#86efac; }
    .workflow-connector { width:24px; height:1px; background:#475569; }
    .section-title { font-size:.82rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:#334155;
      margin:28px 0 12px; }
    .insights-title { margin-top:0; }
    .insight-subtitle { color:#334155; font-size:.78rem; font-weight:700; letter-spacing:.04em; margin:20px 0 8px; text-transform:uppercase; }
    .upload-slot { min-height:96px; }
    .upload-slot__eyebrow, .plan-header__eyebrow { display:block; color:#1d4ed8; font-size:.72rem; font-weight:700;
      letter-spacing:.08em; text-transform:uppercase; margin-bottom:5px; }
    .upload-slot--revised .upload-slot__eyebrow, .plan-header--revised .plan-header__eyebrow { color:#7c3aed; }
    .upload-slot h3, .plan-header h3 { font-size:1.05rem; line-height:1.25; margin:0; }
    .upload-slot p { margin:5px 0 0; max-width:42ch; }
    .plan-header { display:flex; align-items:flex-start; justify-content:space-between; gap:var(--space-3); margin-bottom:var(--space-3); }
    .plan-header .plan-state__status { flex:0 0 auto; margin-top:2px; }
    .empty-state { background:#eff6ff; border:1px solid #bfdbfe; border-left:4px solid var(--accent); border-radius:var(--radius-lg);
      padding:16px 18px; display:flex; flex-direction:column; gap:4px; color:#1e3a8a; margin:14px 0 20px; }
    .empty-state span { color:#1d4ed8; }
    .plan-state__status { color:#166534; font-size:.76rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase; }
    .success-strip { background:var(--success-bg); color:#166534; border:1px solid #bbf7d0; border-left:4px solid var(--success);
      border-radius:var(--radius-lg); padding:12px 16px; font-weight:600; margin:18px 0; }
    .summary-card { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius-lg); padding:20px 22px;
      font-size:.98rem; line-height:1.6; color:var(--ink); overflow-wrap:anywhere; box-shadow:0 8px 30px rgba(15,23,42,.05); }

    /* Site-facing change register. Internal data such as detection boxes stays in the
       backend; this surface is intended for a site lead's release discussion. */
    .change-card { background:var(--surface); border:1px solid var(--border); border-left:4px solid #f59e0b;
      border-radius:var(--radius-md); padding:20px 22px; margin:12px 0; box-shadow:0 8px 24px rgba(15,23,42,.045); }
    .change-card.severity-high { border-left-color:#dc2626; }
    .change-card.severity-low { border-left-color:#16a34a; }
    .change-card__topline { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:10px; }
    .change-number { color:#334155; font-size:.72rem; font-weight:700; letter-spacing:.07em; text-transform:uppercase; }
    .change-category, .change-status { font-size:.74rem; font-weight:600; border-radius:999px; padding:4px 9px; }
    .change-category { color:#1e40af; background:#dbeafe; }
    .change-status { margin-left:auto; }
    .change-status.requires-check { color:#92400e; background:#fef3c7; }
    .change-status.ready-for-work { color:#166534; background:#dcfce7; }
    .change-card h4 { font-size:1.05rem; line-height:1.35; margin:0 0 18px; color:var(--ink); }
    .change-details { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; padding:14px 0;
      border-top:1px solid var(--border); border-bottom:1px solid var(--border); }
    .change-details div:last-child { grid-column:1 / -1; }
    .change-details div, .change-action, .change-work { min-width:0; }
    .change-details span, .change-action span, .change-work span { display:block; color:var(--muted); font-size:.72rem; font-weight:600;
      letter-spacing:.04em; text-transform:uppercase; margin-bottom:4px; }
    .change-details strong { display:block; font-size:.88rem; font-weight:600; color:var(--ink); overflow-wrap:anywhere; }
    .change-action, .change-work { padding-top:14px; }
    .change-action p, .change-work p { color:var(--ink); font-size:.9rem; margin:0; }
    .change-work { padding-top:10px; }
    .change-work p { color:#475569; }

    div[data-testid="stMetric"] { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius-lg); padding:var(--space-4);
      box-shadow:0 8px 30px rgba(15,23,42,.04); }
    div[data-testid="stMetricLabel"] { color:var(--muted); font-size:.78rem; }
    div[data-testid="stMetricValue"] { color:var(--ink); font-variant-numeric:tabular-nums; }

    /* Buttons: label text renders inside a <p> in current Streamlit builds, so the
       global `p { color:var(--muted) }` rule above would otherwise win and leave
       button labels low-contrast grey-on-accent instead of the white set here. */
    .stButton > button { border-radius:var(--radius-sm); border:1px solid var(--accent); background:var(--accent); color:white; font-weight:600; min-height:42px; transition:background-color 120ms ease-out, border-color 120ms ease-out; }
    .stButton > button p { color:inherit; }
    .stButton > button:hover { background:var(--accent-hover); border-color:var(--accent-hover); }
    .stButton > button:focus-visible { outline:2px solid var(--accent-ring); outline-offset:2px; }
    .stButton > button:disabled { background:var(--border); border-color:var(--border); color:var(--muted); }
    /* Secondary-kind buttons (the layers list) read as flat list rows, not a wall of accent-filled boxes. */
    .stButton > button[kind="secondary"] { background:var(--surface); border-color:var(--border); color:var(--ink); font-weight:400; justify-content:flex-start; text-align:left; }
    .stButton > button[kind="secondary"]:hover { background:var(--bg); border-color:var(--border); }

    div[data-baseweb="tab-list"] { gap:var(--space-6); }
    button[data-baseweb="tab"] { height:40px; }
    button[data-baseweb="tab"] p { font-size:.86rem; }

    /* Tool palette: a horizontal stRadio restyled as a segmented control. */
    div[data-testid="stRadio"] > div[role="radiogroup"] { display:flex; gap:2px; background:var(--surface); border:1px solid var(--border); border-radius:var(--radius-md); padding:3px; width:fit-content; }
    div[data-testid="stRadio"] label { margin:0 !important; border-radius:var(--radius-sm); padding:4px 12px !important; cursor:pointer; transition:background-color 120ms ease-out; }
    div[data-testid="stRadio"] label:hover { background:var(--bg); }
    div[data-testid="stRadio"] label > div:first-child { display:none; }
    div[data-testid="stRadio"] label p { font-size:.82rem; color:var(--ink); }
    div[data-testid="stRadio"] label:has(input:checked) { background:var(--accent); }
    div[data-testid="stRadio"] label:has(input:checked) p { color:white; }

    /* Alerts: a hairline card with a colored left rule instead of a filled pastel block. */
    div[data-testid="stAlert"] { background:var(--surface); border:1px solid var(--border); border-left:3px solid var(--accent); border-radius:var(--radius-sm); }
    div[data-testid="stAlert"] p { color:var(--ink); }

    div[data-testid="stFileUploader"] section { min-height:132px; background:var(--surface-2); border:1px dashed #94a3b8; border-radius:var(--radius-md); padding:12px; touch-action:manipulation; }
    div[data-testid="stFileUploader"] section:focus-within { border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-ring); }
    div[data-testid="stFileUploader"] button { border-radius:var(--radius-sm); background:var(--surface-2); color:var(--ink); border-color:var(--border); }
    div[data-testid="stFileUploader"] button:hover { background:#eff6ff; color:#1d4ed8; border-color:#93c5fd; }
    div[data-testid="stExpander"] { border:1px solid var(--border); border-radius:var(--radius-md); background:var(--surface); }
    div[data-testid="stExpander"] details summary { font-weight:600; font-size:.88rem; }

    @media (max-width:720px) {
      .block-container { padding:38px 16px 44px; }
      .workspace-intro { padding:24px 20px; }
      .workflow-connector { display:none; }
      .upload-slot { min-height:0; }
      .change-details { grid-template-columns:1fr; gap:10px; }
      .change-details div:last-child { grid-column:auto; }
      .change-status { margin-left:0; }
    }
    @media (prefers-reduced-motion: reduce) { *,*::before,*::after { scroll-behavior:auto!important; transition:none!important; } }
    </style>
    """, unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(page_title="ArkiRev | Revision brief", page_icon="AR", layout="wide")
    apply_styles()
    budget = load_budget(BUDGET_FILE)

    st.markdown(f'''
    <header class="app-topbar">
      <div class="brand">
        <span class="mark">AR</span>
        <span class="name">ArkiRev</span>
        <span class="project">{escape(str(budget["project_name"]))}</span>
      </div>
      <div class="stat-strip">
        <span class="stat-pill"><strong>{money(budget["allotted_budget"])}</strong> allotted</span>
        <span class="stat-pill"><strong>{money(budget["actual_spent"])}</strong> actual spend</span>
        <span class="stat-pill"><strong>{budget["contingency_pct"]}%</strong> contingency</span>
      </div>
    </header>
    ''', unsafe_allow_html=True)

    live_upload_workflow()


if __name__ == "__main__":
    main()
