"""ArkiRev's Person B demo interface.

The app deliberately works before the engine branch lands: it uses the
integration stubs when the real package or its data files are unavailable.
"""
from __future__ import annotations

import json
import hashlib
from html import escape
from io import BytesIO
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st
from PIL import Image

from arkirev.annotations import annotate_revised_plan
from arkirev.canvas import rescale_drawing, shapes_to_changes

ROOT = Path(__file__).parent
SAMPLE_PLAN = ROOT / "data" / "samples" / "RevA.png"
MOCK_ANALYSIS = ROOT / "data" / "samples" / "mock_analysis.json"
PITCH_DIR = ROOT / "data" / "samples" / "pitch_revised_floor_plan"
PITCH_ORIGINAL = PITCH_DIR / "0000-0009_base_original.png"
PITCH_REVISED = PITCH_DIR / "0000-0009_revised_mock.png"
PITCH_ANNOTATED = PITCH_DIR / "0000-0009_annotated_demo.png"
PITCH_ANALYSIS = PITCH_DIR / "0000-0009_revision_analysis.json"
BUDGET_FILE = ROOT / "data" / "project_budget.json"
TEMPLATES_FILE = ROOT / "data" / "task_templates.json"
CATEGORIES = ["unknown_change", "door_move", "new_opening", "layout_change", "dimension_or_note_change", "equipment_or_fixture_change"]
SEVERITIES = ["low", "medium", "high"]
TRADES = ["general", "structural", "demolition", "carpentry", "masonry", "mep", "architecture"]
EDITOR_FIELDS = ["summary", "category", "severity", "trade"]
TOOLS = [("transform", "Select"), ("rect", "Rectangle"), ("circle", "Ellipse"), ("line", "Line")]
ZOOM_LEVELS = [50, 75, 100, 125, 150]


def engine() -> tuple[Any, Any, Any, Any, Any, bool]:
    """Prefer Person A's engine; retain a deterministic, integration-safe fallback."""
    try:
        from arkirev.budget import estimate_impact, load_budget
        from arkirev.schedule import build_tasks, compute_cpm, load_templates
        if BUDGET_FILE.exists() and TEMPLATES_FILE.exists():
            return estimate_impact, build_tasks, compute_cpm, load_budget, load_templates, True
    except ImportError:
        pass
    from arkirev._stubs import build_tasks, compute_cpm, estimate_impact, load_budget, load_templates
    return estimate_impact, build_tasks, compute_cpm, load_budget, load_templates, False


def money(amount: float) -> str:
    return f"₱{amount:,.0f}"


def default_changes() -> list[dict[str, Any]]:
    return []


def mock_changes() -> tuple[list[dict[str, Any]], str, list[str]]:
    with MOCK_ANALYSIS.open(encoding="utf-8") as file:
        payload = json.load(file)
    return payload["changes"], payload["field_brief"], payload["risks"]


def make_analysis(rows: list[dict[str, Any]], real_engine: bool) -> Any:
    fields = {"summary", "category", "severity", "trade", "bbox", "verify_before_build"}
    clean = [{key: value for key, value in row.items() if key in fields} for row in rows if str(row.get("summary", "")).strip()]
    if not real_engine:
        return {"changes": clean}
    from arkirev.models import ChangeItem, RevisionAnalysis
    return RevisionAnalysis(changes=[ChangeItem(**item) for item in clean])


