# unit-20 구현 노트 — converter 앱 웹 뷰/템플릿/프런트엔드

- 담당 REQ-ID: REQ-001, REQ-010, REQ-015
- 확정 파일 범위: `webapp/converter/views.py`, `webapp/converter/urls.py`(신규),
  `webapp/converter/templates/converter/*.html`, `webapp/converter/static/converter/app.js`,
  `webapp/config/urls.py`(1줄 include, 03 §1-3 unit-20 행 명시 허용)
- **속도 트랙: L3**(오케스트레이터로부터 별도 트랙 지정 없음 — ORCHESTRATOR.md 1장 기본값 적용)
- **병렬 실행**: 이 unit은 병렬 웨이브로 진행됐다. 동시에 진행 중이던 unit: **unit-21**(`converter/executor.py`), **unit-24**(`converter/limits.py`, `core/middleware.py`), **unit-25**(`legal/` 앱). 작업 종료 시점에 세 unit 모두 이미 파일을 생성 완료한 상태였다(구현 도중 확인).

## 1. 구현 범위

### 1-1. 라우트(views.py/urls.py) — 03 §4-4 그대로
- `GET /` (`index`): 업로드 폼 + 4패널 셸 렌더. `limits.py`(unit-24)에서 `MAX_UPLOAD_SIZE_BYTES`/`CONVERSION_SOFT_TIMEOUT_SECONDS`를 읽어와 템플릿에 `json_script`로 흘려보낸다(사전고지 문구/클라이언트 타이머와 실제 서버 상수가 어긋나지 않도록).
- `POST /convert` (`convert`): 파일 존재/PDF 여부 검증(400) → OCR 체크박스+언어 검증(400) → `storage.save_uploaded_file()`로 저장 → `ConversionJob(PENDING)` 생성 → `executor.submit_job(job_id)` 호출(지연 import, 아래 2절 참고) → 202 `{"job_id": ...}` 또는 `QueueFullError` 캐치 시 503.
- `GET /api/jobs/<uuid:job_id>/` (`job_status`): DB 조회만, 존재하지 않거나 `EXPIRED` 상태면 404.
- `GET /download/<uuid:job_id>/` (`download`): 상태별 분기(PENDING/PROCESSING→409, FAILED→422 일반문구, DONE+result_success=False→422+errors, DONE+True→200 스트리밍). 스트리밍 완료(파일 핸들 `close()` 시점) 후에만 `downloaded_at`/`purged_at` 기록 + `storage.delete_job_objects()` 호출 — `_AutoDeleteFile` 래퍼로 구현(아래 3절).

### 1-2. 템플릿
- `_base.html`: 헤더(스킵링크, 서비스명, 상시 배너), `<main>`, 푸터(개인정보처리방침/후원하기/GitHub/라이선스 문구), 색상·타이포 토큰을 인라인 `<style>`로 포함(04 §3-1/§3-2 값 그대로), `{% static 'converter/app.js' %}` 로드.
- `index.html`: `noscript` 경고 + Panel A(업로드)/B(진행)/C(결과)/D(조회불가) 4개 `<section>`을 한 페이지에 모두 렌더하고 JS가 `.is-active` 클래스로 전환한다.

### 1-3. app.js
- 파일 선택/OCR 언어 유효성검사/제출 버튼 활성화 로직.
- `POST /convert` fetch(폼 자체에서 `FormData` 생성 → CSRF 히든필드 자동 포함) → 202/413/429/503/기타 분기(04 §1-2 문구 그대로).
- `GET /api/jobs/<id>/` 0.75초 간격 폴링, 5초 응답지연 배너, 폴링 네트워크 실패 시 최대 3회 후 오프라인 배너(자동 재개, 04 §6-3), 5분 경과+processing 시 소프트타임아웃 배너(클라이언트 타이머, 04 §7 표 그대로).
- 결과 렌더: `result_warnings`/`result_errors` 코드→아이콘/메시지 매핑(04 §2 Panel C 표 그대로 이식).
- 다운로드: `fetch('/download/<job_id>/')` → `blob()` → `URL.createObjectURL` → 동적 `<a download>` 클릭 → `revokeObjectURL`(직접 URL 이동 아님, 04 §1-3 필수 요구사항 충족).
- `sessionStorage["job:pending:filename"]` → `job:<job_id>:filename` 승격, 다운로드 시 `.pdf`→`.hwpx` 치환(없으면 `converted.hwpx`로 조용히 대체).
- `history.replaceState`로 `/?job=<job_id>` 반영, 페이지 재진입 시 그 값으로 폴링 재개(Could-have 중 "새로고침 복원"만 구현).
- 패널 전환 시 새 패널 `<h1 tabindex="-1">`로 포커스 이동(04 §5-1).

