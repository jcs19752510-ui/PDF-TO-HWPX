"""converter 앱 뷰 (03-system-design.md §4-4, unit-20).

라우트: `GET /`, `POST /convert`, `GET /api/jobs/<uuid:job_id>/`,
`GET /download/<uuid:job_id>/`.

각 뷰를 독립 함수로 유지한다(unit-23 레이트리밋 데코레이터를 나중에
얹기 쉽도록, 오케스트레이터 지시사항).

`converter.executor`는 `convert()` 뷰 내부에서만 지연 import 한다. 이 모듈이
`pdf_to_hwpx` 변환 라이브러리와 스레드풀까지 끌어오므로, 최상단 import로
바꾸면 의존성 누락 시 URLconf 로드 자체가 실패해 `GET /`·`/healthz` 등 무관한
라우트까지 전부 죽는다. import 실패는 503으로 위장하지 않고 500 + 전체 스택
로그로 드러낸다(unit-20-note.md 재작업 v2).
"""

from __future__ import annotations

import logging
import threading
import uuid

from django.http import FileResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from . import cleanup, limits, ratelimit, storage
from .models import ConversionJob

logger = logging.getLogger(__name__)

# REQ-014/03 §3-2 — OCR 언어 체크박스는 한국어/영어 2개만 제공(04-ux-design.md §2 Panel A).
_OCR_LANG_FIELDS = (("kor", "ocr_lang_kor"), ("eng", "ocr_lang_eng"))

# 대기열 용량 판정(`executor.submit_job`의 카운트)과 그 직후 PENDING 승격을 한 덩어리로
# 직렬화한다 — 없으면 동시 요청이 서로의 "예약 행"을 세지 못해 한도를 넘겨 통과한다.
# 프로세스 1개 전제(03 §2-1 `--workers 1`, ratelimit.py와 동일 전제).
_submit_lock = threading.Lock()


def index(request):
    """`GET /` — 업로드 폼 + 진행/결과 패널 셸(04-ux-design.md §1-2/§2).

    사전 고지 문구("최대 50MB")와 클라이언트 소프트타임아웃 배너(5분)가
    `limits.py`(unit-24)의 상수와 어긋나지 않도록 템플릿에 그대로 흘려보낸다
    — 04-ux-design.md §7이 이미 소프트타임아웃 판정을 "클라이언트 타이머"로
    해소해뒀으므로(서버가 별도 필드를 내려줄 필요 없음), 값 자체만 공유한다.

    이 뷰가 REQ-028(TTL 지연 스윕, unit-22)의 트리거 지점이다(03 §3-2,
    "요청 처리 중 트리거" — unit-22-note.md §2가 남긴 통합 지점을 오케스트레이터가
    반영). 스윕 자체는 5분 쿨다운을 자체 관리하므로 매 요청마다 DB에 부담을
    주지 않는다.
    """
    try:
        cleanup.run_lazy_sweep_if_due()
    except Exception:  # noqa: BLE001 — 페이지 렌더링을 막지 않는다(REQ-028 §8-1 한계와 동일 성격)
        logger.exception("REQ-028 지연 스윕 중 예외 발생 — 페이지 렌더링은 계속 진행")

    return render(
        request,
        "converter/index.html",
        {
            "max_upload_mb": limits.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024),
            "soft_timeout_seconds": limits.CONVERSION_SOFT_TIMEOUT_SECONDS,
        },
    )


