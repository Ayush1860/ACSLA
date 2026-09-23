"""Build docs/index.html: a self-contained Plotly version of the Power BI report.

Runs the cleaning pipeline, pre-aggregates every KPI for each combination of the
three report slicers (class x travel type x customer type, including "All"), and
writes one HTML file with plotly.js inlined. The page has the same four tabs as
the Power BI report and uses the measure definitions in docs/dax_measures.md.

Usage:
    python scripts/build_web_dashboard.py
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from plotly.offline import get_plotlyjs

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clean  # noqa: E402
import download_data  # noqa: E402
from clean import AGE_BANDS, DELAY_BUCKETS, DISTANCE_BANDS, SERVICE_COLUMNS, SERVICE_LABELS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "docs" / "index.html"

CLASSES = ["Business", "Eco Plus", "Economy"]
TRAVEL_TYPES = ["Business Travel", "Personal Travel"]
CUSTOMER_TYPES = ["Loyal Customer", "Disloyal Customer"]
SERVICE_NAMES = [SERVICE_LABELS[c][0] for c in SERVICE_COLUMNS]
ALL = "All"


def run_pipeline() -> pd.DataFrame:
    """Download (if needed) and clean the data, then return the wide cleaned table."""
    if not download_data.already_downloaded():
        download_data.RAW_DIR.mkdir(parents=True, exist_ok=True)
        if not (download_data.download_kaggle() or download_data.download_mirror()):
            sys.exit("Could not download the raw data - see scripts/download_data.py.")
    clean.main()
    return pd.read_csv(PROCESSED / "flights_clean.csv")


def ratio(num: float, den: float) -> float | None:
    """DAX DIVIDE(): blank instead of an error on a zero denominator."""
    return None if den == 0 else float(num) / float(den)


def sat_rate(df: pd.DataFrame) -> float | None:
    return ratio(df["is_satisfied"].sum(), len(df))


def pts(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else (a - b) * 100


def avg_rating(ratings: pd.DataFrame) -> float | None:
    """Avg Service Rating: mean of all applicable (non-zero) ratings in the selection."""
    values = ratings.to_numpy(dtype=float).ravel()
    values = values[values > 0]
    return None if values.size == 0 else float(values.mean())


def aggregate(df: pd.DataFrame, overall_rate: float) -> dict:
    """Every number the four pages need, for one slicer selection."""
    total = len(df)
    if total == 0:
        return {"empty": True}

    rate = sat_rate(df)
    delayed = df[df["dep_delay"] > 15]
    on_time_rate = sat_rate(df[df["dep_delay"] == 0])
    ratings = df[SERVICE_COLUMNS]

    # --- Page 1 --------------------------------------------------------------
    by_class = [sat_rate(df[df["class"] == c]) for c in CLASSES]
    travel_class = {
        c: [sat_rate(df[(df["travel_type"] == t) & (df["class"] == c)]) for t in TRAVEL_TYPES]
        for c in CLASSES
    }

    # --- Page 2 --------------------------------------------------------------
    loyal = sat_rate(df[df["customer_type"] == "Loyal Customer"])
    disloyal = sat_rate(df[df["customer_type"] == "Disloyal Customer"])
    age_matrix = [
        [sat_rate(df[(df["age_band"] == a) & (df["customer_type"] == ct)]) for ct in CUSTOMER_TYPES]
        for a in AGE_BANDS
    ]
    age_counts = [
        [int(((df["age_band"] == a) & (df["customer_type"] == ct)).sum()) for ct in CUSTOMER_TYPES]
        for a in AGE_BANDS
    ]
    gender = df["gender"].value_counts().reindex(["Female", "Male"], fill_value=0)
    by_distance = [sat_rate(df[df["distance_band"] == b]) for b in DISTANCE_BANDS]
    trip = df.assign(trip_segment=df["travel_type"] + " | " + df["class"] + " | " + df["distance_band"])
    trip_stats = trip.groupby("trip_segment").agg(
        passengers=("is_satisfied", "size"),
        satisfied=("is_satisfied", "sum"),
        avg_delay=("dep_delay", "mean"),
    )
    trip_stats["dissatisfied"] = trip_stats["passengers"] - trip_stats["satisfied"]
    trip_stats["rate"] = trip_stats["satisfied"] / trip_stats["passengers"]
    top_trips = trip_stats.sort_values("dissatisfied", ascending=False).head(10)

    # --- Page 3 --------------------------------------------------------------
    service_avg, service_sat, service_dis = [], [], []
    for col in SERVICE_COLUMNS:
        service_avg.append(avg_rating(df[[col]]))
        service_sat.append(avg_rating(df.loc[df["is_satisfied"] == 1, [col]]))
        service_dis.append(avg_rating(df.loc[df["is_satisfied"] == 0, [col]]))
    service_class = [
        [avg_rating(df.loc[df["class"] == c, [col]]) for c in CLASSES] for col in SERVICE_COLUMNS
    ]
    applicable = (ratings > 0).to_numpy().sum()
    avg_all = avg_rating(ratings)

    # --- Page 4 --------------------------------------------------------------
    by_bucket = [sat_rate(df[df["delay_bucket"] == b]) for b in DELAY_BUCKETS]
    bucket_counts = [int((df["delay_bucket"] == b).sum()) for b in DELAY_BUCKETS]

    return {
        "empty": False,
        "kpi": {
            "total": total,
            "satisfied": int(df["is_satisfied"].sum()),
            "rate": rate,
            "vs_overall_pts": pts(rate, overall_rate),
            "delayed_pct": ratio(len(delayed), total),
            "avg_delay": float(df["dep_delay"].mean()),
            "rate_on_time": on_time_rate,
            "rate_delayed_15": sat_rate(delayed),
            "rate_delayed_60": sat_rate(df[df["dep_delay"] > 60]),
            "delay_impact_pts": pts(on_time_rate, rate),
            "delay_penalty_pts": pts(on_time_rate, sat_rate(delayed)),
            # inputs for the what-if projection (computed in the browser)
            "rate_le_15": sat_rate(df[df["dep_delay"] <= 15]),
            "delayed_pax": len(delayed),
            "delayed_sat": int(delayed["is_satisfied"].sum()),
            "loyal_rate": loyal,
            "disloyal_rate": disloyal,
            "loyalty_gap_pts": pts(loyal, disloyal),
            "avg_service_rating": avg_all,
            "service_gap": None if avg_all is None else 5 - avg_all,
            "low_rating_pct": ratio(ratings.isin([1, 2]).to_numpy().sum(), applicable),
            "na_pct": ratio((ratings == 0).to_numpy().sum(), ratings.size),
        },
        "by_class": by_class,
        "travel_class": travel_class,
        "age_matrix": age_matrix,
        "age_counts": age_counts,
        "gender": [int(v) for v in gender.to_numpy()],
        "by_distance": by_distance,
        "top_trips": {
            "segment": top_trips.index.tolist(),
            "dissatisfied": top_trips["dissatisfied"].astype(int).tolist(),
            "rate": top_trips["rate"].round(4).tolist(),
        },
        "trips": {
            "segment": trip_stats.index.tolist(),
            "avg_delay": trip_stats["avg_delay"].round(2).tolist(),
            "rate": trip_stats["rate"].round(4).tolist(),
            "passengers": trip_stats["passengers"].astype(int).tolist(),
        },
        "service_avg": service_avg,
        "service_sat": service_sat,
        "service_dis": service_dis,
        "service_class": service_class,
        "by_bucket": by_bucket,
        "bucket_counts": bucket_counts,
    }


def round_floats(obj, digits: int = 6):
    if isinstance(obj, float):
        return None if np.isnan(obj) else round(obj, digits)
    if isinstance(obj, dict):
        return {k: round_floats(v, digits) for k, v in obj.items()}
    if isinstance(obj, list):
        return [round_floats(v, digits) for v in obj]
    return obj


def build_data(df: pd.DataFrame) -> dict:
    overall = sat_rate(df)
    selections = {}
    for c, t, ct in itertools.product([ALL, *CLASSES], [ALL, *TRAVEL_TYPES], [ALL, *CUSTOMER_TYPES]):
        sub = df
        if c != ALL:
            sub = sub[sub["class"] == c]
        if t != ALL:
            sub = sub[sub["travel_type"] == t]
        if ct != ALL:
            sub = sub[sub["customer_type"] == ct]
        selections[f"{c}|{t}|{ct}"] = aggregate(sub, overall)

    drivers = pd.read_csv(PROCESSED / "driver_importance.csv")
    uplift_path = PROCESSED / "service_uplift.csv"
    uplift = pd.read_csv(uplift_path) if uplift_path.exists() else None

    return round_floats({
        "dims": {
            "classes": CLASSES,
            "travel_types": TRAVEL_TYPES,
            "customer_types": CUSTOMER_TYPES,
            "age_bands": AGE_BANDS,
            "delay_buckets": DELAY_BUCKETS,
            "distance_bands": DISTANCE_BANDS,
            "services": SERVICE_NAMES,
        },
        "selections": selections,
        "drivers": {
            "label": drivers["label"].tolist(),
            "importance": drivers["importance"].clip(lower=0).tolist(),
            "is_service": drivers["feature"].isin(SERVICE_COLUMNS).tolist(),
        },
        "uplift": None if uplift is None else {
            "service": uplift["service"].tolist(),
            "uplift_pts": uplift["uplift_pts"].tolist(),
        },
    })


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Airline Satisfaction Dashboard</title>
<meta name="description" content="Interactive preview of the Airline Customer Satisfaction & Loyalty Power BI report (Python/Plotly build).">
<style>
:root {
  color-scheme: light;
  --page: #f7f7f5; --surface: #fcfcfb; --border: #e8e7e2;
  --text: #0b0b0b; --text-2: #52514e; --text-3: #7a7974; --grid: #e8e7e2;
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a;
  --seq-lo: #eaf2fc; --seq-hi: #1f5fae;
  --accent: #2a78d6;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page: #111110; --surface: #1a1a19; --border: #2e2e2c;
    --text: #ffffff; --text-2: #c3c2b7; --text-3: #95948c; --grid: #2e2e2c;
    --s1: #3987e5; --s2: #d95926; --s3: #199e70;
    --seq-lo: #1d2a3a; --seq-hi: #6aa7f0;
    --accent: #3987e5;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #111110; --surface: #1a1a19; --border: #2e2e2c;
  --text: #ffffff; --text-2: #c3c2b7; --text-3: #95948c; --grid: #2e2e2c;
  --s1: #3987e5; --s2: #d95926; --s3: #199e70;
  --seq-lo: #1d2a3a; --seq-hi: #6aa7f0;
  --accent: #3987e5;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--page); color: var(--text);
  font: 14px/1.45 "Segoe UI", system-ui, -apple-system, Roboto, sans-serif;
}
.wrap { max-width: 1320px; margin: 0 auto; padding: 20px 16px 40px; }
header h1 { font-size: 22px; margin: 0 0 2px; }
header p { margin: 0; color: var(--text-2); }
nav.tabs { display: flex; gap: 4px; margin: 18px 0 0; border-bottom: 1px solid var(--border); overflow-x: auto; }
nav.tabs button {
  appearance: none; border: 0; background: none; color: var(--text-2); cursor: pointer;
  padding: 10px 14px; font: inherit; font-weight: 600; white-space: nowrap;
  border-bottom: 3px solid transparent; margin-bottom: -1px;
}
nav.tabs button[aria-selected="true"] { color: var(--text); border-bottom-color: var(--accent); }
nav.tabs button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.filters { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; padding: 14px 0; }
.filters label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-2); }
.filters select {
  min-width: 170px; padding: 7px 10px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--surface); color: var(--text); font: inherit;
}
.filters .reset {
  padding: 7px 12px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface);
  color: var(--text-2); font: inherit; cursor: pointer;
}
.page { display: none; }
.page.active { display: block; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 12px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
.card .label { font-size: 12px; color: var(--text-2); }
.card .value { font-size: 28px; font-weight: 650; margin-top: 2px; font-variant-numeric: tabular-nums; }
.card .sub { font-size: 12px; color: var(--text-3); margin-top: 2px; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.panel { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 12px 12px 4px; min-width: 0; }
.panel h2 { font-size: 14px; margin: 2px 4px 0; }
.panel .note { font-size: 12px; color: var(--text-3); margin: 2px 4px 0; }
.chart { width: 100%; height: 360px; }
.chart.tall { height: 520px; }
.span-2 { grid-column: span 2; }
.whatif { display: flex; flex-direction: column; justify-content: center; gap: 6px; }
.whatif input { width: 100%; accent-color: var(--accent); }
.empty { padding: 40px; text-align: center; color: var(--text-2); }
footer { margin-top: 24px; font-size: 12px; color: var(--text-3); }
footer a { color: var(--accent); }
@media (max-width: 860px) {
  .grid { grid-template-columns: minmax(0, 1fr); }
  .span-2 { grid-column: auto; }
  .chart { height: 320px; }
  .filters select { min-width: 0; width: 100%; }
  .filters label { flex: 1 1 140px; }
}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Airline Customer Satisfaction &amp; Loyalty</h1>
    <p>__TOTAL__ passengers · Python/Plotly build of the Power BI report pages · Source: Kaggle Airline Passenger Satisfaction</p>
  </header>

  <nav class="tabs" role="tablist">
    <button role="tab" aria-selected="true" data-page="overview">Executive Overview</button>
    <button role="tab" aria-selected="false" data-page="segments">Customer Segments</button>
    <button role="tab" aria-selected="false" data-page="services">Service Drivers</button>
    <button role="tab" aria-selected="false" data-page="delay">Delay Impact</button>
  </nav>

  <div class="filters">
    <label>Class <select id="f-class"></select></label>
    <label>Travel type <select id="f-travel"></select></label>
    <label>Customer type <select id="f-customer"></select></label>
    <button class="reset" id="f-reset" type="button">Reset filters</button>
  </div>

  <div id="empty" class="empty" hidden>No passengers match this combination of filters.</div>

  <section class="page active" id="page-overview">
    <div class="cards">
      <div class="card"><div class="label">Total Passengers</div><div class="value" id="k-total"></div></div>
      <div class="card"><div class="label">Satisfaction %</div><div class="value" id="k-rate"></div><div class="sub" id="k-vs"></div></div>
      <div class="card"><div class="label">Delayed % (&gt;15 min)</div><div class="value" id="k-delayed"></div></div>
      <div class="card"><div class="label">Avg Dep Delay</div><div class="value" id="k-avgdelay"></div><div class="sub">minutes</div></div>
    </div>
    <div class="grid">
      <div class="panel"><h2>Satisfaction % by class</h2><div class="chart" id="c-class"></div></div>
      <div class="panel"><h2>Satisfaction % by travel type and class</h2><div class="chart" id="c-travel-class"></div></div>
    </div>
  </section>

  <section class="page" id="page-segments">
    <div class="cards">
      <div class="card"><div class="label">Loyal Satisfaction %</div><div class="value" id="k-loyal"></div></div>
      <div class="card"><div class="label">Disloyal Satisfaction %</div><div class="value" id="k-disloyal"></div></div>
      <div class="card"><div class="label">Loyalty Gap</div><div class="value" id="k-loyalgap"></div><div class="sub">loyal minus disloyal</div></div>
    </div>
    <div class="grid">
      <div class="panel"><h2>Satisfaction % — age band × customer type</h2><div class="chart" id="c-age"></div></div>
      <div class="panel"><h2>Passengers by gender</h2><div class="chart" id="c-gender"></div></div>
      <div class="panel"><h2>Satisfaction % by distance band</h2><div class="chart" id="c-distance"></div></div>
      <div class="panel"><h2>Dissatisfied passengers — top 10 trip segments</h2><div class="chart" id="c-trips"></div></div>
    </div>
  </section>

  <section class="page" id="page-services">
    <div class="cards">
      <div class="card"><div class="label">Avg Service Rating</div><div class="value" id="k-avgrating"></div><div class="sub">out of 5, N/A excluded</div></div>
      <div class="card"><div class="label">Service Gap</div><div class="value" id="k-servicegap"></div><div class="sub">5 − avg rating</div></div>
      <div class="card"><div class="label">Low Rating % (1–2)</div><div class="value" id="k-low"></div></div>
      <div class="card"><div class="label">Not Applicable %</div><div class="value" id="k-na"></div></div>
    </div>
    <div class="grid">
      <div class="panel"><h2>Key drivers of satisfaction</h2><p class="note">Permutation importance from the logistic regression (all passengers, not filtered) — stands in for Power BI's Key Influencers.</p><div class="chart tall" id="c-drivers"></div></div>
      <div class="panel"><h2>Service Gap ranking (5 − avg rating)</h2><div class="chart tall" id="c-gap"></div></div>
      <div class="panel"><h2>Avg rating by service and class</h2><div class="chart tall" id="c-heat"></div></div>
      <div class="panel"><h2>Avg rating: satisfied vs dissatisfied passengers</h2><div class="chart tall" id="c-ratinggap"></div></div>
    </div>
  </section>

  <section class="page" id="page-delay">
    <div class="cards">
      <div class="card"><div class="label">Delayed % (&gt;15 min)</div><div class="value" id="k-delayed2"></div></div>
      <div class="card"><div class="label">Delay Penalty &gt;15</div><div class="value" id="k-penalty"></div><div class="sub">on time vs &gt;15 min late</div></div>
      <div class="card"><div class="label">Delay Impact</div><div class="value" id="k-impact"></div><div class="sub">on time vs all passengers</div></div>
      <div class="card whatif">
        <div class="label">What-if: delays removed <strong id="w-val">50%</strong></div>
        <input type="range" id="w-slider" min="0" max="100" step="5" value="50" aria-label="Share of delays over 15 minutes removed">
      </div>
      <div class="card"><div class="label">Projected Satisfaction %</div><div class="value" id="k-proj"></div><div class="sub" id="k-gain"></div></div>
    </div>
    <div class="grid">
      <div class="panel"><h2>Satisfaction % by departure delay</h2><div class="chart" id="c-bucket"></div></div>
      <div class="panel"><h2>Avg delay vs satisfaction by trip segment</h2><p class="note">Bubble size = passengers.</p><div class="chart" id="c-scatter"></div></div>
    </div>
  </section>

  <footer>
    Measures follow <a href="https://github.com/Ayush1860/ACSLA/blob/main/docs/dax_measures.md">docs/dax_measures.md</a>.
    Built by <code>scripts/build_web_dashboard.py</code> ·
    <a href="https://github.com/Ayush1860/ACSLA">Source on GitHub</a>
  </footer>
</div>

<script>__PLOTLY__</script>
<script>
const DATA = __DATA__;
const D = DATA.dims;
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const C = {};
function readColors() {
  for (const k of ["text", "text-2", "text-3", "grid", "surface", "s1", "s2", "s3", "seq-lo", "seq-hi", "border"])
    C[k] = css("--" + k);
}

const fmtPct = (v) => v == null ? "–" : (v * 100).toFixed(1) + "%";
const fmtPts = (v) => v == null ? "–" : (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(1) + " pts";
const fmtInt = (v) => v == null ? "–" : v.toLocaleString("en-US");
const fmtNum = (v, d = 2) => v == null ? "–" : v.toFixed(d);
const set = (id, text) => { document.getElementById(id).textContent = text; };

function baseLayout(extra = {}) {
  return Object.assign({
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Segoe UI, system-ui, sans-serif", size: 12, color: C["text-2"] },
    margin: { l: 10, r: 24, t: 16, b: 40 },
    hoverlabel: { bgcolor: C.surface, bordercolor: C.border, font: { color: C.text } },
    xaxis: { gridcolor: C.grid, zeroline: false, automargin: true, linecolor: C.border },
    yaxis: { gridcolor: C.grid, zeroline: false, automargin: true, linecolor: C.border },
    legend: { orientation: "h", y: 1.08, x: 0 },
    bargap: 0.35,
  }, extra);
}
const CONFIG = { displayModeBar: false, responsive: true };
const pctAxis = (max = 1) => ({ tickformat: ".0%", range: [0, max], gridcolor: C.grid, zeroline: false, automargin: true });
const barText = (vals) => vals.map((v) => v == null ? "" : (v * 100).toFixed(1) + "%");

function draw(id, traces, layout) {
  Plotly.react(id, traces, baseLayout(layout), CONFIG);
}

// ---------- filters ----------
function fillSelect(id, values) {
  const el = document.getElementById(id);
  el.innerHTML = ["All", ...values].map((v) => `<option>${v}</option>`).join("");
  el.addEventListener("change", render);
}
fillSelect("f-class", D.classes);
fillSelect("f-travel", D.travel_types);
fillSelect("f-customer", D.customer_types);
document.getElementById("f-reset").addEventListener("click", () => {
  for (const id of ["f-class", "f-travel", "f-customer"]) document.getElementById(id).value = "All";
  render();
});
const current = () => DATA.selections[[
  document.getElementById("f-class").value,
  document.getElementById("f-travel").value,
  document.getElementById("f-customer").value,
].join("|")];

// ---------- tabs ----------
let activePage = "overview";
document.querySelectorAll("nav.tabs button").forEach((btn) => {
  btn.addEventListener("click", () => {
    activePage = btn.dataset.page;
    document.querySelectorAll("nav.tabs button").forEach((b) => b.setAttribute("aria-selected", b === btn));
    document.querySelectorAll(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + activePage));
    render();
  });
});

// ---------- pages ----------
function overview(s) {
  const k = s.kpi;
  set("k-total", fmtInt(k.total));
  set("k-rate", fmtPct(k.rate));
  set("k-vs", fmtPts(k.vs_overall_pts) + " vs all passengers");
  set("k-delayed", fmtPct(k.delayed_pct));
  set("k-avgdelay", fmtNum(k.avg_delay, 1));

  draw("c-class", [{
    type: "bar", orientation: "h", y: D.classes, x: s.by_class, marker: { color: C.s1 },
    text: barText(s.by_class), textposition: "outside", cliponaxis: false,
    hovertemplate: "%{y}: %{x:.1%}<extra></extra>",
  }], { xaxis: pctAxis(), yaxis: { autorange: "reversed", automargin: true }, showlegend: false });

  const colors = [C.s1, C.s2, C.s3];
  draw("c-travel-class", D.classes.map((c, i) => ({
    type: "bar", name: c, x: D.travel_types, y: s.travel_class[c], marker: { color: colors[i] },
    hovertemplate: c + " · %{x}: %{y:.1%}<extra></extra>",
  })), { yaxis: pctAxis(), barmode: "group", bargroupgap: 0.08 });
}

function segments(s) {
  const k = s.kpi;
  set("k-loyal", fmtPct(k.loyal_rate));
  set("k-disloyal", fmtPct(k.disloyal_rate));
  set("k-loyalgap", fmtPts(k.loyalty_gap_pts));

  draw("c-age", [{
    type: "heatmap", x: D.customer_types, y: D.age_bands, z: s.age_matrix, customdata: s.age_counts,
    zmin: 0, zmax: 1, colorscale: [[0, C["seq-lo"]], [1, C["seq-hi"]]], xgap: 3, ygap: 3,
    colorbar: { tickformat: ".0%", outlinewidth: 0, thickness: 10 },
    text: s.age_matrix.map((r) => r.map((v) => v == null ? "–" : (v * 100).toFixed(0) + "%")),
    texttemplate: "%{text}", textfont: { size: 13 },
    hovertemplate: "%{y} · %{x}<br>Satisfaction %{z:.1%}<br>%{customdata:,} passengers<extra></extra>",
  }], { yaxis: { autorange: "reversed", automargin: true }, xaxis: { automargin: true } });

  draw("c-gender", [{
    type: "pie", hole: 0.6, labels: ["Female", "Male"], values: s.gender, sort: false,
    marker: { colors: [C.s1, C.s2], line: { color: C.surface, width: 2 } },
    textinfo: "label+percent", hovertemplate: "%{label}: %{value:,} passengers<extra></extra>",
  }], { showlegend: false });

  draw("c-distance", [{
    type: "bar", orientation: "h", y: D.distance_bands, x: s.by_distance, marker: { color: C.s1 },
    text: barText(s.by_distance), textposition: "outside", cliponaxis: false,
    hovertemplate: "%{y}: %{x:.1%}<extra></extra>",
  }], { xaxis: pctAxis(), yaxis: { autorange: "reversed", automargin: true }, showlegend: false });

  const t = s.top_trips;
  draw("c-trips", [{
    type: "bar", orientation: "h", y: t.segment, x: t.dissatisfied, customdata: t.rate,
    marker: { color: C.s2 }, text: t.dissatisfied.map(fmtInt), textposition: "outside", cliponaxis: false,
    hovertemplate: "%{y}<br>%{x:,} dissatisfied · satisfaction %{customdata:.1%}<extra></extra>",
  }], { yaxis: { autorange: "reversed", automargin: true, tickfont: { size: 11 } },
        xaxis: { gridcolor: C.grid, zeroline: false }, showlegend: false,
        margin: { l: 10, r: 56, t: 16, b: 40 } });
}

function sortedBy(labels, values, desc = true) {
  const idx = labels.map((_, i) => i).filter((i) => values[i] != null);
  idx.sort((a, b) => desc ? values[b] - values[a] : values[a] - values[b]);
  return idx;
}

function services(s) {
  const k = s.kpi;
  set("k-avgrating", fmtNum(k.avg_service_rating));
  set("k-servicegap", fmtNum(k.service_gap));
  set("k-low", fmtPct(k.low_rating_pct));
  set("k-na", fmtPct(k.na_pct));

  const dr = DATA.drivers;
  draw("c-drivers", [{
    type: "bar", orientation: "h", y: dr.label, x: dr.importance,
    marker: { color: dr.is_service.map((v) => v ? C.s1 : C.s2) },
    hovertemplate: "%{y}: AUC drop %{x:.3f}<extra></extra>",
  }], { yaxis: { autorange: "reversed", automargin: true }, xaxis: { gridcolor: C.grid, zeroline: false, title: { text: "Drop in ROC AUC", font: { size: 11 } } },
        showlegend: false, margin: { l: 10, r: 24, t: 30, b: 48 },
        annotations: [{ xref: "paper", yref: "paper", x: 0, y: 1.01, xanchor: "left", yanchor: "bottom", showarrow: false,
                        text: `<span style="color:${C.s1}">■</span> service rating   <span style="color:${C.s2}">■</span> trip / customer`,
                        font: { size: 11, color: C["text-2"] } }] });

  const gaps = s.service_avg.map((v) => v == null ? null : 5 - v);
  const gi = sortedBy(D.services, gaps);
  draw("c-gap", [{
    type: "bar", orientation: "h", y: gi.map((i) => D.services[i]), x: gi.map((i) => gaps[i]),
    marker: { color: C.s2 }, text: gi.map((i) => gaps[i].toFixed(2)), textposition: "outside", cliponaxis: false,
    customdata: gi.map((i) => s.service_avg[i]),
    hovertemplate: "%{y}<br>Gap %{x:.2f} · avg rating %{customdata:.2f}<extra></extra>",
  }], { yaxis: { autorange: "reversed", automargin: true }, xaxis: { range: [0, 4], gridcolor: C.grid, zeroline: false }, showlegend: false });

  draw("c-heat", [{
    type: "heatmap", x: D.classes, y: D.services, z: s.service_class, zmin: 1, zmax: 5,
    colorscale: [[0, C["seq-lo"]], [1, C["seq-hi"]]], xgap: 3, ygap: 3,
    colorbar: { outlinewidth: 0, thickness: 10 },
    text: s.service_class.map((r) => r.map((v) => v == null ? "–" : v.toFixed(2))), texttemplate: "%{text}",
    hovertemplate: "%{y} · %{x}: %{z:.2f}<extra></extra>",
  }], { yaxis: { autorange: "reversed", automargin: true } });

  const diff = s.service_sat.map((v, i) => v == null || s.service_dis[i] == null ? null : v - s.service_dis[i]);
  const ri = sortedBy(D.services, diff);
  const ys = ri.map((i) => D.services[i]);
  draw("c-ratinggap", [
    { type: "scatter", mode: "lines", x: ri.flatMap((i) => [s.service_dis[i], s.service_sat[i], null]),
      y: ys.flatMap((y) => [y, y, null]), line: { color: C.grid, width: 3 }, hoverinfo: "skip", showlegend: false },
    { type: "scatter", mode: "markers", name: "Neutral / dissatisfied", x: ri.map((i) => s.service_dis[i]), y: ys,
      marker: { color: C.s2, size: 10 }, hovertemplate: "%{y}: %{x:.2f}<extra>Dissatisfied</extra>" },
    { type: "scatter", mode: "markers", name: "Satisfied", x: ri.map((i) => s.service_sat[i]), y: ys,
      marker: { color: C.s1, size: 10 }, hovertemplate: "%{y}: %{x:.2f}<extra>Satisfied</extra>" },
  ], { yaxis: { autorange: "reversed", automargin: true }, xaxis: { range: [1, 5], gridcolor: C.grid, zeroline: false } });
}

function projected(k, pct) {
  // Projected Satisfaction % (see docs/dax_measures.md)
  const r = pct / 100;
  const recovered = r * (k.delayed_pax * (k.rate_le_15 ?? 0) - k.delayed_sat);
  return (k.satisfied + recovered) / k.total;
}

function delay(s) {
  const k = s.kpi;
  set("k-delayed2", fmtPct(k.delayed_pct));
  set("k-penalty", fmtPts(k.delay_penalty_pts));
  set("k-impact", fmtPts(k.delay_impact_pts));
  updateWhatIf();

  draw("c-bucket", [{
    type: "bar", x: D.delay_buckets, y: s.by_bucket, customdata: s.bucket_counts, marker: { color: C.s1 },
    text: barText(s.by_bucket), textposition: "outside", cliponaxis: false,
    hovertemplate: "%{x}: %{y:.1%}<br>%{customdata:,} passengers<extra></extra>",
  }], { yaxis: pctAxis(Math.min(1, Math.max(...s.by_bucket.map((v) => v ?? 0)) * 1.2 + 0.02)), showlegend: false });

  const t = s.trips;
  const maxPax = Math.max(...t.passengers);
  draw("c-scatter", [{
    type: "scatter", mode: "markers", x: t.avg_delay, y: t.rate, text: t.segment, customdata: t.passengers,
    marker: { color: C.s1, opacity: 0.75, line: { color: C.surface, width: 2 },
              size: t.passengers, sizemode: "area", sizeref: (2 * maxPax) / (46 ** 2), sizemin: 5 },
    hovertemplate: "%{text}<br>Avg delay %{x:.1f} min · satisfaction %{y:.1%}<br>%{customdata:,} passengers<extra></extra>",
  }], { yaxis: pctAxis(), xaxis: { gridcolor: C.grid, zeroline: false, title: { text: "Avg departure delay (min)", font: { size: 11 } } }, showlegend: false });
}

function updateWhatIf() {
  const s = current();
  if (!s || s.empty) return;
  const pct = +document.getElementById("w-slider").value;
  set("w-val", pct + "%");
  const p = projected(s.kpi, pct);
  set("k-proj", fmtPct(p));
  set("k-gain", fmtPts((p - s.kpi.rate) * 100) + " vs today");
}
document.getElementById("w-slider").addEventListener("input", updateWhatIf);

const PAGES = { overview, segments, services, delay };
function render() {
  readColors();
  const s = current();
  const empty = !s || s.empty;
  document.getElementById("empty").hidden = !empty;
  document.querySelectorAll(".page").forEach((p) => {
    p.style.visibility = empty ? "hidden" : "";
  });
  if (empty) return;
  PAGES[activePage](s);
}
render();
if (window.matchMedia) {
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", render);
}
</script>
</body>
</html>
"""


def main() -> None:
    df = run_pipeline()
    data = build_data(df)
    html = (
        PAGE.replace("__PLOTLY__", get_plotlyjs())
        .replace("__DATA__", json.dumps(data, separators=(",", ":")))
        .replace("__TOTAL__", f"{len(df):,}")
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    all_kpi = data["selections"]["All|All|All"]["kpi"]
    print(f"Wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e6:.1f} MB, "
          f"{len(data['selections'])} filter combinations)")
    print(f"  Satisfaction % {all_kpi['rate']:.1%} | Delayed % {all_kpi['delayed_pct']:.1%} | "
          f"Avg Service Rating {all_kpi['avg_service_rating']:.2f}")


if __name__ == "__main__":
    main()
