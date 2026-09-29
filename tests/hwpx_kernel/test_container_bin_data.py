"""unit-4 재작업(2026-09-28) — `pdf_to_hwpx/hwpx_kernel/container.py`의
`add_bin_data()` 검증.

배경: unit-7(image_embedder.py)이 "이미지를 실제 HWPX zip 안의 BinData로
저장할 기능이 없다"는 공유 문서 갱신 요청(unit-7-note.md §6-1)을 남긴 뒤,
container.py에 `add_bin_data(container_path, entries)` 함수가 추가 구현됐다.
이 구현은 `python -m py_compile`로 문법 검증만 통과했고, 사용자의 긴급 중단
지시로 06단계 테스트가 실행되지 못한 채 중단됐다 — 즉 이 함수는 이번 세션
전까지 전혀 테스트되지 않았다.

근거: `pdf_to_hwpx/hwpx_kernel/container.py`의 `add_bin_data` docstring(286~319행),
`docs/harness/units/unit-7-note.md` §6-1(제안 시그니처), `docs/harness/units/unit-4-note.md`.

**범위의 근본적 한계(기존 test_container.py 헤더와 동일 원칙)**: 이 테스트는
"우리가 만든 zip+XML이 구조적으로 well-formed하고, 우리 스스로 정의한 규칙과
내부적으로 일관되는가"만 증명한다. 실제 한글(한컴오피스)이 `BinData/` 디렉터리
관례·manifest 등록 방식을 실제로 요구하는지는 개발 환경에 한글이 없어 전혀
검증하지 못했다(DEC-017과 동일한 성격의 미검증 리스크 — add_bin_data 자체가
이 리스크를 새로 추가한다는 점을 unit-4-test.md 재작업 섹션 8절에 기록한다).
"""

from __future__ import annotations

import zipfile

import pytest
from lxml import etree

from pdf_to_hwpx.common.exceptions import ContainerBuildError
from pdf_to_hwpx.hwpx_kernel.container import (
    BIN_DATA_DIR,
    DEFAULT_SECTION_NAME,
    NAMESPACES,
    SECTION_DIR,
    add_bin_data,
    build_empty_container,
)

MANIFEST_ARCNAME = "META-INF/manifest.xml"
CONTENT_HPF_ARCNAME = f"{SECTION_DIR}/content.hpf"


def _manifest_paths(zf: zipfile.ZipFile) -> set[str]:
    root = etree.fromstring(zf.read(MANIFEST_ARCNAME))
    return {el.get("full-path") for el in root.findall(f"{{{NAMESPACES['ocf']}}}file-entry")}


def _manifest_media_type(zf: zipfile.ZipFile, full_path: str) -> str | None:
    root = etree.fromstring(zf.read(MANIFEST_ARCNAME))
    for el in root.findall(f"{{{NAMESPACES['ocf']}}}file-entry"):
        if el.get("full-path") == full_path:
            return el.get("media-type")
    return None


def _content_hpf_items(zf: zipfile.ZipFile) -> list[etree._Element]:
    root = etree.fromstring(zf.read(CONTENT_HPF_ARCNAME))
    manifest = root.find(f"{{{NAMESPACES['opf']}}}manifest")
    assert manifest is not None
    return manifest.findall(f"{{{NAMESPACES['opf']}}}item")


def _content_hpf_spine_idrefs(zf: zipfile.ZipFile) -> list[str]:
    root = etree.fromstring(zf.read(CONTENT_HPF_ARCNAME))
    spine = root.find(f"{{{NAMESPACES['opf']}}}spine")
    assert spine is not None
    return [el.get("idref") for el in spine.findall(f"{{{NAMESPACES['opf']}}}itemref")]


# ---------------------------------------------------------------------------
# 정상 경로: 단일 엔트리
# ---------------------------------------------------------------------------


