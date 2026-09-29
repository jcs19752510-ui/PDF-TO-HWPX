"""OWPML 네임스페이스·프롤로그·단위·관찰된 enum 어휘 (unit-4R, REQ-008).

근거는 전부 `docs/harness/analysis/hwpx-reference-structure.md`(분석서)의 관찰 사실이다.
스펙 기억으로 채운 값은 없다. 분석서가 【미확인】으로 표시한 것(이탤릭, 가로 용지,
그림 등)은 이 모듈에 어휘를 두지 않는다.
"""

from __future__ import annotations

from lxml import etree

# 분석서 §4: 본문·header·hpf·masterpage 루트에 동일하게 선언되는 15개 (선언 순서 = 관찰 순서).
NAMESPACES: dict[str, str] = {
    "ha": "http://www.hancom.co.kr/hwpml/2011/app",
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hp10": "http://www.hancom.co.kr/hwpml/2016/paragraph",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hhs": "http://www.hancom.co.kr/hwpml/2011/history",
    "hm": "http://www.hancom.co.kr/hwpml/2011/master-page",
    "hpf": "http://www.hancom.co.kr/schema/2011/hpf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "opf": "http://www.idpf.org/2007/opf/",
    "ooxmlchart": "http://www.hancom.co.kr/hwpml/2016/ooxmlchart",
    "hwpunitchar": "http://www.hancom.co.kr/hwpml/2016/HwpUnitChar",
    "epub": "http://www.idpf.org/2007/ops",
    "config": "urn:oasis:names:tc:opendocument:xmlns:config:1.0",
}

# 분석서 §4/§3: 네임스페이스 선언 수가 다른 패키지 메타 파트 전용.
NS_VERSION = "http://www.hancom.co.kr/hwpml/2011/version"  # version.xml (prefix hv)
NS_OCF = "urn:oasis:names:tc:opendocument:xmlns:container"  # META-INF/container.xml (prefix ocf)
NS_ODF_MANIFEST = "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"  # manifest.xml (prefix odf)

HWPUNIT_PER_PT = 100  # 분석서 §9: 1/7200 inch 실측 검증
HWPX_XML_VERSION = "1.4"  # version.xml@xmlVersion == hh:head@version (분석서 §3-1)

# 분석서 §2: 모든 XML 파트가 이 바이트열로 시작하고 루트가 개행 없이 바로 이어진다.
XML_PROLOG = b'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'

MIMETYPE_CONTENT = b"application/hwp+zip"

# 분석서 §6-3: 관찰된 값 하나. 의미는 【미확인】(고유 번호가 아님)이라 R1 다수값으로 통일한다.
PARAGRAPH_ID = "2147483648"

# 분석서 §5-3 numbering paraHead / §5-3 charPr 등에서 관찰된 "지정 안 함" 센티널 (추론).
NO_CHAR_PR_REF = "4294967295"

LANGS: tuple[str, ...] = ("HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER")
LANG_ATTR_NAMES: tuple[str, ...] = (
    "hangul", "latin", "hanja", "japanese", "other", "symbol", "user",
)


def qn(prefix: str, tag: str) -> str:
    """``qn("hp", "p")`` -> ``{ns-uri}p`` (lxml Clark notation)."""
    return f"{{{NAMESPACES[prefix]}}}{tag}"


def pt_to_hwpunit(value_pt: float) -> int:
    return round(value_pt * HWPUNIT_PER_PT)


def full_nsmap() -> dict[str, str]:
    """15개 선언을 담은 새 nsmap (호출자가 변형해도 전역이 오염되지 않도록 사본)."""
    return dict(NAMESPACES)


def new_root(prefix: str, tag: str) -> etree._Element:
    """15개 네임스페이스를 모두 선언한 루트 요소 (분석서 §4, 실험 E-N 전까지 초집합)."""
    return etree.Element(qn(prefix, tag), nsmap=full_nsmap())


def serialize_xml(root: etree._Element) -> bytes:
    """R1 프롤로그 바이트 형태 + 루트 (개행 없음, BOM 없음)."""
    return XML_PROLOG + etree.tostring(root, encoding="UTF-8", xml_declaration=False)
