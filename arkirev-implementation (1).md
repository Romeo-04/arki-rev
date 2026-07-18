# ArkiRev Implementation Plan (revised)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Streamlit demo where a user submits an approved floor plan (Rev A), **draws the needed revision directly on it inside the app**, and ArkiRev returns (1) a **budget planner** showing allotted / actual / at-risk with a per-trade breakdown, and (2) a **real critical-path (CPM) schedule** showing the sequenced tasks the revision forces — and which of them are on the critical path — all without AutoCAD or a live ERP.

**Core insight (changed from v1):** The revision is captured as **structured data at draw-time**, not reverse-engineered from two images. The user draws a markup box on Rev A and labels it (category + note). Because the app already knows *what* changed and *where*, it can compute cost and schedule deterministically. A vision LLM is now an **optional assist** ("suggest changes for me"), not a load-bearing dependency.

**Architecture:** A single Streamlit app loads Rev A → renders it in a drawable canvas → user draws + labels change markups → each change expands (via a task-template library) into construction tasks with durations and dependencies → a CPM engine computes the schedule and critical path → a budget engine maps changes to unit costs → the UI renders a field brief, a per-trade budget panel, and a Gantt-style critical-path view.

**Tech Stack:** Python 3.11+, Streamlit, `streamlit-drawable-canvas` (markup), Pillow, Plotly (Gantt), pydantic, python-dotenv, local JSON for budget/unit costs + task templates, OpenAI SDK (optional vision assist).

---

## Phasing (this replaces the single 4-hour box)

The v1 plan was time-boxed at 4h. Drawing canvas + real CPM + Gantt is realistically **8–12h** (or a team splitting frontend/schedule/budget). To never risk the demo, build in two phases:

- **Phase 1 — Demo-safe MVP (~4–5h):** Structured-change entry (no canvas yet — a simple form/table), budget planner, **real CPM engine + Gantt**. This alone is a complete, compelling demo.
- **Phase 2 — Interactive markup (~3–4h):** Replace the form with `streamlit-drawable-canvas` so changes are drawn *on the plan*; add optional vision auto-suggest; add editable durations/costs.

If you run short, Phase 1 ships. The CPM engine is the differentiator, so it lives in Phase 1, not Phase 2.

---

## Parallelization — two implementers

The build splits along one clean seam: **the engine** (pure Python, fully testable, no Streamlit) and **the app** (everything the user sees). They meet at exactly one place — the data contracts in `models.py` — so once those are agreed, the two people work in parallel with almost no blocking.

### Person A — Engine owner (`arkirev/` package + `tests/`)
Owns all business logic and data. No Streamlit code.
- **Files:** `arkirev/models.py`, `arkirev/schedule.py`, `arkirev/budget.py`, `arkirev/compare.py`, `arkirev/prompts.py`, `data/project_budget.json`, `data/task_templates.json`, all of `tests/`.
- **Tasks:** 2, 3, 4, 5 (and the two engine data files from Task 0).
- **Deliverable contract (what Person B builds against):**
  - `build_tasks(analysis, templates) -> dict[str, Task]`
  - `compute_cpm(tasks) -> ScheduleResult`
  - `estimate_impact(analysis, budget) -> dict` (keys: `budget_at_risk`, `contingency`, `projected_actual`, `remaining_allotment`, `over_budget`, `by_trade`, `line_items`)
  - `load_budget(path)`, `load_templates(path)`, `compare_revisions(...)`
- **Why this person is unblocked:** every function is testable in isolation. Person A never needs the UI to make progress — `pytest` is the whole feedback loop.

### Person B — App/UX owner (`app.py` + canvas + visuals + assets)
Owns everything the user touches.
- **Files:** `app.py`, `arkirev/canvas.py`, `data/samples/RevA.png`, `data/samples/mock_analysis.json`, `docs/DEMO_SCRIPT.md`, `README.md`, `requirements.txt`, `.env.example`, `.gitignore`.
- **Tasks:** 1 (skeleton), 6 (Phase 1 UI), 7 (Phase 2 canvas), 8 (demo), plus the `RevA.png` asset from Task 0.
- **Why this person is unblocked:** Person B codes against a **stub module** (see handshake below) that returns fake `ScheduleResult` / impact dicts matching Person A's contract. The UI, Gantt, budget panel, and canvas can all be built and styled before the real engine exists.