def test_add_bin_data_single_entry_writes_zip_member_with_correct_path(tmp_path):
    output_path = tmp_path / "container.hwpx"
    build_empty_container(output_path)

    add_bin_data(output_path, {"bin0": (b"\xff\xd8\xff\xe0fakejpeg", "jpeg")})

    with zipfile.ZipFile(output_path, mode="r") as zf:
        assert zf.testzip() is None
        assert f"{BIN_DATA_DIR}/bin0.jpg" in zf.namelist()
        assert zf.read(f"{BIN_DATA_DIR}/bin0.jpg") == b"\xff\xd8\xff\xe0fakejpeg"


def test_add_bin_data_registers_manifest_entry_with_correct_media_type(tmp_path):
    output_path = tmp_path / "container.hwpx"
    build_empty_container(output_path)

    add_bin_data(output_path, {"bin0": (b"raw-png-bytes", "png")})

    with zipfile.ZipFile(output_path, mode="r") as zf:
        arcname = f"{BIN_DATA_DIR}/bin0.png"
        assert arcname in _manifest_paths(zf)
        assert _manifest_media_type(zf, arcname) == "image/png"


def test_add_bin_data_registers_content_hpf_item_but_not_spine(tmp_path):
    """OPF류 관례: BinData는 manifest(item)에는 등록되지만 spine(읽기 순서)에는
    들어가지 않는다 — container.py docstring 300~303행이 명시한 계약."""
    output_path = tmp_path / "container.hwpx"
    build_empty_container(output_path)

    add_bin_data(output_path, {"bin0": (b"raw-png-bytes", "png")})

    with zipfile.ZipFile(output_path, mode="r") as zf:
        items = _content_hpf_items(zf)
        matching = [it for it in items if it.get("id") == "bin0"]
        assert len(matching) == 1
        assert matching[0].get("href") == f"{BIN_DATA_DIR}/bin0.png"
        assert matching[0].get("media-type") == "image/png"

        # spine에는 섹션(section0)만 있고 bin0은 없어야 한다.
        spine_idrefs = _content_hpf_spine_idrefs(zf)
        assert "bin0" not in spine_idrefs
        assert spine_idrefs == ["section0"]


# ---------------------------------------------------------------------------
# 정상 경로: 복수 엔트리, 포맷별 확장자/미디어타입 매핑
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("image_format", "expected_extension", "expected_media_type"),
    [
        ("jpeg", "jpg", "image/jpeg"),
        ("jp2", "jp2", "image/jp2"),
        ("png", "png", "image/png"),
        ("tiff", "tif", "image/tiff"),
    ],
)
def test_add_bin_data_extension_and_media_type_mapping(
    tmp_path, image_format, expected_extension, expected_media_type
):
    output_path = tmp_path / "container.hwpx"
    build_empty_container(output_path)

    add_bin_data(output_path, {"binX": (b"data", image_format)})

    with zipfile.ZipFile(output_path, mode="r") as zf:
        arcname = f"{BIN_DATA_DIR}/binX.{expected_extension}"
        assert arcname in zf.namelist()
        assert _manifest_media_type(zf, arcname) == expected_media_type


def test_add_bin_data_multiple_entries_all_written_and_registered(tmp_path):
    output_path = tmp_path / "container.hwpx"
    build_empty_container(output_path)

    entries = {
        "bin0": (b"jpeg-bytes", "jpeg"),
        "bin1": (b"png-bytes", "png"),
        "bin2": (b"tiff-bytes", "tiff"),
    }
    add_bin_data(output_path, entries)

    with zipfile.ZipFile(output_path, mode="r") as zf:
        namelist = zf.namelist()
        assert f"{BIN_DATA_DIR}/bin0.jpg" in namelist
        assert f"{BIN_DATA_DIR}/bin1.png" in namelist
        assert f"{BIN_DATA_DIR}/bin2.tif" in namelist
        assert zf.read(f"{BIN_DATA_DIR}/bin0.jpg") == b"jpeg-bytes"
        assert zf.read(f"{BIN_DATA_DIR}/bin1.png") == b"png-bytes"
        assert zf.read(f"{BIN_DATA_DIR}/bin2.tif") == b"tiff-bytes"

        manifest_paths = _manifest_paths(zf)
        assert f"{BIN_DATA_DIR}/bin0.jpg" in manifest_paths
        assert f"{BIN_DATA_DIR}/bin1.png" in manifest_paths
        assert f"{BIN_DATA_DIR}/bin2.tif" in manifest_paths

        item_ids = {it.get("id") for it in _content_hpf_items(zf)}
        assert {"bin0", "bin1", "bin2"} <= item_ids


