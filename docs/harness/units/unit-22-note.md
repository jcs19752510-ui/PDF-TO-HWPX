# unit-22 구현 노트 — `converter/cleanup.py` (TTL 지연 스윕)

- 작성 에이전트: 05-unit-developer
- 커버 REQ-ID: REQ-028
- **속도 트랙: 표기 없음 → 기본 L3**(오케스트레이터 호출 프롬프트에 트랙 명시 없음). 06/07단계는 L3 기준 검증 깊이로 진행할 것.
- **병렬 실행 여부: 병렬 웨이브** — 이 호출과 동시에 **unit-9**(`core/net_guard.py`, 아웃바운드 화이트리스트)가 별도 호출로 진행 중이었다. 이 unit은 프롬프트로 지정된 파일 범위(`webapp/converter/cleanup.py`, `webapp/.env.example`)만 수정했다 — `git status` 확인 결과 unit-9는 `core/net_guard.py`(신규), `config/wsgi.py`/`config/settings/base.py`/`requirements.txt`(공유 파일, M 상태)를 건드리는 중이었고, 이 unit이 작업한 파일과는 전혀 겹치지 않았다.

## 1. 구현 범위

`webapp/converter/cleanup.py` 신규 작성. 03-system-design.md §3-2/§6-2(362~364행)의 "3중 TTL 삭제 구조" 중 2번째 계층(지연 스윕)을 구현했다:

- `TTL_MINUTES = 60`(DEC-029), `SWEEP_COOLDOWN_SECONDS = 5*60`(03 §6-2 "최근 실행이 5분 이내면 스킵"), `SWEEP_BATCH_LIMIT = 20`(03 §6-2 "배치(최대 20건)로 정리").
- `_last_swept_monotonic`: 프로세스 전역 변수(`time.monotonic()` 기준) + `threading.Lock()`. 별도 DB 테이블/Redis 락 없이 쿨다운을 판정한다(오케스트레이터 지시, 과설계 방지). 프로세스 재시작 시 초기화되는 것은 의도된 동작(재시작 직후 스윕이 한 번 더 돌아도 `delete_job_objects`가 멱등이라 무해).
- `run_lazy_sweep_if_due() -> int`: 공개 진입점. 쿨다운 이내면 DB 쿼리 없이 `0`을 즉시 반환. 아니면 `_sweep_expired_jobs()`를 호출하고, 그 안에서 예상치 못한 예외가 나도 호출자(요청-응답 경로)의 본 작업을 방해하지 않도록 잡아서 로그만 남기고 `0`을 반환한다(예외를 삼켜서 "무시"하는 것이 아니라 `logger.exception`으로 반드시 기록 — 게이트2 체크리스트 참고).
- `_sweep_expired_jobs() -> int`: `ConversionJob.objects.exclude(status=EXPIRED).filter(created_at__lt=cutoff)`로 60분 경과 + 아직 EXPIRED가 아닌 job을 `created_at` 오름차순으로 최대 20건 조회(models.py의 `["status", "created_at"]` 복합 인덱스를 그대로 활용, unit-19 산출물). 각 job에 대해 `storage.delete_job_objects(job_id)`를 호출하고, 성공한 job_id만 모아 한 번의 `UPDATE ... WHERE job_id IN (...)` 쿼리로 `status=EXPIRED, purged_at=now()`로 일괄 전이한다. 개별 job의 오브젝트 삭제가 실패해도(예: R2 일시 장애) 그 job만 이번 배치에서 제외하고 나머지는 계속 처리한다(벌크헤드, 03 §5와 동일한 정신) — 실패한 job은 status가 그대로 남아 다음 스윕에서 삭제가 재시도된다.

**정리 대상 확인**: DONE/FAILED로 최종 전이된 job과 PENDING/PROCESSING에 60분 넘게 멈춰있는 "좀비 job"(unit-21-note.md §10이 언급한 프로세스 재시작 유실 케이스) 둘 다 `exclude(status=EXPIRED)` 조건 하나로 자연스럽게 포괄된다(`status` 값을 구분하지 않고 `created_at`만 본다). 이미 다운로드되어 `purged_at`이 채워진(오브젝트가 이미 삭제된) DONE job도 대상에 포함되는데, `storage.delete_job_objects()`가 `default_storage.exists()`로 존재 여부를 먼저 확인하므로 이미 삭제된 오브젝트에 대해서는 아무 일도 하지 않고(에러 없이) 그대로 진행되어 결국 `status=EXPIRED`로 전이된다 — 다운로드 완료 후에도 job 행 자체는 DONE으로 남아있다가 60분 뒤 이 스윕으로 EXPIRED가 되는 것이 의도된 동작이다(`job_status`/`download` 뷰가 EXPIRED를 404로 처리하므로 결과적으로 "이 job은 더 이상 조회 불가"라는 상태로 자연스럽게 수렴).

