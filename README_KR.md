# Nozzle Engineering System — GitHub Team Edition v1.0

소규모 팀이 **월 비용 0원으로 시작**할 수 있도록 구성한 Streamlit + GitHub 버전입니다.

## 권장 구조

```text
[Private App Repo] nozzle-engineering-app
        │
        └─ Streamlit Community Cloud에서 streamlit_app.py 배포

[Private Data Repo] nozzle-engineering-data
        │
        └─ projects/*.json  ← 팀 공용 프로젝트 저장
```

**App Repo와 Data Repo를 분리하는 것을 권장합니다.** Streamlit Community Cloud는 배포된 앱의 GitHub 소스 저장소에 커밋이 들어오면 앱에 변경을 반영합니다. 따라서 프로젝트 저장 데이터를 같은 저장소에 계속 커밋하면 업무 저장 자체가 앱 업데이트로 인식될 수 있습니다. Data Repo를 별도로 두면 이 문제를 피할 수 있습니다.

---

## 현재 Team Edition v1 기능

- Streamlit 웹 UI
- GitHub Private Data Repo 공용 프로젝트 저장/불러오기
- Working Copy 저장과 Project Revision 저장 분리
- `Last Saved Rxx / Current Working Rxx`
- GitHub SHA 기반 동시 수정 충돌 방지
- Owner / Updated By / Updated At 표시
- Member / Admin 역할
- Admin만 Project hard delete
- 프로젝트 내 Nozzle 1~5개
- RFQ 입력
- RFQ 텍스트 Quick Import → 검토 → 선택 적용
- Fluid / Injection Type / Qty / Min·Normal·Max Flow / Air Pressure / Spray Angle 등
- 13개 디지털 성능 데이터 모델 포함
- Normal Flow 기준 모델 추천
- 모델 / Atomizing Air curve 선택
- Interactive Digital Performance Curve
- 그래프 선택 포인트 또는 직접 Flow 입력으로 Design Point 추가
- L/min / L/hr 그래프 단위 선택
- Multi Design Points
- Data Sheet Excel 다운로드
- Performance Curve PDF 다운로드
- PDF 가로/세로
- Project Info / Design Point / Point Table / Metric Description 포함 여부 선택
- Project JSON 백업 다운로드
- Revision snapshot 확인 및 Working Copy 복원
- 기존 v2.16 단일 HTML을 `legacy/`에 보존

> Team Edition v1은 기존 단일 HTML을 그대로 서버에 얹은 것이 아니라, 팀 공유에 필요한 핵심 기능을 Streamlit/Python으로 이식한 MVP입니다. PDF/Excel의 세부 디자인은 기존 HTML 버전과 픽셀 단위로 완전히 동일하지 않을 수 있습니다.

---

# 1. GitHub App Repo 만들기

GitHub에서 **Private repository** 하나를 생성합니다.

예시:

```text
nozzle-engineering-app
```

이 ZIP의 내용 전체를 해당 저장소 **루트**에 업로드합니다.

중요 파일:

```text
streamlit_app.py
engineering.py
github_store.py
outputs.py
requirements.txt
.streamlit/config.toml
.streamlit/secrets.toml.example
data/performance_data.json
```

실제 `.streamlit/secrets.toml`은 GitHub에 올리지 마세요. `.gitignore`에 이미 제외되어 있습니다.

---

# 2. GitHub Data Repo 만들기

두 번째 **Private repository**를 만듭니다.

예시:

```text
nozzle-engineering-data
```

README 파일 하나만 생성해도 됩니다. 프로그램이 프로젝트를 저장하면 아래처럼 자동 생성됩니다.

```text
projects/
  PROJECT-A__xxxxxxxxxx.json
  PROJECT-B__xxxxxxxxxx.json
```

프로젝트 JSON 변경 자체가 Git commit이므로 GitHub History가 추가 백업 역할을 합니다.

---

# 3. GitHub Fine-grained PAT 만들기

GitHub Settings → Developer settings → Personal access tokens → Fine-grained tokens에서 생성합니다.

권장 범위:

- Repository access: `nozzle-engineering-data` **하나만 선택**
- Repository permissions
  - Contents: **Read and write**
  - Metadata: Read-only (기본)

App Repo에 쓰기 권한을 줄 필요는 없습니다.

생성된 토큰은 GitHub 코드에 넣지 않고 **Streamlit Secrets에만 저장**합니다.

---

# 4. 팀 PIN Hash 만들기

로컬 PC에서:

```bash
python make_pin_hash.py
```

PIN을 입력하면 SHA-256 hash가 출력됩니다.

예시 Secrets 구조:

```toml
[team.users.oliver]
name = "Oliver"
role = "Admin"
pin_sha256 = "생성된 SHA256"

[team.users.member1]
name = "Member 1"
role = "Member"
pin_sha256 = "생성된 SHA256"
```

이 앱 내부 PIN은 **Admin/Member 역할을 구분하는 가벼운 내부 제어**입니다. 앱 자체 접근 제한은 Streamlit Community Cloud의 Private App Viewer 권한을 함께 사용하세요.

---

# 5. Streamlit Secrets 입력

