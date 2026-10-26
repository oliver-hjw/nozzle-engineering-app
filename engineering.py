from __future__ import annotations

import copy
import json
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def revision_label(n: int | None) -> str:
    return "R--" if n is None else f"R{int(n):02d}"


def new_nozzle(index: int = 1) -> dict[str, Any]:
    return {
        "name": f"Nozzle {index}",
        "injection_type": "RA",
        "fluid": "Urea Solution",
        "concentration": "",
        "qty": 1,
        "min_flow_lmin": 0.0,
        "normal_flow_lmin": 0.0,
        "max_flow_lmin": 0.0,
        "air_pressure_barg": 0.0,
        "air_flow_nm3h": "",
        "liquid_pressure_barg": "",
        "spray_angle_deg": 55.0,
        "droplet_size": "",
        "selected_model": "",
        "selected_air_barg": None,
        "design_points": [],
        "data_sheet_revision": "A",
        "performance_curve_revision": "A",
        "manual": {
            "nozzle_type": "",
            "run_type": "",
            "spraying_type": "",
            "dimension": "",
            "tip_material": "",
            "pipe_material": "",
            "empty_weight": "",
            "operating_weight": "",
            "air_connection": "",
            "liquid_connection": "",
            "unit_number": "",
            "design_temperature": "",
            "operating_temperature": "",
            "remark": "",
        },
        "additional_specs": [],
        "pdf_options": {
            "orientation": "landscape",
            "project_info": True,
            "graph_design_points": True,
            "point_table": True,
            "metric_descriptions": True,
            "metrics": {
                "flow": True,
                "liquidPressure": True,
                "airRate": True,
                "d32": True,
                "dv05": True,
                "dv09": True,
                "dmax": True,
                "x90": True,
                "x99": True,
            },
        },
    }


def new_project(owner: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": uuid.uuid4().hex[:10],
        "project_no": "",
        "project_name": "",
        "customer": "",
        "owner": owner,
        "status": "Working",
        "created_at": utc_now(),
        "created_by": owner,
        "updated_at": utc_now(),
        "updated_by": owner,
        "last_saved_revision": None,
        "current_working_revision": 0,
        "revision_history": [],
        "nozzles": [new_nozzle(1)],
        "notes": "",
    }


def safe_filename(project: dict[str, Any]) -> str:
    base = (project.get("project_no") or project.get("project_name") or "PROJECT").strip()
    base = re.sub(r"[^0-9A-Za-z._-]+", "_", base).strip("_")[:48] or "PROJECT"
    return f"{base}__{project.get('id','project')}.json"


def snapshot_for_revision(project: dict[str, Any]) -> dict[str, Any]:
    snap = copy.deepcopy(project)
    snap.pop("revision_history", None)
    return snap


def save_revision(project: dict[str, Any], actor: str) -> str:
    rev = int(project.get("current_working_revision", 0))
    label = revision_label(rev)
    project.setdefault("revision_history", []).append(
        {
            "revision": label,
            "saved_at": utc_now(),
            "saved_by": actor,
            "snapshot": snapshot_for_revision(project),
        }
    )
    project["last_saved_revision"] = rev
    project["current_working_revision"] = rev + 1
    project["updated_at"] = utc_now()
    project["updated_by"] = actor
    return label