### The handshake (do this together, first ~20 min — this is the only hard dependency)
1. Both agree on `arkirev/models.py` — `ChangeItem`, `RevisionAnalysis`, `Task`, `ScheduleResult`. **Freeze these signatures.** This is the contract; changing it later is what forces rework.
2. Person A writes `models.py` for real. Person B writes `arkirev/_stubs.py` returning hardcoded objects of those types, e.g.:
   ```python
   # arkirev/_stubs.py  (Person B, deleted at integration)
   from arkirev.models import Task, ScheduleResult
   def compute_cpm(_tasks): return ScheduleResult(
       tasks=[Task(id="0:0", name="Cut opening", trade="demolition",
                   duration_days=1, change_index=0, es=0, ef=1, critical=True)],
       project_duration_days=5.5, critical_path=["0:0"])
   def estimate_impact(_a, _b): return {"budget_at_risk": 47000, "contingency": 4700,
       "projected_actual": 371700, "remaining_allotment": 628300, "over_budget": False,
       "by_trade": {"demolition": 12000, "structural": 35000}, "line_items": []}
   ```
3. Person B imports from `_stubs` while building; at integration, swap `from arkirev._stubs import ...` → `from arkirev.schedule/budget import ...`. One-line change per import.

### Integration checkpoint (~end of Phase 1)
When Person A's Tasks 2–5 are green and Person B's Task 6 UI renders against stubs: swap the stub imports for the real ones, run the app end-to-end, commit `feat: integrate engine into Phase 1 UI`. If the contract held, this is a 10-minute merge. Person B's canvas (Task 7) then layers on with no engine changes at all — the canvas only produces `ChangeItem`s, which already flow through the frozen contract.

### Merge hygiene
Because the two owners touch almost disjoint file sets, git conflicts are rare. The only shared files are `models.py` (frozen early, Person A owns) and Task 0's data split (`RevA.png` → B; `*.json` → A). Work on separate branches (`engine`, `app`); integrate at the checkpoint above.

---

## Product story (updated)

1. Company sets scope + **allotted budget** (e.g. ₱1,000,000).
2. Architect's approved draft = **Rev A** (uploaded once).
3. Revision needed → user **draws/labels the changes on Rev A inside ArkiRev** (Phase 2) or enters them structurally (Phase 1).
4. ArkiRev computes: **what changed**, **₱ at risk (per trade)**, and **the critical path + total added days**.
5. Demo metrics: **time to brief**, **₱ at risk if ignored**, **days added to schedule**.

**Not in scope:** live ERP, BIM/Revit, auth, multi-project DB, YOLO training, resource leveling, cost-loaded scheduling.

---

## File structure

```text
arkirev/
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── app.py                      # Streamlit UI entry
├── data/
│   ├── project_budget.json     # allotted, actual, unit costs
│   ├── task_templates.json     # category -> construction tasks (durations, deps)
│   └── samples/
│       └── RevA.png            # approved floor plan (only Rev A needed now)
├── arkirev/
│   ├── __init__.py
│   ├── models.py               # ChangeItem, RevisionAnalysis, Task, ScheduleResult
│   ├── budget.py               # load costs, per-trade impact
│   ├── schedule.py             # task expansion + CPM engine  ← new, the core
│   ├── compare.py              # OPTIONAL vision assist
│   ├── prompts.py              # system/user prompt templates
│   └── canvas.py               # Phase 2: markup -> structured changes
└── tests/
    ├── test_budget.py
    ├── test_schedule.py        # ← new, most important test file
    └── test_compare_parse.py
```

> **Rename note:** the v1 package was `revbrief/`. Rename to `arkirev/` and update imports and commit messages. A single find-and-replace of `revbrief` → `arkirev` covers it.