## 2. 설계서 대비 편차 및 사유

1. **소프트타임아웃(5분) 판정 주체**: 03 §4-4 원문은 "views.py의 폴링 응답 생성 시" 판정한다고 서술하지만, **04-ux-design.md §7**이 이미 이 문장을 "클라이언트 타이머(sessionStorage 제출시각 기준)로 해소 — 서버가 별도 필드를 내려줄 필요 없음"이라고 명시적으로 정리해뒀다(04는 PASS 확정 문서). 본 unit은 04의 이 해석을 그대로 따라 **서버(job_status)는 타임아웃을 전혀 판정하지 않고**, `app.js`가 `state.submittedAt` 대비 경과시간으로 배너를 띄운다. 다만 `converter/limits.py`(unit-24)의 주석은 "실제 판정은 unit-20의 폴링 응답 생성 로직 몫"이라고 03 원문 그대로 서술해뒀는데, 이는 unit-24가 04의 해소 결정을 인지하지 못하고 03만 참고해 남긴 주석으로 보인다 — **코드 동작에는 영향 없음**(값만 참조), 다만 오케스트레이터가 unit-24-note.md와 대조해 문서상 혼선이 없는지 확인 권장.
2. **CSS를 별도 정적 파일로 만들지 않고 `_base.html`의 인라인 `<style>`로 구현**: 03 §1-3 패키지 레이아웃(96~120행)이 `static/converter/*.js`만 명시하고 `*.css`를 나열하지 않았다 — 확정 파일범위를 벗어난 새 정적 파일(`style.css`)을 임의로 추가하지 않기 위한 선택이다. 디자인 시스템(04 §3)의 색상/타이포/간격 토큰은 모두 반영했다.
3. **`/download/`, `/api/jobs/`의 404/기타 에러 응답에 JSON 바디를 포함**: 03/04는 이 엔드포인트들의 에러 바디 스키마를 규정하지 않았다(04 §7 "에러 바디 스키마 미정 — 클라이언트는 상태코드만 사용"). 본 unit은 순수 상태코드 404/409/422/503만으로 프런트 분기를 만들었고(04 §7과 정합), 다만 서버 쪽 응답에 `{"error": "..."}` 최소 바디를 실어 API 소비자(디버깅/향후 재사용) 편의를 더했다 — 프런트가 이 바디 내용에 의존하지 않으므로 규칙 위반은 아니다.
4. **후원 링크(`href="#"`) placeholder 유지**: 03 §1-3 unit-18 행이 "삽입 지점이 `converter/templates/converter/index.html`(unit-20 소유 파일)로 이동, 순차(unit-20 이후)"라고 명시했으므로, 실제 `SPONSOR_URL`은 이번 unit이 채우지 않고 자리표시자만 남겼다(`_base.html` 푸터, HTML 주석으로 unit-18 인계 표시). GitHub 링크는 이미 공개된 저장소 주소(`https://github.com/jcs19752510-ui/PDF-TO-HWPX`)를 그대로 사용했다.
5. **"진행상황 링크 복사" 버튼(04 §2 Panel B, 명시적 Could-have)은 구현하지 않음** — 04 원문이 "05단계가 시간이 부족하면 생략 가능"이라고 명시했고, `job_id` URL 반영(`?job=`) 자체는 구현했으므로 핵심 가치(새로고침 복원)는 유지된다.
6. **업로드 크기(50MB) 서버측 방어는 이 unit이 수행하지 않음** — 오케스트레이터 지시 및 03 §1-3 unit-24 행에 따라 `ContentLengthLimitMiddleware`(unit-24, `core/middleware.py`)에 전적으로 위임했다. `convert()` 뷰는 파일 존재/PDF 여부만 검증한다.
7. **`converter.executor` 지연(lazy) import**: `views.py` 모듈 최상단이 아니라 `convert()` 함수 내부에서 `from .executor import submit_job, QueueFullError`를 import한다. 병렬 웨이브 시작 시점에 `executor.py`가 아직 없을 수 있다는 지시사항에 따른 방어이며, 없을 경우 `ImportError`를 잡아 503("서버가 바쁩니다")으로 폴백한다. **실제로는 구현 완료 시점에 unit-21이 이미 `executor.py`를 완성해뒀음을 확인**했고(2절), 방어 코드는 그대로 남겨둔다(정상 배포 시 해가 되지 않는 코드).