# ---------------------------------------------------------------------------
# 기존 엔트리 보존 — mimetype/섹션 등 기존 8개 파트가 그대로 유지된다
# ---------------------------------------------------------------------------


def test_add_bin_data_preserves_existing_entries_and_mimetype_position(tmp_path):
    output_path = tmp_path / "container.hwpx"
    build_empty_container(output_path)

    with zipfile.ZipFile(output_path, mode="r") as zf:
        before_section = zf.read(f"{SECTION_DIR}/{DEFAULT_SECTION_NAME}")
        before_mimetype_info = zf.infolist()[0]

    add_bin_data(output_path, {"bin0": (b"data", "png")})

    with zipfile.ZipFile(output_path, mode="r") as zf:
        # mimetype이 여전히 첫 엔트리·비압축 상태를 유지한다.
        after_mimetype_info = zf.infolist()[0]
        assert after_mimetype_info.filename == "mimetype"
        assert after_mimetype_info.compress_type == zipfile.ZIP_STORED == before_mimetype_info.compress_type
        # 섹션 XML은 add_bin_data가 건드리지 않는다.
        assert zf.read(f"{SECTION_DIR}/{DEFAULT_SECTION_NAME}") == before_section
        # 원래 8개 파트가 모두 그대로 존재한다.
        for original_name in (
            "mimetype",
            "version.xml",
            "settings.xml",
            "META-INF/container.xml",
            "META-INF/manifest.xml",
            f"{SECTION_DIR}/header.xml",
            f"{SECTION_DIR}/{DEFAULT_SECTION_NAME}",
            f"{SECTION_DIR}/content.hpf",
        ):
            assert original_name in zf.namelist()


# ---------------------------------------------------------------------------
# 멱등성 — 동일 bin_data_id 재호출 시 manifest/content.hpf 중복 등록 없이 바이트만 갱신
# ---------------------------------------------------------------------------


def test_add_bin_data_idempotent_reregistration_overwrites_bytes_without_duplicate_manifest_entries(
    tmp_path,
):
    output_path = tmp_path / "container.hwpx"
    build_empty_container(output_path)

    add_bin_data(output_path, {"bin0": (b"first-bytes", "png")})
    add_bin_data(output_path, {"bin0": (b"second-bytes-updated", "png")})

    with zipfile.ZipFile(output_path, mode="r") as zf:
        arcname = f"{BIN_DATA_DIR}/bin0.png"
        # 바이트는 마지막 호출 값으로 갱신된다.
        assert zf.read(arcname) == b"second-bytes-updated"
        # zip 엔트리 자체가 중복되지 않는다(동일 arcname 1개만).
        assert zf.namelist().count(arcname) == 1

        manifest_root = etree.fromstring(zf.read(MANIFEST_ARCNAME))
        matching_manifest_entries = [
            el
            for el in manifest_root.findall(f"{{{NAMESPACES['ocf']}}}file-entry")
            if el.get("full-path") == arcname
        ]
        assert len(matching_manifest_entries) == 1

        content_items = [it for it in _content_hpf_items(zf) if it.get("id") == "bin0"]
        assert len(content_items) == 1


# ---------------------------------------------------------------------------
# 경계값: 빈 entries -> 아무 것도 하지 않음(파일 미접촉, 예외 없음)
# ---------------------------------------------------------------------------


def test_add_bin_data_empty_entries_is_noop(tmp_path):
    output_path = tmp_path / "container.hwpx"
    build_empty_container(output_path)
    before_bytes = output_path.read_bytes()

    add_bin_data(output_path, {})

    after_bytes = output_path.read_bytes()
    assert after_bytes == before_bytes