def load_performance_db(path: str | Path) -> list[dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def model_flow_range_lhr(model: dict[str, Any]) -> tuple[float, float]:
    vals = [float(p["flow"]) for c in model.get("curves", []) for p in c.get("data", []) if p.get("flow") is not None]
    return (min(vals), max(vals)) if vals else (0.0, 0.0)


def recommend_models(db: list[dict[str, Any]], normal_lmin: float, spray_angle: float | None = None) -> list[dict[str, Any]]:
    target = max(0.0, float(normal_lmin or 0)) * 60.0
    out = []
    for m in db:
        lo, hi = model_flow_range_lhr(m)
        if target <= 0:
            distance = 0.0
            in_range = True
        elif lo <= target <= hi:
            distance = 0.0
            in_range = True
        else:
            distance = min(abs(target - lo), abs(target - hi)) / max(target, 1.0)
            in_range = False
        angle_penalty = 0.0
        if spray_angle and m.get("angle"):
            angle_penalty = abs(float(m["angle"]) - float(spray_angle)) / 180.0
        score = distance * 10 + angle_penalty
        out.append(
            {
                "model": m["model"],
                "family": m.get("family", ""),
                "angle": m.get("angle"),
                "source": m.get("source", ""),
                "min_lmin": lo / 60.0,
                "max_lmin": hi / 60.0,
                "in_range": in_range,
                "score": score,
                "air_options": [float(c.get("air", 0)) for c in m.get("curves", [])],
            }
        )
    return sorted(out, key=lambda x: (x["score"], x["model"]))


def find_model(db: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((m for m in db if m.get("model") == name), None)


def find_curve(model: dict[str, Any] | None, air_barg: float | None) -> dict[str, Any] | None:
    if not model or not model.get("curves"):
        return None
    if air_barg is None:
        return model["curves"][0]
    return min(model["curves"], key=lambda c: abs(float(c.get("air", 0)) - float(air_barg)))


def interp(curve: dict[str, Any], flow_lhr: float) -> dict[str, float]:
    pts = sorted(curve.get("data", []), key=lambda x: float(x.get("flow", 0)))
    if not pts:
        return {}
    x = float(flow_lhr)
    if x <= float(pts[0]["flow"]):
        a = b = pts[0]
    elif x >= float(pts[-1]["flow"]):
        a = b = pts[-1]
    else:
        a = b = pts[0]
        for p1, p2 in zip(pts, pts[1:]):
            if float(p1["flow"]) <= x <= float(p2["flow"]):
                a, b = p1, p2
                break
    xa, xb = float(a["flow"]), float(b["flow"])
    t = 0.0 if xb == xa else (x - xa) / (xb - xa)
    keys = {k for p in (a, b) for k, v in p.items() if isinstance(v, (int, float))}
    out = {"flow": x}
    for k in keys:
        if k == "flow":
            continue
        va, vb = a.get(k), b.get(k)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            out[k] = float(va) + (float(vb) - float(va)) * t
    return out


def parse_rfq_text(text: str) -> list[dict[str, Any]]:
    """Conservative label-first RFQ parser. Unclear values are flagged for review."""
    raw = re.sub(r"\r", "", text or "")
    lines = [re.sub(r"\s+", " ", x).strip() for x in raw.split("\n") if x.strip()]
    joined = "\n".join(lines)
    items: list[dict[str, Any]] = []

    def add(field: str, label: str, value: Any, confidence: str = "high", source: str = ""):
        if value in (None, ""):
            return
        if not any(x["field"] == field for x in items):
            items.append({"apply": confidence == "high", "field": field, "label": label, "value": value, "confidence": confidence, "source": source})

    def labeled(patterns: list[str]) -> tuple[str | None, str]:
        for line in lines:
            for p in patterns:
                m = re.search(p, line, re.I)
                if m:
                    return m.group(1).strip(" :-"), line
        return None, ""

    val, src = labeled([r"(?:customer|client|end user)\s*[:=\-]\s*(.+)$", r"(?:고객사|발주처)\s*[:=\-]\s*(.+)$"])
    add("customer", "Customer", val, "high", src)
    val, src = labeled([r"(?:project\s*(?:no\.?|number)|pjt\s*no\.?)\s*[:=\-]\s*(.+)$"])
    add("project_no", "Project No.", val, "high", src)
    val, src = labeled([r"(?:project\s*(?:name|title)|project)\s*[:=\-]\s*(.+)$"])
    add("project_name", "Project Name", val, "high", src)

    low = joined.lower()
    if "urea" in low or "요소" in low:
        add("fluid", "Fluid", "Urea Solution", "high", "keyword: urea")
    elif "ammonia" in low or "nh4oh" in low or "암모니아" in low:
        add("fluid", "Fluid", "Ammonia Solution", "high", "keyword: ammonia")
    elif "hydrated lime" in low or "slaked lime" in low or "소석회" in low:
        add("fluid", "Fluid", "Hydrated Lime", "high", "keyword: hydrated lime")
    elif re.search(r"\bwater\b|\bH2O\b|물", joined, re.I):
        add("fluid", "Fluid", "Water", "high", "keyword: water")

    m = re.search(r"(?:urea|ammonia|solution|concentration|농도)[^\n%]{0,20}(\d+(?:\.\d+)?)\s*%", joined, re.I)
    if m:
        add("concentration", "Concentration", m.group(1) + "%", "high", m.group(0))

    m = re.search(r"(?:qty|quantity|nozzle\s*(?:qty|quantity)|수량)\s*[:=\-]?\s*(\d+)\s*(?:ea|sets?|nos?)?", joined, re.I)
    if m:
        add("qty", "Nozzle Qty", int(m.group(1)), "high", m.group(0))

    flow_patterns = [
        ("min_flow_lmin", "Min Flow", r"(?:min(?:imum)?\s*(?:flow|capacity)|flow\s*min)\s*[:=\-]?\s*(\d+(?:\.\d+)?)\s*(l\s*/\s*(?:min|hr|h))"),
        ("normal_flow_lmin", "Normal Flow", r"(?:normal|nominal|rated)\s*(?:flow|capacity)?\s*[:=\-]?\s*(\d+(?:\.\d+)?)\s*(l\s*/\s*(?:min|hr|h))"),
        ("max_flow_lmin", "Max Flow", r"(?:max(?:imum)?\s*(?:flow|capacity)|flow\s*max)\s*[:=\-]?\s*(\d+(?:\.\d+)?)\s*(l\s*/\s*(?:min|hr|h))"),
    ]
    for field, label, pat in flow_patterns:
        m = re.search(pat, joined, re.I)
        if m:
            v = float(m.group(1))
            unit = re.sub(r"\s+", "", m.group(2).lower())
            if unit in ("l/hr", "l/h"):
                v /= 60.0
            add(field, label, round(v, 6), "high", m.group(0))

    # Generic flow is useful, but deliberately review-only.
    if not any(x["field"] == "normal_flow_lmin" for x in items):
        m = re.search(r"(?:flow|capacity)\s*[:=\-]?\s*(\d+(?:\.\d+)?)\s*(l\s*/\s*(?:min|hr|h))", joined, re.I)
        if m:
            v = float(m.group(1)); unit = re.sub(r"\s+", "", m.group(2).lower())
            if unit in ("l/hr", "l/h"):
                v /= 60.0
            add("normal_flow_lmin", "Normal Flow", round(v, 6), "review", m.group(0))

    m = re.search(r"(?:atomizing\s*air|air)\s*(?:pressure)?\s*[:=\-]?\s*(\d+(?:\.\d+)?)\s*(bar\.?g|barg|bar|psi)", joined, re.I)
    if m:
        v, unit = float(m.group(1)), m.group(2).lower()
        if unit == "psi":
            v *= 0.0689476
        add("air_pressure_barg", "Air Pressure", round(v, 4), "high" if "g" in unit or unit == "psi" else "review", m.group(0))

    m = re.search(r"(?:spray\s*angle|spraying\s*degree|angle)\s*[:=\-]?\s*(\d+(?:\.\d+)?)\s*(?:°|deg|degree)?", joined, re.I)
    if m:
        add("spray_angle_deg", "Spray Angle", float(m.group(1)), "high", m.group(0))

    mat = None
    for token in ["Hastelloy C-276", "Hastelloy C276", "SS316L", "316L", "316SS", "SUS316L", "304H", "321", "Inconel 718", "Alloy 230", "HC22"]:
        if token.lower() in low:
            mat = token; break
    if mat:
        add("manual.pipe_material", "Material", mat, "review", f"keyword: {mat}")

    inj = None
    for token in ["AMMONIA", "DI", "RA"]:
        if re.search(rf"\b{token}\b", joined, re.I):
            inj = token; break
    if inj:
        add("injection_type", "Injection Type", inj, "review", f"keyword: {inj}")

    return items


def apply_import_items(project: dict[str, Any], nozzle_index: int, rows: list[dict[str, Any]]) -> None:
    n = project["nozzles"][nozzle_index]
    for row in rows:
        if not row.get("apply"):
            continue
        field = row["field"]
        value = row["value"]
        if field.startswith("manual."):
            n.setdefault("manual", {})[field.split(".", 1)[1]] = value
        elif field in n:
            n[field] = value
        elif field in project:
            project[field] = value


METRIC_DESCRIPTIONS = {
    "flow": ("Flow Rate", "Liquid flow rate through one nozzle at the selected operating condition."),
    "liquidPressure": ("Liquid Pressure", "Liquid-side pressure corresponding to the selected liquid flow and atomizing-air condition."),
    "airRate": ("Air Capacity / Air Flow", "Atomizing-air consumption required at the selected operating condition."),
    "d32": ("D32 / SMD", "Sauter Mean Diameter: droplet diameter representing the same volume-to-surface-area ratio as the spray."),
    "dv05": ("Dv0.5", "Volume median diameter: 50% of sprayed liquid volume is contained in droplets smaller than this size."),
    "dv09": ("Dv0.9", "90% volume diameter: 90% of sprayed liquid volume is contained in droplets smaller than this size."),
    "dmax": ("Dmax", "Maximum droplet diameter represented or reported in the source performance data."),
    "x90": ("X90", "90th-percentile droplet-size value reported in the source dataset; interpretation follows the source definition."),
    "x99": ("X99", "99th-percentile droplet-size value reported in the source dataset; interpretation follows the source definition."),
}
