# unit-25 구현 노트 — 개인정보처리방침 정적 페이지 (`legal` 앱)

- 담당 REQ-ID: REQ-030
- 소속 Feature: Feature B(공개 웹 서비스 계층), 03 §1-3 unit-25 행
- **속도 트랙: L3**(오케스트레이터 호출 프롬프트에 명시적 트랙 표기 없음 → ORCHESTRATOR.md 1장 "구현 속도 트랙" 기본값 L3 적용. 06/07단계는 L3 표준 절차 그대로 따를 것 — 정식 구현, 정식 06(10섹션 전체), 정식 07, 규칙 B 원문 적용)
- 구현일: 2026-09-29
- **병렬 웨이브**: 이번 호출은 병렬 웨이브였다 — unit-20/21/24와 동시에 진행되었다(unit-19 완료 후 공통 웨이브). 아래 "공유 자원 접촉"에 상세 기록.
- 입력 문서: `docs/harness/03-system-design.md` §1-3(96~141행 패키지 레이아웃·확정 파일범위 표), §4-4(295행 라우트 표), `docs/harness/04-ux-design.md` W-2절(190~201행), `docs/harness/decisions.md` DEC-021/022/023/026/029/035/036, `docs/harness/02-planning.md` REQ-030(107행), 9절 unit-25 행(292행), `docs/harness/units/unit-19-note.md`(§2-2 편차 — unit-25가 `INSTALLED_APPS`에 `"legal"`을 직접 추가해야 한다고 예정해둔 부분)

## 1. 구현 범위

03 §1-3 unit-25 확정 파일범위(130행) 그대로:

| 파일 | 내용 |
|---|---|
| `webapp/legal/__init__.py` | 빈 패키지 초기화 파일 |
| `webapp/legal/apps.py` | `LegalConfig` 최소 AppConfig |
| `webapp/legal/views.py` | `privacy(request)` — DB/모델 조회 없는 100% 정적 렌더 뷰 |
| `webapp/legal/urls.py` | `GET /privacy/` 1개 라우트 (03 §4-4 295행과 trailing slash까지 정확히 일치) |
| `webapp/legal/templates/legal/privacy.html` | 04-ux-design.md W-2절이 요구하는 전체 콘텐츠(§2 아래 상세) |

프롬프트가 명시적으로 지시한 공유 파일 1줄 변경(범위 밖 파일이지만 사전 승인된 예외):
- `webapp/config/settings/base.py`의 `INSTALLED_APPS`에 `"legal"` 1줄 추가.
- `webapp/config/urls.py`에 `legal` 앱 include 1줄 추가.

## 2. `privacy.html` 콘텐츠 매핑 (04-ux-design.md W-2 요구사항 대비)

| W-2 요구 항목 | 구현 위치 |
|---|---|
| 처리 목적("PDF→HWPX 변환 전용") | "처리 목적" 절 |
| 수집 항목(파일명·이용자 식별정보 미수집) | "수집 항목" 절 |
| 보관기간(60분/다운로드 즉시삭제, 운영통계 30일) | "보관기간" 절 — 두 기간을 별개 항목(`<li>`)으로 분리 서술(03 §3-2 "문구 혼동 방지" 지시 반영) |
| 국외이전 고지 5항목 | "국외이전에 관한 사항" 절, `<table>`로 5개 행(이전국가/이전받는자/이전목적/보유이용기간/이전거부방법) 구성 |
| OCR 고유식별정보 고지 | "OCR 처리에 관한 안내" 절 |
| 문의 채널(GitHub Issues) | "문의" 절, `https://github.com/jcs19752510-ui/PDF-TO-HWPX/issues` (git remote origin에서 실측 확인) |
| 웹 신뢰 신호(HTTPS 자물쇠) | `.trust-banner` div |

**국외이전 5항목 중 자리표시자 처리(지시사항 그대로)**:
- "이전되는 국가": `[배포 확정 시 기재 — 예: 싱가포르 등, 최종 확정 리전]`
- "이전받는 자": `[배포 확정 시 기재 — 서버 호스팅사(Render Inc.), 데이터베이스 운영사, Cloudflare Inc.의 정확한 법인명]`
- 나머지 3항목(이전목적/보유이용기간/이전거부방법)은 03 §2-3(183행)이 이미 확정한 문구를 그대로 채웠다(자리표시자 아님 — "거부 시 서비스 이용 불가"를 정직하게 고지).

## 3. 설계서 대비 편차 (사유 포함)