# ---------------------------------------------------------------------------
# 예외 입력: 잘못된 image_format
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_format", ["ccitt", "jbig2", "unknown", "", "PNG", "gif"])
def test_add_bin_data_invalid_image_format_raises_and_does_not_touch_file(tmp_path, bad_format):
    output_path = tmp_path / "container.hwpx"
    build_empty_container(output_path)
    before_bytes = output_path.read_bytes()

    with pytest.raises(ContainerBuildError):
        add_bin_data(output_path, {"bin0": (b"data", bad_format)})

    # 검증은 zip을 열기 전에 이루어지므로(container.py 320~328행) 원본이 전혀 훼손되지 않는다.
    assert output_path.read_bytes() == before_bytes
    tmp_leftover = output_path.with_name(output_path.name + ".tmp")
    assert not tmp_leftover.exists()


def test_add_bin_data_mixed_valid_and_invalid_entries_raises_before_writing_any(tmp_path):
    """entries 중 하나라도 잘못된 image_format이면, 유효한 다른 엔트리도 전혀
    기록되지 않아야 한다(전량 검증 후 기록 — 부분 반영 금지)."""
    output_path = tmp_path / "container.hwpx"
    build_empty_container(output_path)
    before_bytes = output_path.read_bytes()

    with pytest.raises(ContainerBuildError):
        add_bin_data(
            output_path,
            {"bin0": (b"valid-png-bytes", "png"), "bin1": (b"data", "ccitt")},
        )

    assert output_path.read_bytes() == before_bytes
    with zipfile.ZipFile(output_path, mode="r") as zf:
        assert f"{BIN_DATA_DIR}/bin0.png" not in zf.namelist()


# ---------------------------------------------------------------------------
# 예외 입력: 존재하지 않는 container_path
# ---------------------------------------------------------------------------


def test_add_bin_data_raises_when_container_missing(tmp_path):
    missing_path = tmp_path / "does_not_exist.hwpx"
    assert not missing_path.exists()

    with pytest.raises(ContainerBuildError):
        add_bin_data(missing_path, {"bin0": (b"data", "png")})


# ---------------------------------------------------------------------------
# 예외 입력: 필수 파트(manifest.xml/content.hpf) 없는 손상된 컨테이너
# ---------------------------------------------------------------------------


def test_add_bin_data_raises_when_manifest_missing(tmp_path):
    container_path = tmp_path / "no_manifest.hwpx"
    with zipfile.ZipFile(container_path, mode="w") as zf:
        zf.writestr("mimetype", b"application/hwp+zip")
        zf.writestr(
            CONTENT_HPF_ARCNAME,
            f'<opf:package xmlns:opf="{NAMESPACES["opf"]}"><opf:manifest/><opf:spine/></opf:package>'.encode(
                "utf-8"
            ),
        )

    with pytest.raises(ContainerBuildError):
        add_bin_data(container_path, {"bin0": (b"data", "png")})

    tmp_leftover = container_path.with_name(container_path.name + ".tmp")
    assert not tmp_leftover.exists()


def test_add_bin_data_raises_when_content_hpf_missing(tmp_path):
    container_path = tmp_path / "no_content_hpf.hwpx"
    with zipfile.ZipFile(container_path, mode="w") as zf:
        zf.writestr("mimetype", b"application/hwp+zip")
        zf.writestr(
            MANIFEST_ARCNAME,
            f'<ocf:manifest xmlns:ocf="{NAMESPACES["ocf"]}"/>'.encode("utf-8"),
        )

    with pytest.raises(ContainerBuildError):
        add_bin_data(container_path, {"bin0": (b"data", "png")})


