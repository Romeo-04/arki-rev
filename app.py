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

from arkirev.canvas import rectangles_to_changes

ROOT = Path(__file__).parent
SAMPLE_PLAN = ROOT / "data" / "samples" / "RevA.png"
MOCK_ANALYSIS = ROOT / "data" / "samples" / "mock_analysis.json"
BUDGET_FILE = ROOT / "data" / "project_budget.json"
TEMPLATES_FILE = ROOT / "data" / "task_templates.json"
CATEGORIES = ["door_move", "new_opening", "layout_change", "dimension_or_note_change", "equipment_or_fixture_change", "unknown_change"]
SEVERITIES = ["low", "medium", "high"]
TRADES = ["general", "structural", "demolition", "carpentry", "masonry", "mep", "architecture"]
EDITOR_FIELDS = ["summary", "category", "severity", "trade"]


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
    :root { --ink:#17212b; --muted:#607080; --canvas:#f5f7f8; --surface:#ffffff; --line:#d9e1e6; --accent:#0f766e; --radius:12px; }
    .stApp { background:var(--canvas); color:var(--ink); }
    .block-container { max-width:1400px; padding:32px clamp(16px,4vw,56px) 48px; }
    h1,h2,h3 { color:var(--ink); letter-spacing:-0.02em; } h1 { font-size:2.15rem; margin-bottom:4px; } p { color:var(--muted); }
    div[data-testid="stMetric"] { background:var(--surface); border:1px solid var(--line); border-radius:var(--radius); padding:16px; }
    div[data-testid="stMetricLabel"] { color:var(--muted); font-size:.8rem; } div[data-testid="stMetricValue"] { color:var(--ink); }
    .project-card { background:var(--ink); border-radius:var(--radius); padding:20px 24px; color:white; margin:20px 0 24px; }
    .project-card p { color:#cbd5e1; margin:4px 0 0; } .eyebrow { color:#0f766e; font-size:.78rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; }
    .stButton > button { border-radius:8px; border:1px solid var(--accent); background:var(--accent); color:white; font-weight:600; min-height:40px; }
    .stButton > button:hover { background:#115e59; border-color:#115e59; } .stButton > button:focus-visible { outline:3px solid #5eead4; outline-offset:2px; }
    div[data-baseweb="tab-list"] { gap:24px; } button[data-baseweb="tab"] { height:42px; }
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

    st.markdown('<div class="eyebrow">Construction revision intelligence</div>', unsafe_allow_html=True)
    st.title("Turn marked-up plans into a field-ready brief.")
    st.caption("Capture a revision, verify its scope, then see the budget exposure and critical construction sequence.")
    st.markdown(f'''<div class="project-card"><strong>{budget["project_name"]}</strong><p>{money(budget["allotted_budget"])} allotted · {money(budget["actual_spent"])} actual spend · {budget["contingency_pct"]}% contingency</p></div>''', unsafe_allow_html=True)

    with st.sidebar:
        st.subheader("Demo controls")
        if st.button("Use mock changes", use_container_width=True):
            st.session_state.changes, st.session_state.brief, st.session_state.risks = mock_changes()
            st.session_state.generated = True
            st.rerun()
        st.caption("The mock path has no canvas or API dependency.")
        plan_upload = st.file_uploader("Replace the approved Rev A", type=["png", "jpg", "jpeg"])
        (st.success if real_engine else st.info)("Connected to the production engine." if real_engine else "Using integration stubs until the engine branch is merged.")

    plan = Image.open(plan_upload).convert("RGB") if plan_upload else Image.open(SAMPLE_PLAN).convert("RGB")
    entry_tab, markup_tab = st.tabs(["1 · Structured changes", "2 · Draw on plan"])
    with entry_tab:
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

    with markup_tab:
        st.subheader("Mark the approved floor plan")
        st.caption("Draw a rectangle around each revision, label it below, then add the marked changes to the review table.")
        try:
            from streamlit_drawable_canvas import st_canvas
            displayed_width = min(plan.width, 880)
            displayed_height = round(plan.height * displayed_width / plan.width)
            result = st_canvas(fill_color="rgba(15, 118, 110, 0.14)", stroke_width=3, stroke_color="#0f766e", background_image=plan,
                               update_streamlit=True, height=displayed_height, width=displayed_width, drawing_mode="rect", key="revision_canvas")
            objects = result.json_data.get("objects", []) if result.json_data else []
            rectangles = [item for item in objects if item.get("type") == "rect"]
            labels: list[dict[str, str]] = []
            for index in range(len(rectangles)):
                with st.expander(f"Markup {index + 1}", expanded=True):
                    left, right = st.columns([2, 1])
                    summary = left.text_input("Revision note", key=f"markup_summary_{index}", placeholder="e.g. Add pass-through opening")
                    category = right.selectbox("Category", CATEGORIES, key=f"markup_category_{index}")
                    severity, trade = st.columns(2)
                    labels.append({"summary": summary, "category": category, "severity": severity.selectbox("Severity", SEVERITIES, key=f"markup_severity_{index}"), "trade": trade.selectbox("Lead trade", TRADES, key=f"markup_trade_{index}")})
            marked = rectangles_to_changes(
                objects,
                labels,
                coordinate_scale=(plan.width / displayed_width, plan.height / displayed_height),
            )
            if marked and st.button("Add marked changes to review table"):
                st.session_state.changes = [*st.session_state.changes, *marked]
                st.session_state.generated = False
                st.rerun()
            if not rectangles:
                st.info("No markups yet. Choose the rectangle tool and draw directly on the plan.")
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
