# Nozzle Engineering System — HTML Team Edition v2

이 버전은 **기존 v2.16 HTML UI/그래프를 메인 프로그램으로 그대로 사용**하고, Streamlit은 로그인과 GitHub 저장/불러오기만 담당합니다.

## 기존 Team Edition v1과 다른 점
- Streamlit 위젯으로 RFQ/그래프를 다시 만들지 않습니다.
- 원본 HTML의 카드, RFQ Quick Import, Source-style Digital Curve, Hover, Multi Design Point, Data Sheet, Excel, Performance Curve PDF, PDF 옵션/Metric 설명을 그대로 사용합니다.
- HTML 위에 얇은 `TEAM SYNC` 바만 추가됩니다.
- `Working Copy 저장` / `Revision 저장` 버튼이 GitHub Data Repo와 직접 동기화됩니다.

## 현재 사용 중인 Streamlit Secrets는 그대로 사용
```toml
[github]
token = "github_pat_..."
data_repo = "oliver-hjw/nozzle-engineering-data"
branch = "main"
projects_path = "projects"

[team.users.oliver]
name = "Oliver"
role = "Admin"
pin_sha256 = "..."
```

## 기존 Streamlit 앱 교체
1. 현재 `nozzle-engineering-app` GitHub 저장소의 파일을 이 ZIP 내용으로 교체합니다.
2. GitHub에서 Commit 합니다.
3. Streamlit Community Cloud가 같은 `streamlit_app.py`를 자동 재배포합니다.
4. 기존 Secrets는 지우지 않습니다.

## 팀 사용 흐름
1. 로그인
2. 상단 `TEAM SYNC`에서 GitHub 프로젝트 선택 → Open
3. 평소처럼 기존 HTML에서 작업
4. RFQ 화면의 `Working Copy 저장` → GitHub 동기화
5. `Revision 저장` → Revision 생성 + GitHub 저장
6. Excel/PDF는 기존 HTML 방식 그대로 브라우저에서 다운로드

## 중요
기존 Data Repo에 Team Edition v1 형식의 TEST 프로젝트가 있어도 열 수 있도록 호환 변환을 포함했습니다. 새로 저장되는 프로젝트는 HTML v2.16 구조를 그대로 JSON으로 저장합니다.