def make_brief(rows: list[dict[str, Any]]) -> tuple[str, list[str]]:
    names = [str(row["summary"]).strip() for row in rows if str(row.get("summary", "")).strip()]
    if not names:
        return "No revisions have been entered. Add a structured change or mark the plan to generate a field brief.", []
    risks = ["Confirm dimensions and field conditions before releasing work."]
    if any(row.get("category") == "new_opening" for row in rows):
        risks.insert(0, "Obtain structural review before cutting any new opening.")
    if any(row.get("category") == "equipment_or_fixture_change" for row in rows):
        risks.append("Coordinate MEP rough-in before finishes are closed.")
    return f"{len(names)} revision{'s' if len(names) != 1 else ''} require field coordination: {'; '.join(names)}.", risks


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
    st.markdown('<div class="section-title">Detected Changes</div>', unsafe_allow_html=True)
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
              <h3>{escape(str(change.get("summary", "Plan revision")))}</h3>
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
    st.markdown("""
    <section class="hero-panel">
      <div>
        <div class="eyebrow">Revision Intelligence</div>
        <h1>Compare two floor plans and produce a build-ready revision brief.</h1>
        <p>Upload the approved plan and the revised plan. ArkiRev maps the changed areas, predicts cost and schedule impact, and returns an annotated drawing for site review.</p>
      </div>
    </section>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">1. Upload Approved Plan</div>', unsafe_allow_html=True)
    approved_upload = st.file_uploader("Approved / original floor plan", type=["png", "jpg", "jpeg"], key="live_approved")
    approved_data = read_image_upload(approved_upload)
    if approved_data is None:
        st.markdown("""
        <div class="empty-state">
          <strong>Waiting for the approved floor plan.</strong>
          <span>Upload the approved/base drawing first. The revised-plan upload will appear after that.</span>
        </div>
        """, unsafe_allow_html=True)
        return

    approved_image, approved_bytes, approved_name = approved_data
    st.image(approved_image, caption=f"Approved: {approved_name}", width="stretch")

    st.markdown('<div class="section-title">2. Upload Revised Plan</div>', unsafe_allow_html=True)
    revised_upload = st.file_uploader("Revised floor plan", type=["png", "jpg", "jpeg"], key="live_revised")
    revised_data = read_image_upload(revised_upload)
    if revised_data is None:
        st.markdown("""
        <div class="empty-state ready">
          <strong>Approved plan loaded.</strong>
          <span>Now upload the revised floor plan. ArkiRev will generate the output automatically.</span>
        </div>
        """, unsafe_allow_html=True)
        return

    revised_image, revised_bytes, revised_name = revised_data
    st.markdown('<div class="section-title">3. Uploaded Plan Pair</div>', unsafe_allow_html=True)
    preview_left, preview_right = st.columns(2)
    preview_left.image(approved_image, caption=f"Approved: {approved_name}", width="stretch")
    preview_right.image(revised_image, caption=f"Revised: {revised_name}", width="stretch")

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

    result = st.session_state.get("live_result")
    if not result:
        st.info("Processing the revised plan...")
        return

    workflow = result["workflow"]
    st.markdown(f'<div class="success-strip">Workflow completed in {result["elapsed"]:.1f}s</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">4. Annotated Output</div>', unsafe_allow_html=True)
    st.image(result["annotated"], caption="ArkiRev annotated revised floor plan", width="stretch")
    metrics = st.columns(4)
    metrics[0].metric("Risk", workflow["report"]["prediction"]["risk_level"].title())
    metrics[1].metric("Budget at risk", money(workflow["impact"]["budget_at_risk"]))
    metrics[2].metric("Revision days", f"{workflow['schedule']['project_duration_days']:g}")
    metrics[3].metric("Days added/reduced", f"+{workflow['schedule']['duration_change']['days_added']:g} / -{workflow['schedule']['duration_change']['days_reduced']:g}")

    st.markdown('<div class="section-title">5. Revision Brief</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="summary-card">{workflow["report"]["executive_summary"]}</div>', unsafe_allow_html=True)

    report_cols = st.columns(3)
    report_cols[0].markdown("**What changed**")
    for item in workflow["report"]["what_changed"]:
        report_cols[0].write(f"- {item['summary']}")
    report_cols[1].markdown("**What happens next**")
    for action in workflow["report"]["field_actions"][:3]:
        report_cols[1].write(f"- {action}")
    report_cols[2].markdown("**Prediction**")
    report_cols[2].write(f"- Critical trades: {', '.join(workflow['report']['prediction']['likely_bottleneck_trades']) or 'None'}")
    report_cols[2].write(f"- Highest cost trade: {workflow['report']['prediction']['highest_cost_trade'] or 'None'}")
    report_cols[2].write(f"- Over budget: {'Yes' if workflow['impact']['over_budget'] else 'No'}")

    render_change_register(workflow["report"]["what_changed"])


def gantt(schedule: Any) -> None:
    if not schedule.tasks:
        st.info("Add at least one change to build a construction sequence.")
        return
    rows = [{"Task": task.name, "Trade": task.trade.title(), "Start": task.es, "Finish": task.ef,
             "Critical": "Critical path" if task.critical else "Has slack", "Change": f"Change {task.change_index + 1}"}
            for task in schedule.tasks]
    frame = pd.DataFrame(rows)
    base = pd.Timestamp("2026-01-01")
    frame["Start"] = base + pd.to_timedelta(frame["Start"], unit="D")
    frame["Finish"] = base + pd.to_timedelta(frame["Finish"], unit="D")
    figure = px.timeline(frame, x_start="Start", x_end="Finish", y="Task", color="Critical", hover_data=["Trade", "Change"],
                         color_discrete_map={"Critical path": "#c2410c", "Has slack": "#94a3b8"})
    figure.update_layout(height=max(330, 72 * len(frame)), margin=dict(l=8, r=8, t=24, b=8), legend_title_text="")
    figure.update_yaxes(autorange="reversed", title=None)
    figure.update_xaxes(title="Construction day", tickformat="Day %d")
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})


def apply_styles() -> None:
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    :root {
      --space-1:4px; --space-2:8px; --space-3:12px; --space-4:16px; --space-6:24px; --space-8:32px; --space-12:48px; --space-16:64px;
      --radius-sm:8px; --radius-md:10px; --radius-lg:14px; --radius-xl:18px;
      --bg:#f6f7f9; --surface:#ffffff; --surface-2:#f9fafb; --border:#e5e7eb;
      --ink:#111827; --muted:#6b7280;
      --accent:#2563eb; --accent-hover:#1d4ed8; --accent-ring:#bfdbfe;
      --success:#16a34a; --success-bg:#dcfce7;
    }
    html, body, .stApp { font-family:'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .stApp { background:var(--bg); color:var(--ink); }
    /* Top padding must clear Streamlit's fixed header or content renders hidden underneath it. */
    .block-container { max-width:1320px; padding:var(--space-12) clamp(18px,3vw,44px) var(--space-12); }
    h1,h2,h3 { color:var(--ink); letter-spacing:-0.01em; font-weight:600; }
    h1 { font-size:clamp(2rem,4vw,3.7rem); line-height:1; margin:0; letter-spacing:-.03em; }
    h2 { font-size:1.25rem; } h3 { font-size:1rem; }
    p { color:var(--muted); line-height:1.5; font-size:.92rem; }
    [data-testid="stSidebar"] { display:none; }
    [data-testid="collapsedControl"] { display:none; }

    /* Top bar: a slim app header instead of a marketing hero. */
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

    .hero-panel { background:linear-gradient(135deg,#0f172a 0%,#1e3a8a 52%,#0f766e 100%); border-radius:var(--radius-xl);
      padding:38px 42px; margin:0 0 var(--space-8); color:white; box-shadow:0 20px 70px rgba(15,23,42,.18); }
    .hero-panel h1 { color:white; max-width:900px; }
    .hero-panel p { color:#dbeafe; max-width:760px; font-size:1rem; margin:18px 0 0; }
    .eyebrow { color:#bfdbfe; font-size:.75rem; font-weight:700; letter-spacing:.12em; text-transform:uppercase; margin-bottom:12px; }
    .section-title { font-size:.82rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:#334155;
      margin:28px 0 12px; }
    .upload-heading { font-size:.84rem; font-weight:700; color:var(--ink); margin-bottom:8px; }
    .empty-state { background:#eff6ff; border:1px solid #bfdbfe; border-left:4px solid var(--accent); border-radius:var(--radius-lg);
      padding:16px 18px; display:flex; flex-direction:column; gap:4px; color:#1e3a8a; margin:14px 0 20px; }
    .empty-state span { color:#1d4ed8; }
    .success-strip { background:var(--success-bg); color:#166534; border:1px solid #bbf7d0; border-left:4px solid var(--success);
      border-radius:var(--radius-lg); padding:12px 16px; font-weight:600; margin:18px 0; }
    .summary-card { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius-lg); padding:20px 22px;
      font-size:.98rem; line-height:1.6; color:var(--ink); box-shadow:0 8px 30px rgba(15,23,42,.05); }

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
    .change-card h3 { font-size:1.05rem; line-height:1.35; margin:0 0 18px; color:var(--ink); }
    .change-details { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; padding:14px 0;
      border-top:1px solid var(--border); border-bottom:1px solid var(--border); }
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
    div[data-testid="stMetricValue"] { color:var(--ink); }

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

    div[data-testid="stFileUploader"] section { background:#111827; border:1px solid #374151; border-radius:var(--radius-lg); }
    div[data-testid="stFileUploader"] button { border-radius:8px; }

    @media (max-width:720px) {
      .block-container { padding:38px 16px 44px; }
      .hero-panel { padding:28px 22px; border-radius:var(--radius-lg); }
      .change-details { grid-template-columns:1fr; gap:10px; }
      .change-status { margin-left:0; }
    }
    @media (prefers-reduced-motion: reduce) { *,*::before,*::after { scroll-behavior:auto!important; transition:none!important; } }
    </style>
    """, unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(page_title="ArkiRev | Revision brief", page_icon="AR", layout="wide")
    apply_styles()
    estimate_impact, build_tasks, compute_cpm, load_budget, load_templates, real_engine = engine()
    budget, templates = load_budget(BUDGET_FILE), load_templates(TEMPLATES_FILE)
    if "changes" not in st.session_state:
        st.session_state.changes = default_changes()
    if "brief" not in st.session_state:
        st.session_state.brief, st.session_state.risks = make_brief(st.session_state.changes)
    if "generated" not in st.session_state:
        st.session_state.generated = False

    st.markdown(f'''
    <div class="app-topbar">
      <div class="brand">
        <span class="mark">AR</span>
        <span class="name">ArkiRev</span>
        <span class="project">{budget["project_name"]}</span>
      </div>
      <div class="stat-strip">
        <span class="stat-pill"><strong>{money(budget["allotted_budget"])}</strong> allotted</span>
        <span class="stat-pill"><strong>{money(budget["actual_spent"])}</strong> actual spend</span>
        <span class="stat-pill"><strong>{budget["contingency_pct"]}%</strong> contingency</span>
      </div>
    </div>
    ''', unsafe_allow_html=True)

    if real_engine:
        st.caption("Production backend connected: vision comparison, annotation, budget, schedule, and report generation.")
    else:
        st.warning("Using integration stubs until the backend data files are available.")

    live_upload_workflow()
    return

    plan_upload = None
    plan = Image.open(plan_upload).convert("RGB") if plan_upload else Image.open(SAMPLE_PLAN).convert("RGB")
    # A conditional render, not st.tabs: st.tabs pre-builds every tab's content into the
    # DOM and only toggles CSS visibility, so the drawing canvas would mount once while
    # its tab is display:none, measure its own height as 0, and never re-measure once
    # shown. Only ever building the active view's content sidesteps that entirely.
    view = st.radio("View", ["1 · Structured changes", "2 · Draw on plan"], horizontal=True, label_visibility="collapsed", key="active_view")
    st.markdown('<div style="border-bottom:1px solid var(--border); margin:-8px 0 var(--space-4);"></div>', unsafe_allow_html=True)
    if view == "1 · Structured changes":
        st.subheader("Review and edit the proposed scope")
        st.caption("This table is the source of truth. You can add, correct, or remove rows before computing impact.")
        source_rows = st.session_state.changes
        editor_rows = [{field: row.get(field, "") for field in EDITOR_FIELDS} for row in source_rows]
        edited = st.data_editor(pd.DataFrame(editor_rows, columns=EDITOR_FIELDS), num_rows="dynamic", hide_index=True, width="stretch",
            column_config={"summary": st.column_config.TextColumn("Revision", required=True, width="large"),
                           "category": st.column_config.SelectboxColumn("Category", options=CATEGORIES, required=True),
                           "severity": st.column_config.SelectboxColumn("Severity", options=SEVERITIES, required=True),
                           "trade": st.column_config.SelectboxColumn("Lead trade", options=TRADES, required=True)}, key="change_editor")
        edited_rows = edited.fillna("").to_dict("records")
        st.session_state.changes = [
            {**(source_rows[index] if index < len(source_rows) else {}), **{field: row.get(field, "") for field in EDITOR_FIELDS}}
            for index, row in enumerate(edited_rows)
        ]
        if not st.session_state.changes:
            st.caption("No revisions yet. Click the **+** row above to add one, mark up the plan in the next tab, or use **Use mock changes** in the sidebar.")

    else:
        try:
            from streamlit_drawable_canvas import st_canvas

            toolbar_left, toolbar_right = st.columns([3, 1])
            with toolbar_left:
                tool_label = st.radio("Tool", [label for _, label in TOOLS], index=1, horizontal=True, label_visibility="collapsed", key="canvas_tool_label")
            with toolbar_right:
                zoom = st.select_slider("Zoom", options=ZOOM_LEVELS, value=st.session_state.get("canvas_zoom", 100),
                                         format_func=lambda value: f"{value}%", label_visibility="collapsed", key="canvas_zoom")
            tool_mode = next(mode for mode, label in TOOLS if label == tool_label)

            layers_col, canvas_col, props_col = st.columns([1, 2.6, 1.1], gap="medium")

            with canvas_col:
                base_width = min(plan.width, 600)
                displayed_width = round(base_width * zoom / 100)
                displayed_height = round(plan.height * displayed_width / plan.width)
                prev_zoom = st.session_state.get("_prev_zoom", 100)
                initial_drawing = None
                if zoom != prev_zoom:
                    initial_drawing = rescale_drawing(st.session_state.get("_last_canvas_json"), zoom / prev_zoom)
                st.session_state["_prev_zoom"] = zoom
                result = st_canvas(fill_color="rgba(13, 153, 255, 0.14)", stroke_width=2, stroke_color="#0d99ff", background_image=plan,
                                   update_streamlit=True, height=displayed_height, width=displayed_width, drawing_mode=tool_mode,
                                   initial_drawing=initial_drawing, display_toolbar=True, key=f"revision_canvas_{zoom}")
                objects = result.json_data.get("objects", []) if result.json_data else []
                st.session_state["_last_canvas_json"] = result.json_data
            shapes = [item for item in objects if item.get("type") in {"rect", "circle", "line"}]

            if st.session_state.get("_last_shape_count", -1) != len(shapes):
                st.session_state.selected_layer = max(len(shapes) - 1, 0)
            st.session_state["_last_shape_count"] = len(shapes)

            with layers_col:
                st.markdown('<div class="panel-label">Layers</div>', unsafe_allow_html=True)
                if not shapes:
                    st.caption("Nothing drawn yet.")
                for index in range(len(shapes)):
                    category = st.session_state.get(f"markup_category_{index}", "unknown_change")
                    label_text = st.session_state.get(f"markup_summary_{index}") or f"Markup {index + 1}"
                    selected = st.session_state.get("selected_layer") == index
                    row_label = f"{label_text}  ·  {category.replace('_', ' ').title()}"
                    if st.button(row_label, key=f"layer_btn_{index}", width="stretch",
                                 type="primary" if selected else "secondary"):
                        st.session_state.selected_layer = index
                        st.rerun()

            with props_col:
                st.markdown('<div class="panel-label">Properties</div>', unsafe_allow_html=True)
                if shapes:
                    index = min(st.session_state.get("selected_layer", 0), len(shapes) - 1)
                    st.session_state.selected_layer = index
                    st.text_input("Revision note", key=f"markup_summary_{index}", placeholder="e.g. Add pass-through opening")
                    current_category = st.session_state.get(f"markup_category_{index}", "unknown_change")
                    st.selectbox("Category", CATEGORIES, index=CATEGORIES.index(current_category), key=f"markup_category_{index}")
                    current_severity = st.session_state.get(f"markup_severity_{index}", "medium")
                    current_trade = st.session_state.get(f"markup_trade_{index}", "general")
                    sev_col, trade_col = st.columns(2)
                    sev_col.selectbox("Severity", SEVERITIES, index=SEVERITIES.index(current_severity), key=f"markup_severity_{index}")
                    trade_col.selectbox("Lead trade", TRADES, index=TRADES.index(current_trade), key=f"markup_trade_{index}")
                    shape = shapes[index]
                    x_col, y_col = st.columns(2)
                    x_col.metric("X", f"{shape.get('left', 0):.0f}")
                    y_col.metric("Y", f"{shape.get('top', 0):.0f}")
                    w_col, h_col = st.columns(2)
                    w_col.metric("W", f"{abs(shape.get('width', 0) * shape.get('scaleX', 1)):.0f}")
                    h_col.metric("H", f"{abs(shape.get('height', 0) * shape.get('scaleY', 1)):.0f}")
                else:
                    st.caption("Draw a shape on the plan to label it here.")

            labels = [{
                "summary": st.session_state.get(f"markup_summary_{index}", ""),
                "category": st.session_state.get(f"markup_category_{index}", "unknown_change"),
                "severity": st.session_state.get(f"markup_severity_{index}", "medium"),
                "trade": st.session_state.get(f"markup_trade_{index}", "general"),
            } for index in range(len(shapes))]
            marked = shapes_to_changes(objects, labels, coordinate_scale=(plan.width / displayed_width, plan.height / displayed_height))
            if marked and st.button("Add marked changes to review table", type="primary"):
                st.session_state.changes = [*st.session_state.changes, *marked]
                st.session_state.generated = False
                st.rerun()
        except ImportError:
            st.warning("The drawing component is not installed. Run `pip install -r requirements.txt`; the structured-change flow remains available.")
        except (AttributeError, TypeError):
            st.warning("The installed drawing component is incompatible with this Streamlit version. Reinstall from `requirements.txt` (Streamlit 1.32 is pinned for canvas support).")

    st.divider()
    action_left, action_right = st.columns([1, 3])
    with action_left:
        generate = st.button("Generate field brief", type="primary", width="stretch")
    with action_right:
        st.caption("All calculations are deterministic templates; no live ERP, CAD, or API is required.")
    if generate:
        start = perf_counter()
        analysis = make_analysis(st.session_state.changes, real_engine)
        st.session_state.impact = estimate_impact(analysis, budget)
        st.session_state.schedule = compute_cpm(build_tasks(analysis, templates))
        st.session_state.elapsed = max(perf_counter() - start, 0.1)
        st.session_state.brief, st.session_state.risks = make_brief(st.session_state.changes)
        st.session_state.generated = True

    if not st.session_state.generated:
        st.info("Ready when you are — generate the brief to calculate budget and schedule effects.")
        return
    analysis = make_analysis(st.session_state.changes, real_engine)
    impact = st.session_state.get("impact") or estimate_impact(analysis, budget)
    schedule = st.session_state.get("schedule") or compute_cpm(build_tasks(analysis, templates))
    st.subheader("Revision impact")
    a, b, c, d = st.columns(4)
    a.metric("Entry time", f"{st.session_state.get('elapsed', 0.1):.1f}s")
    b.metric("Budget at risk", money(impact["budget_at_risk"]))
    c.metric("Contingency", money(impact["contingency"]))
    d.metric("Days added", f"{schedule.project_duration_days:g} days")
    if impact["over_budget"]:
        st.error(f"Projected spend exceeds the allotment by {money(abs(impact['remaining_allotment']))}.")

    budget_tab, schedule_tab, brief_tab = st.tabs(["Budget planner", "Critical path", "Field brief"])
    with budget_tab:
        left, right = st.columns(2)
        with left:
            st.subheader("Cost exposure by trade")
            trade_rows = [{"Trade": trade.title(), "At risk": money(amount)} for trade, amount in impact["by_trade"].items()]
            st.dataframe(pd.DataFrame(trade_rows), hide_index=True, width="stretch")
        with right:
            st.subheader("Allotment status")
            st.metric("Projected actual", money(impact["projected_actual"]))
            st.metric("Remaining allotment", money(impact["remaining_allotment"]))
        st.subheader("Revision line items")
        st.dataframe(pd.DataFrame(impact["line_items"]), hide_index=True, width="stretch")
    with schedule_tab:
        st.subheader(f"Critical construction sequence · {schedule.project_duration_days:g} days")
        st.caption("Terracotta tasks are on the critical path. Grey tasks can run in parallel without extending the finish date.")
        gantt(schedule)
    with brief_tab:
        st.subheader("Field-ready revision brief")
        st.write(st.session_state.brief)
        if st.session_state.risks:
            st.subheader("Verify before build")
            for risk in st.session_state.risks:
                st.write(f"• {risk}")


if __name__ == "__main__":
    main()
