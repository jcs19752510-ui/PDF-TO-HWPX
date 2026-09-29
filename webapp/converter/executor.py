"""ThreadPoolExecutor 기반 비동기 변환 실행기.

(docs/harness/03-system-design.md §4-4(299~320행)가 고정한 시그니처를 그대로
구현한다 — unit-20(views.py)이 `submit_job()`을 import해서 호출하므로 이름/
인자/예외를 임의로 바꾸지 않는다.)

DEC-031: `_POOL`은 프로세스 전역 싱글톤 `ThreadPoolExecutor(max_workers=2)`다.
HTTP 요청-응답 스레드(views.py)는 `submit_job(job_id)`를 호출해 즉시 반환받고,
실제 변환(`pdf_to_hwpx.core.orchestrator.convert()` 호출)은 이 모듈의 `_run()`이
스레드풀 워커 스레드 안에서 수행한다(REQ-027 "블로킹 없음").

로깅: `pdf_to_hwpx.common.logging_setup.install()`을 호출하지 않는다(03 §1-1,
§4-4 319행) — `orchestrator.convert()` 내부의 `logging.getLogger(...)` 호출은
Django 표준 로깅(콘솔 핸들러)에 그대로 위임한다.

소프트 타임아웃(5분, §5)은 이 모듈이 강제하지 않는다 — views.py가 폴링 응답
생성 시 "생성 후 5분 경과 + 아직 처리중"을 판단해 사용자에게 안내한다(스레드
자체를 강제 종료하지 않음, §8-1 한계 명시). `PIL.Image.MAX_IMAGE_PIXELS`
전역 설정은 unit-24 책임이며, 이 모듈은 그 설정이 이미 적용돼 있다고 가정하고
`orchestrator.convert()`를 그대로 호출할 뿐 별도로 설정하지 않는다.
"""

from __future__ import annotations

import dataclasses
import logging
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from django.utils import timezone

from converter import storage
from converter.models import ConversionJob
from pdf_to_hwpx.core.orchestrator import ConversionOptions, ProgressEvent, convert

_logger = logging.getLogger(__name__)

_POOL = ThreadPoolExecutor(max_workers=2)  # DEC-031: 프로세스 전역 싱글톤
_PENDING_QUEUE_LIMIT = 20  # REQ-029, 03 §5


class QueueFullError(Exception):
    """대기중+실행중 job 합계가 `_PENDING_QUEUE_LIMIT`을 넘었을 때 던진다.

    호출자(views.py)가 이를 잡아 HTTP 503으로 매핑한다(03 §4-4).
    """


def submit_job(job_id: uuid.UUID) -> None:
    """PENDING 상태의 `ConversionJob`을 스레드풀에 제출한다.

    큐 포화(실행중+대기중 job 합계 >= `_PENDING_QUEUE_LIMIT`) 시
    `QueueFullError`를 던지고, 이 경우 스레드풀에 제출하지 않는다.
    """
    pending_count = ConversionJob.objects.filter(
        status__in=[ConversionJob.Status.PENDING, ConversionJob.Status.PROCESSING]
    ).count()
    if pending_count >= _PENDING_QUEUE_LIMIT:
        raise QueueFullError(
            f"대기열이 가득 찼습니다({pending_count}/{_PENDING_QUEUE_LIMIT})."
        )
    _POOL.submit(_run, job_id)


def _run(job_id: uuid.UUID) -> None:
    """실제 워커 함수(스레드풀 안에서 실행).

    R2(또는 dev의 로컬 FileSystemStorage)에서 입력파일을 로컬 임시경로로
    내려받고, `ConversionOptions.progress_callback`으로 매 `ProgressEvent`마다
    `ConversionJob` 행을 UPDATE한다. `orchestrator.convert()` 완료 후 결과를
    스토리지에 올리고 `ConversionJob.status`/`result_*`를 UPDATE한다.

    이 함수 안에서 어떤 예외가 발생하더라도 스레드를 죽이지 않고
    `ConversionJob.status=FAILED` + 로그 기록으로 이어진다(예외를 삼켜서
    무시하지 않는다).
    """
    try:
        job = ConversionJob.objects.get(job_id=job_id)
    except ConversionJob.DoesNotExist:
        _logger.error("submit된 job_id에 해당하는 ConversionJob이 없습니다: %s", job_id)
        return

    try:
        job.status = ConversionJob.Status.PROCESSING
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at"])

        with tempfile.TemporaryDirectory(prefix=f"pdf-to-hwpx-{job_id}-") as tmp_dir:
            input_path = Path(tmp_dir) / "input.pdf"
            output_path = Path(tmp_dir) / "output.hwpx"

            storage.download_upload_to_local(job_id, input_path)

            def _on_progress(event: ProgressEvent) -> None:
                job.progress_stage = event.stage
                job.progress_current_page = event.current_page
                job.progress_total_pages = event.total_pages
                job.progress_message = event.message
                job.save(
                    update_fields=[
                        "progress_stage",
                        "progress_current_page",
                        "progress_total_pages",
                        "progress_message",
                    ]
                )

            options = ConversionOptions(
                enable_ocr=job.enable_ocr,
                ocr_lang=job.ocr_lang,
                progress_callback=_on_progress,
            )
            result = convert(input_path, output_path, options)

            if result.success and result.output_path is not None:
                storage.save_result_file(job_id, result.output_path)
                job.output_object_key = storage.result_object_key(job_id)

            job.status = ConversionJob.Status.DONE
            job.finished_at = timezone.now()
            job.result_success = result.success
            job.result_warnings = [dataclasses.asdict(w) for w in result.warnings]
            job.result_errors = [dataclasses.asdict(e) for e in result.errors]
            job.save(
                update_fields=[
                    "status",
                    "finished_at",
                    "result_success",
                    "result_warnings",
                    "result_errors",
                    "output_object_key",
                ]
            )
    except Exception:
        _logger.exception("job 처리 중 인프라 레벨 오류(job_id=%s)", job_id)
        try:
            job.status = ConversionJob.Status.FAILED
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "finished_at"])
        except Exception:
            _logger.exception(
                "FAILED 상태 기록 자체도 실패했습니다(job_id=%s) — job이 고아 상태로"
                " 남을 수 있습니다(cleanup.py의 TTL 스윕이 최종 정리)",
                job_id,
            )
