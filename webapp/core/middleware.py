"""core 앱 미들웨어 (03-system-design.md §1-3 unit-24, §6-4).

`ContentLengthLimitMiddleware`: 요청 본문을 실제로 읽기 전에 `Content-Length`
헤더값만으로 업로드 크기 상한(REQ-029)을 강제한다. `MIDDLEWARE` 리스트에서
`SecurityMiddleware`보다도 앞단(최상단)에 등록해야 한다(03 §6-4) — 본문을
읽어들이는 그 어떤 처리(파싱/저장)도 시작하기 전에 거절해야 불필요한
메모리·대역폭 소모 자체를 회피할 수 있기 때문이다.
"""

from __future__ import annotations

from django.http import HttpResponse

from converter.limits import is_content_length_too_large


class ContentLengthLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        raw_content_length = request.META.get("CONTENT_LENGTH")
        if raw_content_length:
            try:
                content_length = int(raw_content_length)
            except (TypeError, ValueError):
                # 헤더 형식이 잘못된 경우도 외부 입력이므로 예외를 삼키지
                # 않고, 신뢰할 수 없는 값으로 취급해 본문 처리를 그대로
                # 뒤 단계(Django/WSGI 서버)에 맡긴다 — 크기 제한 판단만
                # 이 미들웨어의 책임이다.
                content_length = None
            if content_length is not None and is_content_length_too_large(content_length):
                return HttpResponse(
                    "업로드 파일이 너무 큽니다. 최대 50MB까지 허용됩니다.",
                    status=413,
                    content_type="text/plain; charset=utf-8",
                )
        return self.get_response(request)
