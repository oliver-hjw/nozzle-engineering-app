from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from github_store import ConflictError, GitHubProjectStore, GitHubStoreError, LocalProjectStore

ROOT = Path(__file__).parent
APP_VERSION = "HTML Team Edition v2.0"
html_ui = components.declare_component("nozzle_html_ui", path=str(ROOT / "component"))

st.set_page_config(page_title="Nozzle Engineering System", page_icon="⚙️", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
#MainMenu,header,footer,[data-testid="stSidebar"],.stDeployButton{display:none!important}
.block-container{max-width:none!important;padding:0!important;margin:0!important}
[data-testid="stAppViewContainer"]>.main{overflow:visible}
iframe[title="nozzle_html_ui"]{border:0!important;width:100%!important}
</style>
""", unsafe_allow_html=True)


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def secret_get(*parts, default=None):
    try:
        obj = st.secrets
        for p in parts:
            obj = obj[p]
        return obj
    except Exception:
        return default


def load_users():
    raw = secret_get("team", "users", default=None)
    users = {}
    if raw:
        for key in raw:
            v = raw[key]
            users[key] = {"name": str(v.get("name", key)), "role": str(v.get("role", "Member")), "pin_sha256": str(v.get("pin_sha256", ""))}
    if not users:
        users = {"demo": {"name": "Demo Admin", "role": "Admin", "pin_sha256": sha256("0000")}}
    return users


def login_gate():
    users = load_users()
    if "auth_user" in st.session_state:
        return st.session_state.auth_user
    st.markdown("<div style='max-width:520px;margin:80px auto;padding:28px;border:1px solid #dfe6ee;border-radius:14px;background:white'>", unsafe_allow_html=True)
    st.title("⚙️ Nozzle Engineering System")
    st.caption(f"{APP_VERSION} · Original HTML UI + GitHub Team Sync")
    with st.form("login"):
        username = st.selectbox("User", list(users.keys()), format_func=lambda k: users[k]["name"])
        pin = st.text_input("PIN", type="password")
        ok = st.form_submit_button("Login", type="primary", use_container_width=True)
    if ok:
        rec = users[username]
        if rec["pin_sha256"] and sha256(pin) == rec["pin_sha256"]:
            st.session_state.auth_user = {"id": username, **rec}
            st.rerun()
        st.error("PIN이 맞지 않습니다.")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


def make_store():
    token = secret_get("github", "token", default="")
    repo = secret_get("github", "data_repo", default="")
    branch = secret_get("github", "branch", default="main")
    path = secret_get("github", "projects_path", default="projects")
    if token and repo:
        return GitHubProjectStore(str(token), str(repo), str(branch), str(path)), False
    return LocalProjectStore(ROOT / "projects"), True


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def legacy_new_project(owner: str):
    return {
        "id": "p_" + uuid.uuid4().hex[:12], "projectNo": "", "projectName": "", "customer": "", "owner": owner,
        "participants": "", "status": "Draft", "revisionCount": 0, "revisions": [], "locked": False,
        "createdAt": now_iso(), "updatedAt": now_iso(), "nozzles": [legacy_new_nozzle(0)]
    }


def legacy_new_nozzle(i: int):
    return {"name":f"Type-{i+1}","typeTag":f"Type-{i+1}","injectionType":"RA","selectedModel":"","dataSheetRevision":"A","fluid":"Urea Solution","concentration":"","qty":1,"sprayAngle":"","minFlow":"","normalFlow":"","maxFlow":"","airPressure":"","airFlow":"","dropletSize":"","liquidPressure":"","manualNozzleType":"Internal-mix, Air Atomizing","manualRunType":"Flow control","manualSprayingType":"Round","manualDimension":"","manualTipMaterial":"","manualPipeMaterial":"316LSS","manualEmptyWeight":"","manualOperatingWeight":"","manualAirConnection":"","manualLiquidConnection":"","manualUnitNumber":"","manualDesignTemp":"","manualOperatingTemp":"","manualRemark":"","additionalSpecs":[],"designPoints":[],"performanceRevision":"A"}


def to_legacy(p):
    if not p or "projectNo" in p:
        return p
    q = legacy_new_project(p.get("owner") or "")
    q.update(id=p.get("id") or q["id"], projectNo=p.get("project_no", ""), projectName=p.get("project_name", ""), customer=p.get("customer", ""), owner=p.get("owner", ""), createdAt=p.get("created_at") or q["createdAt"], updatedAt=p.get("updated_at") or q["updatedAt"])
    status = p.get("status", "Working")
    q["status"] = "Completed" if status == "Completed" else "Hold" if status == "On Hold" else status if status not in ("Working", "") else "Draft"
    q["locked"] = q["status"] == "Completed"
    q["revisionCount"] = max(0, int(p.get("last_saved_revision") or 0))
    q["revisions"] = p.get("revision_history") or []
    out_nozzles = []
    for i, x in enumerate((p.get("nozzles") or [{}])[:5]):
        n = legacy_new_nozzle(i); m=x.get("manual") or {}; po=x.get("pdf_options") or {}; mets=po.get("metrics") or {}
        n.update(name=x.get("name") or n["name"], typeTag=x.get("name") or n["typeTag"], injectionType=x.get("injection_type") or "RA", selectedModel=x.get("selected_model") or "", dataSheetRevision=x.get("data_sheet_revision") or "A", fluid=x.get("fluid") or "Urea Solution", concentration=x.get("concentration") or "", qty=x.get("qty") or 1, sprayAngle="" if x.get("spray_angle_deg") is None else str(x.get("spray_angle_deg")), minFlow="" if x.get("min_flow_lmin") is None else float(x.get("min_flow_lmin"))*60, normalFlow="" if x.get("normal_flow_lmin") is None else float(x.get("normal_flow_lmin"))*60, maxFlow="" if x.get("max_flow_lmin") is None else float(x.get("max_flow_lmin"))*60, airPressure="" if x.get("air_pressure_barg") is None else str(x.get("air_pressure_barg")), airFlow="" if x.get("air_flow_nm3h") is None else str(x.get("air_flow_nm3h")), liquidPressure="" if x.get("liquid_pressure_barg") is None else str(x.get("liquid_pressure_barg")), dropletSize=x.get("droplet_size") or "", selectedAir="" if x.get("selected_air_barg") is None else str(x.get("selected_air_barg")), designPoints=x.get("design_points") or [], performanceRevision=x.get("performance_curve_revision") or "A")
        n.update(manualNozzleType=m.get("nozzle_type") or n["manualNozzleType"],manualRunType=m.get("run_type") or n["manualRunType"],manualSprayingType=m.get("spraying_type") or n["manualSprayingType"],manualDimension=m.get("dimension") or "",manualTipMaterial=m.get("tip_material") or "",manualPipeMaterial=m.get("pipe_material") or n["manualPipeMaterial"],manualEmptyWeight=m.get("empty_weight") or "",manualOperatingWeight=m.get("operating_weight") or "",manualAirConnection=m.get("air_connection") or "",manualLiquidConnection=m.get("liquid_connection") or "",manualUnitNumber=m.get("unit_number") or "",manualDesignTemp=m.get("design_temperature") or "",manualOperatingTemp=m.get("operating_temperature") or "",manualRemark=m.get("remark") or "",additionalSpecs=x.get("additional_specs") or [])
        n.update(pdfOrientation=po.get("orientation","landscape"),pdfProjectInfo=po.get("project_info",True),pdfDesignPoints=po.get("graph_design_points",True),pdfPointTable=po.get("point_table",True),pdfMetricDescriptions=po.get("metric_descriptions",True),pdfMetricDescSelection={k:mets.get(k,True) for k in ["flow","liquidPressure","airRate","d32","dv05","dv09","dmax","x90","x99"]})
        out_nozzles.append(n)
    q["nozzles"] = out_nozzles
    return q


def safe_filename(p):
    raw = (p.get("projectNo") or p.get("projectName") or p.get("id") or "project").strip()
    raw = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._") or "project"
    return raw[:80] + ".json"


def ensure_state(user):
    defaults = {"project": None, "project_sha": None, "project_filename": None, "sync_status": "Ready", "flash": "", "load_token": 0, "last_event_id": None}
    for k,v in defaults.items():
        if k not in st.session_state: st.session_state[k]=v


def list_refs(store):
    try:
        return [{"name": r.name, "label": r.name} for r in store.list_projects()]
    except Exception as e:
        st.session_state.sync_status="Error"; st.session_state.flash=str(e); return []


def save_submitted(store,user,project,revision=False):
    if not project: return
    project["owner"] = project.get("owner") or user["name"]
    project["updatedAt"] = now_iso()
    filename = st.session_state.project_filename or safe_filename(project)
    msg = ("Save revision" if revision else "Update working copy") + f": {project.get('projectNo') or project.get('projectName') or filename} by {user['name']}"
    try:
        sha = store.save_project(filename, project, st.session_state.project_sha, user["name"], msg)
        st.session_state.project=project;st.session_state.project_sha=sha;st.session_state.project_filename=filename;st.session_state.sync_status="Synced";st.session_state.flash="Revision 저장 완료" if revision else "Working Copy 저장 완료";st.session_state.load_token+=1
    except ConflictError as e:
        st.session_state.project=project;st.session_state.sync_status="Conflict";st.session_state.flash="다른 사용자가 먼저 저장했습니다. 현재 화면의 작업내용은 유지됩니다. 최신본을 다시 열기 전에 필요한 경우 Excel/PDF 또는 JSON 백업을 권장합니다. " + str(e);st.session_state.load_token+=1
    except GitHubStoreError as e:
        st.session_state.project=project;st.session_state.sync_status="Error";st.session_state.flash=str(e);st.session_state.load_token+=1


user=login_gate(); store,local_mode=make_store(); ensure_state(user)
refs=list_refs(store)
value=html_ui(project=st.session_state.project, project_refs=refs, current_filename=st.session_state.project_filename, current_sha=st.session_state.project_sha, user=user, sync_status=st.session_state.sync_status if not local_mode else "LOCAL DEMO", flash=st.session_state.flash, load_token=st.session_state.load_token, open_view="rfq", key="nozzle_html_team_v2", default=None)

if isinstance(value,dict):
    event_id=value.get("event_id")
    if event_id and event_id!=st.session_state.last_event_id:
        st.session_state.last_event_id=event_id
        action=value.get("action")
        if action=="logout":
            st.session_state.clear();st.rerun()
        elif action=="new_project":
            st.session_state.project=legacy_new_project(user["name"]);st.session_state.project_sha=None;st.session_state.project_filename=None;st.session_state.sync_status="New / unsaved";st.session_state.flash="새 프로젝트";st.session_state.load_token+=1;st.rerun()
        elif action=="open_project":
            try:
                p,sha=store.read_project(value.get("filename",""));st.session_state.project=to_legacy(p);st.session_state.project_sha=sha;st.session_state.project_filename=value.get("filename");st.session_state.sync_status="Synced";st.session_state.flash="GitHub 프로젝트를 불러왔습니다.";st.session_state.load_token+=1
            except Exception as e:
                st.session_state.sync_status="Error";st.session_state.flash=str(e)
            st.rerun()
        elif action=="refresh":
            st.session_state.flash="프로젝트 목록을 새로고침했습니다.";st.rerun()
        elif action=="save_working":
            save_submitted(store,user,value.get("project"),False);st.rerun()
        elif action=="save_revision":
            save_submitted(store,user,value.get("project"),True);st.rerun()
        elif action=="delete_project":
            if user.get("role","").lower()!="admin":
                st.session_state.sync_status="Error";st.session_state.flash="Admin만 삭제할 수 있습니다.";st.rerun()
            try:
                store.delete_project(st.session_state.project_filename or value.get("filename",""),st.session_state.project_sha,user["name"]);st.session_state.project=None;st.session_state.project_sha=None;st.session_state.project_filename=None;st.session_state.sync_status="Deleted";st.session_state.flash="프로젝트를 삭제했습니다.";st.session_state.load_token+=1
            except Exception as e:
                st.session_state.sync_status="Error";st.session_state.flash=str(e)
            st.rerun()