`ConversionJob.Status`에 새 값을 추가하지 않고 모델이 이미 정의해둔 `EXPIRED`를 그대로 사용했다(unit-19 산출물, 임의 확장 없음).

## 2. 트리거 지점 — 설계 모호함에 대한 자체 판단 (규칙A 질문 대상 아님, 프롬프트가 명시적으로 허용)

03 원문(§6-2)은 "`core/middleware.py`에 훅"이라고 서술하지만, 프롬프트가 이 문장을 "가역적 구현 세부사항"으로 규정하고 미들웨어/뷰 함수 중 자체 판단을 허용했다. **뷰 함수 호출 방식을 선택**했다 — 이유:

1. 미들웨어 방식은 `core/middleware.py`(클래스 추가)뿐 아니라 `config/settings/base.py`(`MIDDLEWARE` 리스트 등록)까지 최소 2개의 out-of-scope 공유 파일을 건드려야 하는데, 뷰 함수 방식은 `converter/views.py`(unit-20 소유) 1개 파일에 1줄만 추가하면 된다.
2. 이 unit의 확정 파일 범위는 `converter/cleanup.py`뿐이고 **`views.py`/`config/`는 건드리지 않는 것이 명시적 지시**이므로, 이 unit은 실제로 어떤 파일도 대신 수정하지 않는다. 아래에 오케스트레이터가 반영해야 할 정확한 변경 내용을 남긴다.

### 오케스트레이터가 반영해야 할 변경 (이 unit이 직접 수행하지 않음)

`webapp/converter/views.py`의 `index(request)` 함수(파일 34~49행 부근, `GET /` 핸들러) 최상단에 아래 2줄 추가 권장:

```python
from . import cleanup
...
def index(request):
    cleanup.run_lazy_sweep_if_due()
    ...(기존 코드 그대로)
```

**`index`를 선택한 이유**: `GET /`는 방문자가 페이지에 진입할 때마다(사실상 가장 트래픽이 많은 라우트) 호출되므로 스윕이 제때 트리거될 확률이 가장 높고, 크리티컬 패스인 `POST /convert`(업로드 응답 지연에 민감)에는 부하를 얹지 않는다. `run_lazy_sweep_if_due()`는 쿨다운 이내면 DB 쿼리 0회로 즉시 반환하므로 정상 트래픽 하에서 `index` 뷰의 응답 지연에 미치는 영향은 무시할 수준이다(로컬 실측: 쿨다운 hit 시 함수 호출 자체가 `time.monotonic()` 비교 1회뿐).

대안으로 `convert()`(POST /convert) 진입부에 추가해도 되지만, 그러면 업로드 트래픽이 없는 시간대(방문만 있고 업로드는 없는)에는 스윕이 덜 트리거된다는 단점이 있어 `index`를 1순위로 권장한다. 필요하면 둘 다에 추가해도 무해하다(멱등, 쿨다운이 중복 실행을 막음).

## 3. R2 버킷 라이프사이클 백스톱 (3중 구조의 3번째 계층, 코드 아님)

`webapp/.env.example`에 안내 주석으로 추가했다(코드로 구현할 수 없는 항목 — 실제 R2 콘솔/IaC 설정):

- 위치: R2 자격증명 환경변수 블록 바로 아래.
- 내용 요약: R2 대시보드 > 버킷 > Settings > Object lifecycle rules에서 "Age of object = 1 day(24시간)" 조건으로 삭제 규칙을 추가할 것. 이 규칙은 앱 로직(60분 목표)이 실패하거나 트래픽 부재로 지연되는 경우를 막는 2차 방어선이며, 정상 동작 시에는 이 규칙이 발동하기 전에 이미 오브젝트가 삭제되어 있어야 한다.
- 실제 버킷 생성은 10~12단계 몫이므로(03 §8-3), 이 unit은 코드/설정 파일이 아니라 안내 텍스트만 남겼다. `webapp/render.yaml`은 아직 unit-26이 만들지 않은 파일이므로 참조하지 않았다(프롬프트 지시 그대로 준수).