@require_http_methods(["POST"])
@ratelimit.enforce_rate_limit
def convert(request):
    """`POST /convert` (03 §4-4).

    (1) 업로드 파일 자체 검증(시스템 경계 입력값 검증), (2) R2/로컬 스토리지에
    저장, (3) `ConversionJob(PENDING)` 생성, (4) `executor.submit_job()` 제출.
    큐 포화(`QueueFullError`)는 503으로 매핑한다(REQ-029, 03 §4-4).
    """
    uploaded_file = request.FILES.get("file")
    if uploaded_file is None or not uploaded_file.name:
        return JsonResponse({"error": "파일이 없습니다."}, status=400)

    filename = uploaded_file.name
    looks_like_pdf = filename.lower().endswith(".pdf") or uploaded_file.content_type == "application/pdf"
    if not looks_like_pdf:
        return JsonResponse({"error": "PDF 파일만 업로드할 수 있습니다."}, status=400)

    enable_ocr = request.POST.get("enable_ocr") in ("on", "true", "1")
    ocr_lang = "kor"
    if enable_ocr:
        selected_langs = [
            code
            for code, field_name in _OCR_LANG_FIELDS
            if request.POST.get(field_name) in ("on", "true", "1")
        ]
        if not selected_langs:
            return JsonResponse(
                {"error": "OCR 언어를 최소 1개 선택해야 합니다."}, status=400
            )
        ocr_lang = "+".join(selected_langs)

    # 업로드 저장/job 생성보다 먼저 import한다 — 설치 오류가 나도 고아 업로드
    # 파일·PENDING job이 남지 않는다.
    try:
        from .executor import QueueFullError, submit_job
    except ImportError:
        # 재시도로 해결되지 않는 배포/설치 오류다. 503("바쁨")으로 위장하지 않고
        # 진짜 원인은 전체 스택과 함께 로그에만 남긴다(응답에는 내부 정보 비노출).
        # Django 기본 500 처리에 맡기지 않는 이유: LOGGING 미설정 + DEBUG=False에서는
        # ADMINS 메일 외에 스택이 어디에도 출력되지 않는다.
        logger.exception("converter.executor import 실패 — 배포 의존성 점검 필요")
        return JsonResponse(
            {"error": "예상치 못한 문제가 발생했습니다. 같은 문제가 계속되면 GitHub Issue로 알려주세요."},
            status=500,
        )

    job = ConversionJob(
        status=ConversionJob.Status.PENDING,
        enable_ocr=enable_ocr,
        ocr_lang=ocr_lang,
        input_object_key=storage.upload_object_key(uuid.uuid4()),
    )
    # job.job_id는 default=uuid.uuid4 콜러블이 인스턴스 생성 시점에 이미 채워둔
    # 값이다(save() 이전에도 접근 가능) — 위에서 임시로 넣은 input_object_key를
    # 실제 job_id 기준 키로 다시 맞춘다.
    job.input_object_key = storage.upload_object_key(job.job_id)

    storage.save_uploaded_file(job.job_id, uploaded_file)

    try:
        _save_and_submit(job, submit_job)
    except QueueFullError:
        # 큐 포화 — 방금 저장한 job 행·업로드는 즉시 폐기한다. PENDING으로 남겨두면
        # 실행되지도 않는 행이 대기열 카운트를 최대 60분(TTL) 차지해 포화가 스스로 길어진다.
        _discard_job(job.job_id)
        return JsonResponse(
            {"error": "지금은 이용자가 많아 서버가 바쁩니다. 1~2분 후 다시 시도해주세요."},
            status=503,
        )
    except Exception:
        _discard_job(job.job_id)
        raise

    return JsonResponse({"job_id": str(job.job_id)}, status=202)


def _save_and_submit(job, submit_job):
    """job 행 저장 → 큐 제출 → PENDING 승격. `_submit_lock` 안에서만 수행한다.

    `submit_job`은 PENDING+PROCESSING 행 수가 20 이상이면 거절하는데(03 §5, 20건까지
    허용) 새 job이 이미 PENDING으로 저장돼 있으면 스스로를 세어 실효 용량이 19가 된다.
    그래서 제출 전에는 카운트 대상이 아닌 EXPIRED로 저장해 두고, 제출 성공 뒤에만
    PENDING으로 올린다. 승격은 조건부 UPDATE라 워커가 그 사이 PROCESSING/DONE으로
    바꿨다면 덮어쓰지 않는다. EXPIRED는 폴링·다운로드 뷰에서 404이지만 job_id를
    클라이언트가 아직 받기 전이라 노출되지 않는다.
    """
    with _submit_lock:
        job.status = ConversionJob.Status.EXPIRED
        job.save()
        submit_job(job.job_id)
        try:
            ConversionJob.objects.filter(
                job_id=job.job_id, status=ConversionJob.Status.EXPIRED
            ).update(status=ConversionJob.Status.PENDING)
        except Exception:
            # 이미 워커에 제출됐으므로 폐기하지 않는다(워커가 곧 PROCESSING으로 바꾼다).
            logger.exception("job PENDING 승격 실패(job_id=%s)", job.job_id)