1. **`legal/migrations/` 디렉터리를 만들지 않음.** `LegalConfig`는 모델을 정의하지 않으므로(02-planning.md A-21 "DB/모델 없음" 가정과 일치) 마이그레이션이 필요 없다. `manage.py check`/`makemigrations`로 이 앱에 대해 아무 문제가 없음을 확인했다(§5 실행 로그).
2. **템플릿을 어떤 공유 `base.html`도 extends하지 않고 완전히 독립적인(self-contained) HTML로 작성.** 03/04 설계서는 이 부분을 명시하지 않았으나, 작업 시점에 `webapp/` 트리 전체에 HTML 템플릿이 하나도 없었고(unit-20이 병렬로 `converter/templates/`를 만드는 중이라 공유 `base.html`이 존재/확정되지 않음) 병렬 웨이브 파일 범위 원칙상 unit-20의 템플릿 결정을 기다리지 않고 독립적으로 완성 가능해야 했기 때문이다. 04-ux-design.md 3장의 색상/타이포그래피 토큰 값은 인라인 `<style>`로 이 페이지 안에 직접 반영해 디자인 시스템과 정합을 맞췄다.
3. **(버그 발견 및 수정, 편차 아님)** 최초 작성 시 템플릿 최상단에 여러 줄짜리 Django 주석 `{# ... #}`을 넣었는데, Django의 `{# #}` 주석 태그는 **한 줄만 지원하고 여러 줄에 걸치면 주석으로 인식되지 않는다**는 사실을 로컬 렌더링 검증 중 실측으로 발견했다(§5 참고). `{% comment %}...{% endcomment %}` 블록 태그로 교체해 실제 HTTP 응답에 원본 주석 텍스트가 그대로 노출되던 문제를 해결했다.

## 4. 게이트 1 — 정적 분석/린트

- 리포지토리 루트 `pyproject.toml`에서 ruff/flake8/black/mypy/pylint 관련 설정을 다시 검색했으나 **없음을 확인**(unit-0/unit-19-note.md와 동일한 결론 — 있는데 건너뛴 것이 아니라 애초에 설정이 없다).
- 대신 `python -m py_compile`로 이번 unit이 수정/생성한 모든 `.py` 파일(`legal/apps.py`, `legal/views.py`, `legal/urls.py`, `config/urls.py`)에 대해 문법 검증 실행 → **전부 컴파일 성공**.
- `manage.py check`(Django 시스템 체크)도 0 issues로 통과.
- 병렬 웨이브 참고: 이번 unit의 범위(위 파일들) 기준으로는 전부 통과했다. 다른 병렬 단위(unit-20/21/24)의 산출물이 동시에 `base.py`/`urls.py`에 반영되고 있었으나(§6 참고), 최종 확인 시점에 `manage.py check`가 전체적으로도 0 issues였으므로 unit-25 자신의 게이트1 판정에 영향을 준 실패는 없었다.

## 5. 로컬 기동 확인 (실제 실행 결과)

임시 venv `.harness-tmp/venv_05_unit25/`에서 실행 후 규칙 K에 따라 삭제 완료.

```bash
cd webapp
python -m venv ../.harness-tmp/venv_05_unit25
../.harness-tmp/venv_05_unit25/Scripts/python.exe -m pip install -r requirements.txt
```

**차단 이슈 발견(내 파일 범위 밖, 기록만 함)**: `pip install -r requirements.txt` 후 `manage.py check`를 실행하자 `config/settings/base.py`에서 `ModuleNotFoundError: No module named 'PIL'`로 실패했다. 원인은 병렬로 진행 중인 unit-24가 `base.py`에 `from PIL import Image`(이미지 디컴프레션 폭탄 방지, `Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS`)를 추가했는데, `requirements.txt`(공유 매니페스트, 내 파일 범위 아님)에는 아직 Pillow가 반영되지 않은 상태였기 때문이다. `requirements.txt`는 공유 자원이라 직접 고치지 않고, 검증을 계속하기 위해 임시 venv에만 `pip install Pillow`를 추가로 실행해(requirements.txt는 건드리지 않음) 우회했다. **오케스트레이터 확인 필요**: unit-24(또는 unit-26)가 `requirements.txt`에 `Pillow` 추가를 반영해야 한다(§6 "공유 문서 갱신 요청" 참고 — traceability 갱신 요청이 아니라 오케스트레이터 조율 요청이라 여기 별도로 남긴다).