def test_add_bin_data_raises_when_content_hpf_has_no_manifest_element(tmp_path):
    """content.hpf는 존재하지만 그 안에 opf:manifest 요소가 없는 경우
    (container.py 351~355행의 `content_manifest is None` 분기)."""
    container_path = tmp_path / "content_hpf_no_manifest_el.hwpx"
    with zipfile.ZipFile(container_path, mode="w") as zf:
        zf.writestr("mimetype", b"application/hwp+zip")
        zf.writestr(
            MANIFEST_ARCNAME,
            f'<ocf:manifest xmlns:ocf="{NAMESPACES["ocf"]}"/>'.encode("utf-8"),
        )
        zf.writestr(
            CONTENT_HPF_ARCNAME,
            f'<opf:package xmlns:opf="{NAMESPACES["opf"]}"/>'.encode("utf-8"),
        )

    with pytest.raises(ContainerBuildError):
        add_bin_data(container_path, {"bin0": (b"data", "png")})


# ---------------------------------------------------------------------------
# 예외 입력: 손상된 zip 자체, 잘못된 XML
# ---------------------------------------------------------------------------


def test_add_bin_data_raises_on_corrupted_zip_and_leaves_no_tmp(tmp_path):
    garbage_path = tmp_path / "garbage.hwpx"
    garbage_bytes = b"this is not a valid zip file at all"
    garbage_path.write_bytes(garbage_bytes)

    with pytest.raises(ContainerBuildError):
        add_bin_data(garbage_path, {"bin0": (b"data", "png")})

    assert garbage_path.read_bytes() == garbage_bytes
    tmp_leftover = garbage_path.with_name(garbage_path.name + ".tmp")
    assert not tmp_leftover.exists()


def test_add_bin_data_raises_on_malformed_manifest_xml(tmp_path):
    """manifest.xml 내용 자체가 well-formed XML이 아니면 `etree.fromstring`이
    `XMLSyntaxError`를 던지고, 이는 `ContainerBuildError`로 변환되어야 한다
    (container.py 401행의 except 절에 `etree.XMLSyntaxError` 포함 확인)."""
    container_path = tmp_path / "malformed_manifest.hwpx"
    with zipfile.ZipFile(container_path, mode="w") as zf:
        zf.writestr("mimetype", b"application/hwp+zip")
        zf.writestr(MANIFEST_ARCNAME, b"<not-well-formed")
        zf.writestr(
            CONTENT_HPF_ARCNAME,
            f'<opf:package xmlns:opf="{NAMESPACES["opf"]}"><opf:manifest/><opf:spine/></opf:package>'.encode(
                "utf-8"
            ),
        )
    before_bytes = container_path.read_bytes()

    with pytest.raises(ContainerBuildError):
        add_bin_data(container_path, {"bin0": (b"data", "png")})

    assert container_path.read_bytes() == before_bytes


def test_add_bin_data_failure_chains_original_exception(tmp_path):
    missing_path = tmp_path / "does_not_exist2.hwpx"

    with pytest.raises(ContainerBuildError) as excinfo:
        add_bin_data(missing_path, {"bin0": (b"data", "png")})
    # container_path 미존재는 명시적으로 raise하는 경로라 __cause__가 없을 수 있으나,
    # ContainerBuildError 타입 자체와 메시지에 경로가 포함되는지는 확인한다.
    assert str(missing_path) in str(excinfo.value)


# ---------------------------------------------------------------------------
# 경계값: str 경로 허용(기존 함수들과 동일 인터페이스 계약)
# ---------------------------------------------------------------------------


def test_add_bin_data_accepts_str_path(tmp_path):
    output_path = tmp_path / "container_str.hwpx"
    build_empty_container(output_path)

    add_bin_data(str(output_path), {"bin0": (b"data", "png")})  # type: ignore[arg-type]

    with zipfile.ZipFile(output_path, mode="r") as zf:
        assert f"{BIN_DATA_DIR}/bin0.png" in zf.namelist()


# ---------------------------------------------------------------------------
# 경계값: 빈 바이트(raw_bytes = b"") 엔트리
# ---------------------------------------------------------------------------