## 3. `_AutoDeleteFile` 구현 노트 (설계서에 없는 구현 세부, 계약 위반 아님)

03 §4-4는 "스트리밍이 끝나면 즉시 삭제"라고만 서술하고 구현 방법은 위임했다. `FileResponse`가 스트리밍을 완전히 마친 뒤에만 파일 핸들의 `close()`를 호출하는 Django 내부 동작(`_resource_closers`)을 이용해, `close()`가 호출된 시점에 (a) 원본 파일 핸들을 먼저 닫고 (b) 그 다음에 `storage.delete_job_objects()` + `downloaded_at`/`purged_at` 갱신을 실행하는 래퍼 클래스로 구현했다. 로컬(FileSystemStorage, Windows) 환경에서 "열려있는 파일을 지우려다 잠금 오류가 나는" 문제를 피하기 위한 순서다 — 실측으로 정상 동작 확인(4절).

## 4. 로컬 동작 확인 (`.harness-tmp/venv_05_unit20/`, 작업 완료 후 정리함)

`python -m venv` + `pip install -r webapp/requirements.txt` + `pip install -e .`(pdf_to_hwpx editable) 후:

1. `python manage.py check` → `System check identified no issues (0 silenced)`.
2. `python manage.py migrate` → 정상.
3. `python manage.py runserver` 기동 후:
   - `GET /` → **HTTP 200**, 렌더된 HTML에 `PDF→HWPX 변환`/`panel-a`/`csrfmiddlewaretoken`/`max-upload-mb` 마커 확인.
   - `GET /healthz` → 200, `GET /static/converter/app.js` → 200.
   - `POST /convert`(curl, CSRF 쿠키+토큰 수동 첨부, pypdf로 생성한 1페이지 더미 PDF 업로드) → **HTTP 202**, `{"job_id": "..."}` 반환.
   - `GET /api/jobs/<job_id>/` 반복 폴링 → `pending`을 거치지 않고(더미 PDF라 즉시) `status=done, result_success` 계열 정상 반환 — **unit-21의 실행기가 실제로 스레드풀에서 `orchestrator.convert()`를 호출해 결과를 DB에 기록하는 것까지 end-to-end로 확인됨** (이 unit의 목표를 넘어선 통합 확인이지만, 병렬 웨이브 특성상 자연스럽게 검증됨).
   - `GET /download/<job_id>/` → **HTTP 200**, `Content-Disposition: attachment; filename="converted.hwpx"`, 응답 바이트가 실제 HWPX(zip 기반, `file` 명령으로 `Hancom HWP ... HWPX` 확인)임을 확인.
   - 같은 job으로 **재다운로드 시도 → HTTP 404**(삭제 후 재요청, 의도된 동작) 확인.
   - `GET /api/jobs/00000000-0000-0000-0000-000000000000/`(존재하지 않는 UUID) → 404 확인.
   - `POST /convert`(파일 누락) → 400 + `{"error": "파일이 없습니다."}` 확인.