---

### Task 0: Prep assets  · *Owner: split — A owns the JSON, B owns the image*

**Files:** `data/samples/RevA.png` (**B**), `data/project_budget.json` (**A**), `data/task_templates.json` (**A**)

- [ ] **Step 1:** Pick one readable residential floor plan (Kaggle `samirshabani/architecture`, clear living/kitchen plans). Save as `data/samples/RevA.png`. **No Rev B needed anymore** — the revision is created in-app.

- [ ] **Step 2:** Create `data/project_budget.json` (adds per-trade + contingency vs v1):

```json
{
  "project_name": "Demo House — Phase 1",
  "currency": "PHP",
  "allotted_budget": 1000000,
  "actual_spent": 320000,
  "contingency_pct": 10,
  "manual_review_minutes_baseline": 30,
  "unit_costs": {
    "door_move": 12000,
    "new_opening": 35000,
    "layout_change": 25000,
    "dimension_or_note_change": 5000,
    "equipment_or_fixture_change": 18000,
    "unknown_change": 10000
  }
}
```

- [ ] **Step 3:** Create `data/task_templates.json`. Each category expands into tasks with `duration_days`, `trade`, and `after` (indices of predecessor tasks *within the same change*). This is the data that makes CPM real.

```json
{
  "new_opening": [
    {"name": "Structural review",   "trade": "structural",  "duration_days": 1,   "after": []},
    {"name": "Mark & protect area", "trade": "general",     "duration_days": 0.5, "after": [0]},
    {"name": "Cut opening",         "trade": "demolition",  "duration_days": 1,   "after": [1]},
    {"name": "Install lintel",      "trade": "structural",  "duration_days": 1,   "after": [2]},
    {"name": "Frame opening",       "trade": "carpentry",   "duration_days": 2,   "after": [3]}
  ],
  "door_move": [
    {"name": "Close old opening",   "trade": "masonry",     "duration_days": 1,   "after": []},
    {"name": "Cut new opening",     "trade": "demolition",  "duration_days": 1,   "after": [0]},
    {"name": "Frame & hang door",   "trade": "carpentry",   "duration_days": 1.5, "after": [1]}
  ],
  "layout_change": [
    {"name": "Re-layout walls",     "trade": "general",     "duration_days": 1,   "after": []},
    {"name": "Build/remove partition","trade": "masonry",   "duration_days": 2,   "after": [0]}
  ],
  "dimension_or_note_change": [
    {"name": "Update field drawings","trade": "architecture","duration_days": 0.25,"after": []}
  ],
  "equipment_or_fixture_change": [
    {"name": "Confirm spec & MEP rough-in","trade": "mep",  "duration_days": 1,   "after": []},
    {"name": "Install fixture",     "trade": "mep",         "duration_days": 1,   "after": [0]}
  ],
  "unknown_change": [
    {"name": "Investigate & scope", "trade": "general",     "duration_days": 0.5, "after": []}
  ]
}
```

- [ ] **Step 4:** Commit.
```bash
git add data/
git commit -m "chore: add Rev A sample, demo budget, and task templates"
```

---

### Task 1: Project skeleton  · *Owner: Person B (App/UX)*

**Files:** `requirements.txt`, `.env.example`, `.gitignore`, `arkirev/__init__.py`, `README.md`

> Do this first so both people have a package to import. Person A can start `models.py` the moment `arkirev/__init__.py` exists.

- [ ] **Step 1:** `requirements.txt` (adds canvas + plotly):
```text
streamlit>=1.32.0
streamlit-drawable-canvas>=0.9.3
plotly>=5.20.0
openai>=1.40.0
python-dotenv>=1.0.0
Pillow>=10.0.0
pydantic>=2.0.0
pytest>=8.0.0
```

> **Compatibility risk:** `streamlit-drawable-canvas` can lag behind the newest Streamlit. If it fails to install/render, pin Streamlit to a version the canvas supports (e.g. `streamlit~=1.32`) — do this *before* burning demo time. Phase 1 does not need the canvas, so this risk is isolated to Phase 2.

