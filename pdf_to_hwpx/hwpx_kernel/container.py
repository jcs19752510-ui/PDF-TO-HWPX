"""HWPX 패키지(zip + 패키지 메타 파트) 작성 (unit-4R, 03 §3-3-6, 분석서 §2/§3).

발행은 초집합이다: 분석서에서 R1에 항상 존재하던 파트는 전부 쓴다. 관찰 근거가 있는
생략만 한다(``masterpage0.xml``: 구역 2 형태, ``Preview/PrvImage.png``: container에
미등재이고 렌더링 기능이 필요). 생략 가능성은 사용자 실험(E-Z/E-P/E-Ablation)으로만
넓힌다. BinData(그림)는 04_그림.hwpx 관찰 전이라 지원하지 않는다(unit-4P).
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from lxml import etree

from pdf_to_hwpx import __version__
from pdf_to_hwpx.common.exceptions import ContainerBuildError
from pdf_to_hwpx.hwpx_kernel.constants import (
    HWPX_XML_VERSION,
    MIMETYPE_CONTENT,
    NAMESPACES,
    NS_OCF,
    NS_ODF_MANIFEST,
    NS_VERSION,
    new_root,
    qn,
    serialize_xml,
)
from pdf_to_hwpx.hwpx_kernel.schema import sanitize_text

GENERATOR_NAME = "pdf-to-hwpx"

# zip 타임스탬프는 R1과 같은 1980-01-01 고정 (재현성, 생성 시각 비기록 -- DEC-060).
_FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)
# 분석서 §2 【미확인】: create_system/external_attr가 수용에 영향을 주는지. OS와 무관하게
# 결정적이도록 MS-DOS(0) + archive 비트로 고정한다.
_ZIP_CREATE_SYSTEM = 0
_ZIP_EXTERNAL_ATTR = 0x20

PREVIEW_MAX_CHARS = 1000  # 분석서 §3-6: 약 1,000자

_WEEKDAYS_KO = "월화수목금토일"


@dataclass(frozen=True)
class VersionInfo:
    """``version.xml``의 ``application``/``appVersion`` (실험 E-V, 프로브 P1a/P1b)."""

    application: str
    app_version: str


VERSION_R1_OBSERVED = VersionInfo(
    "Hancom Office Hangul", "9, 6, 1, 10097 WIN32LEWindows_Unknown_Version"
)
VERSION_OWN = VersionInfo(GENERATOR_NAME, __version__)


@dataclass(frozen=True)
class PackageMeta:
    version: VersionInfo = VERSION_OWN
    creator: str = GENERATOR_NAME
    last_saved_by: str = GENERATOR_NAME
    created: datetime | None = None  # UTC. None이면 변환 시각.

    def resolved_created(self) -> datetime:
        stamp = self.created or datetime.now(UTC)
        if stamp.tzinfo is not None:
            stamp = stamp.astimezone(UTC)
        return stamp.replace(microsecond=0, tzinfo=None)


def format_preview_text(paragraph_texts: Iterable[str]) -> str:
    """PrvText.txt 내용: 첫 줄은 ``<...>``로 감싸고, CRLF 줄 구분, 약 1,000자 (분석서 §3-6)."""
    lines = [sanitize_text(t).strip() for t in paragraph_texts]
    lines = [t for t in lines if t]
    if not lines:
        return ""
    first = lines[0][: PREVIEW_MAX_CHARS - 2]
    text = f"<{first}>\r\n\r\n" + "\r\n".join(lines[1:])
    return text[:PREVIEW_MAX_CHARS]


def _korean_date(stamp: datetime) -> str:
    # 형식 자체(오전/오후, 시 무패딩)는 R1 date 메타의 구조 패턴에서 가져왔다(값은 복사하지 않음).
    meridiem = "오전" if stamp.hour < 12 else "오후"
    hour12 = stamp.hour % 12 or 12
    return (
        f"{stamp.year}년 {stamp.month:02d}월 {stamp.day:02d}일 "
        f"{_WEEKDAYS_KO[stamp.weekday()]}요일 {meridiem} {hour12}:{stamp.minute:02d}:{stamp.second:02d}"
    )


def build_version_xml(info: VersionInfo) -> bytes:
    root = etree.Element(f"{{{NS_VERSION}}}HCFVersion", nsmap={"hv": NS_VERSION})
    for key, value in (
        ("tagetApplication", "WORDPROCESSOR"),  # 철자는 R1 그대로 (분석서 §3-1)
        ("major", "5"),
        ("minor", "0"),
        ("micro", "5"),
        ("buildNumber", "0"),
        ("os", "1"),
        ("xmlVersion", HWPX_XML_VERSION),
        ("application", info.application),
        ("appVersion", info.app_version),
    ):
        root.set(key, value)
    return serialize_xml(root)


def build_container_xml() -> bytes:
    root = etree.Element(
        f"{{{NS_OCF}}}container", nsmap={"ocf": NS_OCF, "hpf": NAMESPACES["hpf"]}
    )
    rootfiles = etree.SubElement(root, f"{{{NS_OCF}}}rootfiles")
    for path, media_type in (
        ("Contents/content.hpf", "application/hwpml-package+xml"),
        ("Preview/PrvText.txt", "text/plain"),
    ):
        etree.SubElement(
            rootfiles, f"{{{NS_OCF}}}rootfile", {"full-path": path, "media-type": media_type}
        )
    return serialize_xml(root)


def build_manifest_xml() -> bytes:
    """분석서 §3-3: 자식 없는 빈 ``odf:manifest``."""
    return serialize_xml(etree.Element(f"{{{NS_ODF_MANIFEST}}}manifest", nsmap={"odf": NS_ODF_MANIFEST}))


def build_settings_xml() -> bytes:
    root = etree.Element(
        qn("ha", "HWPApplicationSetting"),
        nsmap={"ha": NAMESPACES["ha"], "config": NAMESPACES["config"]},
    )
    etree.SubElement(
        root, qn("ha", "CaretPosition"), {"listIDRef": "0", "paraIDRef": "0", "pos": "0"}
    )
    item_set = etree.SubElement(root, qn("config", "config-item-set"), {"name": "PrintInfo"})
    for name, kind, value in (
        ("PrintAutoFootNote", "boolean", "false"),
        ("PrintAutoHeadNote", "boolean", "false"),
        ("PrintMethod", "short", "0"),
        ("PrintCropMark", "short", "0"),
        ("BinderHoleType", "short", "0"),
        ("ZoomX", "short", "100"),
        ("ZoomY", "short", "100"),
    ):
        item = etree.SubElement(item_set, qn("config", "config-item"), {"name": name, "type": kind})
        item.text = value
    return serialize_xml(root)


def build_content_hpf(section_count: int, meta: PackageMeta) -> bytes:
    """분석서 §3-4. ``opf:title``은 비운다(DEC-060, 입력 제목 미기록)."""
    stamp = meta.resolved_created()
    iso = stamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    root = new_root("opf", "package")
    for key in ("version", "unique-identifier", "id"):
        root.set(key, "")
    metadata = etree.SubElement(root, qn("opf", "metadata"))
    etree.SubElement(metadata, qn("opf", "title")).text = ""
    etree.SubElement(metadata, qn("opf", "language")).text = "ko"
    for name, value in (
        ("creator", meta.creator),
        ("subject", None),
        ("description", None),
        ("lastsaveby", meta.last_saved_by),
        ("CreatedDate", iso),
        ("ModifiedDate", iso),
        ("date", _korean_date(stamp)),
        ("keyword", None),
    ):
        el = etree.SubElement(metadata, qn("opf", "meta"), {"name": name, "content": "text"})
        if value is not None:
            el.text = value

    manifest = etree.SubElement(root, qn("opf", "manifest"))
    items = [("header", "Contents/header.xml")]
    items += [(f"section{i}", f"Contents/section{i}.xml") for i in range(section_count)]
    items.append(("settings", "settings.xml"))
    for item_id, href in items:
        etree.SubElement(
            manifest, qn("opf", "item"), {"id": item_id, "href": href, "media-type": "application/xml"}
        )
    spine = etree.SubElement(root, qn("opf", "spine"))
    for idref in ["header", *[f"section{i}" for i in range(section_count)]]:
        etree.SubElement(spine, qn("opf", "itemref"), {"idref": idref, "linear": "yes"})
    return serialize_xml(root)


class HwpxPackage:
    def __init__(self, meta: PackageMeta | None = None) -> None:
        self.meta = meta or PackageMeta()
        self._header: bytes | None = None
        self._sections: list[bytes] = []
        self._preview_text = ""

    def set_header(self, xml: bytes) -> None:
        self._header = xml

    def add_section(self, xml: bytes) -> int:
        self._sections.append(xml)
        return len(self._sections) - 1

    def set_preview_text(self, text: str) -> None:
        self._preview_text = text

    @property
    def section_count(self) -> int:
        return len(self._sections)

    def _check(self) -> None:
        if self._header is None:
            raise ContainerBuildError("header.xml이 설정되지 않았습니다.")
        if not self._sections:
            raise ContainerBuildError("구역(section)이 하나도 없습니다.")
        try:
            root = etree.fromstring(self._header)
        except etree.XMLSyntaxError as exc:
            raise ContainerBuildError(f"header.xml이 well-formed가 아닙니다: {exc}") from exc
        if root.tag != qn("hh", "head") or root.get("secCnt") != str(len(self._sections)):
            raise ContainerBuildError(
                f"header의 secCnt({root.get('secCnt')})가 구역 수({len(self._sections)})와 다릅니다."
            )

    def _entries(self) -> Sequence[tuple[str, bytes, bool]]:
        """(이름, 데이터, deflate 여부). 순서는 R1 zip 중앙 디렉터리 순서(분석서 §2)."""
        if self._header is None:
            raise ContainerBuildError("header.xml이 설정되지 않았습니다.")
        entries: list[tuple[str, bytes, bool]] = [
            ("mimetype", MIMETYPE_CONTENT, False),
            ("version.xml", build_version_xml(self.meta.version), False),
            ("Contents/header.xml", self._header, True),
        ]
        entries += [(f"Contents/section{i}.xml", xml, True) for i, xml in enumerate(self._sections)]
        entries += [
            ("Preview/PrvText.txt", self._preview_text.encode("utf-8"), True),
            ("settings.xml", build_settings_xml(), True),
            ("META-INF/container.xml", build_container_xml(), True),
            ("Contents/content.hpf", build_content_hpf(len(self._sections), self.meta), True),
            ("META-INF/manifest.xml", build_manifest_xml(), True),
        ]
        return entries

    def to_bytes(self) -> bytes:
        self._check()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w") as zf:
            for name, data, deflate in self._entries():
                info = zipfile.ZipInfo(name, date_time=_FIXED_DATE_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED if deflate else zipfile.ZIP_STORED
                info.create_system = _ZIP_CREATE_SYSTEM
                info.external_attr = _ZIP_EXTERNAL_ATTR
                zf.writestr(info, data)
        return buf.getvalue()

    def write(self, output_path: Path | str) -> None:
        """원자적으로 쓴다(임시 파일 -> replace). 실패는 ``ContainerBuildError``."""
        output_path = Path(output_path)
        data = self.to_bytes()
        tmp_path = output_path.with_name(output_path.name + ".tmp")
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_bytes(data)
            tmp_path.replace(output_path)
        except OSError as exc:
            tmp_path.unlink(missing_ok=True)
            raise ContainerBuildError(f"HWPX 파일 쓰기 실패: {output_path} ({exc})") from exc
