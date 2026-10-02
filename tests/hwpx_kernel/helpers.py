"""hwpx_kernel 테스트 보조: zip 읽기와 가벼운 ID 참조 무결성 검사.

정식 구조 검증(V1~V13)은 unit-27 validator의 몫이다. 여기서는 이 unit이 만든 문서가
스스로 일관된지(끊긴 참조, 개수 불일치) 확인하는 최소 검사만 한다. 이 파일은
참조 HWPX를 읽지 않는다.
"""

from __future__ import annotations

import io
import zipfile

from lxml import etree

NS = {
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "opf": "http://www.idpf.org/2007/opf/",
}

# 이전 자체 스키마(B0)가 쓰던 표준 밖 이름들 -- 어디에도 나타나면 안 된다.
FORBIDDEN_NAMES = {
    "bboxPt", "fontName", "fontSizeHwpunit", "charShapeIDRef", "paraShapeIDRef",
    "tagID", "hasMergedCells", "binDataIDRef", "xHwpunit", "yHwpunit",
    "widthHwpunit", "heightHwpunit",
}


def open_zip(data: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(data))


def parse(zf: zipfile.ZipFile, name: str) -> etree._Element:
    return etree.fromstring(zf.read(name))


def all_xml_parts(zf: zipfile.ZipFile) -> dict[str, etree._Element]:
    return {
        n: parse(zf, n) for n in zf.namelist() if n.endswith((".xml", ".hpf"))
    }


def ids(root: etree._Element, xpath: str) -> set[int]:
    return {int(v) for v in root.xpath(xpath, namespaces=NS)}


def check_reference_integrity(zf: zipfile.ZipFile) -> list[str]:
    """분석서 §5-4 참조 그래프 중 이 unit이 만드는 부분. 위반 설명 목록을 반환한다."""
    problems: list[str] = []
    header = parse(zf, "Contents/header.xml")
    char_ids = ids(header, "//hh:charPr/@id")
    para_ids = ids(header, "//hh:paraPr/@id")
    border_ids = ids(header, "//hh:borderFill/@id")
    style_ids = ids(header, "//hh:style/@id")
    tab_ids = ids(header, "//hh:tabPr/@id")
    numbering_ids = ids(header, "//hh:numbering/@id")

    for n in zf.namelist():
        if not n.startswith("Contents/section"):
            continue
        sec = parse(zf, n)
        for label, xpath, valid in (
            ("charPrIDRef", "//hp:run/@charPrIDRef", char_ids),
            ("paraPrIDRef", "//hp:p/@paraPrIDRef", para_ids),
            ("styleIDRef", "//hp:p/@styleIDRef", style_ids),
            ("borderFillIDRef", "//hp:tbl/@borderFillIDRef | //hp:tc/@borderFillIDRef", border_ids),
            ("pageBorderFill", "//hp:pageBorderFill/@borderFillIDRef", border_ids),
            ("outlineShapeIDRef", "//hp:secPr/@outlineShapeIDRef", numbering_ids),
        ):
            missing = ids(sec, xpath) - valid
            if missing:
                problems.append(f"{n}: {label} 참조 끊김 {sorted(missing)}")
        tbl_ids = [int(v) for v in sec.xpath("//hp:tbl/@id", namespaces=NS)]
        if len(tbl_ids) != len(set(tbl_ids)):
            problems.append(f"{n}: tbl id 중복")
        if len(sec.xpath("//hp:secPr", namespaces=NS)) != 1:
            problems.append(f"{n}: secPr가 정확히 1개가 아님")
        first_run = sec.xpath("/hs:sec/hp:p[1]/hp:run[1]/hp:secPr", namespaces=NS)
        if not first_run:
            problems.append(f"{n}: secPr가 첫 문단 첫 run 안에 없음")

    if ids(header, "//hh:charPr/@borderFillIDRef") - border_ids:
        problems.append("header charPr borderFillIDRef 끊김")
    if ids(header, "//hh:paraPr/@tabPrIDRef") - tab_ids:
        problems.append("header paraPr tabPrIDRef 끊김")
    if ids(header, "//hh:paraPr/hh:border/@borderFillIDRef") - border_ids:
        problems.append("header paraPr border 참조 끊김")
    if ids(header, "//hh:style/@paraPrIDRef") - para_ids:
        problems.append("header style paraPrIDRef 끊김")
    if ids(header, "//hh:style/@charPrIDRef") - char_ids:
        problems.append("header style charPrIDRef 끊김")

    font_counts = {
        ff.get("lang"): int(ff.get("fontCnt")) for ff in header.xpath("//hh:fontface", namespaces=NS)
    }
    for ref in header.xpath("//hh:charPr/hh:fontRef", namespaces=NS):
        for lang_attr, value in ref.attrib.items():
            if int(value) >= min(font_counts.values()):
                problems.append(f"fontRef {lang_attr}={value} 범위 밖")

    for container in header.xpath("//hh:refList/*", namespaces=NS):
        if int(container.get("itemCnt")) != len(container):
            problems.append(f"itemCnt 불일치: {etree.QName(container).localname}")
    for ff in header.xpath("//hh:fontface", namespaces=NS):
        if int(ff.get("fontCnt")) != len(ff):
            problems.append("fontCnt 불일치")
    sec_files = [n for n in zf.namelist() if n.startswith("Contents/section")]
    if int(header.get("secCnt")) != len(sec_files):
        problems.append("secCnt 불일치")
    return problems


def forbidden_hits(zf: zipfile.ZipFile) -> list[str]:
    hits: list[str] = []
    for name, root in all_xml_parts(zf).items():
        for el in root.iter():
            if not isinstance(el.tag, str):
                continue
            local = etree.QName(el).localname
            if local in FORBIDDEN_NAMES:
                hits.append(f"{name}: element {local}")
            hits += [f"{name}: attr {k}" for k in el.attrib if etree.QName(k).localname in FORBIDDEN_NAMES]
    return hits