4. `python -m py_compile`로 `views.py`/`urls.py`/`config/urls.py` 구문 확인, `node --check`로 `app.js` 구문 확인(둘 다 통과).
5. 작업 종료 후 `db.sqlite3`, `.dev-media/`, 임시 venv, curl 테스트 산출물 전부 삭제(규칙 K).

## 5. 게이트 1 — 정적 분석/린트

프로젝트 전체(루트 `pyproject.toml`, `webapp/`)에 **ruff/flake8/black/mypy/eslint 등 설정이 존재하지 않는다**(확인: `pyproject.toml`에 `[tool.ruff]`/`[tool.black]` 등 섹션 없음, `.flake8`/`ruff.toml`/`.eslintrc*`/`mypy.ini` 파일 자체가 저장소에 없음). 설정이 없으므로 이 게이트는 "생략 가능"이 아니라 **"검사 대상 설정이 없음"으로 사실만 기록**하고, 대체 확인으로 `python -m py_compile`(3개 파일) + `node --check`(app.js) 구문 검사를 수행해 전부 통과했다(4절 4번).

## 6. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현 일치 — 03 §4-4 라우트 표·상태 전이 규칙, 04 §1~§5 화면/컴포넌트/접근성 요구를 항목별로 대조하며 구현(2절에 편차 전부 명시, 임의 편차 없음).
- [x] 에러 처리 누락 경로 없음 — `convert()`/`job_status()`/`download()` 모두 방어적으로 처리되지 않은 예외는 그대로 전파시켜(예: DB 저장 실패, 스토리지 I/O 실패 등 "진짜 예상 못한" 예외) Django 표준 500 처리(§7-2 `mail_admins` 자동알림)로 넘긴다 — 조용히 삼키는 `except: pass` 없음. `executor` 미존재(ImportError)/큐포화(QueueFullError)/입력값 오류(400)는 각각 명시적으로 처리.
- [x] 입력값 검증이 시스템 경계에서 이루어짐 — `POST /convert`에서 파일 존재 여부, PDF 확장자/MIME, OCR 언어 최소 1개 선택을 뷰 진입 즉시 검증(400). 업로드 크기는 의도적으로 미들웨어(unit-24)에 위임(2-6절).
- [x] 하드코딩된 시크릿/자격증명 없음 — 이 unit이 만든 파일에는 시크릿을 다루는 코드 자체가 없음(스토리지/DB 자격증명은 unit-19/24 settings 영역).
- [x] 신규 외부 의존성 없음 — 이 unit은 `requirements.txt`/`pyproject.toml`을 수정하지 않았고 새 패키지를 추가하지 않았다(Django 표준 기능 + 기존 unit-19/21/24 산출물만 소비).
- [x] 범위를 벗어난 곁다리 리팩터링 없음 — `models.py`/`storage.py`/`executor.py`/`limits.py`/`core/middleware.py`/`legal/` 등 타 unit 소유 파일은 전혀 수정하지 않았다(단, `config/urls.py`/`config/settings/base.py`는 병렬 충돌 관련 3-1절 참고).

## 7. 6단계 테스터를 위한 인수 조건(Acceptance Criteria)

