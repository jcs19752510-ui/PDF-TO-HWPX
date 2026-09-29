"""IP 기반 레이트리밋 (03-system-design.md §6-4, DEC-032, unit-23).

`admin_auth.py`(AI-AUTO-WORK, `webapp/core/admin_auth.py`)의
`is_rate_limited(ip)` 패턴(Django `LocMemCache` + `cache.incr` 고정윈도우
카운터)을 그대로 재사용해 "IP당 시간당 20회 업로드"를 구현한다.

"IP당 동시 진행중(PENDING+PROCESSING) job 2건"은 `ConversionJob`에 IP
필드가 없으므로(DEC-036/03 §3-2 "client_ip를 DB에 영속 저장하지 않는다")
다른 방식으로 판정한다 — 이 IP가 최근 제출한 job_id 목록만 LocMemCache에
휘발성으로 보관해두고(값 자체는 DB에 저장하지 않음, §3-2 그대로 준수),
그 job_id들의 **현재** 상태를 `ConversionJob` 테이블에서 조회해 PENDING/
PROCESSING인 것만 센다. 이렇게 하면 job이 실제로 끝났는지(DONE/FAILED)를
executor.py(unit-21)나 views.py를 건드리지 않고도 정확히 반영할 수 있다.

캡차(hCaptcha)는 DEC-032에 따라 v1에서 구현하지 않는다.
"""

from __future__ import annotations

import json
from functools import wraps

from django.core.cache import cache
from django.http import JsonResponse

from .models import ConversionJob

# 시간당 업로드 횟수 상한(03 §6-4, DEC-032).
UPLOAD_RATE_LIMIT_MAX_ATTEMPTS = 20
UPLOAD_RATE_LIMIT_WINDOW_SECONDS = 60 * 60  # 1시간

# IP당 동시 진행중(PENDING+PROCESSING) job 상한(03 §6-4, DEC-032).
CONCURRENT_JOB_LIMIT = 2

# 추적 목록 보관기간 — TTL(60분, DEC-029) 근방으로 맞춘다. 이보다 오래 들고
# 있어봐야 그 job은 이미 EXPIRED로 정리됐을 것이므로 의미가 없다.
_TRACKED_JOBS_TTL_SECONDS = 60 * 60
# 추적 목록 자체가 무한정 커지는 것을 막는 안전핀(한 IP가 아주 짧은 시간에
# 수십 건을 시도해도 캐시 값 크기가 발산하지 않도록).
_MAX_TRACKED_JOBS_PER_IP = 50

# 04-ux-design.md §1-2/§7 확정 문구 — 시간당 횟수 초과/동시 진행중 초과를
# 구분하지 않고 단일 일반 문구로 통합 처리한다(03 §4-4가 두 사유를 구분하는
# 에러 바디 스키마를 정의하지 않았기 때문, 04 §7 표 그대로).
_RATE_LIMIT_MESSAGE = (
    "요청이 제한되었습니다. 시간당 업로드 횟수를 초과했거나 이미 진행 중인"
    " 작업이 있습니다. 잠시 후 다시 시도해주세요"
)


def _upload_attempts_cache_key(client_ip: str) -> str:
    return f"converter:ratelimit:uploads:{client_ip}"


def _tracked_jobs_cache_key(client_ip: str) -> str:
    return f"converter:ratelimit:jobs:{client_ip}"


def is_upload_rate_limited(client_ip: str) -> bool:
    """시간당 업로드 시도 횟수가 상한을 초과했는지 판정한다(`admin_auth.py` 패턴).

    성공/실패(400 등) 여부와 무관하게 `POST /convert` 시도 자체를 센다 —
    `admin_auth.py`의 로그인 시도 카운터가 자격증명 valid 여부와 무관하게
    모든 POST 시도를 세는 것과 동일한 설계(무효 시도를 반복해 우회하는
    경로를 남기지 않기 위함).
    """
    if not client_ip:
        return False
    key = _upload_attempts_cache_key(client_ip)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=UPLOAD_RATE_LIMIT_WINDOW_SECONDS)
        count = 1
    return count > UPLOAD_RATE_LIMIT_MAX_ATTEMPTS


def is_concurrent_limit_exceeded(client_ip: str) -> bool:
    """이 IP가 이미 동시 진행중(PENDING+PROCESSING) job을 2건 갖고 있는지 판정한다."""
    if not client_ip:
        return False
    tracked_job_ids = cache.get(_tracked_jobs_cache_key(client_ip)) or []
    if not tracked_job_ids:
        return False
    in_progress_count = ConversionJob.objects.filter(
        job_id__in=tracked_job_ids,
        status__in=[ConversionJob.Status.PENDING, ConversionJob.Status.PROCESSING],
    ).count()
    return in_progress_count >= CONCURRENT_JOB_LIMIT


def _track_submitted_job(client_ip: str, job_id: str) -> None:
    if not client_ip or not job_id:
        return
    key = _tracked_jobs_cache_key(client_ip)
    tracked_job_ids = cache.get(key) or []
    tracked_job_ids = (tracked_job_ids + [job_id])[-_MAX_TRACKED_JOBS_PER_IP:]
    cache.set(key, tracked_job_ids, timeout=_TRACKED_JOBS_TTL_SECONDS)


def enforce_rate_limit(view_func):
    """`POST /convert` 뷰(views.py, unit-20)에 얹는 데코레이터.

    (1) 시간당 업로드 횟수, (2) 동시 진행중 job 2건 — 둘 중 하나라도
    초과하면 원래 뷰를 호출하지 않고(파일 저장/DB insert 등 부수효과가
    시작되지 않도록) 429를 반환한다. 통과해 원래 뷰가 202로 신규 job을
    발급하면, 그 job_id를 이 IP의 추적 목록에 추가해 다음 요청부터 동시
    진행중 판정에 반영되게 한다.
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        client_ip = request.META.get("REMOTE_ADDR", "")

        if is_upload_rate_limited(client_ip) or is_concurrent_limit_exceeded(client_ip):
            return JsonResponse({"error": _RATE_LIMIT_MESSAGE}, status=429)

        response = view_func(request, *args, **kwargs)

        if response.status_code == 202:
            try:
                job_id = json.loads(response.content).get("job_id")
            except (ValueError, AttributeError):
                job_id = None
            _track_submitted_job(client_ip, job_id)

        return response

    return _wrapped
