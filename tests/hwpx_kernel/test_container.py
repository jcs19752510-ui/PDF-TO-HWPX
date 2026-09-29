"""unit-4 AC-1 — `pdf_to_hwpx/hwpx_kernel/container.py` 검증.

근거: docs/harness/units/unit-4-note.md §7 AC-1(1~9번),
docs/harness/decisions.md DEC-017.

**범위의 근본적 한계(반드시 읽을 것)**: 이 테스트 파일은 "우리가 만든 zip+XML이
구조적으로 well-formed하고, 우리 스스로 정의한 규칙(엔트리 순서/이름/속성)과
내부적으로 일관되는가"만 증명한다. 실제 한글(한컴오피스)이 이 파일을 경고 없이
여는지는 개발 환경에 한글이 없어 전혀 검증하지 못했다(DEC-017). 이 사실을
"PASS = 실제 호환성 검증됨"으로 잘못 해석해서는 안 된다 — 자세한 내용은
docs/harness/units/unit-4-test.md §8(리스크)을 참고할 것.
"""

from __future__ import annotations

import zipfile

import pytest
from lxml import etree

from pdf_to_hwpx.common.exceptions import ContainerBuildError
from pdf_to_hwpx.hwpx_kernel.container import (
    DEFAULT_SECTION_NAME,
    MIMETYPE_CONTENT,
    SECTION_DIR,
    add_section_xml,
    build_empty_container,
)

EXPECTED_ENTRY_ORDER = [
    "mimetype",
    "version.xml",
    "settings.xml",
    "META-INF/container.xml",
    "META-INF/manifest.xml",
    f"{SECTION_DIR}/header.xml",
    f"{SECTION_DIR}/{DEFAULT_SECTION_NAME}",
    f"{SECTION_DIR}/content.hpf",
]


# ---------------------------------------------------------------------------
# AC-1-1, AC-1-2: 정상 경로 — 파일 존재, zipfile로 예외 없이 열림, 엔트리 순서/개수
# ---------------------------------------------------------------------------


def test_build_empty_container_creates_readable_zip(tmp_path):
    output_path = tmp_path / "empty.hwpx"
    build_empty_container(output_path)

    assert output_path.exists()
    with zipfile.ZipFile(output_path, mode="r") as zf:
        # 예외 없이 열리고, 손상 검사(testzip)도 통과해야 한다.
        assert zf.testzip() is None


def test_build_empty_container_namelist_matches_expected_order(tmp_path):
    output_path = tmp_path / "empty.hwpx"
    build_empty_container(output_path)

    with zipfile.ZipFile(output_path, mode="r") as zf:
        assert zf.namelist() == EXPECTED_ENTRY_ORDER


# ---------------------------------------------------------------------------
# AC-1-3: mimetype이 첫 엔트리, 비압축, 내용 일치
# ---------------------------------------------------------------------------


def test_mimetype_is_first_entry_uncompressed_with_expected_content(tmp_path):
    output_path = tmp_path / "empty.hwpx"
    build_empty_container(output_path)

    with zipfile.ZipFile(output_path, mode="r") as zf:
        first_info = zf.infolist()[0]
        assert first_info.filename == "mimetype"
        assert first_info.compress_type == zipfile.ZIP_STORED
        assert zf.read("mimetype") == MIMETYPE_CONTENT == b"application/hwp+zip"


# ---------------------------------------------------------------------------
# AC-1-4: mimetype을 제외한 모든 엔트리가 well-formed XML
# ---------------------------------------------------------------------------


def test_all_non_mimetype_entries_are_well_formed_xml(tmp_path):
    output_path = tmp_path / "empty.hwpx"
    build_empty_container(output_path)

    with zipfile.ZipFile(output_path, mode="r") as zf:
        for name in zf.namelist():
            if name == "mimetype":
                continue
            data = zf.read(name)
            try:
                root = etree.fromstring(data)
            except etree.XMLSyntaxError as exc:  # pragma: no cover - 실패 시에만 도달
                pytest.fail(f"{name}이 well-formed XML이 아님: {exc}")
            assert root is not None


@pytest.mark.parametrize("name", [n for n in EXPECTED_ENTRY_ORDER if n != "mimetype"])
def test_each_xml_part_individually_well_formed(tmp_path, name):
    """개별 파트 단위로도 명시적으로 파싱해, 전체 루프 테스트가 놓칠 수 있는
    부분(예: 특정 파트만 조용히 스킵되는 버그)을 배제한다."""
    output_path = tmp_path / "empty.hwpx"
    build_empty_container(output_path)

    with zipfile.ZipFile(output_path, mode="r") as zf:
        data = zf.read(name)
    root = etree.fromstring(data)
    assert etree.QName(root).localname  # 루트 태그의 로컬 이름이 비어있지 않음