- **AC-1**: `GET /` → 200, 응답 HTML에 4개 패널(`#panel-a~d`) DOM, `noscript` 경고, `{% csrf_token %}` 히든필드, `/static/converter/app.js` 참조가 모두 존재.
- **AC-2**: 유효한 PDF(≤50MB, `.pdf` 확장자 또는 `application/pdf` MIME) + CSRF 토큰으로 `POST /convert` → 202 + `{"job_id": "<uuid4>"}`, 동시에 `ConversionJob(status=PENDING)` 행이 생성되고 스토리지에 `uploads/<job_id>.pdf`가 저장됨.
- **AC-3**: `file` 파트 누락 → 400 JSON. `.txt` 등 비-PDF 업로드(확장자 불일치 + MIME 불일치 동시) → 400 JSON.
- **AC-4**: `enable_ocr=on`이면서 `ocr_lang_kor`/`ocr_lang_eng` 둘 다 미포함 → 400 JSON("OCR 언어를 최소 1개 선택해야 합니다.").
- **AC-5**: PENDING+PROCESSING 합계가 20건 이상인 상태에서 `POST /convert` → 503 JSON("지금은 이용자가 많아…"), 이때 새로 생성된 job 행/업로드 파일은 삭제되지 않고 그대로 남는다(cleanup, unit-22 책임 — 06단계는 이 unit의 결함으로 반려하지 말 것). *주의: 이번 unit 자체 테스트에서 20건 생성 재현까지는 수행하지 않았음(6절 "수동 확인 필요" 참고), 코드 경로만 확인.*
- **AC-6**: 존재하지 않는/EXPIRED `job_id`로 `GET /api/jobs/<job_id>/` 또는 `GET /download/<job_id>/` → 둘 다 404.
- **AC-7**: PENDING/PROCESSING 상태 job을 `GET /download/<job_id>/` → 409.
- **AC-8**: `status=failed`인 job을 다운로드 → 422 + 내부 원인이 노출되지 않는 고정 일반 문구(“서버 처리 중 오류가 발생했습니다. 다시 시도해주세요.”), `result_errors` 내용과 무관하게 항상 이 문구.
- **AC-9**: `status=done, result_success=false`인 job을 다운로드 → 422 + `{"errors": [...]}`(내용은 `result_errors` 그대로).
- **AC-10**: `status=done, result_success=true`인 job을 다운로드 → 200, `Content-Disposition: attachment; filename="converted.hwpx"`, 응답 바이트가 유효한 HWPX(zip) 파일. 스트리밍 완료 후 같은 `job_id`로 재다운로드 시 404(오브젝트 삭제 확인).
- **AC-11**: 브라우저에서 실제 업로드→다운로드 시, 네트워크 탭에 `/download/<job_id>/`에 대한 `fetch` 요청이 잡히고(직접 `<a href>` 네비게이션이 아님), 저장 대화상자의 기본 파일명이 서버가 보낸 `converted.hwpx`가 아니라 **원본 파일명(확장자만 `.hwpx`로 치환)**으로 뜬다(같은 탭, 새로고침 없이). 다른 탭에서 `job_id` 링크만으로 접속해 다운로드하면 `converted.hwpx`로 조용히 대체됨(에러 아님).
- **AC-12**: 429/413/503/기타 오류 발생 시 Panel A에 머문 채 인라인 배너만 나타나고, 선택했던 파일이 그대로 유지된다(페이지 이동/모달 없음).
- **AC-13**: OCR 체크박스를 켜면 언어 선택 영역이 나타나고, 둘 다 해제하면 [변환 시작] 버튼이 비활성화된다.
- **AC-14**: 50MB 초과 파일을 선택하면 서버 왕복 없이 즉시 클라이언트 배지("파일이 너무 큽니다…")가 뜨고 [변환 시작]이 비활성화된다.
- **AC-15**: 패널 전환(A→B→C/D) 시 포커스가 새 패널의 `<h1>`로 이동한다(키보드 Tab 진행 또는 스크린리더로 확인, 자동화 어려움 — 수동 확인 권장).
- **AC-16**: 진행 중(Panel B)에 폴링을 인위적으로 끊었다가(예: DevTools 네트워크 오프라인 토글) 복구하면, 사용자 개입 없이 폴링이 자동 재개된다(04 §6-3).

## 8. 수동으로 확인이 필요한 부분 (자동화/curl로 검증 불가하거나 이번 세션에서 미수행)

