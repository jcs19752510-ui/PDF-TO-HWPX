"""공유 오브젝트 스토리지 접근 계약 (unit-19~26의 공통 선행 산출물).

03-system-design.md §1-2가 `storage.py`를 패키지 레이아웃에 명시했고 §1-3(139행)이
"storage.delete_job_objects() 시그니처"를 unit-20/21/22가 공유하는 고정 계약이라고
전제했지만, 실제 함수 시그니처까지는 어느 unit의 확정 파일 범위에도 배정되지 않았다
(unit-19~26 파일범위 표에 storage.py가 없음). unit-20/21/22를 같은 웨이브에 병렬
배치하면서 이 파일을 각자 다르게 만들면 충돌하므로, DEC-016(ir.py 선례)과 동일한
방식으로 오케스트레이터가 병렬 웨이브 착수 전에 직접 생성한다(decisions.md DEC-039).

Django의 `STORAGES["default"]`가 이미 dev(로컬 FileSystemStorage)/production(R2
S3Storage) 전환을 담당하므로(unit-19), 이 모듈은 `default_storage`를 감싸는 얇은
헬퍼일 뿐 백엔드를 직접 분기하지 않는다.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile


def upload_object_key(job_id: uuid.UUID) -> str:
    return f"uploads/{job_id}.pdf"


def result_object_key(job_id: uuid.UUID) -> str:
    return f"results/{job_id}.hwpx"


def save_uploaded_file(job_id: uuid.UUID, uploaded_file: UploadedFile) -> None:
    """`request.FILES["file"]`를 그대로 받아 업로드 오브젝트로 저장한다(unit-20)."""
    default_storage.save(upload_object_key(job_id), uploaded_file)


def download_upload_to_local(job_id: uuid.UUID, local_path: Path) -> None:
    """실행기(unit-21)가 `orchestrator.convert()`에 넘길 로컬 임시 경로로 내려받는다."""
    key = upload_object_key(job_id)
    with default_storage.open(key, "rb") as src, open(local_path, "wb") as dst:
        dst.write(src.read())


def save_result_file(job_id: uuid.UUID, local_path: Path) -> None:
    """`orchestrator.convert()`가 만든 로컬 HWPX 파일을 결과 오브젝트로 업로드한다(unit-21)."""
    with open(local_path, "rb") as f:
        default_storage.save(result_object_key(job_id), UploadedFile(f))


def open_result_for_read(job_id: uuid.UUID):
    """다운로드 뷰(unit-20)가 프록시 스트리밍할 때 쓰는 읽기 핸들을 연다(DEC-036)."""
    return default_storage.open(result_object_key(job_id), "rb")


def delete_job_objects(job_id: uuid.UUID) -> None:
    """업로드본+결과본을 존재 여부와 무관하게 안전하게 삭제한다(REQ-028, unit-20/22가 호출)."""
    for key in (upload_object_key(job_id), result_object_key(job_id)):
        if default_storage.exists(key):
            default_storage.delete(key)
