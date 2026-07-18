"""ArkiRev's Person B demo interface.

The app deliberately works before the engine branch lands: it uses the
integration stubs when the real package or its data files are unavailable.
"""
from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st
from PIL import Image

from arkirev.canvas import rescale_drawing, shapes_to_changes

ROOT = Path(__file__).parent
SAMPLE_PLAN = ROOT / "data" / "samples" / "RevA.png"
MOCK_ANALYSIS = ROOT / "data" / "samples" / "mock_analysis.json"
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
    st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False})


def apply_styles() -> None:
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    :root {
      --space-1:4px; --space-2:8px; --space-3:12px; --space-4:16px; --space-6:24px; --space-8:32px; --space-12:48px; --space-16:64px;
      --radius-sm:6px; --radius-md:8px; --radius-lg:10px;
      --bg:#f2f2f3; --surface:#ffffff; --border:#e2e2e4;
      --ink:#1e1e20; --muted:#6c6c72;
      --accent:#0d99ff; --accent-hover:#0b84dc; --accent-ring:#b3e0ff;
    }
    html, body, .stApp { font-family:'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .stApp { background:var(--bg); color:var(--ink); }
    /* Top padding must clear Streamlit's fixed header or content renders hidden underneath it. */
    .block-container { max-width:1440px; padding:var(--space-12) clamp(16px,3vw,40px) var(--space-12); }
    h1,h2,h3 { color:var(--ink); letter-spacing:-0.01em; font-weight:600; }
    h2 { font-size:1.05rem; } h3 { font-size:.95rem; }
    p { color:var(--muted); line-height:1.5; font-size:.92rem; }

    /* Top bar: a slim app header instead of a marketing hero. */
    .app-topbar { display:flex; align-items:center; justify-content:space-between; gap:var(--space-4); flex-wrap:wrap;
      padding-bottom:var(--space-4); margin-bottom:var(--space-4); border-bottom:1px solid var(--border); }
    .app-topbar .brand { display:flex; align-items:center; gap:var(--space-2); }
    .app-topbar .brand .mark { width:24px; height:24px; border-radius:var(--radius-sm); background:var(--accent);
      color:white; font-size:.68rem; font-weight:700; display:flex; align-items:center; justify-content:center; letter-spacing:0; }
    .app-topbar .brand .name { font-weight:600; font-size:.95rem; color:var(--ink); }
    .app-topbar .brand .project { font-size:.82rem; color:var(--muted); padding-left:var(--space-2); border-left:1px solid var(--border); }
    .stat-strip { display:flex; gap:var(--space-2); flex-wrap:wrap; }
    .stat-pill { background:var(--surface); border:1px solid var(--border); border-radius:999px; padding:5px 14px; font-size:.78rem; color:var(--muted); white-space:nowrap; }
    .stat-pill strong { color:var(--ink); font-weight:600; }

    .panel-label { font-size:.72rem; font-weight:600; letter-spacing:.04em; text-transform:uppercase; color:var(--muted); margin-bottom:var(--space-2); }

    div[data-testid="stMetric"] { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius-lg); padding:var(--space-4); }
    div[data-testid="stMetricLabel"] { color:var(--muted); font-size:.78rem; }
    div[data-testid="stMetricValue"] { color:var(--ink); }

    /* Buttons: label text renders inside a <p> in current Streamlit builds, so the
       global `p { color:var(--muted) }` rule above would otherwise win and leave
       button labels low-contrast grey-on-accent instead of the white set here. */
    .stButton > button { border-radius:var(--radius-sm); border:1px solid var(--accent); background:var(--accent); color:white; font-weight:500; min-height:38px; transition:background-color 120ms ease-out, border-color 120ms ease-out; }
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

    section[data-testid="stSidebar"] { background:var(--surface); border-right:1px solid var(--border); }

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

    with st.sidebar:
        st.markdown('<div class="panel-label">Demo controls</div>', unsafe_allow_html=True)
        if st.button("Use mock changes", use_container_width=True, type="primary"):
            st.session_state.changes, st.session_state.brief, st.session_state.risks = mock_changes()
            st.session_state.generated = True
            st.rerun()
        st.caption("The mock path has no canvas or API dependency.")
        plan_upload = st.file_uploader("Replace the approved Rev A", type=["png", "jpg", "jpeg"])
        (st.success if real_engine else st.info)("Connected to the production engine." if real_engine else "Using integration stubs until the engine branch is merged.")

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
        edited = st.data_editor(pd.DataFrame(editor_rows, columns=EDITOR_FIELDS), num_rows="dynamic", hide_index=True, use_container_width=True,
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
                    if st.button(row_label, key=f"layer_btn_{index}", use_container_width=True,
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
        generate = st.button("Generate field brief", type="primary", use_container_width=True)
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
            st.dataframe(pd.DataFrame(trade_rows), hide_index=True, use_container_width=True)
        with right:
            st.subheader("Allotment status")
            st.metric("Projected actual", money(impact["projected_actual"]))
            st.metric("Remaining allotment", money(impact["remaining_allotment"]))
        st.subheader("Revision line items")
        st.dataframe(pd.DataFrame(impact["line_items"]), hide_index=True, use_container_width=True)
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