## 4. 설계서 대비 편차

없음. 03 §3-2/§6-2가 명시한 수치(TTL 60분, 쿨다운 5분, 배치 20건)를 상수 그대로 반영했고, `delete_job_objects`/`ConversionJob` 시그니처를 재정의하지 않고 그대로 소비했다. 트리거 지점 선택(§2)만 프롬프트가 명시적으로 허용한 가역적 구현 세부사항이다.

## 5. 게이트 1 — 정적 분석/린트

리포지토리 전체(루트 `pyproject.toml`, `webapp/`)에 ruff/flake8/black/mypy/pylint 관련 설정 파일·섹션이 **없음을 확인**(unit-0/19/20/21/24-note.md와 동일한 결론 — 있는데 건너뛴 것이 아니라 애초에 설정이 없음).

대신 `python -m py_compile webapp/converter/cleanup.py` → 컴파일 성공. `python manage.py check`(Django 시스템 체크, dev 설정) → `System check identified no issues (0 silenced)`. `manage.py shell`을 통한 실제 런타임 import(`from converter import cleanup, storage`) + 함수 실행까지 성공했으므로 py_compile보다 강한 런타임 검증도 완료했다(§6 참고).

## 6. 게이트 2 — 자체 코드 리뷰 체크리스트

- [x] 설계서/디자인서 명세와 실제 구현이 일치하는가 — TTL 60분/쿨다운 5분/배치 20건(03 §6-2), 좀비 job(PENDING/PROCESSING 방치) 정리 포함(03 §5), `delete_job_objects`/`ConversionJob.Status.EXPIRED` 등 기존 계약을 그대로 소비하고 재정의하지 않음.
- [x] 에러 처리가 누락된 경로가 없는가 — `run_lazy_sweep_if_due()`가 `_sweep_expired_jobs()` 전체를 감싸 예상치 못한 예외를 `logger.exception`으로 반드시 기록 후 안전하게 반환(요청 스레드를 죽이지 않음). `_sweep_expired_jobs()` 내부에서도 개별 job의 `storage.delete_job_objects()` 실패를 job 단위로 격리 처리(전체 배치를 막지 않음, 로그 기록 후 계속 진행). 예외를 아무 조치 없이 삼키는 `except: pass` 스타일 코드 없음.
- [x] 입력값 검증이 시스템 경계에서 이루어지는가 — 이 unit은 사용자 입력을 직접 받지 않는다(내부 배치 작업, DB에 이미 저장된 `job_id`/`created_at`만 다룸). 시스템 경계 검증은 이 unit의 책임 범위가 아니며 해당 없음.
- [x] 하드코딩된 시크릿/자격증명이 없는가 — 없음. `.env.example`에 추가한 것은 시크릿 값이 아니라 R2 콘솔 설정 절차 안내 텍스트뿐(빈 변수 슬롯 자체는 기존 unit-19 산출물, 이 unit이 값 채운 것 없음).
- [x] 새로 추가한 외부 의존성이 있다면 실존 여부를 확인했는가 — **신규 패키지 없음**(표준 라이브러리 `threading`/`time`/`datetime`/`uuid`/`logging`, 그리고 기존 `django.utils.timezone`/`converter.storage`/`converter.models`만 사용). `requirements.txt`/`pyproject.toml` 변경 없음.
- [x] 범위를 벗어난 변경이 섞여 있지 않은가 — `git status`로 `webapp/converter/cleanup.py`(신규)와 `webapp/.env.example`(안내 주석 추가) 2개 파일만 수정되었음을 확인. `views.py`/`core/middleware.py`/`config/settings/base.py`/`config/urls.py` 등 다른 unit 소유 파일은 전혀 건드리지 않았다(§2의 필요한 변경은 코드로 직접 반영하지 않고 위에 명시만 함).

## 7. 로컬 동작 확인 (`.harness-tmp/venv_05_unit22/`, 확인 후 삭제 완료)

`python -m venv .harness-tmp/venv_05_unit22` 생성 → `pip install -r webapp/requirements.txt` + `pip install -e .`(pdf_to_hwpx editable) → `manage.py check`(통과) → `manage.py migrate --run-syncdb`(SQLite dev 폴백) → `manage.py shell`로 아래 시나리오를 실제로 실행:

1. **DONE job, `created_at`을 61분 전으로 설정** + 업로드/결과 오브젝트를 로컬 `FileSystemStorage`에 실제로 저장.
2. **PROCESSING 좀비 job(60분 넘게 멈춤), `created_at`을 61분 전으로 설정** + 동일하게 오브젝트 저장.
3. **PROCESSING 신선한 job, `created_at`을 10분 전으로 설정**(60분 미경과) + 오브젝트 저장.
4. `cleanup.run_lazy_sweep_if_due()` 1회 호출 → **반환값 2**(대상 2건만 정리) 확인.
5. 스윕 후 재조회: **DONE job과 좀비 job 모두 `status=EXPIRED`, `purged_at`이 채워짐, 두 job의 업로드/결과 오브젝트가 스토리지에서 실제로 사라짐**(`default_storage.exists()`가 둘 다 `False`)을 확인. **신선한 job은 `status=PROCESSING` 그대로 유지되고 오브젝트도 그대로 남아있음**(`exists()` 둘 다 `True`)을 확인 — 60분 미경과 job은 건드리지 않는다는 요구를 실측 확인.
6. **쿨다운 확인**: 같은 프로세스 내에서 새로운 만료 대상 job을 하나 더 만든 뒤 `run_lazy_sweep_if_due()`를 즉시 재호출 → **반환값 0**(쿨다운 이내라 스킵), 새 job은 여전히 `DONE` 상태로 남아있음(스윕되지 않음)을 확인.
7. 모든 assertion 통과, `ALL ASSERTIONS PASSED` 출력 확인(전체 로그는 이 세션의 도구 호출 기록에 남아있음, 별도 파일로 저장하지 않았음 — 규칙 K에 따라 임시 산출물 최소화).
8. 확인 후 `.harness-tmp/venv_05_unit22/`, `webapp/db.sqlite3`, `webapp/.dev-media/`를 전부 삭제해 정리 완료. 병렬로 동시 진행 중이던 unit-9의 `.harness-tmp/venv_05_unit9/`는 건드리지 않았다.

## 8. 6단계 테스터를 위한 인수 조건 (Acceptance Criteria)

- **AC-1 (좀비/방치 job 정리)**: `created_at`이 60분보다 더 과거이고 `status`가 `EXPIRED`가 아닌 `ConversionJob`(상태가 `PENDING`/`PROCESSING`/`DONE`/`FAILED` 무엇이든)이 존재하는 상태에서 `cleanup.run_lazy_sweep_if_due()`를 호출하면, 해당 job의 `status`가 `EXPIRED`로 바뀌고 `purged_at`이 채워지며, 그 job의 업로드/결과 스토리지 오브젝트가 (존재했다면) 삭제되어야 한다.
- **AC-2 (미경과 job 보존)**: `created_at`이 60분 이내인 job은 `status`/`purged_at`/스토리지 오브젝트 모두 스윕 호출 전후로 변화가 없어야 한다.
- **AC-3 (쿨다운)**: `run_lazy_sweep_if_due()`를 호출한 직후(5분 이내) 다시 호출하면, 그 사이 새로 60분을 경과한 job이 생겼더라도 두 번째 호출은 아무것도 정리하지 않고 `0`을 반환해야 한다(DB 쿼리가 발생하지 않아야 하며, 이는 코드 상 `time.monotonic()` 비교만으로 확인 가능 — 필요시 `unittest.mock`으로 `ConversionJob.objects` 접근이 없음을 스파이 검증 권장).
- **AC-4 (배치 상한)**: 60분을 경과한 job이 20건을 초과해 존재하면, 한 번의 `run_lazy_sweep_if_due()` 호출은 정확히 20건만(가장 오래된 것부터, `created_at` 오름차순) 정리하고 나머지는 다음 호출(쿨다운 경과 후)로 넘겨야 한다.
- **AC-5 (부분 실패 격리)**: 스윕 대상 job 중 일부의 `storage.delete_job_objects()` 호출이 예외를 던지도록 만들어도(예: `unittest.mock.patch`), 그 job만 `EXPIRED` 전이에서 제외되고 나머지 정상 job들은 예정대로 `EXPIRED`로 전이되어야 하며, 스윕 함수 자체는 예외를 전파하지 않고 정상적으로 반환해야 한다(로그에 `logger.exception` 기록은 남아야 함).
- **AC-6 (모델 계약 준수)**: `ConversionJob.Status`에 새로운 값이 추가되지 않았고, `status` 필드는 항상 기존 `TextChoices`(`pending`/`processing`/`done`/`failed`/`expired`) 중 하나여야 한다.
- **AC-7 (트리거 미통합 상태 인지)**: **이 unit 자체는 `run_lazy_sweep_if_due()`가 어떤 HTTP 요청 경로에서도 자동으로 호출되지 않는 상태**다(§2의 통합은 오케스트레이터가 반영). 06단계는 `converter/views.py`에 실제로 이 한 줄이 추가되었는지 별도로 확인하고, 추가되지 않았다면 이 unit의 결함이 아니라 통합 누락으로 분류할 것 — 이 unit의 단위테스트는 `cleanup.run_lazy_sweep_if_due()`를 직접 호출하는 방식(§7의 방식)으로 AC-1~6을 검증하면 된다.