1. 실제 브라우저(Chrome/Firefox/Safari 각 1회 이상)에서 전체 플로우(파일선택→OCR→제출→폴링→완료→다운로드→파일명 복원) 수동 확인 — 이번 검증은 curl+서버 계약 확인까지만 수행했고, `fetch`/`blob`/`sessionStorage`/`URL.createObjectURL` 등 브라우저 전용 API의 실제 동작은 미확인.
2. 스크린리더(NVDA/VoiceOver) 실낭독 확인 — 코드상 `aria-live`/`role="alert|status"`/포커스 이동은 구현했으나 실사용 검증은 안 함.
3. 모바일 뷰포트/터치 타깃(44px) 실기기 또는 에뮬레이터 확인 — 반응형 CSS는 작성했으나 실기기 렌더링 미검증.
4. **429/413 실제 HTTP 재현** — 레이트리밋 데코레이터(unit-23, "views.py의 데코레이터 삽입 지점(1줄)")가 아직 삽입되지 않았고, 크기제한 미들웨어(`core/middleware.py`, unit-24)가 실제 `MIDDLEWARE` 리스트에 production 전용으로 등록되는지는 이 unit 범위 밖 — 06단계는 이 두 상태코드를 이 unit 단독으로는 재현할 수 없음을 인지할 것(미들웨어/데코레이터가 실제로 붙는 것은 후속 통합 단계).
5. 503(큐 포화) 실제 재현 — PENDING+PROCESSING 20건을 인위적으로 만든 뒤 재현 필요(Django shell로 `ConversionJob.objects.bulk_create` 등 활용 가능, 6절 참고).
6. `config/urls.py`/`config/settings/base.py`가 unit-20/21/24/25의 병렬 편집을 모두 정상 병합해 최종 반영됐는지 — 이 unit이 병합을 수행했으나(§9 참고), 오케스트레이터가 웨이브 종료 후 최종 파일 상태를 한 번 더 확인 권장.

## 9. 공유 문서 갱신 요청 (병렬 웨이브 — traceability.md 직접 수정하지 않음)

`docs/harness/traceability.md`에 아래 3개 REQ-ID 행 갱신 요청(기존 unit-21/24/25가 반영해둔 표 형식과 동일한 톤 유지 권장):

| REQ-ID | 작업 단위 컬럼 | 구현 상태 컬럼(제안) |
|---|---|---|
| REQ-001 | `unit-0, unit-20` (변경 없음) | "unit-20: 구현 완료(unit-20) — 6단계 단위테스트 대기. `POST /convert`가 웹 업로드 파일을 받아 `storage.save_uploaded_file()`로 저장하고 `ConversionJob(PENDING)`을 생성함을 로컬 curl 테스트로 확인(unit-20-note.md §4)." (unit-0 분은 기존 문구 그대로 유지) |
| REQ-010 | `unit-8` (변경 없음, unit-20 명시 추가) | "unit-20: 구현 완료(unit-20) — 6단계 단위테스트 대기. `GET /download/<job_id>/`가 실제 R2/로컬 스토리지에서 HWPX 바이트를 프록시 스트리밍해 브라우저 다운로드를 제공하고, 스트리밍 완료 후 즉시 오브젝트를 삭제함을 로컬 end-to-end(curl)로 확인(재다운로드 시 404). 원본 파일명은 서버에 저장하지 않고 클라이언트(app.js, sessionStorage)가 복원함(DEC-036)." (unit-8 분은 기존 문구 유지) |
| REQ-015 | `unit-20`(변경 없음) | "Not Started" → **"구현 완료(unit-20) — 6단계 단위테스트 대기. 단일페이지 4패널(업로드/진행/결과/조회불가)+개인정보처리방침 링크 통합 구현, GET /가 로컬에서 실제 HTML을 반환함을 확인(unit-20-note.md §4). AC-1~AC-16(unit-20-note.md §7) 06단계 인수조건으로 제공."** |

(unit-21/24/25가 이미 자신들의 REQ 행을 "구현 완료(unit-N) — 6단계 단위테스트 대기" 톤으로 갱신해둔 것을 확인했음 — 동일한 문구 관례를 따름.)
