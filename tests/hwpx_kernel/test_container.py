"""container.py: HwpxPackage와 패키지 메타 파트 (T1)."""

from __future__ import annotations

import re
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from lxml import etree

from pdf_to_hwpx.common.exceptions import ContainerBuildError
from pdf_to_hwpx.hwpx_kernel import container
from pdf_to_hwpx.hwpx_kernel.container import (
    VERSION_OWN,
    VERSION_R1_OBSERVED,
    HwpxPackage,
    PackageMeta,
    format_preview_text,
)
from pdf_to_hwpx.hwpx_kernel.section import PageSetup, build_section_xml
from pdf_to_hwpx.hwpx_kernel.styles import StyleRegistry

from .helpers import (
    NS,
    all_xml_parts,
    check_reference_integrity,
    forbidden_hits,
    open_zip,
    parse,
)

PROLOG = b'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
EXPECTED_ORDER = [
    "mimetype",
    "version.xml",
    "Contents/header.xml",
    "Contents/section0.xml",
    "Preview/PrvText.txt",
    "settings.xml",
    "META-INF/container.xml",
    "Contents/content.hpf",
    "META-INF/manifest.xml",
]


def make_package(meta: PackageMeta, sections: int = 1) -> HwpxPackage:
    pkg = HwpxPackage(meta)
    pkg.set_header(StyleRegistry().serialize_header(sections))
    for _ in range(sections):
        pkg.add_section(build_section_xml([], PageSetup.a4()))
    return pkg


@pytest.fixture
def built(fixed_meta):
    return open_zip(make_package(fixed_meta).to_bytes())


def test_zip_layout(built):
    assert built.namelist() == EXPECTED_ORDER
    first = built.infolist()[0]
    assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
    assert built.read("mimetype") == b"application/hwp+zip"  # 개행 없음, 19바이트
    assert first.file_size == 19 and not first.extra
    stored = {i.filename for i in built.infolist() if i.compress_type == zipfile.ZIP_STORED}
    assert stored == {"mimetype", "version.xml"}
    assert all(i.date_time == (1980, 1, 1, 0, 0, 0) for i in built.infolist())
    assert built.testzip() is None


def test_all_xml_parts_well_formed_and_prolog(built):
    parts = all_xml_parts(built)
    assert set(parts) == {n for n in EXPECTED_ORDER if n.endswith((".xml", ".hpf"))}
    for name in parts:
        data = built.read(name)
        assert data.startswith(PROLOG + b"<"), name
        assert b"\n" not in data and not data.startswith(b"\xef\xbb\xbf"), name


def test_no_omitted_parts(built):
    names = built.namelist()
    assert not any(n.startswith(("BinData", "Contents/masterpage")) for n in names)
    assert "Preview/PrvImage.png" not in names


def test_version_xml_r1_observed_and_own(fixed_meta):
    r1 = parse(open_zip(make_package(PackageMeta(version=VERSION_R1_OBSERVED, created=fixed_meta.created)).to_bytes()), "version.xml")
    own = parse(open_zip(make_package(fixed_meta).to_bytes()), "version.xml")
    assert r1.tag == "{http://www.hancom.co.kr/hwpml/2011/version}HCFVersion"
    assert len(r1) == 0
    assert list(r1.attrib) == [
        "tagetApplication", "major", "minor", "micro", "buildNumber", "os", "xmlVersion", "application", "appVersion"
    ]
    assert r1.get("tagetApplication") == "WORDPROCESSOR" and r1.get("xmlVersion") == "1.4"
    assert r1.get("application") == "Hancom Office Hangul"
    assert own.get("application") == "pdf-to-hwpx" == VERSION_OWN.application
    # 두 변형은 application/appVersion만 다르다 (프로브 P1a/P1b의 전제)
    diff = {k for k in r1.attrib if r1.get(k) != own.get(k)}
    assert diff == {"application", "appVersion"}


def test_header_xml_version_matches_version_xml(built):
    assert parse(built, "Contents/header.xml").get("version") == parse(built, "version.xml").get("xmlVersion")