```bash
../.harness-tmp/venv_05_unit25/Scripts/python.exe manage.py check
# → System check identified no issues (0 silenced).

# 렌더링 검증(주석 버그 발견 지점) — render_to_string()으로 직접 렌더링해
# 5개 국외이전 항목, OCR 고지, GitHub Issues 링크, HTTPS 신뢰 배너 문자열이
# 전부 결과 HTML에 포함되어 있음을 문자열 포함 여부로 확인했다.

# manage.py runserver 127.0.0.1:8779/8780 (--noreload, 백그라운드)로 두 차례 기동:
curl -s -o - -w "\nHTTP_STATUS:%{http_code}\n" http://127.0.0.1:8780/privacy/
# → HTTP_STATUS:200, 본문에 <!DOCTYPE html> 직후 {% comment %} 흔적 없음(수정 후 재검증),
#   5개 국외이전 항목 테이블·OCR 안내·GitHub Issues 링크·HTTPS 신뢰 배너 전부 포함.

../.harness-tmp/venv_05_unit25/Scripts/python.exe manage.py check
# → System check identified no issues (0 silenced). (최종 재확인)
```

작업 종료 시 임시 venv(`.harness-tmp/venv_05_unit25/`), 서버 로그, 렌더 출력 파일을 전부 삭제했다. `webapp/db.sqlite3`는 병렬로 실행 중인 다른 unit의 검증 세션이 사용 중일 가능성이 있어(공유 dev DB 파일, git으로 추적되지 않음/`.gitignore` 대상) 임의로 삭제하지 않았다(내가 만들지 않았을 수 있는 파일을 병렬 실행 중 삭제하는 것은 규칙 K "재생성 가능한 산출물만 정리, 애매하면 확인" 원칙에 어긋난다고 판단).

## 6. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 — 라우트(`GET /privacy/`), 파일 범위(`legal/views.py`, `legal/templates/legal/privacy.html`), W-2절이 요구한 7개 콘텐츠 항목(§2 표) 전부 반영. 국외이전 5항목의 자리표시자 표기도 지시사항 그대로.
- [x] 에러 처리가 누락된 경로가 없는가 — 이 페이지는 DB/API 의존이 전혀 없는 순수 정적 템플릿 렌더이므로(04-ux-design.md W-2 "정상 상태만 존재") 실패할 수 있는 경로 자체가 없다. `render()`가 템플릿을 못 찾으면 Django가 표준 `TemplateDoesNotExist` 500을 내는데, 로컬 기동 검증(§5)에서 200이 실제로 나옴을 확인했으므로 이 경로는 발생하지 않는다.
- [x] 입력값 검증이 시스템 경계에서 이루어지는가 — 이 뷰는 사용자 입력(쿼리스트링/바디/헤더)을 전혀 받지 않는다(`request` 인자를 읽지 않음). 검증할 입력 자체가 없다.
- [x] 하드코딩된 시크릿/자격증명이 없는가 — 없음. 국외이전 5항목 중 실제 법인명이 필요한 2항목은 의도적으로 자리표시자 문자열로 남겨뒀다(지시사항).
- [x] 새로 추가한 외부 의존성이 실제 레지스트리에 존재하는지 확인했는가 — 이번 unit은 새 Python 패키지를 추가하지 않았다(N/A). GitHub Issues URL(`https://github.com/jcs19752510-ui/PDF-TO-HWPX/issues`)은 `git remote -v`로 실제 origin을 조회해 확인한 값이다(지어내지 않음).
- [x] 범위를 벗어난 변경(곁다리 리팩터링 등)이 섞여 있지 않은가 — `webapp/legal/` 신규 파일과, 프롬프트가 명시적으로 지시한 `config/settings/base.py`(`INSTALLED_APPS` 1줄) / `config/urls.py`(include 1줄) 외에는 어떤 파일도 수정하지 않았다(`git status --short`로 확인, 다른 병렬 unit이 만든 파일들은 손대지 않음).

## 7. 6단계 테스터가 확인해야 할 인수 조건(Acceptance Criteria)