# ---------------------------------------------------------------------------
# AC-1-5: 존재하지 않는 상위 디렉터리는 자동 생성되어 성공
# ---------------------------------------------------------------------------


def test_build_empty_container_creates_missing_parent_directories(tmp_path):
    output_path = tmp_path / "nested" / "does" / "not" / "exist" / "out.hwpx"
    assert not output_path.parent.exists()

    build_empty_container(output_path)

    assert output_path.exists()
    with zipfile.ZipFile(output_path, mode="r") as zf:
        assert zf.namelist() == EXPECTED_ENTRY_ORDER


# ---------------------------------------------------------------------------
# AC-1-6: 쓰기 불가능한 경로 -> ContainerBuildError
# ---------------------------------------------------------------------------


def test_build_empty_container_raises_container_build_error_when_output_is_directory(tmp_path):
    """출력 경로 자체가 이미 디렉터리인 경우, zipfile이 IsADirectoryError/PermissionError류의
    OSError를 던지고 이를 ContainerBuildError로 변환하는지 확인한다(디스크 공간 부족을
    직접 시뮬레이션하기 어려워, "쓰기 자체가 원천적으로 불가능한 경로"로 동등한 실패
    조건을 재현했다)."""
    blocked_path = tmp_path / "blocked.hwpx"
    blocked_path.mkdir()  # 파일이 있어야 할 자리에 디렉터리를 만들어 충돌시킨다.

    with pytest.raises(ContainerBuildError):
        build_empty_container(blocked_path)


def test_build_empty_container_error_chains_original_oserror(tmp_path):
    """`raise ... from exc` 계약(unit-4-note.md 2-1절) 확인 — 원인 예외가 보존된다."""
    blocked_path = tmp_path / "blocked2.hwpx"
    blocked_path.mkdir()

    with pytest.raises(ContainerBuildError) as excinfo:
        build_empty_container(blocked_path)
    assert excinfo.value.__cause__ is not None
    assert isinstance(excinfo.value.__cause__, OSError)


# ---------------------------------------------------------------------------
# AC-1-7: add_section_xml 라운드트립 — 대상 섹션만 교체, 나머지 7개 그대로
# ---------------------------------------------------------------------------


def test_add_section_xml_replaces_only_target_entry(tmp_path):
    output_path = tmp_path / "container.hwpx"
    build_empty_container(output_path)

    with zipfile.ZipFile(output_path, mode="r") as zf:
        before_names = zf.namelist()
        before_mimetype_info = zf.infolist()[0]
        before_other_contents = {
            name: zf.read(name) for name in before_names if name != f"{SECTION_DIR}/{DEFAULT_SECTION_NAME}"
        }

    new_section = (
        '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
        'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
        '<hp:p paraShapeIDRef="0"><hp:run charShapeIDRef="0">'
        "<hp:t>검증용 텍스트</hp:t>"
        "</hp:run></hp:p></hs:sec>"
    ).encode("utf-8")

    add_section_xml(output_path, new_section)

    with zipfile.ZipFile(output_path, mode="r") as zf:
        after_names = zf.namelist()
        after_mimetype_info = zf.infolist()[0]
        after_section_content = zf.read(f"{SECTION_DIR}/{DEFAULT_SECTION_NAME}")
        after_other_contents = {
            name: zf.read(name) for name in after_names if name != f"{SECTION_DIR}/{DEFAULT_SECTION_NAME}"
        }

    # 엔트리 목록(순서 포함)과 mimetype 첫 엔트리/비압축 상태가 그대로 유지된다.
    assert after_names == before_names
    assert after_mimetype_info.filename == "mimetype"
    assert after_mimetype_info.compress_type == zipfile.ZIP_STORED == before_mimetype_info.compress_type

    # 교체 대상 외 7개 엔트리는 바이트 단위로 완전히 동일하다.
    assert after_other_contents == before_other_contents

    # 교체 대상은 새 내용으로 바뀌었고 well-formed XML이다.
    assert after_section_content == new_section
    parsed = etree.fromstring(after_section_content)
    assert etree.QName(parsed).localname == "sec"