## 9. 수동으로 확인이 필요한 부분

1. **§2의 `views.py::index` 1줄 통합**이 오케스트레이터에 의해 실제로 반영되었는지, 반영 후에도 `GET /`가 정상 200을 반환하는지 재확인 필요(이 unit은 해당 통합을 수행하지 않았음).
2. **R2 실제 라이프사이클 규칙 설정**(§3)은 10~12단계에서 실제 버킷이 생성된 뒤에만 검증 가능 — 이번 unit은 안내 텍스트만 남겼고 실제 R2 콘솔 설정 여부는 이 unit의 검증 범위 밖이다.
3. **다중 워커 프로세스 환경(gunicorn 여러 워커)에서의 쿨다운 정확도**: `_last_swept_monotonic`은 프로세스 전역 변수이므로, gunicorn이 워커를 2개 이상 띄우면 워커마다 독립적인 쿨다운을 갖게 되어(각 워커가 5분마다 한 번씩) 이론상 스윕이 워커 수만큼 더 자주 실행될 수 있다 — 03 §6-2 원문도 이 멀티프로세스 시나리오를 명시적으로 다루지 않았고, 배치 크기(20건)/삭제 멱등성 덕분에 안전성에는 문제가 없으나(중복 실행이 정확성을 깨지 않음), 09단계(성능/부하) 또는 10단계(배포) 검증 시 실제 gunicorn 워커 수 설정과 함께 오버헤드를 재확인할 가치가 있다.

## 10. 공유 문서 갱신 요청 (오케스트레이터가 웨이브 종료 후 반영 — traceability.md 직접 수정하지 않음)

`docs/harness/traceability.md`의 REQ-028 행(41번째 줄)을 아래와 같이 갱신 요청:

| 컬럼 | 현재 값 | 요청 값 |
|---|---|---|
| 작업 단위 (unit-n) | `unit-22(신규)` | `unit-22` ("(신규)" 표기 제거) |
| 구현 상태 | `Not Started` | `구현 완료(unit-22) — 6단계 단위테스트 대기. converter/cleanup.py가 60분 경과 + EXPIRED가 아닌 job(PENDING/PROCESSING 좀비 포함)을 최대 20건 배치로 정리(status→EXPIRED, purged_at 기록, storage 오브젝트 삭제)하며, 5분 쿨다운으로 반복 실행을 제한함을 로컬 실측(unit-22-note.md §7)으로 확인. 단, run_lazy_sweep_if_due()를 실제 HTTP 요청 경로(views.py::index)에 연결하는 1줄 통합은 아직 반영되지 않았음(unit-22-note.md §2 — 오케스트레이터 반영 대기).` |
| (비고 열) | 기존 서술(DEC-022/DEC-029) 유지 | 기존 서술 뒤에 추가: "R2 버킷 라이프사이클 백스톱 설정 안내는 `webapp/.env.example`에 추가됨(코드 아님, 실제 버킷 생성 시점인 10~12단계에서 적용 확인 필요)." |

decisions.md에 남길 새로운 규칙 A 질문은 없음(트리거 지점 선택은 프롬프트가 명시적으로 자체 판단을 허용한 가역적 구현 세부사항).