- **AC-1 (라우트/응답코드)**: `GET /privacy/` 요청 시 HTTP 200, `Content-Type: text/html`.
- **AC-2 (처리 목적/수집 항목)**: 응답 본문에 "PDF" 및 "HWPX" 문자열이 포함되고(변환 전용 목적 고지), "파일명"과 "이용자를 식별할 수 있는 정보"를 수집하지 않는다는 취지의 문장이 포함되어야 한다.
- **AC-3 (보관기간 이중 서술)**: 응답 본문에 "60분"(업로드/변환 파일 보관)과 "30일"(운영 통계 파기)이 **서로 다른 문장/항목으로** 등장해야 한다(두 기간이 하나로 뭉뚱그려 서술되면 FAIL — 03 §3-2 지시사항 위반).
- **AC-4 (국외이전 5항목 전부 존재)**: 응답 본문(HTML 테이블)에 "이전되는 국가", "이전받는 자", "이전 목적", "보유·이용기간", "이전 거부 방법" 5개 항목명이 모두 존재해야 한다. "이전되는 국가"·"이전받는 자" 값에는 `[배포 확정 시 기재`로 시작하는 자리표시자 텍스트가 있어야 하고(실제 법인명이 임의로 들어가 있으면 FAIL), "이전 거부 방법" 값에는 "이용하실 수 없습니다"(거부 시 서비스 이용 불가) 취지가 명시되어야 한다.
- **AC-5 (OCR 고지)**: 응답 본문에 "OCR"과 "고유식별정보"가 함께 포함된 문장이 있어야 한다.
- **AC-6 (문의 채널)**: 응답 본문에 `https://github.com/jcs19752510-ui/PDF-TO-HWPX/issues` 링크(`<a href="...">`)가 있어야 하고, 이메일 주소 형태의 문의처(mailto: 등)는 없어야 한다(익명 운영 원칙, DEC-023).
- **AC-7 (신뢰 신호 문구)**: 응답 본문에 "HTTPS"와 "자물쇠" 문구가 포함되어야 하고, v2의 "127.0.0.1"/"안전" 관련 문구는 없어야 한다.
- **AC-8 (템플릿 렌더링 정합성 — 이번 unit에서 실제 발견한 버그의 회귀 방지)**: 응답 본문 어디에도 `{#`, `#}`, `{% comment %}`, `{% endcomment %}` 문자열이 그대로 노출되지 않아야 한다(주석이 실제로 렌더링에서 제거됐는지 확인).
- **AC-9 (INSTALLED_APPS/URL 배선)**: `config.settings.dev`로 로드했을 때 `INSTALLED_APPS`에 `"legal"`이 포함돼야 하고, `manage.py check`가 0 issues로 통과해야 한다.
- **AC-10 (범위 확인)**: `git diff --stat` 기준으로 이번 unit이 건드린 파일이 `webapp/legal/**`, `webapp/config/settings/base.py`(INSTALLED_APPS 1줄), `webapp/config/urls.py`(include 1줄)로 한정되는지 확인한다(다른 병렬 unit의 파일 diff와 섞여 있을 수 있으므로, 리뷰 시 `legal` 관련 diff만 골라 확인).
- **수동 확인 권고**: 국외이전 5항목 중 자리표시자로 남긴 실제 법인명(Render Inc./DB 운영사/Cloudflare Inc.)은 배포 확정 시 unit-26 또는 별도 후속 작업에서 실제 값으로 채워야 한다 — 이번 unit의 검증 범위가 아니다(자리표시자로 남아있는 것 자체가 PASS 조건, §2 참고).

## 8. 공유 문서 갱신 요청 (오케스트레이터가 웨이브 종료 후 일괄 반영)

### traceability.md

`docs/harness/traceability.md`의 REQ-030 행(43행 부근)을 아래와 같이 갱신 요청:

| 컬럼 | 값 |
|---|---|
| 구현 상태 | Implemented (unit-25 완료, 06단계 대기) |
| 단위테스트 | 06단계 대기 |
| 비고 (기존 내용에 추가) | unit-25 구현 완료(`webapp/legal/`) — 국외이전 5항목 전부 반영, "이전되는 국가"/"이전받는 자" 2항목은 지시사항에 따라 자리표시자로 남김(배포 확정 시 채움). 상세는 `docs/harness/units/unit-25-note.md` 참고. |

### 오케스트레이터 조율 요청 (traceability/decisions 갱신은 아니지만 병렬 웨이브 조율 필요)

- **`webapp/requirements.txt`에 `Pillow` 추가 필요** — unit-24가 `config/settings/base.py`에 `from PIL import Image`를 추가했으나(§5에서 실측 확인) 공유 매니페스트인 `requirements.txt`에는 아직 반영되지 않았다. 이 상태로는 신규 venv에서 `pip install -r requirements.txt` 후 `manage.py check`가 즉시 `ModuleNotFoundError`로 실패한다. unit-24 또는 unit-26(요구사항 파일 최종 정리 담당)이 이 갱신을 담당해야 한다.
