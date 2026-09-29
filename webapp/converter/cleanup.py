"""TTL 지연 스윕 (03-system-design.md §3-2/§6-2, REQ-028, DEC-029, unit-22).

3중 삭제 구조 중 2번째 계층 담당:
1. 다운로드 완료 즉시 삭제 — `converter/views.py::download`의 `_finalize()`가 이미 처리(unit-20).
2. **다운로드하지 않고 방치된 job의 60분 경과 지연 스윕 — 이 모듈.**
3. R2 버킷 자체 오브젝트 라이프사이클(백스톱) — 코드가 아니라 R2 콘솔 설정(`webapp/.env.example`
   상단 안내, unit-22-note.md §3 참고).

상시 cron/Celery beat 프로세스를 두지 않는다(DEC-029/DEC-031과 동일한 근거 — Render 무료
플랜에 상시 백그라운드 프로세스를 무료로 둘 방법이 마땅치 않음). 대신 `run_lazy_sweep_if_due()`를
HTTP 요청 처리 경로 어딘가(호출 지점은 unit-22-note.md §2 참고 — 이 unit의 확정 파일범위
밖이라 이 모듈은 그 호출부를 직접 등록하지 않는다)에서 호출하면, 최근 실행이
`SWEEP_COOLDOWN_SECONDS` 이내일 때는 즉시 반환하고(DB 쿼리 없음), 아니라면 만료된 job을
최대 `SWEEP_BATCH_LIMIT`건만 배치로 정리한다 — 요청-응답 스레드를 블로킹하지 않도록 가벼운
쿼리 1건 + 대상이 있을 때만 짧은 삭제 루프 수준으로 유지한다.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import timedelta

from django.utils import timezone

from . import storage
from .models import ConversionJob

logger = logging.getLogger(__name__)

TTL_MINUTES = 60
SWEEP_COOLDOWN_SECONDS = 5 * 60
SWEEP_BATCH_LIMIT = 20

_lock = threading.Lock()
# 프로세스 전역 변수(시간 단조 증가 기준, `time.monotonic()`) — 별도 DB 테이블/Redis
# 락 불필요(과설계 방지, 오케스트레이터 지시). 프로세스 재시작 시 초기화되는 것은 의도된
# 동작이다(재시작 직후 한 번은 다시 스윕이 돌아도 무해함 — delete_job_objects가 멱등).
_last_swept_monotonic: float | None = None


def run_lazy_sweep_if_due() -> int:
    """쿨다운 이내면 스킵(0 반환), 아니면 만료 job을 스윕하고 정리 건수를 반환한다."""
    global _last_swept_monotonic

    now_monotonic = time.monotonic()
    with _lock:
        if (
            _last_swept_monotonic is not None
            and now_monotonic - _last_swept_monotonic < SWEEP_COOLDOWN_SECONDS
        ):
            return 0
        _last_swept_monotonic = now_monotonic

    try:
        return _sweep_expired_jobs()
    except Exception:
        # 스윕 실패가 호출자(요청-응답 경로)의 본 작업을 방해해서는 안 된다 — 로그를
        # 반드시 남기고(예외를 무시하지 않음), 다음 정상 요청에서 쿨다운이 지나면
        # 다시 시도된다.
        logger.exception("TTL 지연 스윕 중 예상치 못한 오류가 발생했습니다.")
        return 0


def _sweep_expired_jobs() -> int:
    """`created_at` 기준 60분 경과 + 아직 EXPIRED가 아닌 job을 최대 20건 정리한다.

    DONE/FAILED로 최종 전이된 job과, PENDING/PROCESSING에 60분 넘게 멈춰있는
    "좀비 job"(03 §5 "프로세스 재시작에 따른 job 유실") 둘 다 정리 대상이다.
    """
    cutoff = timezone.now() - timedelta(minutes=TTL_MINUTES)

    job_ids: list[uuid.UUID] = list(
        ConversionJob.objects.exclude(status=ConversionJob.Status.EXPIRED)
        .filter(created_at__lt=cutoff)
        .order_by("created_at")
        .values_list("job_id", flat=True)[:SWEEP_BATCH_LIMIT]
    )
    if not job_ids:
        return 0

    succeeded_ids: list[uuid.UUID] = []
    for job_id in job_ids:
        try:
            storage.delete_job_objects(job_id)
        except Exception:
            # 한 job의 오브젝트 삭제 실패가 나머지 job 정리를 막아서는 안 된다
            # (벌크헤드, 03 §5 원칙과 동일한 정신) — 로그를 남기고 이 job만 이번
            # 배치에서 제외한다(status는 그대로 두어 다음 스윕에서 삭제 재시도).
            logger.exception(
                "TTL 스윕: job %s 오브젝트 삭제 실패, 이번 배치에서 제외합니다(다음 스윕에서 재시도).",
                job_id,
            )
            continue
        succeeded_ids.append(job_id)

    if not succeeded_ids:
        return 0

    purged_at = timezone.now()
    updated = ConversionJob.objects.filter(job_id__in=succeeded_ids).update(
        status=ConversionJob.Status.EXPIRED, purged_at=purged_at
    )
    if updated:
        logger.info("TTL 지연 스윕: %d건 정리(EXPIRED 처리)", updated)
    return updated
