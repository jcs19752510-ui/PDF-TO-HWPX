# unit-21 구현 노트 — `converter/executor.py` (ThreadPoolExecutor 기반 비동기 변환 실행기)

- 작성 에이전트: 05-unit-developer
- 커버 REQ-ID: REQ-027
- **속도 트랙: 명시 없음 → 기본 L3** (오케스트레이터 호출 프롬프트에 트랙 표기가 없었음. 06/07단계는 L3 기준 검증 깊이로 진행할 것)
- **병렬 실행 여부: 병렬 웨이브** — 동시에 unit-20, unit-24, unit-25가 진행 중이었음. 이 unit은 `webapp/converter/executor.py` 1개 파일만 수정했다(범위 밖 파일 미접촉 확인 — 아래 "파일 범위 준수 확인" 참고).

## 1. 구현 범위

`webapp/converter/executor.py` 신규 작성. 03-system-design.md §4-4(299~320행)가 고정한 시그니처를 그대로 구현했다:

- `_POOL = ThreadPoolExecutor(max_workers=2)` — 모듈 로드 시 1회 생성되는 프로세스 전역 싱글톤(DEC-031).
- `_PENDING_QUEUE_LIMIT = 20`
- `class QueueFullError(Exception)` — 설계서 문서 어디에도 이 클래스의 정의 위치가 배정되어 있지 않아(공유 예외 모듈이 없음), 이 파일이 유일한 소유자이자 정의처로 삼았다. `converter.executor.QueueFullError`로 import 가능.
- `submit_job(job_id: uuid.UUID) -> None`
- `_run(job_id: uuid.UUID) -> None`

## 2. `progress_callback` 매핑

`orchestrator.convert()`에 넘기는 `ConversionOptions.progress_callback`으로 클로저 `_on_progress(event: ProgressEvent)`를 전달한다. 매 `ProgressEvent` 발생마다(스테이지: loading/extracting/building/saving/done, 페이지마다 반복 호출됨) 아래 필드를 그대로 매핑해 `ConversionJob.save(update_fields=[...])`로 즉시 DB에 반영한다:

| `ProgressEvent` 필드 | `ConversionJob` 필드 |
|---|---|
| `stage` | `progress_stage` |
| `current_page` | `progress_current_page` |
| `total_pages` | `progress_total_pages` |
| `message` | `progress_message` |

`_run`이 로컬 변수로 들고 있는 동일한 `job` ORM 인스턴스를 재사용(재조회 없음) — 한 job_id는 정확히 하나의 워커 스레드에서만 처리되므로 동시 쓰기 충돌이 없다.

## 3. 큐 포화 판정 로직

`submit_job()` 진입 시 `ConversionJob.objects.filter(status__in=[PENDING, PROCESSING]).count()`를 계산한다. views.py(unit-20)가 `submit_job()` 호출 **이전에** 이미 `ConversionJob(status=PENDING)` 행을 생성해두는 계약(03 §4-4 `/convert` 라우트 설명)이므로, 이 카운트에는 지금 제출하려는 job 자신도 이미 포함되어 있다. 카운트가 `_PENDING_QUEUE_LIMIT`(20) 이상이면 `QueueFullError`를 던지고 **`_POOL.submit()`을 호출하지 않는다** — 즉 이미 생성된 DB 행을 이 함수가 지우거나 상태를 바꾸지는 않는다(그 행을 어떻게 처리할지는 호출자 views.py의 책임, 03 §4-4 "호출자가 이를 잡아 HTTP 503으로 매핑"). 20건 미만이면 `_POOL.submit(_run, job_id)`로 제출한다.

## 4. 예외 처리 경로 상세

`_run(job_id)`는 두 단계 try 구조다:

1. **바깥 try**: `ConversionJob.objects.get(job_id=job_id)` — 존재하지 않으면(`DoesNotExist`, 예: 레이스로 이미 cleanup이 삭제한 경우) `_logger.error`로 기록하고 조용히 `return`한다(더 이상 갱신할 DB 행이 없으므로 이것이 유일하게 안전한 처리).
2. **본체 try** (job을 성공적으로 가져온 이후):
   - `status=PROCESSING`, `started_at=now()` 저장.
   - `tempfile.TemporaryDirectory()`로 임시 디렉터리를 만들고 그 안에 `input.pdf`/`output.hwpx` 경로를 잡는다 — `with` 블록이 끝나면(정상/예외 무관) 자동으로 삭제된다(임시 파일 정리 보장).
   - `storage.download_upload_to_local(job_id, input_path)`로 입력 파일을 내려받는다.
   - `orchestrator.convert(input_path, output_path, options)` 호출. **이 함수 자체는 REQ-009 계약상 예외를 던지지 않고 항상 `ConversionResult`를 반환**하므로(pdf_to_hwpx/core/orchestrator.py 확인 완료), 이 호출 지점에서 예외가 발생한다면 그것은 orchestrator 계약 위반(라이브러리 버그)이거나 `progress_callback`(위 `_on_progress`)이 raise한 경우인데, 후자도 실제로는 orchestrator 내부의 `except Exception` 블록에 흡수되어 `ConversionResult(success=False, errors=[INTERNAL_ERROR])`로 반환된다(모듈 docstring/코드 확인 완료) — 즉 정상 경로에서는 이 줄이 예외를 던지지 않는다.
   - `result.success and result.output_path is not None`이면 `storage.save_result_file()`로 결과를 업로드하고 `output_object_key`를 채운다. `result.success=False`(orchestrator가 통제된 방식으로 실패 반환한 경우, REQ-009)이면 업로드를 건너뛴다.
   - **DONE은 orchestrator가 예외 없이 반환된 모든 경우**(성공이든 통제된 실패든)에 설정한다 — 03 §3-2 상태 전이 주석과 일치.
   - `result_success`/`result_warnings`/`result_errors`를 `dataclasses.asdict()`로 직렬화해 저장(`ConversionWarning`/`ConversionIssue`는 `dataclass`라 `asdict` 그대로 사용 가능, 필드 확인 완료).
3. **바깥 except Exception** (본체 try 전체를 감쌈): storage 다운로드/업로드 실패, DB 저장 실패, 그 외 예상치 못한 모든 예외를 포착한다. `_logger.exception(...)`으로 traceback을 반드시 로그에 남긴 뒤(예외를 삼켜서 무시하지 않음), `status=FAILED`, `finished_at=now()`를 저장 시도한다.
4. **이중 방어**: 3번의 FAILED 저장 자체가 실패할 수도 있는 극단적 경우(예: DB 연결이 완전히 끊긴 상태)에 대비해 그 저장 시도도 `try/except Exception`으로 감싸고, 실패하면 다시 `_logger.exception`으로 기록한다 — 이 경우 job은 "고아 상태"(PROCESSING에 머무름)로 남을 수 있음을 로그 메시지에 명시했고, 이는 03 §5 "프로세스 재시작에 따른 job 유실"과 동일한 성격의 이미 문서화된 한계로 `cleanup.py`(unit-22)의 TTL 스윕이 최종적으로 정리한다.

이 구조로 `_run` 내부에서 어떤 예외가 발생해도 **로그에 반드시 기록되고**, 스레드는 죽지 않으며(ThreadPoolExecutor 워커 스레드 자체가 예외를 삼키는 것과 별개로, 우리 코드가 명시적으로 처리), 최대한 `FAILED` 상태로 귀결된다.

## 5. 설계서 대비 편차

- `QueueFullError`의 정의 위치가 설계서에 명시되어 있지 않아 이 파일에 직접 정의했다(사유는 위 §1). 다른 unit이 공유 예외 모듈을 원하면 후속 리팩터링으로 이동 가능 — 현재 `converter.executor.QueueFullError`로 import 가능한 상태이므로 unit-20(views.py)의 소비에는 지장이 없다.
- 그 외 시그니처(`_POOL`, `_PENDING_QUEUE_LIMIT`, `submit_job`, `_run`)는 설계서 원문과 이름·인자 100% 일치.

## 6. 로컬 동작 확인 (완료)

`.harness-tmp/venv_05_unit21/`에 격리 venv를 만들어(Django 5.2.17, dj-database-url, python-dotenv, whitenoise, reportlab + `pip install -e .`로 `pdf_to_hwpx` 편집설치) 아래를 직접 실행하고 **작업 완료 후 venv와 생성된 `webapp/db.sqlite3`/`webapp/.dev-media/`를 전부 삭제**했다(규칙 K):

1. **정상 경로 end-to-end**: `reportlab`으로 만든 실제 1페이지 텍스트 PDF를 `converter.storage.save_uploaded_file()`로 로컬 `FileSystemStorage`(dev 폴백)에 업로드 → `ConversionJob(status=PENDING)` 생성 → `submit_job(job_id)` 호출 → 스레드풀에서 `_run`이 완료될 때까지 최대 30초 폴링 대기 → **결과: `status=DONE`, `result_success=True`, `progress_stage="done"`, `output_object_key`가 채워짐, 그리고 `default_storage.exists(output_object_key)`가 `True`임을 직접 확인** — 즉 실제 변환이 스레드풀에서 끝까지 돌아 결과 파일이 스토리지에 저장되는 것을 코드로 검증했다.
2. **큐 포화 경로**: `ConversionJob(status=PENDING)` 20건을 만든 뒤 21번째 job에 대해 `submit_job()`을 호출 → `QueueFullError`가 정확히 발생함을 확인(`21/20`이라는 메시지로 카운트가 의도대로 계산됨도 확인).
3. **인프라 실패 경로(FAILED)**: 스토리지에 실제로 존재하지 않는 `input_object_key`를 가진 job으로 `submit_job()` 호출 → `_run` 내부에서 `FileNotFoundError`가 발생 → 로그에 traceback이 정확히 기록됨(터미널에 `_logger.exception` 출력 확인) → 최종 `status=FAILED`, `finished_at`이 채워짐을 확인. 스레드풀 자체는 죽지 않고(이후 프로세스가 계속 정상 동작) 예외가 삼켜지지 않았음을 확인.

