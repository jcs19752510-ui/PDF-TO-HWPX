"""ConversionJob 모델(03-system-design.md §3-2, unit-19 산출물).

unit-20/21/22/24가 이 모델을 그대로 소비한다 — 필드명/타입을 임의로 바꾸지
않는다(03 §1-3 unit-19 행 "공유 자원 접촉" 참고).
"""

import uuid

from django.db import models


class ConversionJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "대기중"
        PROCESSING = "processing", "변환중"
        DONE = "done", "완료"
        FAILED = "failed", "실패"
        EXPIRED = "expired", "만료(파일삭제됨)"

        # 상태 전이 규칙(구현자 필독): PENDING -> PROCESSING -> (DONE | FAILED) -> EXPIRED.
        # DONE = orchestrator.convert()가 예외 없이 반환됨(REQ-009 계약대로) — 이 경우
        #   result_success=True/False 둘 다 가능하다(False는 "변환은 끝났지만 품질/부분
        #   실패", 예: 손상된 PDF를 orchestrator가 스스로 감지해 errors에 담아 반환한
        #   경우). 즉 DONE은 "라이브러리가 통제된 방식으로 마쳤다"는 뜻이지 "성공"의
        #   동의어가 아니다.
        # FAILED = executor 자신의 인프라 레벨 실패(orchestrator.convert() 호출 자체가
        #   처리되지 못함) — 예: R2 업로드/다운로드 실패, 예상치 못한 미핸들링 예외로
        #   워커 함수가 죽음. 이 경우 result_success/result_warnings/result_errors는
        #   비어 있을 수 있다.
        # 다운로드 뷰(§4-4)는 이 둘을 구분해 사용자 메시지를 다르게 보여준다:
        #   DONE+result_success=False -> result_errors를 그대로 노출(사용자가 이해할
        #   수 있는 콘텐츠 문제, REQ-009). FAILED -> "서버 처리 중 오류가 발생했습니다.
        #   다시 시도해주세요" 같은 일반 메시지(내부 원인을 사용자에게 노출하지 않음).

    job_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    downloaded_at = models.DateTimeField(null=True, blank=True)
    purged_at = models.DateTimeField(null=True, blank=True)  # R2 오브젝트/원본파일명 삭제 완료 시각

    # 입력 옵션(REQ-014 OCR 등) — ConversionOptions와 1:1 대응
    enable_ocr = models.BooleanField(default=False)
    ocr_lang = models.CharField(max_length=16, default="kor")

    # R2 오브젝트 키(파일 내용 자체는 DB에 없음, §2-1)
    input_object_key = models.CharField(max_length=255)
    output_object_key = models.CharField(max_length=255, blank=True)

    # 진행률(ProgressEvent를 그대로 매핑, §4-1)
    progress_stage = models.CharField(max_length=16, blank=True)
    progress_current_page = models.IntegerField(default=0)
    progress_total_pages = models.IntegerField(default=0)
    progress_message = models.CharField(max_length=255, blank=True)

    # 결과(ConversionResult를 그대로 매핑)
    result_success = models.BooleanField(null=True)
    result_warnings = models.JSONField(default=list)   # list[dict] — ConversionWarning 직렬화
    result_errors = models.JSONField(default=list)      # list[dict] — ConversionIssue 직렬화

    class Meta:
        indexes = [models.Index(fields=["status", "created_at"])]  # cleanup.py의 TTL 스캔 쿼리용