**오케스트레이터 액션 아이템(§2 재정리)**: `webapp/converter/views.py`의 `index(request)` 함수 상단에 `from . import cleanup` import 추가 + 함수 본문 첫 줄에 `cleanup.run_lazy_sweep_if_due()` 호출 추가. 이 변경 없이는 REQ-028의 "지연 스윕" 계층이 실제로는 트리거되지 않는다(코드는 존재하지만 아무도 호출하지 않는 상태) — 06단계 착수 전 반드시 반영 확인.


---

## R. 재작업 이력 v2 — DEF-020c-01 안전망 (DEC-063, 규칙 F, 2026-09-29)

### R-1. 배경
unit-20의 업로드 뷰가 새 job을 `EXPIRED`로 예약 저장한 뒤 submit 성공 시 `PENDING`으로 승격한다(DEC-052/053). `os._exit`·`BaseException`·폐기 실패 등으로 정리되지 못한 예약 행(EXPIRED, `purged_at` NULL)과 업로드 PDF를 기존 스윕이 `exclude(status=EXPIRED)`로 건너뛰어 영구 잔존했다(unit-20-test.md 12절 TC-280/282/PD-1).

### R-2. 변경 (`webapp/converter/cleanup.py` 만)
- 스윕 대상에 "고아 예약 행" 추가: `status=EXPIRED AND purged_at IS NULL AND created_at < now - (TTL_MINUTES 60 + ORPHAN_RESERVATION_GRACE_MINUTES 10)` = 생성 후 70분 경과. 기존 대상(60분 경과 비-EXPIRED)이 먼저, 배치 합계 상한 20(`SWEEP_BATCH_LIMIT`)의 남는 여유분으로 처리.
- 정리 = `storage.delete_job_objects()`(업로드·결과 키, 존재하지 않아도 무오류) + `purged_at` 기록. 행은 정상 만료 행과 동일하게 EXPIRED+`purged_at` 상태로 남긴다. 고아용 UPDATE는 조건부(`status=EXPIRED AND purged_at IS NULL`)라 조회 후 승격/처리된 행은 건드리지 않는다.
- 삭제 루프를 `_delete_objects()`로 추출(동작 동일). 삭제 실패 job은 행을 그대로 두므로 다음 스윕에서 자동 재시도.
- 정상 만료 행은 항상 `purged_at`이 있어(스윕 update, 다운로드 `_finalize`) 재처리되지 않는다(멱등).

### R-3. 유예 시간 근거
- 예약 행이 존재하는 정상 구간은 `_submit_lock` 안의 `job.save()`~승격 UPDATE뿐이다(unit-20-test 12-4 (다): 정상 시 수 ms~수십 ms, 락으로 직렬화되어 동시에 최대 1건). 인위적으로 submit을 1초·3초 지연시킨 실측(TC-270/271)에서도 초 단위. 그러므로 60분을 넘긴 EXPIRED+purged_at NULL은 정상 흐름에서 존재할 수 없다.
- 그럼에도 기준을 "60분 + 10분"으로 보수적으로 잡았다(시계 오차, Neon 지연, gunicorn worker 타임아웃 등 여유). 실측 최대 수 초 대비 약 2백 배 이상.
- 60분 약속과의 충돌 없음: 예약 job_id는 클라이언트에 전달된 적 없어 사용자가 약속을 인지하는 job이 아니다. 잔존 최대 시간은 70분 + 스윕 쿨다운 5분 + 트리거(GET /) 빈도.
- **주의(질문 목록 Q-1)**: 계약의 "뷰의 예약 관련 상수 60분"은 views.py에 존재하지 않는다(60분은 주석에만 있음). 그래서 cleanup.TTL_MINUTES(60)를 기준으로 삼았다.

### R-4. 락/빈도/부하/다중 프로세스
- `run_lazy_sweep_if_due` 쿨다운(5분, 프로세스 전역)·락 구조 무변경. 쿼리는 스윕 시 최대 2회(기존 1 + 고아 1, 인덱스 `(status, created_at)` 사용, LIMIT 20). 일반 대상이 20건을 채우면 고아 쿼리는 생략된다.
- 다중 프로세스: 동일 행을 동시에 처리해도 삭제는 멱등, 고아 UPDATE는 조건부라 안전. 03 §2-1 단일 워커 전제.
- 일반 만료 대상이 매 배치 20건을 계속 채우면 고아 처리가 이월될 수 있다(기아 가능성은 트래픽이 20건/5분을 상시 초과할 때뿐, 무료 플랜 규모에서 비현실적; 스윕은 배치 반복으로 결국 소진).
- 로그는 job_id(UUID)만 기록. 스토리지 키는 UUID 기반이라 파일명(원본 이름)이 로그·예외 메시지에 들어가지 않는다.