- [ ] **Step 2–4:** `.env.example` (`OPENAI_API_KEY`, `OPENAI_MODEL=gpt-4o`, optional `OPENAI_BASE_URL`), `.gitignore` (`.env`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `*.pyc`), and `README.md` with setup steps. Create the package: `mkdir -p arkirev tests data/samples && touch arkirev/__init__.py`.

- [ ] **Step 5:** Install + verify: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && pytest -q || true`.

- [ ] **Step 6:** Commit `chore: scaffold ArkiRev Python app`.

---

### Task 2: Result + schedule models  · *Owner: Person A (Engine) — ⚠ FROZEN CONTRACT, agree with B first*

**Files:** `arkirev/models.py`, `tests/test_compare_parse.py`

- [ ] **Step 1:** Write a failing test for the analysis shape (same as v1) plus a `Task` shape test.

- [ ] **Step 2:** Implement `models.py`:

```python
# arkirev/models.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal
from pydantic import BaseModel, Field

ChangeCategory = Literal[
    "door_move", "new_opening", "layout_change",
    "dimension_or_note_change", "equipment_or_fixture_change", "unknown_change",
]

class ChangeItem(BaseModel):
    summary: str
    category: ChangeCategory = "unknown_change"
    severity: Literal["low", "medium", "high"] = "medium"
    trade: str = "general"
    verify_before_build: bool = True
    # Phase 2: spatial location of the markup on the plan (px), optional
    bbox: list[float] | None = None

class RevisionAnalysis(BaseModel):
    changes: list[ChangeItem] = Field(default_factory=list)
    field_brief: str = ""
    risks: list[str] = Field(default_factory=list)

@dataclass
class Task:
    id: str
    name: str
    trade: str
    duration_days: float
    change_index: int
    predecessors: list[str] = field(default_factory=list)
    # CPM outputs (filled by schedule.compute_cpm):
    es: float = 0.0   # earliest start
    ef: float = 0.0   # earliest finish
    ls: float = 0.0   # latest start
    lf: float = 0.0   # latest finish
    slack: float = 0.0
    critical: bool = False

@dataclass
class ScheduleResult:
    tasks: list[Task]
    project_duration_days: float
    critical_path: list[str]   # ordered task ids with zero slack
```

- [ ] **Step 3:** Run tests → PASS. Commit `feat: add analysis + schedule models`.

---

### Task 3: CPM schedule engine (the core new capability)  · *Owner: Person A (Engine)*

**Files:** `arkirev/schedule.py`, `tests/test_schedule.py`

This is the differentiator. Build it test-first — CPM has deterministic, checkable outputs.

- [ ] **Step 1:** Write failing tests. Key cases: (a) a single change expands into its template tasks with correct within-change dependencies; (b) two independent changes run in parallel, so project duration = the longer chain, not the sum; (c) the critical path is exactly the zero-slack tasks; (d) a cyclic template raises.

```python
# tests/test_schedule.py
from pathlib import Path
from arkirev.models import ChangeItem, RevisionAnalysis
from arkirev.schedule import load_templates, build_tasks, compute_cpm

TEMPLATES = load_templates(Path("data/task_templates.json"))

def test_single_change_chain_duration():
    analysis = RevisionAnalysis(changes=[ChangeItem(summary="x", category="door_move")])
    tasks = build_tasks(analysis, TEMPLATES)
    result = compute_cpm(tasks)
    # door_move chain: 1 + 1 + 1.5 = 3.5 days, all critical
    assert result.project_duration_days == 3.5
    assert all(t.critical for t in result.tasks)

def test_parallel_changes_take_the_longer_chain():
    analysis = RevisionAnalysis(changes=[
        ChangeItem(summary="a", category="new_opening"),            # 1+0.5+1+1+2 = 5.5
        ChangeItem(summary="b", category="dimension_or_note_change") # 0.25
    ])
    result = compute_cpm(build_tasks(analysis, TEMPLATES))
    assert result.project_duration_days == 5.5
    # the note-change task has slack (not on critical path)
    note = [t for t in result.tasks if t.change_index == 1][0]
    assert note.slack > 0 and not note.critical
