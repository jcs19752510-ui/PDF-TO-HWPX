"""리소스 남용 방지 상한값 (03-system-design.md §5/§6-4, REQ-029, unit-24).

이 모듈은 **상수와 순수 검증 함수만** 정의한다. 실제 카운팅(동시 실행 수·
대기열, unit-21 `executor.py`)과 소프트 타임아웃 판정(unit-20 `views.py`
폴링 응답)은 이 값을 import해서 참조할 뿐이며, 그 로직 자체는 이 모듈에
흡수하지 않는다(03 §1-3 unit-24 행 "값 참조만 하고 로직은 흡수되지 않음").
"""

from __future__ import annotations

# 업로드 파일 크기 상한 (03 §5, DEC-030) — ContentLengthLimitMiddleware가
# Content-Length 헤더만으로 사전 검사한다(core/middleware.py).
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024  # 50MB

# 변환 처리 소프트 타임아웃 (03 §5) — 실제 판정("생성 후 5분 경과 + 아직
# processing")은 unit-20의 폴링 응답 생성 로직 몫이다. 여기서는 기준값만
# 제공한다.
CONVERSION_SOFT_TIMEOUT_SECONDS = 5 * 60  # 300초

# 동시 변환 처리 상한 (03 §5, DEC-031) — 실제 ThreadPoolExecutor 생성/
# 관리는 unit-21 `executor.py` 몫이다.
MAX_CONCURRENT_CONVERSIONS = 2

# 대기열(PENDING+PROCESSING 합계) 상한 (03 §5, §4-4) — 초과 시 신규 업로드를
# 503으로 거절한다. 실제 카운팅/거절 로직은 unit-21 `executor.py`(제출 시점
# 검사) 몫이다.
PENDING_QUEUE_LIMIT = 20

# 이미지 디컴프레션 상한 (03 §5, `PIL.Image.MAX_IMAGE_PIXELS`) — Django
# 진입점(config/settings/base.py)에서 전역 1회 설정한다. `pdf_to_hwpx/
# pdf_reader/image_extractor.py`는 수정하지 않는다(03 §1-3 unit-24 행).
MAX_IMAGE_PIXELS = 128_000_000  # 1억 2,800만 픽셀


def is_content_length_too_large(content_length: int) -> bool:
    """Content-Length 헤더값(바이트)이 업로드 상한을 초과하는지 검사한다.

    `ContentLengthLimitMiddleware`(core/middleware.py)가 사용한다.
    """
    return content_length > MAX_UPLOAD_SIZE_BYTES
