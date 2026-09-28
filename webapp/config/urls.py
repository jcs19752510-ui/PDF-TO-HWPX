"""프로젝트 루트 URL 설정(03-system-design.md §4-4 라우트 표, §1-3 unit-19).

`GET /`(업로드 폼)·`POST /convert`·`/api/jobs/<job_id>/`·`/download/<job_id>/`는
unit-20/21이 `converter/urls.py`를 만든 뒤 여기 include할 예정이라 아직
연결하지 않는다(존재하지 않는 모듈을 import하면 기동이 깨진다). `/privacy/`도
동일 사유로 unit-25(legal 앱) 착수 후 연결한다.

이번 unit(19)은 (a) Django 표준 admin, (b) `/healthz`(얕은 헬스체크, 로컬
기동 확인용) 두 라우트만 연결한다 — 03 §1-3 unit-19 확정 파일범위 표에는
`core/urls.py`/`core/views.py`가 명시적으로 배정되어 있지 않으나, 03 §1-3
패키지 레이아웃(96~120행)이 `core/` 앱의 표준 구성요소로 `views.py(healthz)`,
`urls.py`를 이미 나열해뒀고 이후 어느 unit(20~26)의 확정 파일범위 행에도
이 두 파일이 배정되어 있지 않다. 오케스트레이터가 "로컬에서 실제로 뜨는지
직접 확인"을 이번 unit의 최우선 목표로 명시했으므로, 검증 가능한 최소
엔드포인트(healthz)를 이번 unit이 함께 만든다(향후 unit과의 파일 충돌
없음 — 상세는 unit-19-note.md "설계서 대비 편차" 참고).
"""

from django.contrib import admin
from django.urls import include, path

from core import urls as core_urls

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include(core_urls)),
]