def _discard_job(job_id):
    """제출에 실패한 job의 행과 업로드 오브젝트를 정리한다(TTL 스윕은 EXPIRED 행을 건너뛴다)."""
    try:
        storage.delete_job_objects(job_id)
    except Exception:
        logger.exception("제출 실패 job의 업로드 삭제 실패(job_id=%s)", job_id)
    ConversionJob.objects.filter(job_id=job_id).delete()


@require_GET
def job_status(request, job_id):
    """`GET /api/jobs/<uuid:job_id>/` (03 §4-4) — DB 조회만, 라이브러리 재호출 없음."""
    try:
        job = ConversionJob.objects.get(job_id=job_id)
    except ConversionJob.DoesNotExist:
        return JsonResponse({"error": "요청을 찾을 수 없습니다."}, status=404)

    if job.status == ConversionJob.Status.EXPIRED:
        return JsonResponse({"error": "요청을 찾을 수 없습니다."}, status=404)

    return JsonResponse(
        {
            "status": job.status,
            "progress": {
                "stage": job.progress_stage,
                "current_page": job.progress_current_page,
                "total_pages": job.progress_total_pages,
                "message": job.progress_message,
            },
            "warnings": job.result_warnings,
            "errors": job.result_errors,
        }
    )


class _AutoDeleteFile:
    """스트리밍이 끝나 `close()`가 호출된 뒤에만 삭제 콜백을 실행하는 래퍼.

    Django `FileResponse`는 파일류 객체의 `close`를 `_resource_closers`에
    등록해 응답 스트리밍이 완전히 끝난 뒤 정확히 한 번 호출한다 — 이 시점은
    "스트리밍이 끝나면 즉시 삭제한다"(03 §4-4/DEC-036)는 요구를 그대로
    만족하며, 파일 핸들이 이미 닫힌 뒤에 삭제하므로 로컬(FileSystemStorage)
    백엔드에서도 안전하다(연 상태의 파일을 지우려다 잠금 오류가 나는 것을
    피한다).
    """

    def __init__(self, fileobj, on_close):
        self._fileobj = fileobj
        self._on_close = on_close
        self._done = False

    def read(self, *args, **kwargs):
        return self._fileobj.read(*args, **kwargs)

    def close(self):
        try:
            self._fileobj.close()
        finally:
            if not self._done:
                self._done = True
                self._on_close()

    def __getattr__(self, name):
        return getattr(self._fileobj, name)


@require_GET
def download(request, job_id):
    """`GET /download/<uuid:job_id>/` (03 §4-4, DEC-036 프록시 스트리밍)."""
    try:
        job = ConversionJob.objects.get(job_id=job_id)
    except ConversionJob.DoesNotExist:
        return JsonResponse({"error": "요청을 찾을 수 없습니다."}, status=404)

    if job.status == ConversionJob.Status.EXPIRED:
        return JsonResponse({"error": "요청을 찾을 수 없습니다."}, status=404)

    if job.status in (ConversionJob.Status.PENDING, ConversionJob.Status.PROCESSING):
        return JsonResponse({"error": "아직 처리 중입니다."}, status=409)

    if job.status == ConversionJob.Status.FAILED:
        # 03 §3-2 상태전이 규칙: FAILED는 result_errors가 비어있을 수 있으므로
        # 내용에 의존하지 않고 일반 메시지만 노출한다(내부 원인 비노출).
        return JsonResponse(
            {"error": "서버 처리 중 오류가 발생했습니다. 다시 시도해주세요."},
            status=422,
        )

    # status == DONE
    if not job.result_success:
        return JsonResponse({"errors": job.result_errors}, status=422)

    try:
        raw_file = storage.open_result_for_read(job.job_id)
    except FileNotFoundError:
        # 이미 다운로드되어 삭제됐거나(재다운로드 시도), 예상과 달리 결과
        # 오브젝트가 없는 경우 — 둘 다 "더 이상 제공할 수 없음"이므로 404.
        return JsonResponse({"error": "요청을 찾을 수 없습니다."}, status=404)

    def _finalize():
        now = timezone.now()
        storage.delete_job_objects(job.job_id)
        ConversionJob.objects.filter(job_id=job.job_id).update(
            downloaded_at=now, purged_at=now
        )

    response = FileResponse(
        _AutoDeleteFile(raw_file, _finalize),
        as_attachment=True,
        filename="converted.hwpx",
        content_type="application/octet-stream",
    )
    return response