```

- [ ] **Step 2:** Run → FAIL (module missing).

- [ ] **Step 3:** Implement `schedule.py`:

```python
# arkirev/schedule.py
from __future__ import annotations
import json
from collections import deque
from pathlib import Path
from typing import Any
from arkirev.models import RevisionAnalysis, Task, ScheduleResult

def load_templates(path: Path) -> dict[str, list[dict[str, Any]]]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)

def build_tasks(analysis: RevisionAnalysis, templates: dict[str, list[dict]]) -> dict[str, Task]:
    """Expand each change into template tasks. IDs: '{change_index}:{task_index}'.
    Changes are independent (run in parallel); dependencies are within-change only."""
    tasks: dict[str, Task] = {}
    for ci, change in enumerate(analysis.changes):
        template = templates.get(change.category, templates["unknown_change"])
        for ti, t in enumerate(template):
            tid = f"{ci}:{ti}"
            preds = [f"{ci}:{a}" for a in t.get("after", [])]
            tasks[tid] = Task(
                id=tid, name=t["name"], trade=t["trade"],
                duration_days=float(t["duration_days"]),
                change_index=ci, predecessors=preds,
            )
    return tasks

def compute_cpm(tasks: dict[str, Task]) -> ScheduleResult:
    # Build successor map + indegree for topological sort
    succ: dict[str, list[str]] = {tid: [] for tid in tasks}
    indeg: dict[str, int] = {tid: 0 for tid in tasks}
    for t in tasks.values():
        for p in t.predecessors:
            succ[p].append(t.id)
            indeg[t.id] += 1

    q = deque(tid for tid, d in indeg.items() if d == 0)
    topo: list[str] = []
    while q:
        n = q.popleft()
        topo.append(n)
        for s in succ[n]:
            indeg[s] -= 1
            if indeg[s] == 0:
                q.append(s)
    if len(topo) != len(tasks):
        raise ValueError("Cycle detected in task graph")

    # Forward pass: earliest start/finish
    for tid in topo:
        t = tasks[tid]
        t.es = max((tasks[p].ef for p in t.predecessors), default=0.0)
        t.ef = t.es + t.duration_days
    project_end = max((t.ef for t in tasks.values()), default=0.0)

    # Backward pass: latest start/finish + slack
    for tid in reversed(topo):
        t = tasks[tid]
        t.lf = min((tasks[s].ls for s in succ[tid]), default=project_end)
        t.ls = t.lf - t.duration_days
        t.slack = round(t.ls - t.es, 6)
        t.critical = abs(t.slack) < 1e-9

    critical_path = [tid for tid in topo if tasks[tid].critical]
    return ScheduleResult(
        tasks=list(tasks.values()),
        project_duration_days=round(project_end, 6),
        critical_path=critical_path,
    )