### R-5. 실측 (수정 전 HEAD vs 수정 후, 별도 SQLite/MEDIA_ROOT `.harness-tmp/_05_unit22b`, 확인 후 삭제)
| 시나리오 | 수정 전 | 수정 후 |
|---|---|---|
| EXPIRED+purged NULL, 200분 경과 + 업로드 파일 | 잔존(FAIL) | 파일 삭제 + purged_at 기록 |
| 방금 만든(1분) 예약 행 | 보존 | 보존 |
| 65분 경과(유예 구간) 예약 행 | 보존 | 보존 |
| 이미 purged된 정상 EXPIRED 행 | 무변경 | 무변경 |
| 90분 DONE(기존 동작) | 정리 | 정리 |
| 재스윕(쿨다운 해제) | - | 0건, purged_at 불변(멱등) |
| `delete_job_objects` OSError | - | 0건, 행 purged_at NULL·파일 잔존 -> 다음 스윕 재시도 성공 |
| 일반 15 + 고아 15 | - | 합계 20건 처리, 고아 10건 이월 |
| 삭제 중 PENDING으로 승격된 행 | - | purged_at 미기록(조건부 UPDATE) |
결과: 수정 전 FAIL 2(고아 2항목)만, 수정 후 FAILS 0. 검증 스크립트는 저장소에 남기지 않음(unit-22 관례).

### R-6. 게이트
- 게이트 1: 저장소에 lint/type-check 설정 없음(기존 note §5와 동일). `py_compile` 통과, 실행 검증에서 import 성공.
- 게이트 2: [x] 명세(계약) 일치 [x] 예외 삼킴 없음(logger.exception) [x] 시스템 경계 입력 없음(내부 DB) [x] 시크릿 없음 [x] 신규 의존성 없음 [x] 범위 외 변경 없음(cleanup.py만).
- 06 테스트는 실행하지 않음. 규칙 B 검증 로그: `docs/harness/verify-log_unit-22-note.md`.

### R-7. 신규 인수 조건
- AC-8: EXPIRED+`purged_at` NULL+생성 71분 이상 경과 행은 스윕 후 업로드·결과 오브젝트가 삭제되고 `purged_at`이 채워진다.
- AC-9: 같은 조건이지만 생성 60분 미만·69분 등 70분 미만 행은 변화 없다.
- AC-10: `purged_at`이 이미 있는 EXPIRED 행은 스윕 전후 `purged_at` 값이 동일하다.
- AC-11: 고아 삭제 실패 시 행이 `purged_at` NULL로 남고 다음 스윕에서 재시도된다.
- AC-12: 배치 합계 상한 20 유지. 속도 트랙: L3.

### R-8. 미결 질문 / 관찰
- Q-1: 뷰에 예약 TTL 상수가 없음(위). 필요하면 공용 상수화는 unit-20 쪽 결정.
- OBS: 스윕 트리거가 현재 `GET /`(views.index)뿐이라 트래픽이 없으면 실행되지 않는다(기존 설계, 무변경). R2 라이프사이클 백스톱은 여전히 유효.

### R-9. 공유 문서 갱신 요청
- DEF-020c-01: 상태 -> 5단계 안전망 수정 완료(unit-22 R절), 06 재검증 대기 (DEC-063 근거).
- REQ-028 / 구현 상태: "고아 예약 EXPIRED 행 정리 추가(unit-22 재작업 v2)" 덧붙임.
- decisions.md: DEC-064(제안) 고아 예약 행 유예 = TTL 60분 + 10분, 정리 시 행 유지+purged_at 기록.

### R-10. git status 원문
```
 M docs/harness/03-system-design.md
 M docs/harness/decisions.md
 M docs/harness/traceability.md
 M docs/harness/units/unit-20-test.md
 M docs/harness/verify-log_03-system-design.md
 M docs/harness/verify-log_unit-20-test.md
 M webapp/converter/cleanup.py      <- 이 작업
 M webapp/converter/views.py        <- 다른 에이전트(unit-20)
?? docs/harness/analysis/
(이 작업이 추가로 수정한 파일: cleanup.py, unit-22-note.md, verify-log_unit-22-note.md(신규). 다른 항목은 동시 작업/기존 변경.)
```