## 7. 6단계 테스터를 위한 인수 조건 (Acceptance Criteria)

- **AC-1 (정상 변환)**: 유효한 1페이지 이상 PDF를 `input_object_key`로 가리키는 `ConversionJob(status=PENDING)`을 만들고 `submit_job(job.job_id)`를 호출하면, 일정 시간 내(수 초, 소프트타임아웃 5분 이내) `ConversionJob.status`가 `DONE`으로 바뀌고 `result_success=True`, `output_object_key`가 비어있지 않으며, 그 키로 `default_storage.exists()`가 `True`를 반환해야 한다.
- **AC-2 (진행률 갱신)**: 변환 도중(스레드가 실행 중인 동안) `ConversionJob`을 재조회하면 `progress_stage`가 `"loading"/"extracting"/"building"/"saving"/"done"` 중 하나로, 완료 시점에는 `"done"`으로 관측되어야 한다(다중 페이지 PDF로 테스트하면 중간 스테이지도 관측 가능).
- **AC-3 (orchestrator가 통제된 실패를 반환하는 경우)**: 암호화 PDF/손상 PDF 등 `pdf_to_hwpx.core.orchestrator.convert()`가 예외 없이 `success=False`를 반환하는 입력을 넣으면, `ConversionJob.status`는 여전히 `DONE`이어야 하고(`FAILED`가 아님) `result_success=False`, `result_errors`가 비어있지 않아야 한다.
- **AC-4 (인프라 레벨 실패)**: 존재하지 않는 `input_object_key`(또는 storage 접근 자체가 실패하는 상황)로 `submit_job()`을 호출하면 `ConversionJob.status`가 `FAILED`로 바뀌고 `finished_at`이 채워져야 한다. 이 예외는 애플리케이션 로그(콘솔)에 traceback과 함께 기록되어야 한다(조용히 삼켜지면 결함).
- **AC-5 (큐 포화)**: `status in (PENDING, PROCESSING)`인 `ConversionJob`이 이미 20건 이상 존재하는 상태에서 `submit_job(new_job_id)`를 호출하면 `converter.executor.QueueFullError`가 즉시(스레드풀 제출 없이) 발생해야 한다. views.py(unit-20)와의 통합 테스트에서는 이 예외가 HTTP 503으로 매핑되는지 함께 확인 필요(그 매핑 자체는 unit-20 책임, 이 unit은 예외 발생까지만 보장).
- **AC-6 (임시 파일 정리)**: 여러 건을 연속 처리해도 `tempfile.gettempdir()`(또는 OS 임시 디렉터리) 아래에 `pdf-to-hwpx-<job_id>-*` 접두사의 디렉터리가 처리 완료 후 남아있지 않아야 한다(성공/실패 경로 모두).
- **AC-7 (스레드풀 생존)**: `_run`에서 예외가 발생한 job 처리 이후에도, 동일 프로세스에서 이어지는 다음 `submit_job()` 호출이 정상적으로 처리되어야 한다(스레드풀이 죽거나 멈추지 않음) — AC-4 케이스 직후 AC-1 케이스를 실행해 순서대로 확인 가능.

## 8. 게이트 1 — 정적 분석/린트

- 저장소 루트(`pyproject.toml`)와 `webapp/`에 ruff/flake8/black/mypy/pylint 관련 설정 파일·섹션이 **없음을 확인**(unit-0/unit-19-note.md와 동일 결론 — 있는데 건너뛴 것이 아니라 애초에 설정이 없음).
- 대신 `python -m py_compile webapp/converter/executor.py` 실행 → **컴파일 성공**.
- `manage.py check`는 이번 unit 시점에는 `converter.urls`가 아직 `config/urls.py`에 연결되지 않아(unit-20이 병렬로 작업 중) `executor.py`를 자동으로 import하지 않으므로 이 게이트의 대상이 아니다. 대신 위 §6의 end-to-end 스크립트가 `django.setup()` 이후 `from converter.executor import submit_job, QueueFullError, _PENDING_QUEUE_LIMIT`를 실제로 import해 모듈 로드 자체(전역 `_POOL` 생성 포함)가 예외 없이 성공함을 확인했다 — 이는 py_compile보다 강한 "실제 런타임 import" 검증이다.
- 병렬 웨이브 노트(규칙): 이 게이트1 판정은 이 unit이 수정한 `executor.py` 파일 기준이며, 다른 병렬 unit(20/24/25)의 미완성 코드로 인한 전체 실행 실패와는 분리해 보고한다 — 실제로 위 §6 스크립트 실행 시점에 `config/urls.py`/`config/settings/base.py`가 다른 unit에 의해 동시 수정 중이었으나, dev 설정이 아직 `converter`/`legal` 앱의 URL을 필수로 요구하지 않아(§4 확인) 이 unit의 검증에는 영향이 없었다.