```

- [ ] **Step 4:** Run → PASS. Commit `feat: add CPM schedule engine`.

> **Optional realism upgrade (Phase 2):** add cross-change dependencies (e.g. every `demolition` task waits on a single shared "Structural sign-off" milestone). This makes the critical path weave across changes and looks more like a real site sequence. Keep it behind a flag so Phase 1 tests stay simple.

---

### Task 4: Budget engine (per-trade planner)  · *Owner: Person A (Engine)*

**Files:** `arkirev/budget.py`, `tests/test_budget.py`

- [ ] **Step 1:** Tests: total at-risk sums unit costs (as v1); **new** — `by_trade` groups amounts by trade; `with_contingency` adds `contingency_pct`.

- [ ] **Step 2:** Implement `estimate_impact` extending v1 with:
  - `by_trade`: `{trade: total_amount}` aggregated from line items.
  - `contingency`: `round(budget_at_risk * contingency_pct / 100)`.
  - `projected_actual` now = `actual + budget_at_risk + contingency`.
  - keep `remaining_allotment`, `over_budget` as before.

- [ ] **Step 3:** Run → PASS. Commit `feat: add per-trade budget planner with contingency`.

---

### Task 5: Vision assist (now OPTIONAL)  · *Owner: Person A (Engine)*

**Files:** `arkirev/prompts.py`, `arkirev/compare.py`, `tests/test_compare_parse.py`

Unchanged in mechanics from v1 (system prompt returns strict JSON; `parse_model_json` strips fences; `compare_revisions` sends two images). **But its role changed:** it is a convenience button ("Suggest changes from an uploaded Rev B") that pre-fills the change list the user then edits. The demo does **not** depend on it. Keep the smoke test optional and behind `.env`.

- [ ] Implement `prompts.py` + `compare.py` (v1 code is fine), unit-test the parser, commit `feat: add optional vision change-suggestion assist`.

---

### Task 6: Streamlit UI — Phase 1 (structured entry + budget + Gantt)  · *Owner: Person B (App/UX)*

**Files:** `app.py`

Build the whole flow with a **structured change editor first** (no canvas), so the demo works end-to-end before the canvas risk is introduced. **Build against `arkirev/_stubs.py` until the integration checkpoint**, then swap the stub imports for the real `schedule` / `budget` modules.

- [ ] **Step 1:** Load Rev A, budget, and templates. Show the project card: name, allotted ₱, actual ₱, contingency %.

- [ ] **Step 2:** Change editor via `st.data_editor` (a table the user adds rows to): columns `summary`, `category` (selectbox of the 6 categories), `severity`, `trade`. This IS the human-in-the-loop editing you wanted — the reviewer can add/correct/delete changes before anything is computed.

- [ ] **Step 3:** On "Generate brief", build a `RevisionAnalysis` from the table, then:
  - `impact = estimate_impact(analysis, budget)`
  - `schedule = compute_cpm(build_tasks(analysis, templates))`

- [ ] **Step 4:** Metrics row: `AI/entry time`, `Budget at risk ₱`, `Contingency ₱`, `Days added` (= `schedule.project_duration_days`).

- [ ] **Step 5:** Budget panel: per-trade breakdown table + allotted/actual/remaining; red banner if `over_budget`.

- [ ] **Step 6:** **Critical-path Gantt** with Plotly. Build a dataframe from `schedule.tasks` using ES→EF as start/end (day offsets), color critical tasks red and non-critical grey:

```python
import plotly.express as px
import pandas as pd

rows = [{
    "Task": t.name, "Trade": t.trade,
    "Start": t.es, "Finish": t.ef,
    "Critical": "Critical path" if t.critical else "Has slack",
    "Change": f"Change {t.change_index + 1}",
} for t in schedule.tasks]
df = pd.DataFrame(rows)
# px.timeline needs datetimes; map day offsets onto a base date
base = pd.Timestamp("2026-01-01")
df["Start"] = base + pd.to_timedelta(df["Start"], unit="D")
df["Finish"] = base + pd.to_timedelta(df["Finish"], unit="D")
fig = px.timeline(df, x_start="Start", x_end="Finish", y="Task",
                  color="Critical", color_discrete_map={
                      "Critical path": "#d62728", "Has slack": "#9aa0a6"})
