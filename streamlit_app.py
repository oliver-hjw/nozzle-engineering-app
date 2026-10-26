from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engineering import (
    METRIC_DESCRIPTIONS, apply_import_items, find_curve, find_model, interp,
    load_performance_db, new_nozzle, new_project, parse_rfq_text,
    recommend_models, revision_label, safe_filename, save_revision, utc_now,
)
from github_store import ConflictError, GitHubProjectStore, GitHubStoreError, LocalProjectStore
from outputs import build_excel, build_performance_pdf

APP_VERSION = "GitHub Team Edition v1.0"
ROOT = Path(__file__).parent
PERF_DB = load_performance_db(ROOT / "data" / "performance_data.json")

st.set_page_config(page_title="Nozzle Engineering System", page_icon="⚙️", layout="wide")

st.markdown("""
<style>
.block-container{padding-top:1.35rem;max-width:1500px}
.small-note{font-size:.78rem;color:#667085}.sync-ok{color:#067647;font-weight:700}.sync-warn{color:#b54708;font-weight:700}
[data-testid="stMetric"]{border:1px solid #e4e7ec;border-radius:10px;padding:8px 12px;background:#fff}
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


def load_users() -> dict[str, dict[str, str]]:
    raw = secret_get("team", "users", default=None)
    users: dict[str, dict[str, str]] = {}
    if raw:
        try:
            for key in raw:
                v = raw[key]
                users[key] = {
                    "name": str(v.get("name", key)),
                    "role": str(v.get("role", "Member")),
                    "pin_sha256": str(v.get("pin_sha256", "")),
                }
        except Exception:
            pass
    if not users:
        users = {"demo": {"name": "Demo Admin", "role": "Admin", "pin_sha256": sha256("0000")}}
    return users


def login_gate() -> dict[str, str]:
    users = load_users()
    if "auth_user" not in st.session_state:
        st.title("⚙️ Nozzle Engineering System")
        st.caption(f"{APP_VERSION} · Small-team GitHub project storage")
        if list(users) == ["demo"]:
            st.warning("Team users are not configured in Streamlit Secrets. Local/demo login is demo / 0000.")
        with st.form("login"):
            username = st.selectbox("User", list(users.keys()), format_func=lambda k: users[k]["name"])
            pin = st.text_input("PIN", type="password")
            ok = st.form_submit_button("Login", type="primary")
        if ok:
            rec = users[username]
            if rec["pin_sha256"] and sha256(pin) == rec["pin_sha256"]:
                st.session_state.auth_user = {"id": username, **rec}
                st.rerun()
            else:
                st.error("PIN이 맞지 않습니다.")
        st.stop()
    return st.session_state.auth_user


def make_store():
    token = secret_get("github", "token", default="")
    repo = secret_get("github", "data_repo", default="")
    branch = secret_get("github", "branch", default="main")
    path = secret_get("github", "projects_path", default="projects")
    if token and repo:
        return GitHubProjectStore(str(token), str(repo), str(branch), str(path)), False
    return LocalProjectStore(ROOT / "projects"), True


def ensure_state(user):
    if "project" not in st.session_state:
        st.session_state.project = new_project(user["name"])
        st.session_state.project_sha = None
        st.session_state.project_filename = None
        st.session_state.sync_status = "New / unsaved"
    if "active_nozzle" not in st.session_state:
        st.session_state.active_nozzle = 0
    if "rfq_import_rows" not in st.session_state:
        st.session_state.rfq_import_rows = []


def touch(actor: str):
    p = st.session_state.project
    p["updated_at"] = utc_now(); p["updated_by"] = actor


def current_nozzle() -> dict[str, Any]:
    p = st.session_state.project
    idx = min(max(0, st.session_state.active_nozzle), len(p["nozzles"])-1)
    st.session_state.active_nozzle = idx
    return p["nozzles"][idx]


def project_header(user):
    p = st.session_state.project
    c1,c2,c3,c4,c5 = st.columns([1.4,1.2,1,1,1.2])
    c1.metric("Project", p.get("project_no") or p.get("project_name") or "NEW")
    c2.metric("Owner", p.get("owner") or "-")
    c3.metric("Last Saved", revision_label(p.get("last_saved_revision")))
    c4.metric("Working", revision_label(p.get("current_working_revision",0)))
    c5.metric("Sync", st.session_state.sync_status)


def save_working(store, user, revision=False):
    p = st.session_state.project
    if not p.get("project_name") and not p.get("project_no"):
        st.error("Project No. 또는 Project Name을 먼저 입력해주세요."); return
    if revision:
        label = save_revision(p, user["name"])
        msg = f"Save {label}: {p.get('project_no') or p.get('project_name')} by {user['name']}"
    else:
        touch(user["name"])
        msg = f"Update working copy: {p.get('project_no') or p.get('project_name')} by {user['name']}"
    filename = st.session_state.project_filename or safe_filename(p)
    try:
        new_sha = store.save_project(filename, p, st.session_state.project_sha, user["name"], msg)
        st.session_state.project_sha = new_sha
        st.session_state.project_filename = filename
        st.session_state.sync_status = "Synced"
        st.success("GitHub 프로젝트 저장 완료" + (f" · {label}" if revision else ""))
    except ConflictError as e:
        st.session_state.sync_status = "Conflict"
        st.error("동시 수정 충돌: " + str(e))
    except GitHubStoreError as e:
        st.session_state.sync_status = "Error"
        st.error(str(e))


def project_sidebar(store, local_mode, user):
    with st.sidebar:
        st.subheader("Team")
        st.write(f"**{user['name']}** · {user['role']}")
        if st.button("Logout", use_container_width=True):
            st.session_state.clear(); st.rerun()
        st.divider()
        st.subheader("Project Sync")
        if local_mode:
            st.warning("LOCAL DEMO MODE\n\nStreamlit Cloud에서는 영구 저장용이 아닙니다.")
        else:
            try:
                h=store.health(); st.caption(f"Data repo: {h['repo']} · branch: {secret_get('github','branch',default='main')}")
            except Exception as e:
                st.error(str(e))
        try:
            refs=store.list_projects()
        except Exception as e:
            refs=[]; st.error(str(e))
        names=[r.name for r in refs]
        selected=st.selectbox("Saved projects", [""]+names, format_func=lambda x: "— select —" if x=="" else x)
        c1,c2=st.columns(2)
        if c1.button("Open", disabled=not selected, use_container_width=True):
            try:
                p,sha=store.read_project(selected)
                st.session_state.project=p; st.session_state.project_sha=sha; st.session_state.project_filename=selected
                st.session_state.active_nozzle=0; st.session_state.sync_status="Synced"; st.rerun()
            except Exception as e: st.error(str(e))
        if c2.button("New", use_container_width=True):
            st.session_state.project=new_project(user["name"]); st.session_state.project_sha=None; st.session_state.project_filename=None
            st.session_state.active_nozzle=0; st.session_state.sync_status="New / unsaved"; st.rerun()
        if st.button("Save Working Copy", type="primary", use_container_width=True): save_working(store,user,False)
        if st.button("Revision 저장", use_container_width=True): save_working(store,user,True)
        if user["role"].lower()=="admin" and st.session_state.project_sha:
            with st.expander("Admin"):
                confirm=st.checkbox("현재 프로젝트 삭제 확인")
                if st.button("Delete Project", disabled=not confirm, use_container_width=True):
                    try:
                        store.delete_project(st.session_state.project_filename,st.session_state.project_sha,user["name"])
                        st.session_state.project=new_project(user["name"]); st.session_state.project_sha=None; st.session_state.project_filename=None
                        st.session_state.sync_status="Deleted"; st.rerun()
                    except Exception as e: st.error(str(e))


def project_tab(user):
    p=st.session_state.project
    st.subheader("Project Information")
    with st.form("project_info"):
        a,b=st.columns(2)
        project_no=a.text_input("Project No.",p.get("project_no",""))
        project_name=b.text_input("Project Name",p.get("project_name",""))
        customer=a.text_input("Customer",p.get("customer",""))
        owner=b.text_input("Owner",p.get("owner",user["name"]))
        status=a.selectbox("Status",["Working","Completed","On Hold"],index=["Working","Completed","On Hold"].index(p.get("status","Working")) if p.get("status") in ["Working","Completed","On Hold"] else 0)
        notes=st.text_area("Project Notes",p.get("notes",""),height=100)
        submitted=st.form_submit_button("Apply Project Info",type="primary")
    if submitted:
        p.update(project_no=project_no,project_name=project_name,customer=customer,owner=owner,status=status,notes=notes); touch(user["name"]); st.success("Working copy에 반영했습니다. GitHub 저장은 왼쪽 Save Working Copy를 눌러주세요.")
    st.caption(f"Created: {p.get('created_at','-')} · Updated: {p.get('updated_at','-')} by {p.get('updated_by','-')}")


def nozzle_selector(user):
    p=st.session_state.project
    labels=[f"{i+1}. {n.get('name','Nozzle')}" for i,n in enumerate(p["nozzles"])]
    c1,c2,c3=st.columns([3,1,1])
    idx=c1.selectbox("Active Nozzle",range(len(labels)),index=st.session_state.active_nozzle,format_func=lambda i: labels[i],key="nozzle_selector")
    st.session_state.active_nozzle=idx
    if c2.button("+ Add",disabled=len(p["nozzles"])>=5,use_container_width=True):
        p["nozzles"].append(new_nozzle(len(p["nozzles"])+1)); st.session_state.active_nozzle=len(p["nozzles"])-1; touch(user["name"]); st.rerun()
    if c3.button("Remove",disabled=len(p["nozzles"])<=1,use_container_width=True):
        p["nozzles"].pop(st.session_state.active_nozzle); st.session_state.active_nozzle=max(0,st.session_state.active_nozzle-1); touch(user["name"]); st.rerun()


def rfq_tab(user):
    nozzle_selector(user); n=current_nozzle(); p=st.session_state.project
    st.subheader("RFQ / Nozzle Input")
    with st.form(f"rfq_form_{p['id']}_{st.session_state.active_nozzle}"):
        a,b,c=st.columns(3)
        name=a.text_input("Nozzle Name",n.get("name",""))
        injection=b.selectbox("Injection Type",["RA","DI","AMMONIA"],index=["RA","DI","AMMONIA"].index(n.get("injection_type","RA")))
        fluid=c.selectbox("Fluid",["Ammonia Solution","Urea Solution","Hydrated Lime","Water"],index=["Ammonia Solution","Urea Solution","Hydrated Lime","Water"].index(n.get("fluid","Urea Solution")))
        concentration=a.text_input("Concentration",n.get("concentration",""),placeholder="e.g. 40%")
        qty=b.number_input("Nozzle Qty",min_value=1,max_value=999,value=int(n.get("qty",1)),step=1)
        angle=c.number_input("Spray Angle (deg)",min_value=0.0,max_value=180.0,value=float(n.get("spray_angle_deg",55)),step=1.0)
        f1,f2,f3=st.columns(3)
        fmin=f1.number_input("Min Flow / Nozzle (L/min)",min_value=0.0,value=float(n.get("min_flow_lmin",0)),format="%.4f")
        fnorm=f2.number_input("Normal Flow / Nozzle (L/min)",min_value=0.0,value=float(n.get("normal_flow_lmin",0)),format="%.4f")
        fmax=f3.number_input("Max Flow / Nozzle (L/min)",min_value=0.0,value=float(n.get("max_flow_lmin",0)),format="%.4f")
        airp=a.number_input("Atomizing Air Pressure (barg)",min_value=0.0,value=float(n.get("air_pressure_barg",0)),format="%.3f")
        airf=b.text_input("Atomizing Air Flow (Nm³/hr)",str(n.get("air_flow_nm3h","")))
        liqp=c.text_input("Liquid Pressure (barg)",str(n.get("liquid_pressure_barg","")))
        droplet=a.text_input("Droplet Size",str(n.get("droplet_size","")))
        dsrev=b.text_input("Data Sheet Rev.",str(n.get("data_sheet_revision","A")),max_chars=4)
        pcrev=c.text_input("Performance Curve Rev.",str(n.get("performance_curve_revision","A")),max_chars=4)
        st.markdown("**Manual Specifications**")
        m=n.get("manual",{}); m1,m2,m3=st.columns(3)
        nozzle_type=m1.text_input("Nozzle Type",m.get("nozzle_type","")); run_type=m2.text_input("Run Type",m.get("run_type","")); spraying_type=m3.text_input("Spraying Type",m.get("spraying_type",""))
        dimension=m1.text_input("Dimension / DWG",m.get("dimension","")); tipmat=m2.text_input("Nozzle Tip Material",m.get("tip_material","")); pipemat=m3.text_input("Nozzle Pipe Material",m.get("pipe_material",""))
        emptyw=m1.text_input("Empty Weight",m.get("empty_weight","")); opw=m2.text_input("Operating Weight",m.get("operating_weight","")); unitno=m3.text_input("Unit Number",m.get("unit_number",""))
        airconn=m1.text_input("Atomizing Air Connection",m.get("air_connection","")); liqconn=m2.text_input("Liquid Connection",m.get("liquid_connection","")); dtemp=m3.text_input("Design Temperature",m.get("design_temperature",""))
        otemp=m1.text_input("Operating Temperature",m.get("operating_temperature","")); remark=st.text_area("Remark / Note",m.get("remark",""),height=80)
        submit=st.form_submit_button("Apply RFQ / Nozzle",type="primary")
    if submit:
        n.update(name=name,injection_type=injection,fluid=fluid,concentration=concentration,qty=int(qty),spray_angle_deg=angle,min_flow_lmin=fmin,normal_flow_lmin=fnorm,max_flow_lmin=fmax,air_pressure_barg=airp,air_flow_nm3h=airf,liquid_pressure_barg=liqp,droplet_size=droplet,data_sheet_revision=dsrev,performance_curve_revision=pcrev)
        n["manual"]={"nozzle_type":nozzle_type,"run_type":run_type,"spraying_type":spraying_type,"dimension":dimension,"tip_material":tipmat,"pipe_material":pipemat,"empty_weight":emptyw,"operating_weight":opw,"air_connection":airconn,"liquid_connection":liqconn,"unit_number":unitno,"design_temperature":dtemp,"operating_temperature":otemp,"remark":remark}
        touch(user["name"]); st.success("RFQ working copy 반영 완료")

    st.divider(); st.subheader("RFQ Quick Import")
    st.caption("고객 RFQ 텍스트를 붙여넣고 분석 → 검토 → 선택 적용합니다. 이미지/OCR은 포함하지 않았습니다.")
    raw=st.text_area("RFQ Source Text",height=180,key="rfq_source_text")
    if st.button("Analyze RFQ Text"):
        st.session_state.rfq_import_rows=parse_rfq_text(raw)
    rows=st.session_state.rfq_import_rows
    if rows:
        df=pd.DataFrame(rows)
        edited=st.data_editor(df,column_config={"apply":st.column_config.CheckboxColumn("Apply")},disabled=["field","label","value","confidence","source"],hide_index=True,use_container_width=True,key="rfq_review_editor")
        if st.button("선택 항목 RFQ에 적용",type="primary"):
            apply_import_items(p,st.session_state.active_nozzle,edited.to_dict("records")); touch(user["name"]); st.success("적용했습니다. RFQ 입력값을 확인해주세요."); st.rerun()


def performance_figure(model,curve,flow_unit,nozzle):
    factor=1/60 if flow_unit=="L/min" else 1
    data=curve.get("data",[]); x=[p.get("flow",0)*factor for p in data]
    fig=go.Figure()
    if any("liquidPressure" in p for p in data): fig.add_trace(go.Scatter(x=x,y=[p.get("liquidPressure") for p in data],mode="lines+markers",name="Liquid Pressure (barg)",yaxis="y",customdata=[p.get("flow") for p in data]))
    if any("airRate" in p for p in data): fig.add_trace(go.Scatter(x=x,y=[p.get("airRate") for p in data],mode="lines+markers",name="Air Flow (Nm³/hr)",yaxis="y2",customdata=[p.get("flow") for p in data]))
    for k,label in [("d32","D32/SMD"),("dv05","Dv0.5"),("dv09","Dv0.9"),("dmax","Dmax"),("x90","X90"),("x99","X99")]:
        if any(k in p for p in data): fig.add_trace(go.Scatter(x=x,y=[p.get(k) for p in data],mode="lines+markers",name=label,yaxis="y3",customdata=[p.get("flow") for p in data]))
    for i,dp in enumerate(nozzle.get("design_points",[]),1):
        fx=float(dp.get("flow_lhr",0))*factor; fig.add_vline(x=fx,line_dash="dash",annotation_text=f"P{i}",annotation_position="top")
    fig.update_layout(title=f"{model.get('model')} · Atomizing Air {curve.get('air')} barg",height=620,hovermode="x unified",xaxis=dict(title=f"Liquid Flow ({flow_unit})",domain=[.12,.88]),yaxis=dict(title="Liquid Pressure (barg)",side="left"),yaxis2=dict(title="Air Flow (Nm³/hr)",overlaying="y",side="left",position=.04),yaxis3=dict(title="Particle Size (µm)",overlaying="y",side="right"),legend=dict(orientation="h",y=1.12))
    return fig


def curve_tab(user):
    nozzle_selector(user); n=current_nozzle()
    st.subheader("Nozzle Recommendation & Digital Curve")
    recs=recommend_models(PERF_DB,float(n.get("normal_flow_lmin",0)),float(n.get("spray_angle_deg",0)))
    df=pd.DataFrame(recs[:8])[["model","family","angle","min_lmin","max_lmin","in_range","source"]]
    df.columns=["Model","Family","Angle","Min L/min","Max L/min","Normal in range","Source"]
    st.dataframe(df,use_container_width=True,hide_index=True)
    models=[r["model"] for r in recs]
    default=n.get("selected_model") if n.get("selected_model") in models else (models[0] if models else "")
    model_name=st.selectbox("Selected Model",models,index=models.index(default) if default in models else 0)
    model=find_model(PERF_DB,model_name); airs=[float(c.get("air",0)) for c in model.get("curves",[])] if model else []
    selected_air=n.get("selected_air_barg"); air=st.selectbox("Atomizing Air Curve (barg)",airs,index=min(range(len(airs)),key=lambda i:abs(airs[i]-float(selected_air))) if airs and selected_air is not None else 0)
    if st.button("Use Selected Model / Air",type="primary"):
        n["selected_model"]=model_name; n["selected_air_barg"]=air; touch(user["name"]); st.success("선택 모델을 working copy에 반영했습니다.")
    curve=find_curve(model,air)
    if not curve: st.info("Curve data 없음"); return
    flow_unit=st.radio("Graph Flow Unit",["L/min","L/hr"],horizontal=True)
    event=st.plotly_chart(performance_figure(model,curve,flow_unit,n),use_container_width=True,key=f"perf_{st.session_state.project['id']}_{st.session_state.active_nozzle}_{model_name}_{air}",on_select="rerun",selection_mode="points")
    points=[]
    try: points=event.selection.points
    except Exception: pass
    if points:
        x=points[0].get("x"); flow_lhr=float(x)*(60 if flow_unit=="L/min" else 1); st.session_state.last_selected_flow=flow_lhr
        st.caption(f"Selected graph point: {x:g} {flow_unit}")
    c1,c2=st.columns([2,1])
    manual=c1.number_input(f"Design Point Flow ({flow_unit})",min_value=0.0,value=(float(st.session_state.get('last_selected_flow',n.get('normal_flow_lmin',0)*60))/(60 if flow_unit=="L/min" else 1)),format="%.4f")
    if c2.button("Add Design Point",use_container_width=True):
        fhr=manual*(60 if flow_unit=="L/min" else 1); dp=interp(curve,fhr); dp["flow_lhr"]=fhr; dp["model"]=model_name; dp["air_barg"]=air
        if not any(abs(float(x.get("flow_lhr",-1))-fhr)<1e-6 and x.get("model")==model_name and float(x.get("air_barg",-999))==float(air) for x in n.get("design_points",[])):
            n.setdefault("design_points",[]).append(dp); touch(user["name"]); st.rerun()
    if n.get("design_points"):
        shown=[]
        for i,p in enumerate(n["design_points"],1):
            shown.append({"Point":f"P{i}","Flow L/min":float(p.get("flow_lhr",0))/60,"Liquid P barg":p.get("liquidPressure"),"Air Nm3/hr":p.get("airRate"),"D32/SMD":p.get("d32",p.get("smd")),"Dv0.9":p.get("dv09"),"Dmax":p.get("dmax"),"X90":p.get("x90"),"X99":p.get("x99")})
        st.dataframe(pd.DataFrame(shown),hide_index=True,use_container_width=True)
        if st.button("Clear Design Points"): n["design_points"]=[]; touch(user["name"]); st.rerun()


def outputs_tab(user):
    nozzle_selector(user); n=current_nozzle(); p=st.session_state.project
    st.subheader("Customer Outputs")
    a,b,c=st.columns(3)
    orient=a.selectbox("PDF Page Orientation",["landscape","portrait"],index=0 if n.get("pdf_options",{}).get("orientation","landscape")=="landscape" else 1)
    project_info=b.checkbox("Project / Customer Info",value=n.get("pdf_options",{}).get("project_info",True))
    graph_dp=c.checkbox("Graph Design Points",value=n.get("pdf_options",{}).get("graph_design_points",True))
    point_table=a.checkbox("Design Point Table",value=n.get("pdf_options",{}).get("point_table",True))
    metric_desc=b.checkbox("Graph Metric Descriptions",value=n.get("pdf_options",{}).get("metric_descriptions",True))
    flow_unit=c.selectbox("PDF Graph Flow Unit",["L/min","L/hr"])
    metric_opts=n.get("pdf_options",{}).get("metrics",{})
    selected_metrics=st.multiselect("Metric descriptions to include",list(METRIC_DESCRIPTIONS.keys()),default=[k for k in METRIC_DESCRIPTIONS if metric_opts.get(k,True)],format_func=lambda k:METRIC_DESCRIPTIONS[k][0])
    if st.button("Apply PDF Options"):
        n["pdf_options"]={"orientation":orient,"project_info":project_info,"graph_design_points":graph_dp,"point_table":point_table,"metric_descriptions":metric_desc,"metrics":{k:k in selected_metrics for k in METRIC_DESCRIPTIONS}}; touch(user["name"]); st.success("PDF options applied")

    col1,col2,col3=st.columns(3)
    try:
        xlsx=build_excel(p,n); col1.download_button("Download Data Sheet Excel",xlsx,file_name=f"{p.get('project_no') or 'PROJECT'}_{n.get('selected_model') or 'NOZZLE'}_DataSheet.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)
    except Exception as e: col1.error(str(e))
    try:
        pdf=build_performance_pdf(p,n,PERF_DB,flow_unit); col2.download_button("Download Performance Curve PDF",pdf,file_name=f"{p.get('project_no') or 'PROJECT'}_{n.get('selected_model') or 'NOZZLE'}_PerformanceCurve_Rev{n.get('performance_curve_revision','A')}.pdf",mime="application/pdf",use_container_width=True)
    except Exception as e: col2.info("PDF: "+str(e))
    col3.download_button("Download Project JSON",json.dumps(p,ensure_ascii=False,indent=2).encode("utf-8"),file_name=st.session_state.project_filename or safe_filename(p),mime="application/json",use_container_width=True)


def history_tab(user):
    p=st.session_state.project
    st.subheader("Revision History / Team")
    hist=p.get("revision_history",[])
    if hist:
        st.dataframe(pd.DataFrame([{"Revision":h.get("revision"),"Saved At":h.get("saved_at"),"Saved By":h.get("saved_by")} for h in hist]),hide_index=True,use_container_width=True)
        options=[h.get("revision") for h in hist]
        rev=st.selectbox("Revision snapshot",options,index=len(options)-1)
        row=next(h for h in hist if h.get("revision")==rev)
        with st.expander("Snapshot JSON"):
            st.json(row.get("snapshot",{}))
        if st.button("Restore snapshot to working copy"):
            restored=copy.deepcopy(row.get("snapshot",{})); restored["revision_history"]=hist; restored["current_working_revision"]=int(str(rev).lstrip("R") or 0)+1; restored["last_saved_revision"]=int(str(rev).lstrip("R") or 0); restored["updated_at"]=utc_now(); restored["updated_by"]=user["name"]
            st.session_state.project=restored; st.session_state.sync_status="Restored / unsaved"; st.rerun()
    else: st.info("아직 Revision 저장 이력이 없습니다.")
    st.caption("Owner는 표시 정보이며 수정 권한을 제한하지 않습니다. 프로젝트 hard delete는 Admin만 가능합니다.")


user=login_gate(); ensure_state(user); store,local_mode=make_store(); project_sidebar(store,local_mode,user)
st.title("⚙️ Nozzle Engineering System")
st.caption(f"{APP_VERSION} · GitHub project sync · Streamlit team app")
project_header(user)

t1,t2,t3,t4,t5=st.tabs(["Project","RFQ / Nozzles","Recommendation & Curve","Outputs","History / Admin"])
with t1: project_tab(user)
with t2: rfq_tab(user)
with t3: curve_tab(user)
with t4: outputs_tab(user)
with t5: history_tab(user)
