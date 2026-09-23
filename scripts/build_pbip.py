"""Generate the Power BI Project (powerbi/AirlineAnalytics.pbip).

Writes a PBIP folder that Power BI Desktop opens directly:
    powerbi/AirlineAnalytics.pbip
    powerbi/AirlineAnalytics.SemanticModel/   TMDL: tables, Power Query, relationships, DAX measures
    powerbi/AirlineAnalytics.Report/          4 report pages with starter visuals

The semantic model is the single source of truth for measures (docs/dax_measures.md
mirrors it). IDs are deterministic (uuid5) so re-running produces a clean git diff.

Usage:
    python scripts/build_pbip.py
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PBI_DIR = ROOT / "powerbi"
NAME = "AirlineAnalytics"
MODEL_DIR = PBI_DIR / f"{NAME}.SemanticModel"
REPORT_DIR = PBI_DIR / f"{NAME}.Report"

# Default folder the Power Query parameter points at. Change it in Power BI via
# Transform data > Edit parameters > DataFolder (keep the trailing backslash).
DEFAULT_DATA_FOLDER = "C:\\ACSLA\\data\\processed\\"

NS = uuid.UUID("6f1c2f1e-3d7b-4a58-9a52-5b1f0d6f2a10")


def tag(*parts: str) -> str:
    return str(uuid.uuid5(NS, "/".join(parts)))


def q(name: str) -> str:
    """Quote a TMDL object name when needed."""
    if name.replace("_", "").isalnum() and not name[0].isdigit():
        return name
    return "'" + name.replace("'", "''") + "'"


# --------------------------------------------------------------------------------------
# Semantic model definition
# --------------------------------------------------------------------------------------

# column: (name, dataType, options)
TABLES: dict[str, dict] = {
    "Fact_Flights": {
        "file": "fact_flights.csv",
        "columns": [
            ("passenger_id", "int64", {"hidden": True, "summarize": "none"}),
            ("customer_id", "int64", {"hidden": True, "summarize": "none"}),
            ("travel_id", "int64", {"hidden": True, "summarize": "none"}),
            ("age", "int64", {"summarize": "none"}),
            ("flight_distance", "int64", {"summarize": "none", "format": "#,0"}),
            ("dep_delay", "int64", {"summarize": "none", "format": "#,0"}),
            ("arr_delay", "int64", {"summarize": "none", "format": "#,0"}),
            ("delay_bucket", "string", {"sort_by": "delay_bucket_order"}),
            ("delay_bucket_order", "int64", {"hidden": True, "summarize": "none"}),
            ("is_delayed_15", "int64", {"summarize": "sum"}),
            ("avg_service_rating", "double", {"summarize": "none", "format": "0.00"}),
            ("services_not_applicable", "int64", {"summarize": "none"}),
            ("is_satisfied", "int64", {"summarize": "sum"}),
            ("satisfaction", "string", {}),
            ("source_split", "string", {"hidden": True}),
        ],
    },
    "Dim_Customer": {
        "file": "dim_customer.csv",
        "columns": [
            ("customer_id", "int64", {"hidden": True, "summarize": "none"}),
            ("gender", "string", {}),
            ("customer_type", "string", {}),
            ("age_band", "string", {"sort_by": "age_band_order"}),
            ("age_band_order", "int64", {"hidden": True, "summarize": "none"}),
            ("customer_segment", "string", {}),
        ],
    },
    "Dim_Travel": {
        "file": "dim_travel.csv",
        "columns": [
            ("travel_id", "int64", {"hidden": True, "summarize": "none"}),
            ("travel_type", "string", {}),
            ("class", "string", {"sort_by": "class_order"}),
            ("distance_band", "string", {"sort_by": "distance_band_order"}),
            ("class_order", "int64", {"hidden": True, "summarize": "none"}),
            ("distance_band_order", "int64", {"hidden": True, "summarize": "none"}),
            ("trip_segment", "string", {}),
        ],
    },
    "Dim_Service": {
        "file": "dim_service.csv",
        "columns": [
            ("service_id", "int64", {"hidden": True, "summarize": "none"}),
            ("service_key", "string", {"hidden": True}),
            ("service_name", "string", {}),
            ("journey_stage", "string", {}),
        ],
    },
    "Fact_Service_Ratings": {
        "file": "fact_service_ratings.csv",
        "columns": [
            ("passenger_id", "int64", {"hidden": True, "summarize": "none"}),
            ("service_id", "int64", {"hidden": True, "summarize": "none"}),
            ("rating", "int64", {"summarize": "none"}),
        ],
    },
}

# (from many-side column, to one-side column)
RELATIONSHIPS = [
    ("Fact_Flights.customer_id", "Dim_Customer.customer_id"),
    ("Fact_Flights.travel_id", "Dim_Travel.travel_id"),
    ("Fact_Service_Ratings.passenger_id", "Fact_Flights.passenger_id"),
    ("Fact_Service_Ratings.service_id", "Dim_Service.service_id"),
]

PCT = "0.0%"
PTS = '+0.0" pts";-0.0" pts";0.0" pts"'

# table -> list of (name, expression, formatString, displayFolder, description)
MEASURES: dict[str, list[tuple[str, str, str, str, str]]] = {
    "Fact_Flights": [
        ("Total Passengers", "COUNTROWS(Fact_Flights)", "#,0", "1 Core",
         "Number of passengers (one row per passenger in Fact_Flights)."),
        ("Satisfied Passengers", "CALCULATE([Total Passengers], Fact_Flights[is_satisfied] = 1)",
         "#,0", "1 Core", "Passengers who rated the airline 'satisfied'."),
        ("Dissatisfied Passengers", "[Total Passengers] - [Satisfied Passengers]", "#,0", "1 Core",
         "Passengers who were neutral or dissatisfied."),
        ("Satisfaction %", "DIVIDE([Satisfied Passengers], [Total Passengers])", PCT, "1 Core",
         "Share of passengers who are satisfied."),
        ("Satisfaction vs Overall pts",
         "([Satisfaction %] - CALCULATE([Satisfaction %], REMOVEFILTERS())) * 100", PTS, "1 Core",
         "Percentage-point difference between the current selection and all passengers."),
        ("Avg Dep Delay", "AVERAGE(Fact_Flights[dep_delay])", "0.0", "2 Delay",
         "Average departure delay in minutes."),
        ("Delayed %",
         "DIVIDE(\n    CALCULATE([Total Passengers], Fact_Flights[dep_delay] > 15),\n    [Total Passengers]\n)",
         PCT, "2 Delay", "Share of passengers whose departure was more than 15 minutes late."),
        ("Satisfaction % (On Time)", "CALCULATE([Satisfaction %], Fact_Flights[dep_delay] = 0)", PCT,
         "2 Delay", "Satisfaction % for flights that departed on time (0 min delay)."),
        ("Satisfaction % (Delayed >15)", "CALCULATE([Satisfaction %], Fact_Flights[dep_delay] > 15)",
         PCT, "2 Delay", "Satisfaction % for departures more than 15 minutes late."),
        ("Satisfaction % (Delayed >60)", "CALCULATE([Satisfaction %], Fact_Flights[dep_delay] > 60)",
         PCT, "2 Delay", "Satisfaction % for departures more than 60 minutes late."),
        ("Delay Impact pts", "([Satisfaction % (On Time)] - [Satisfaction %]) * 100", PTS, "2 Delay",
         "Points of satisfaction lost versus an all-on-time baseline."),
        ("Delay Penalty >15 pts",
         "([Satisfaction % (On Time)] - [Satisfaction % (Delayed >15)]) * 100", PTS, "2 Delay",
         "Satisfaction gap between on-time and >15 min delayed passengers."),
        ("Projected Satisfaction %",
         "VAR r = [Delay Reduction Value] / 100\n"
         "VAR OnTimeRate = CALCULATE([Satisfaction %], Fact_Flights[dep_delay] <= 15)\n"
         "VAR DelayedPax = CALCULATE([Total Passengers], Fact_Flights[dep_delay] > 15)\n"
         "VAR DelayedSat = CALCULATE([Satisfied Passengers], Fact_Flights[dep_delay] > 15)\n"
         "-- a share r of delayed passengers becomes on time and behaves like on-time passengers\n"
         "VAR Recovered = r * (DelayedPax * OnTimeRate - DelayedSat)\n"
         "RETURN\n"
         "    DIVIDE([Satisfied Passengers] + Recovered, [Total Passengers])",
         PCT, "3 What-if", "Satisfaction % if the selected share of >15 min delays were eliminated."),
        ("Projected Gain pts", "([Projected Satisfaction %] - [Satisfaction %]) * 100", PTS,
         "3 What-if", "Satisfaction points gained under the what-if delay reduction."),
        ("Loyal Satisfaction %",
         'CALCULATE([Satisfaction %], Dim_Customer[customer_type] = "Loyal Customer")', PCT,
         "4 Loyalty", "Satisfaction % of loyal customers."),
        ("Disloyal Satisfaction %",
         'CALCULATE([Satisfaction %], Dim_Customer[customer_type] = "Disloyal Customer")', PCT,
         "4 Loyalty", "Satisfaction % of disloyal customers."),
        ("Loyalty Gap pts", "([Loyal Satisfaction %] - [Disloyal Satisfaction %]) * 100", PTS,
         "4 Loyalty", "Satisfaction gap between loyal and disloyal customers."),
    ],
    "Fact_Service_Ratings": [
        ("Avg Service Rating",
         "CALCULATE(AVERAGE(Fact_Service_Ratings[rating]), Fact_Service_Ratings[rating] > 0)",
         "0.00", "5 Service", "Average 1-5 rating; 0 ('not applicable') is excluded."),
        ("Service Gap", "5 - [Avg Service Rating]", "0.00", "5 Service",
         "Distance from a perfect 5 - larger = more room to improve."),
        ("Avg Rating (Satisfied)", "CALCULATE([Avg Service Rating], Fact_Flights[is_satisfied] = 1)",
         "0.00", "5 Service", "Average rating given by satisfied passengers."),
        ("Avg Rating (Dissatisfied)",
         "CALCULATE([Avg Service Rating], Fact_Flights[is_satisfied] = 0)", "0.00", "5 Service",
         "Average rating given by neutral or dissatisfied passengers."),
        ("Rating Gap (Sat vs Dissat)", "[Avg Rating (Satisfied)] - [Avg Rating (Dissatisfied)]",
         "0.00", "5 Service",
         "How much better satisfied passengers rate a service - a proxy for its influence."),
        ("Low Rating %",
         "DIVIDE(\n"
         "    CALCULATE(COUNTROWS(Fact_Service_Ratings), Fact_Service_Ratings[rating] IN {1, 2}),\n"
         "    CALCULATE(COUNTROWS(Fact_Service_Ratings), Fact_Service_Ratings[rating] > 0)\n)",
         PCT, "5 Service", "Share of applicable ratings that are 1 or 2."),
        ("Not Applicable %",
         "DIVIDE(\n"
         "    CALCULATE(COUNTROWS(Fact_Service_Ratings), Fact_Service_Ratings[rating] = 0),\n"
         "    COUNTROWS(Fact_Service_Ratings)\n)",
         PCT, "5 Service", "Share of ratings recorded as 0 (service not applicable)."),
    ],
    "Delay Reduction": [
        ("Delay Reduction Value", "SELECTEDVALUE('Delay Reduction'[Delay Reduction %], 0)", "0",
         "3 What-if", "What-if parameter: % of >15 min delays eliminated (0-100)."),
    ],
}


def indent(text: str, level: int) -> str:
    pad = "\t" * level
    return "\n".join(pad + line for line in text.splitlines())


def measure_tmdl(table: str, m: tuple[str, str, str, str, str]) -> str:
    name, expr, fmt, folder, desc = m
    lines = [f"\t/// {desc}"]
    if "\n" in expr:
        lines.append(f"\tmeasure {q(name)} =")
        lines.append(indent(expr, 3))
    else:
        lines.append(f"\tmeasure {q(name)} = {expr}")
    lines.append(f"\t\tformatString: {fmt}")
    lines.append(f"\t\tdisplayFolder: {folder}")
    lines.append(f"\t\tlineageTag: {tag(table, 'measure', name)}")
    return "\n".join(lines)


def column_tmdl(table: str, name: str, dtype: str, opts: dict) -> str:
    lines = [f"\tcolumn {q(name)}", f"\t\tdataType: {dtype}"]
    if "format" in opts:
        lines.append(f"\t\tformatString: {opts['format']}")
    elif dtype == "int64":
        lines.append("\t\tformatString: 0")
    if opts.get("hidden"):
        lines.append("\t\tisHidden")
    lines.append(f"\t\tlineageTag: {tag(table, 'column', name)}")
    lines.append(f"\t\tsummarizeBy: {opts.get('summarize', 'none')}")
    lines.append(f"\t\tsourceColumn: {name}")
    if "sort_by" in opts:
        lines.append(f"\t\tsortByColumn: {q(opts['sort_by'])}")
    lines.append("")
    lines.append("\t\tannotation SummarizationSetBy = Automatic")
    return "\n".join(lines)


M_TYPES = {"int64": "Int64.Type", "string": "type text", "double": "type number"}


def partition_tmdl(table: str, spec: dict) -> str:
    types = ", ".join(f'{{"{c}", {M_TYPES[t]}}}' for c, t, _ in spec["columns"])
    m = (
        "let\n"
        f'    Source = Csv.Document(File.Contents(DataFolder & "{spec["file"]}"), '
        "[Delimiter = \",\", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),\n"
        "    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),\n"
        f'    Typed = Table.TransformColumnTypes(Promoted, {{{types}}}, "en-US")\n'
        "in\n"
        "    Typed"
    )
    return f"\tpartition {q(table)} = m\n\t\tmode: import\n\t\tsource =\n{indent(m, 3)}"


def table_tmdl(table: str, spec: dict) -> str:
    parts = [f"table {q(table)}", f"\tlineageTag: {tag(table)}", ""]
    for m in MEASURES.get(table, []):
        parts += [measure_tmdl(table, m), ""]
    for c, t, o in spec["columns"]:
        parts += [column_tmdl(table, c, t, o), ""]
    parts += [partition_tmdl(table, spec), "", "\tannotation PBI_ResultType = Table", ""]
    return "\n".join(parts)


def whatif_table_tmdl() -> str:
    table = "Delay Reduction"
    parts = [f"table {q(table)}", f"\tlineageTag: {tag(table)}", ""]
    for m in MEASURES[table]:
        parts += [measure_tmdl(table, m), ""]
    parts += [
        "\tcolumn 'Delay Reduction %'",
        "\t\tdataType: int64",
        "\t\tformatString: 0",
        f"\t\tlineageTag: {tag(table, 'column', 'Delay Reduction %')}",
        "\t\tsummarizeBy: none",
        "\t\tisNameInferred",
        "\t\tsourceColumn: [Delay Reduction %]",
        "",
        "\t\tannotation SummarizationSetBy = User",
        "",
        f"\tpartition {q(table)} = calculated",
        "\t\tmode: import",
        '\t\tsource = SELECTCOLUMNS(GENERATESERIES(0, 100, 5), "Delay Reduction %", [Value])',
        "",
    ]
    return "\n".join(parts)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, obj: dict) -> None:
    write(path, json.dumps(obj, indent=2) + "\n")


def build_semantic_model() -> None:
    d = MODEL_DIR / "definition"
    write_json(MODEL_DIR / "definition.pbism", {"version": "4.0", "settings": {}})
    write(d / "database.tmdl", "database\n\tcompatibilityLevel: 1567\n")
    query_order = json.dumps(["DataFolder", *TABLES.keys()])
    write(
        d / "model.tmdl",
        "model Model\n"
        "\tculture: en-US\n"
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
        "\tsourceQueryCulture: en-US\n"
        "\tdataAccessOptions\n"
        "\t\tlegacyRedirects\n"
        "\t\treturnErrorValuesAsNull\n\n"
        f"annotation PBI_QueryOrder = {query_order}\n\n"
        "annotation __PBI_TimeIntelligenceEnabled = 0\n",
    )
    write(
        d / "expressions.tmdl",
        f'expression DataFolder = "{DEFAULT_DATA_FOLDER}" '
        'meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n'
        f"\tlineageTag: {tag('DataFolder')}\n\n"
        "\tannotation PBI_ResultType = Text\n\n"
        "\tannotation PBI_NavigationStepName = Navigation\n",
    )
    for table, spec in TABLES.items():
        write(d / "tables" / f"{table}.tmdl", table_tmdl(table, spec))
    write(d / "tables" / "Delay Reduction.tmdl", whatif_table_tmdl())

    rels = []
    for frm, to in RELATIONSHIPS:
        ft, fc = frm.split(".")
        tt, tc = to.split(".")
        rels.append(
            f"relationship {tag('rel', frm, to)}\n"
            f"\tfromColumn: {q(ft)}.{q(fc)}\n"
            f"\ttoColumn: {q(tt)}.{q(tc)}\n"
        )
    write(d / "relationships.tmdl", "\n".join(rels))


# --------------------------------------------------------------------------------------
# Report (PBIR-Legacy report.json with starter visuals)
# --------------------------------------------------------------------------------------

MEASURE_HOME = {name: table for table, ms in MEASURES.items() for name, *_ in ms}


def _field(ref: str) -> tuple[str, str, bool]:
    """'Table.Field' or '[Measure]' -> (table, property, is_measure)."""
    if ref.startswith("["):
        name = ref[1:-1]
        return MEASURE_HOME[name], name, True
    table, prop = ref.split(".", 1)
    return table, prop, False


class Visual:
    def __init__(self, vtype: str, x: int, y: int, w: int, h: int, title: str | None = None,
                 roles: dict[str, list[str]] | None = None, sort_desc: str | None = None,
                 objects: dict | None = None):
        self.vtype, self.x, self.y, self.w, self.h = vtype, x, y, w, h
        self.title, self.roles, self.sort_desc = title, roles or {}, sort_desc
        self.objects = objects or {}

    def container(self, page: str, idx: int) -> dict:
        name = tag("visual", page, str(idx)).replace("-", "")[:20]
        single: dict = {"visualType": self.vtype, "drillFilterOtherVisuals": True}

        if self.roles:
            sources: dict[str, str] = {}
            select, projections = [], {}
            for role, refs in self.roles.items():
                projections[role] = []
                for ref in refs:
                    table, prop, is_measure = _field(ref)
                    alias = sources.setdefault(table, f"t{len(sources)}")
                    key = f"{table}.{prop}"
                    kind = "Measure" if is_measure else "Column"
                    if key not in {s["Name"] for s in select}:
                        select.append({
                            kind: {"Expression": {"SourceRef": {"Source": alias}}, "Property": prop},
                            "Name": key,
                            "NativeReferenceName": prop,
                        })
                    projections[role].append({"queryRef": key})
            query = {
                "Version": 2,
                "From": [{"Name": a, "Entity": t, "Type": 0} for t, a in sources.items()],
                "Select": select,
            }
            if self.sort_desc:
                table, prop, is_measure = _field(self.sort_desc)
                kind = "Measure" if is_measure else "Column"
                query["OrderBy"] = [{
                    "Direction": 2,
                    "Expression": {kind: {"Expression": {"SourceRef": {"Source": sources[table]}},
                                          "Property": prop}},
                }]
            single["projections"] = projections
            single["prototypeQuery"] = query

        if self.objects:
            single["objects"] = self.objects
        if self.title:
            single["vcObjects"] = {"title": [{"properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "text": {"expr": {"Literal": {"Value": f"'{self.title}'"}}},
            }}]}

        config = {
            "name": name,
            "layouts": [{"id": 0, "position": {"x": self.x, "y": self.y, "z": idx * 1000,
                                                "width": self.w, "height": self.h}}],
            "singleVisual": single,
        }
        return {"x": self.x, "y": self.y, "z": idx * 1000, "width": self.w, "height": self.h,
                "config": json.dumps(config), "filters": "[]"}


def textbox(text: str, x: int, y: int, w: int, h: int, size: str = "20pt", bold: bool = True) -> Visual:
    style = {"fontSize": size}
    if bold:
        style["fontWeight"] = "bold"
    return Visual("textbox", x, y, w, h, objects={"general": [{"properties": {
        "paragraphs": [{"textRuns": [{"value": text, "textStyle": style}]}]}}]})


def slicer(field: str, x: int, y: int, w: int, h: int = 56, title: str | None = None) -> Visual:
    return Visual("slicer", x, y, w, h, title=title, roles={"Values": [field]}, objects={
        "data": [{"properties": {"mode": {"expr": {"Literal": {"Value": "'Dropdown'"}}}}}]})


def card(measure: str, x: int, y: int, w: int = 220, h: int = 110) -> Visual:
    return Visual("card", x, y, w, h, roles={"Values": [measure]})


GLOBAL_SLICERS = lambda: [  # noqa: E731 - same slicer row on every page
    slicer("Dim_Travel.class", 700, 20, 180, title="Class"),
    slicer("Dim_Travel.travel_type", 890, 20, 180, title="Travel type"),
    slicer("Dim_Customer.customer_type", 1080, 20, 180, title="Customer type"),
]

PAGES: list[tuple[str, list[Visual]]] = [
    ("Executive Overview", [
        textbox("Executive Overview", 20, 20, 660, 56),
        *GLOBAL_SLICERS(),
        card("[Total Passengers]", 20, 96, 300),
        card("[Satisfaction %]", 340, 96, 300),
        card("[Delayed %]", 660, 96, 300),
        card("[Avg Dep Delay]", 980, 96, 280),
        Visual("clusteredBarChart", 20, 226, 610, 474, "Satisfaction % by class",
               {"Category": ["Dim_Travel.class"], "Y": ["[Satisfaction %]"]}),
        Visual("clusteredColumnChart", 650, 226, 610, 474, "Satisfaction % by travel type and class",
               {"Category": ["Dim_Travel.travel_type"], "Series": ["Dim_Travel.class"],
                "Y": ["[Satisfaction %]"]}),
    ]),
    ("Customer Segments", [
        textbox("Customer Segments - who is at risk?", 20, 20, 660, 56),
        *GLOBAL_SLICERS(),
        Visual("pivotTable", 20, 96, 610, 300, "Satisfaction % - age band x customer type",
               {"Rows": ["Dim_Customer.age_band"], "Columns": ["Dim_Customer.customer_type"],
                "Values": ["[Satisfaction %]"]}),
        Visual("donutChart", 650, 96, 610, 300, "Passengers by gender",
               {"Category": ["Dim_Customer.gender"], "Y": ["[Total Passengers]"]}),
        Visual("clusteredBarChart", 20, 416, 610, 284, "Satisfaction % by distance band",
               {"Category": ["Dim_Travel.distance_band"], "Y": ["[Satisfaction %]"]}),
        Visual("clusteredBarChart", 650, 416, 610, 284, "Dissatisfied passengers by trip segment",
               {"Category": ["Dim_Travel.trip_segment"], "Y": ["[Dissatisfied Passengers]"]},
               sort_desc="[Dissatisfied Passengers]"),
    ]),
    ("Service Drivers", [
        textbox("Service Drivers - what to fix first", 20, 20, 660, 56),
        *GLOBAL_SLICERS(),
        Visual("clusteredBarChart", 20, 96, 400, 604, "Service Gap (5 - avg rating)",
               {"Category": ["Dim_Service.service_name"], "Y": ["[Service Gap]"]},
               sort_desc="[Service Gap]"),
        Visual("pivotTable", 440, 96, 820, 300, "Avg rating by service and class",
               {"Rows": ["Dim_Service.service_name"], "Columns": ["Dim_Travel.class"],
                "Values": ["[Avg Service Rating]"]}),
        Visual("clusteredBarChart", 440, 416, 820, 284,
               "Rating gap: satisfied vs dissatisfied passengers",
               {"Category": ["Dim_Service.service_name"], "Y": ["[Rating Gap (Sat vs Dissat)]"]},
               sort_desc="[Rating Gap (Sat vs Dissat)]"),
    ]),
    ("Delay Impact", [
        textbox("Delay Impact - the cost of late departures", 20, 20, 660, 56),
        *GLOBAL_SLICERS(),
        card("[Delayed %]", 20, 96, 240),
        card("[Delay Penalty >15 pts]", 280, 96, 240),
        slicer("Delay Reduction.Delay Reduction %", 540, 96, 240, 110, title="What-if: delays removed (%)"),
        card("[Projected Satisfaction %]", 800, 96, 220),
        card("[Projected Gain pts]", 1040, 96, 220),
        Visual("clusteredColumnChart", 20, 226, 610, 474, "Satisfaction % by departure delay",
               {"Category": ["Fact_Flights.delay_bucket"], "Y": ["[Satisfaction %]"]}),
        Visual("scatterChart", 650, 226, 610, 474, "Avg delay vs satisfaction by trip segment",
               {"Category": ["Dim_Travel.trip_segment"], "X": ["[Avg Dep Delay]"],
                "Y": ["[Satisfaction %]"], "Size": ["[Total Passengers]"]}),
    ]),
]


def build_report() -> None:
    sections = []
    for i, (display, visuals) in enumerate(PAGES):
        page_id = "ReportSection" + tag("page", display).replace("-", "")[:20]
        sections.append({
            "config": "{}",
            "displayName": display,
            "displayOption": 1,
            "filters": "[]",
            "height": 720.0,
            "name": page_id,
            "ordinal": i,
            "visualContainers": [v.container(display, j) for j, v in enumerate(visuals)],
            "width": 1280.0,
        })
    report = {
        "config": json.dumps({"version": "5.43", "themeCollection": {}, "activeSectionIndex": 0,
                              "defaultDrillFilterOtherVisuals": True}),
        "layoutOptimization": 0,
        "sections": sections,
    }
    write_json(REPORT_DIR / "report.json", report)
    write_json(REPORT_DIR / "definition.pbir", {
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}},
    })


def build_dax_docs() -> None:
    """Render docs/dax_measures.md from MEASURES so the docs never drift from the model."""
    out = [
        "# DAX Measures",
        "",
        "> Generated by `scripts/build_pbip.py` from the same definitions that build the semantic "
        "model (`powerbi/AirlineAnalytics.SemanticModel/definition/tables/*.tmdl`). "
        "Edit the script, not this file.",
        "",
        "Conventions: `%` measures return a ratio formatted as a percentage; `pts` measures return "
        "percentage points (already multiplied by 100). Service-rating measures ignore rating 0 "
        "(\"not applicable\").",
        "",
    ]
    folders: dict[str, list[tuple[str, tuple]]] = {}
    for table, ms in MEASURES.items():
        for m in ms:
            folders.setdefault(m[3], []).append((table, m))
    for folder in sorted(folders):
        out += [f"## {folder.split(' ', 1)[1]}", ""]
        for table, (name, expr, fmt, _, desc) in folders[folder]:
            out += [
                f"### {name}",
                f"*Home table:* `{table}` · *Format:* `{fmt}`",
                "",
                desc,
                "",
                "```DAX",
                f"{name} =" + ("\n" if "\n" in expr else " ") + expr,
                "```",
                "",
            ]
    out += [
        "## What-if parameter",
        "",
        "`Delay Reduction` is a calculated table (`SELECTCOLUMNS(GENERATESERIES(0, 100, 5), "
        "\"Delay Reduction %\", [Value])`). Put `Delay Reduction[Delay Reduction %]` in a single-"
        "select slicer (style: *Single value* / slider) on the Delay Impact page; "
        "`[Projected Satisfaction %]` and `[Projected Gain pts]` respond to it.",
        "",
        "**Projection logic:** a share *r* of passengers delayed more than 15 minutes is assumed to "
        "depart on time instead and to be satisfied at the same rate as passengers who were on "
        "time (≤ 15 min). Everyone else is unchanged.",
        "",
    ]
    write(ROOT / "docs" / "dax_measures.md", "\n".join(out))


def main() -> None:
    for d in (MODEL_DIR, REPORT_DIR):
        if d.exists():
            # Keep Power BI's local cache/settings folder if present.
            for child in d.iterdir():
                if child.name != ".pbi":
                    shutil.rmtree(child) if child.is_dir() else child.unlink()
    build_semantic_model()
    build_report()
    build_dax_docs()
    write_json(PBI_DIR / f"{NAME}.pbip", {
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    })
    print(f"Wrote {PBI_DIR.relative_to(ROOT)}/{NAME}.pbip")
    n = sum(len(v) for v in MEASURES.values())
    print(f"  {len(TABLES) + 1} tables, {len(RELATIONSHIPS)} relationships, {n} measures, "
          f"{len(PAGES)} report pages")


if __name__ == "__main__":
    main()