fig.update_yaxes(autorange="reversed")
st.plotly_chart(fig, use_container_width=True)
```

- [ ] **Step 7:** Field brief + risks (from vision assist if used, else a templated brief assembled from the change list). Commit `feat: Phase 1 UI — change editor, budget planner, CPM Gantt`.

---

### Task 7: Streamlit UI — Phase 2 (draw on the plan)  · *Owner: Person B (App/UX)*

**Files:** `arkirev/canvas.py`, `app.py`

- [ ] **Step 1:** Add `streamlit-drawable-canvas` over Rev A with `drawing_mode="rect"`, Rev A as `background_image`. Each rectangle the user draws becomes a candidate change.

- [ ] **Step 2:** For each drawn rectangle (read from `canvas_result.json_data["objects"]`), render a labeling row: category selectbox + severity + a short note. `canvas.py` converts `(rect + label)` → `ChangeItem(bbox=[left, top, width, height], ...)`.

- [ ] **Step 3:** Feed those `ChangeItem`s into the exact same budget + CPM path from Phase 1. Nothing downstream changes — the canvas is just a nicer front-end for producing the change list.

- [ ] **Step 4:** (Optional) "Auto-suggest" button: user uploads an edited Rev B, `compare_revisions` returns candidate changes, they land as pre-filled rows the user confirms/edits. Commit `feat: Phase 2 — draw revisions on the plan + vision auto-suggest`.

---

### Task 8: Demo script + hardening  · *Owner: Person B (lead), Person A supports*

**Files:** `README.md`, `docs/DEMO_SCRIPT.md`, `data/samples/mock_analysis.json`

- [ ] **Step 1:** Demo script (3 min): show project card (₱1M allotted, ₱320k actual) → draw 3 changes on the plan → click Generate → read field brief → point at **₱ at risk per trade** and the **red critical path + "adds N days"** → close: *"Unread revisions become rework; rework becomes cost and schedule overrun. ArkiRev quantifies both the moment the change is drawn — no BIM, no ERP."*

- [ ] **Step 2:** Fallback: a "Use mock changes" toggle that loads `mock_analysis.json` so the demo runs with zero API/canvas dependency. Keep a screenshot of a good run.

- [ ] **Step 3:** Rehearse end-to-end; freeze code. Commit `docs: demo script + mock fallback`.

---

## Revised schedule (two people in parallel)

| Block | Person A — Engine | Person B — App/UX |
|-------|-------------------|-------------------|
| 0:00–0:20 | **Handshake: freeze `models.py` contract together** | **Handshake** + start skeleton (Task 1) |
| 0:20–0:50 | Task 2 — write real `models.py` | Task 1 done; write `_stubs.py`; RevA.png asset |
| 0:50–1:45 | Task 3 — **CPM engine (tested)** | Task 6 — UI shell + budget panel against stubs |
| 1:45–2:15 | Task 4 — budget planner | Task 6 — **Gantt** against stub `ScheduleResult` |
| 2:15–2:45 | Task 5 — optional vision assist | Task 6 — field brief + metrics wiring |
| 2:45–3:15 | **Integration checkpoint — swap stubs for real engine, together** | **Integration checkpoint** |
| 3:15–4:45 | Support B; Phase-2 cross-change deps (optional realism upgrade) | Task 7 — draw-on-plan canvas |
| 4:45–5:30 | Test hardening; mock data | Task 8 — demo script + fallback + rehearsal |

Wall-clock ≈ **5.5h with two people** vs ~8–12h solo, because the engine and UI are built at the same time against the frozen contract. If time runs out after the integration checkpoint, Phase 1 is already a complete demo.

**Critical dependency:** the 0:00–0:20 handshake. It's the only true blocker — everything else runs in parallel. Don't skip it; a mid-build change to `models.py` is the one thing that forces both people to rework.

---

## Spec coverage check

| Requirement | Task |
|-------------|------|
| Submit Rev A, revise in-app | 0, 6, 7 |
| Draw revision on the plan | 7 (Phase 2) |
| Human edits the change list | 6 (data_editor), 7 |
| Budget planner (per-trade + contingency) | 4, 6 |
| **Critical path (real CPM + timeline)** | 3, 6 |
| Days-added metric | 3, 6 |
| No AutoCAD | 0, 7 (canvas, not CAD) |
| No live ERP | 4 (JSON only) |
| Vision optional, not load-bearing | 5 |

---

## Out of scope (do not build)

- AutoCAD/Revit plugins; full BIM clash detection
- Real ERP/accounting sync
- Auth / multi-tenant / multi-project DB
- Resource leveling, cost-loaded scheduling, calendars/holidays
- Learned (non-templated) task durations