def test_container_xml(built):
    root = parse(built, "META-INF/container.xml")
    ocf = "urn:oasis:names:tc:opendocument:xmlns:container"
    assert root.tag == f"{{{ocf}}}container" and root.attrib == {}  # version 속성 없음
    assert root.nsmap == {"ocf": ocf, "hpf": "http://www.hancom.co.kr/schema/2011/hpf"}
    files = [(e.get("full-path"), e.get("media-type")) for e in root.iter(f"{{{ocf}}}rootfile")]
    assert files == [
        ("Contents/content.hpf", "application/hwpml-package+xml"),
        ("Preview/PrvText.txt", "text/plain"),
    ]


def test_manifest_xml_is_empty_odf_manifest(built):
    root = parse(built, "META-INF/manifest.xml")
    assert root.tag == "{urn:oasis:names:tc:opendocument:xmlns:manifest:1.0}manifest"
    assert len(root) == 0 and root.attrib == {}


def test_settings_xml(built):
    root = parse(built, "settings.xml")
    assert root.tag == "{http://www.hancom.co.kr/hwpml/2011/app}HWPApplicationSetting"
    items = root.findall("{urn:oasis:names:tc:opendocument:xmlns:config:1.0}config-item-set/*")
    assert len(items) == 7
    assert {i.get("type") for i in items} == {"boolean", "short"}


def test_content_hpf_metadata_manifest_spine(fixed_meta):
    zf = open_zip(make_package(fixed_meta, sections=2).to_bytes())
    root = parse(zf, "Contents/content.hpf")
    assert root.tag == f"{{{NS['opf']}}}package"
    assert dict(root.attrib) == {"version": "", "unique-identifier": "", "id": ""}
    assert len(root.nsmap) == 15
    meta = root.find("opf:metadata", NS)
    assert [etree.QName(c).localname for c in meta] == ["title", "language"] + ["meta"] * 8
    assert not meta.find("opf:title", NS).text  # 입력 제목 미기록 (DEC-060)
    assert meta.find("opf:language", NS).text == "ko"
    metas = {m.get("name"): m for m in meta.findall("opf:meta", NS)}
    assert list(metas) == [
        "creator", "subject", "description", "lastsaveby", "CreatedDate", "ModifiedDate", "date", "keyword"
    ]
    assert all(m.get("content") == "text" for m in metas.values())
    assert metas["CreatedDate"].text == metas["ModifiedDate"].text == "2026-09-29T15:04:05Z"
    assert metas["creator"].text == metas["lastsaveby"].text == "pdf-to-hwpx"
    assert re.fullmatch(r"\d{4}년 \d{2}월 \d{2}일 [월화수목금토일]요일 (오전|오후) \d{1,2}:\d{2}:\d{2}", metas["date"].text)
    assert metas["date"].text == "2026년 09월 29일 화요일 오후 3:04:05"
    assert metas["subject"].text is None and metas["keyword"].text is None
    items = [(i.get("id"), i.get("href"), i.get("media-type")) for i in root.findall("opf:manifest/opf:item", NS)]
    assert items == [
        ("header", "Contents/header.xml", "application/xml"),
        ("section0", "Contents/section0.xml", "application/xml"),
        ("section1", "Contents/section1.xml", "application/xml"),
        ("settings", "settings.xml", "application/xml"),
    ]
    spine = [(i.get("idref"), i.get("linear")) for i in root.findall("opf:spine/opf:itemref", NS)]
    assert spine == [("header", "yes"), ("section0", "yes"), ("section1", "yes")]
    hrefs = {i[1] for i in items}
    assert hrefs <= set(zf.namelist())  # manifest <-> zip 일치


def test_content_hpf_never_records_input_title_or_paths(built):
    data = built.read("Contents/content.hpf").decode("utf-8")
    assert "<opf:title></opf:title>" in data