def test_add_section_xml_inserts_new_section_when_name_not_present(tmp_path):
    """AC-7의 "없으면 추가" 분기(container.py 42행 docstring) — 기존에 없는
    section 이름을 주면 새 엔트리로 추가된다."""
    output_path = tmp_path / "container.hwpx"
    build_empty_container(output_path)

    with zipfile.ZipFile(output_path, mode="r") as zf:
        before_count = len(zf.namelist())

    extra_xml = b"<hs:sec xmlns:hs=\"http://www.hancom.co.kr/hwpml/2011/section\"/>"
    add_section_xml(output_path, extra_xml, section_name="section1.xml")

    with zipfile.ZipFile(output_path, mode="r") as zf:
        names = zf.namelist()
        assert len(names) == before_count + 1
        assert f"{SECTION_DIR}/section1.xml" in names
        assert zf.read(f"{SECTION_DIR}/section1.xml") == extra_xml
        # 기존 기본 섹션은 그대로 남아있다.
        assert f"{SECTION_DIR}/{DEFAULT_SECTION_NAME}" in names


# ---------------------------------------------------------------------------
# AC-1-8: 존재하지 않는 container_path -> ContainerBuildError
# ---------------------------------------------------------------------------


def test_add_section_xml_raises_when_container_missing(tmp_path):
    missing_path = tmp_path / "does_not_exist.hwpx"
    assert not missing_path.exists()

    with pytest.raises(ContainerBuildError):
        add_section_xml(missing_path, b"<hs:sec/>")


# ---------------------------------------------------------------------------
# AC-1-9: add_section_xml 실패 시 원본 훼손 없음 + .tmp 잔여물 없음
# ---------------------------------------------------------------------------


def test_add_section_xml_failure_does_not_corrupt_original_or_leave_tmp(tmp_path):
    garbage_path = tmp_path / "garbage.hwpx"
    garbage_bytes = b"this is not a valid zip file at all"
    garbage_path.write_bytes(garbage_bytes)

    with pytest.raises(ContainerBuildError):
        add_section_xml(garbage_path, b"<hs:sec/>")

    # 원본 파일은 훼손되지 않고 그대로 남아있다.
    assert garbage_path.read_bytes() == garbage_bytes

    # 같은 디렉터리에 .tmp 임시 파일이 남지 않는다.
    tmp_leftover = garbage_path.with_name(garbage_path.name + ".tmp")
    assert not tmp_leftover.exists()
    leftover_tmp_files = list(tmp_path.glob("*.tmp"))
    assert leftover_tmp_files == []


def test_add_section_xml_failure_chains_original_exception(tmp_path):
    garbage_path = tmp_path / "garbage2.hwpx"
    garbage_path.write_bytes(b"not a zip")

    with pytest.raises(ContainerBuildError) as excinfo:
        add_section_xml(garbage_path, b"<hs:sec/>")
    assert excinfo.value.__cause__ is not None


# ---------------------------------------------------------------------------
# 경계값/회귀: 동일 경로에 재생성해도 골격이 매번 동일하게 재현된다(재현성).
# ---------------------------------------------------------------------------


def test_build_empty_container_accepts_str_path_not_only_path_object(tmp_path):
    """인터페이스 계약: `output_path`가 `pathlib.Path`뿐 아니라 `str`로 와도
    (unit-5/6/7/8 호출부가 어느 타입을 넘길지 문서화되어 있지 않으므로) 내부에서
    `Path(output_path)`로 변환해 동작해야 한다."""
    output_path_str = str(tmp_path / "str_path.hwpx")
    build_empty_container(output_path_str)  # type: ignore[arg-type]

    with zipfile.ZipFile(output_path_str, mode="r") as zf:
        assert zf.namelist() == EXPECTED_ENTRY_ORDER


def test_add_section_xml_accepts_str_path(tmp_path):
    output_path = tmp_path / "container_str.hwpx"
    build_empty_container(output_path)

    add_section_xml(str(output_path), b"<hs:sec/>")  # type: ignore[arg-type]

    with zipfile.ZipFile(output_path, mode="r") as zf:
        assert zf.read(f"{SECTION_DIR}/{DEFAULT_SECTION_NAME}") == b"<hs:sec/>"


def test_build_empty_container_is_reproducible_when_rebuilt(tmp_path):
    output_path = tmp_path / "container.hwpx"
    build_empty_container(output_path)
    with output_path.open("rb") as f:
        first_bytes = f.read()

    build_empty_container(output_path)  # 같은 경로에 덮어쓰기
    with output_path.open("rb") as f:
        second_bytes = f.read()

    # 타임스탬프가 고정값(1980-01-01)이므로 바이트 단위로 완전히 동일해야 한다.
    assert first_bytes == second_bytes