`.streamlit/secrets.toml.example` 내용을 참고합니다.

예시:

```toml
[github]
token = "github_pat_xxxxxxxxx"
data_repo = "YOUR_GITHUB_ID/nozzle-engineering-data"
branch = "main"
projects_path = "projects"

[team.users.oliver]
name = "Oliver"
role = "Admin"
pin_sha256 = "SHA256_HASH"

[team.users.member1]
name = "Member 1"
role = "Member"
pin_sha256 = "SHA256_HASH"
```

---

# 6. Streamlit Community Cloud 배포

1. `https://share.streamlit.io/` 로그인
2. **Create app**
3. GitHub의 `nozzle-engineering-app` Private Repo 선택
4. Branch: `main`
5. Main file path: `streamlit_app.py`
6. Advanced settings
   - Python: **3.12 권장**
   - Secrets: 위 TOML 내용 붙여넣기
7. Deploy

`requirements.txt`가 필요한 Python 패키지를 자동 설치합니다.

---

# 7. 팀원에게 공유

Streamlit 앱 우측 상단 **Share**에서 팀원 이메일을 Viewer로 초대합니다.

그 다음 팀원은:

```text
앱 URL 접속
→ Streamlit Private App 로그인
→ Nozzle System 내부 User + PIN 로그인
→ 공용 Project 사용
```

순서로 사용합니다.

---

# 동시 수정 방지 방식

프로젝트를 열 때 GitHub 파일의 SHA를 기억합니다.

예:

```text
Oliver가 Project A 열기 → SHA = abc123
Amy가 Project A 저장 → GitHub SHA = def456
Oliver가 예전 화면에서 저장 시도
→ abc123 != def456
→ 저장 중단 + Conflict 경고
```

따라서 마지막 저장자가 다른 사람의 변경 내용을 조용히 덮어쓰는 것을 방지합니다.

충돌 메시지가 나오면 현재 Working Copy를 별도 JSON으로 다운로드한 후, GitHub 최신 프로젝트를 다시 Open해서 필요한 변경을 합치는 방식이 안전합니다.

---

# Revision 정책

### Save Working Copy

일반 작업 저장입니다. Revision 번호를 증가시키지 않습니다.

### Revision 저장

현재 Working Revision을 공식 Project Revision snapshot으로 저장합니다.

초기 프로젝트:

```text
Last Saved R--
Current Working R00
```

첫 `Revision 저장` 후:

```text
Last Saved R00
Current Working R01
```

다음 Revision 저장 후:

```text
Last Saved R01
Current Working R02
```

Data Sheet Revision과 Performance Curve Revision은 Nozzle별 별도 문서 Rev로 유지됩니다.

---

# 권한

### Member

- Project 생성
- 공용 Project Open
- 수정
- Working Copy 저장
- Revision 저장
- Excel/PDF 출력

### Admin

Member 기능 +

- Project hard delete

`Owner`는 담당자 표시용이며 ACL로 사용하지 않습니다.

---

# 로컬 테스트

Windows:

```text
run_local.bat
```

macOS/Linux:

```bash
./run_local.sh
```

Secrets가 없으면 프로그램은 `LOCAL DEMO MODE`로 실행됩니다.

Demo 로그인:

```text
User: Demo Admin
PIN: 0000
```

**주의:** Streamlit Community Cloud에서 LOCAL DEMO MODE의 파일은 영구 프로젝트 DB로 사용하면 안 됩니다. 실제 팀 운영에서는 반드시 GitHub Data Repo를 연결하세요.

---

# 데이터 보안 메모

이 구성은 무료이고 간단하지만 고객 RFQ/프로젝트 JSON은 GitHub Private Repo에, 실행 앱은 Streamlit Community Cloud에 위치합니다. 회사 보안 정책상 고객/프로젝트 자료의 외부 클라우드 저장이 금지되어 있다면 이 구성 대신 사내 서버 배포가 필요합니다.

GitHub token은 반드시 Data Repo 하나에만 최소 권한으로 발급하고 Streamlit Secrets에 보관하세요.

---

# 폴더 구조

```text
nozzle-engineering-app/
├─ streamlit_app.py
├─ engineering.py
├─ github_store.py
├─ outputs.py
├─ requirements.txt
├─ make_pin_hash.py
├─ run_local.bat
├─ run_local.sh
├─ README_KR.md
├─ .gitignore
├─ .streamlit/
│  ├─ config.toml
│  └─ secrets.toml.example
├─ data/
│  └─ performance_data.json
├─ projects/
│  ├─ README.md
│  └─ DEMO-001__sample.json
└─ legacy/
   └─ Nozzle_Engineering_System_v2_16_TextRFQ_Only.html
```

---

# 다음 개선 후보

- GitHub 프로젝트 검색/필터
- Project lock indicator
- 동일 Project 변경 내용 diff 화면
- Revision snapshot 별도 GitHub 파일 분리
- User별 최근 열어본 Project
- PDF/Excel 기존 HTML 양식과 1:1 정밀 일치
- Digital Curve 클릭 시 임의 보간점 직접 저장 UX 개선
- Project 완료 시 Working Copy lock
- Microsoft/Google OIDC 기반 사용자 자동 식별