def test_timestamps_are_utc_normalized():
    kst = timezone(timedelta(hours=9))
    meta = PackageMeta(created=datetime(2026, 9, 30, 0, 4, 5, tzinfo=kst))
    root = parse(open_zip(make_package(meta).to_bytes()), "Contents/content.hpf")
    created = root.xpath("//opf:meta[@name='CreatedDate']", namespaces=NS)[0]
    assert created.text == "2026-09-29T15:04:05Z"


def test_default_created_is_now_utc_without_microseconds():
    stamp = PackageMeta().resolved_created()
    assert stamp.microsecond == 0 and stamp.tzinfo is None


def test_output_is_deterministic_for_fixed_meta(fixed_meta):
    assert make_package(fixed_meta).to_bytes() == make_package(fixed_meta).to_bytes()


def test_preview_text_entry(fixed_meta):
    pkg = make_package(fixed_meta)
    pkg.set_preview_text(format_preview_text(["첫 줄", "둘째 줄", "", "셋째"]))
    zf = open_zip(pkg.to_bytes())
    text = zf.read("Preview/PrvText.txt").decode("utf-8")
    assert text == "<첫 줄>\r\n\r\n둘째 줄\r\n셋째"
    assert not zf.read("Preview/PrvText.txt").startswith(b"\xef\xbb\xbf")


def test_format_preview_text_limits_and_empty():
    assert format_preview_text([]) == ""
    assert format_preview_text(["", "   "]) == ""
    long = format_preview_text(["가" * 5000, "나" * 5000])
    assert len(long) == container.PREVIEW_MAX_CHARS
    assert long.startswith("<가") and long.count(">") == 1
    assert "\t" not in format_preview_text(["a\tb"]) and "\x00" not in format_preview_text(["a\x00b"])


def test_package_requires_header_and_sections(fixed_meta):
    with pytest.raises(ContainerBuildError):
        HwpxPackage(fixed_meta).to_bytes()
    pkg = HwpxPackage(fixed_meta)
    pkg.set_header(StyleRegistry().serialize_header(1))
    with pytest.raises(ContainerBuildError):
        pkg.to_bytes()


def test_sec_cnt_mismatch_and_bad_header_rejected(fixed_meta):
    pkg = HwpxPackage(fixed_meta)
    pkg.set_header(StyleRegistry().serialize_header(2))
    pkg.add_section(build_section_xml([], PageSetup.a4()))
    with pytest.raises(ContainerBuildError, match="secCnt"):
        pkg.to_bytes()
    pkg.set_header(b"<not xml")
    with pytest.raises(ContainerBuildError, match="well-formed"):
        pkg.to_bytes()
    pkg.set_header(b'<a xmlns="x"/>')
    with pytest.raises(ContainerBuildError):
        pkg.to_bytes()


def test_add_section_returns_index_and_count(fixed_meta):
    pkg = HwpxPackage(fixed_meta)
    assert pkg.add_section(b"x") == 0 and pkg.add_section(b"y") == 1
    assert pkg.section_count == 2


def test_write_atomic_creates_parents_and_no_tmp_left(fixed_meta, out_dir):
    target = out_dir / "nested" / "a.hwpx"
    make_package(fixed_meta).write(target)
    assert zipfile.is_zipfile(target)
    assert [p.name for p in target.parent.iterdir()] == ["a.hwpx"]


def test_write_failure_raises_container_build_error(fixed_meta, out_dir):
    blocker = out_dir / "file"
    blocker.write_text("x")
    with pytest.raises(ContainerBuildError):
        make_package(fixed_meta).write(blocker / "sub" / "a.hwpx")


def test_write_overwrites_existing(fixed_meta, out_dir):
    target = out_dir / "a.hwpx"
    target.write_bytes(b"old")
    make_package(fixed_meta).write(target)
    assert zipfile.is_zipfile(target)


def test_package_is_self_consistent_and_has_no_b0_vocabulary(built):
    assert check_reference_integrity(built) == []
    assert forbidden_hits(built) == []


def test_old_container_api_is_gone():
    assert not hasattr(container, "build_empty_container")
    assert not hasattr(container, "add_section_xml")
    assert not hasattr(container, "add_bin_data")