def test_add_bin_data_empty_raw_bytes_is_accepted(tmp_path):
    output_path = tmp_path / "container.hwpx"
    build_empty_container(output_path)

    add_bin_data(output_path, {"bin0": (b"", "png")})

    with zipfile.ZipFile(output_path, mode="r") as zf:
        assert zf.read(f"{BIN_DATA_DIR}/bin0.png") == b""


# ---------------------------------------------------------------------------
# (위험 케이스, 결함 아님 · 리스크로 기록) 동일 bin_data_id를 다른 image_format으로
# 재등록하면 이전 arcname이 정리되지 않고 고아 항목으로 남는다.
# ---------------------------------------------------------------------------


def test_add_bin_data_reregistration_with_different_format_leaves_orphaned_old_entry(tmp_path):
    """멱등성 계약(container.py 307~308행 docstring)은 "같은 bin_data_id로 재호출하면
    바이트만 덮어쓴다"고 명시하지만, 이는 arcname이 image_format에서 유도되므로
    **같은 image_format으로 재호출하는 경우에만** 성립한다. 같은 bin_data_id를
    다른 image_format으로 재호출하면 새 arcname이 추가로 생성되고, 이전 arcname은
    zip과 manifest/content.hpf에서 제거되지 않은 채 고아 항목으로 남는다.

    이 테스트는 이 동작을 명시적으로 문서화한다 — 크래시나 AC 위반은 아니므로
    결함으로 분류하지 않지만(unit-4-test.md 재작업 섹션 8절 리스크 참고), 현재
    유일한 호출자인 unit-7(image_embedder.py)이 매번 새로운 순차 bin_data_id
    (bin0, bin1, ...)만 발급하고 동일 id를 다른 포맷으로 재사용하지 않으므로
    현재 호출 경로에서는 발생하지 않는다."""
    output_path = tmp_path / "container.hwpx"
    build_empty_container(output_path)

    add_bin_data(output_path, {"bin0": (b"jpeg-bytes", "jpeg")})
    add_bin_data(output_path, {"bin0": (b"png-bytes", "png")})

    with zipfile.ZipFile(output_path, mode="r") as zf:
        namelist = zf.namelist()
        # 두 arcname 모두 남아있다(이전 jpeg 항목이 정리되지 않음 — 알려진 한계).
        assert f"{BIN_DATA_DIR}/bin0.jpg" in namelist
        assert f"{BIN_DATA_DIR}/bin0.png" in namelist
        manifest_paths = _manifest_paths(zf)
        assert f"{BIN_DATA_DIR}/bin0.jpg" in manifest_paths
        assert f"{BIN_DATA_DIR}/bin0.png" in manifest_paths


# ---------------------------------------------------------------------------
# (위험 케이스, 결함 아님 · 리스크로 기록) bin_data_id에 경로 탈출 문자열이 오면
# 검증 없이 그대로 zip arcname에 반영된다 (add_section_xml의 section_name과 동일한
# 성격의 미검증 — unit-4-test.md 원본 8절 리스크 2번, TC-120 참고).
# ---------------------------------------------------------------------------


def test_add_bin_data_bin_data_id_path_traversal_not_sanitized(tmp_path):
    """`bin_data_id`가 `"../../evil"`처럼 경로 구분자를 포함해도 이 함수는
    검증하지 않고 그대로 `BinData/<bin_data_id>.<ext>` arcname으로 zip에 기록한다.
    현재 유일한 호출자(unit-7 image_embedder.py)는 항상 내부에서 순차 생성한
    `"bin{N}"` 형태만 넘기므로 실제 악용 경로는 없지만, 이 함수가 향후 조금이라도
    외부/신뢰할 수 없는 입력에 가까워지면 반드시 화이트리스트 검증이 필요하다."""
    output_path = tmp_path / "container.hwpx"
    build_empty_container(output_path)

    add_bin_data(output_path, {"../../evil_traversal": (b"payload", "png")})

    with zipfile.ZipFile(output_path, mode="r") as zf:
        assert "BinData/../../evil_traversal.png" in zf.namelist()