## 9. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 — 03 §4-4 시그니처(`_POOL`, `_PENDING_QUEUE_LIMIT`, `submit_job`, `_run`)를 이름/인자 그대로 구현. `progress_callback`/`storage.*`/`ConversionJob` 필드 매핑도 설계서·기존 산출물(models.py/storage.py/orchestrator.py)과 교차 확인 완료.
- [x] 에러 처리가 누락된 경로가 없는가 — `_run` 전체가 2단계 try/except로 감싸여 있고, 모든 except 블록이 `_logger.exception`/`_logger.error`로 반드시 로그를 남긴 뒤 상태를 갱신한다(§4 상세). 예외를 아무 조치 없이 삼키는 `except: pass` 스타일 코드 없음.
- [x] 입력값 검증이 시스템 경계에서 이루어지는가 — 이 unit의 "입력"은 이미 unit-20이 검증(파일 크기/타입 등, unit-24 담당 영역)을 마친 뒤 DB에 저장한 `job_id`(내부 신뢰 경계 안쪽 값)이므로 이 unit이 추가로 재검증할 사용자 입력 경계가 없다. 대신 "이 job_id가 실제로 존재하는가"(`DoesNotExist` 처리)와 "다운로드가 실제로 성공했는가"(예외 처리)는 이 unit의 경계에서 명시적으로 처리했다.
- [x] 하드코딩된 시크릿/자격증명이 없는가 — 없음(이 파일은 자격증명을 다루지 않음, DB/스토리지 접근은 전부 기존 `storage.py`/Django ORM을 통해 이루어짐).
- [x] 새로 추가한 외부 의존성이 있다면 실존 여부를 확인했는가 — 이 unit은 **신규 패키지를 추가하지 않았다**(표준 라이브러리 `concurrent.futures`/`tempfile`/`dataclasses`/`uuid`/`logging`/`pathlib`, 그리고 이미 설치된 Django·`pdf_to_hwpx`만 사용). `requirements.txt`/`pyproject.toml` 변경 없음(범위 밖 공유자원 미접촉).
- [x] 범위를 벗어난 변경이 섞여 있지 않은가 — `git status`로 `webapp/converter/executor.py` 1개 파일만 신규 생성되었음을 확인(다른 병렬 unit이 동시에 수정 중인 `config/settings/base.py`/`config/urls.py`/`converter/views.py`/`converter/urls.py`/`converter/limits.py`/`core/middleware.py`/`legal/` 등은 전혀 건드리지 않음).

## 10. 공유 문서 갱신 요청 (오케스트레이터가 웨이브 종료 후 반영)

`docs/harness/traceability.md`의 REQ-027 행을 아래와 같이 갱신 요청:

| 컬럼 | 현재 값 | 요청 값 |
|---|---|---|
| 작업 단위 | unit-21(신규) | unit-21 |
| 구현 상태 | Not Started | Implemented (05단계 완료, 06단계 단위테스트 대기) |
| (비고 열, 있다면) | (기존 DEC-024/DEC-031 서술 유지) | 기존 서술 뒤에 추가: "unit-21이 `converter/executor.py`로 구현 완료 — `submit_job()`/`_run()`/`QueueFullError` 시그니처는 03 §4-4와 100% 일치, 로컬 end-to-end(정상/큐포화/인프라실패 3경로) 직접 확인 완료(unit-21-note.md §6)." |

추가로 6단계 호출 시 참고할 사항(질문/결정 기록 요청은 없음 — 이번 unit은 규칙 A 질문이 발생하지 않았다):
- unit-20(views.py)이 `from converter.executor import submit_job, QueueFullError`로 import해 사용할 수 있음을 확인 요청.
- unit-22(cleanup.py)가 "PROCESSING 상태로 고아가 된 job" 정리 로직을 만들 때 참고할 전제: 이 unit은 FAILED 저장 자체가 실패하는 극단적 경우 job을 PROCESSING 상태로 방치할 수 있음(§4의 "이중 방어" 참고, 03 §5에 이미 문서화된 한계와 동일 성격).
