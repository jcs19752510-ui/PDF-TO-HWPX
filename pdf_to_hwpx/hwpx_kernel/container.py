"""HWPX(OWPML/KS X 6101) zip 컨테이너 골격 생성/조작 (unit-4, REQ-008).

**중요 — 미검증 리스크 (docs/harness/decisions.md DEC-017 참고)**
원래 설계(03-system-design.md §2-1, §8-1 트레이드오프 2번)는 "실제 한글이 저장한
최소 빈 문서(.hwpx)를 리버스엔지니어링한 참조 템플릿"을 확보해 그 파일의 실제 zip
엔트리 구성·XML 태그/속성/네임스페이스를 그대로 베끼는 전략이었다. 그러나 이
개발 환경에는 한글(한컴오피스) 프로그램이 설치되어 있지 않아 그런 참조 파일을
확보할 수 없었다(DEC-017). 이 모듈의 모든 파트 이름·디렉터리 구조·XML 네임스페이스
URI·속성 이름은 **공개된 OWPML/KS X 6101 관련 일반 지식과 관례(ODF/OOXML/EPUB류
zip+XML 패키지 포맷의 공통 관례 포함)에 근거한 "합리적 추정"이며, 바이트 단위로
실제 한글이 만드는 파일과 일치한다고 보장하지 않는다.** 추정 근거를 아래에 항목별로
표기했다("확신" vs "추정/미검증"). unit-5/6/7·unit-8(orchestrator)·이후 검증 단계는
반드시 실제 한글(한컴오피스)로 열어보는 검증을 별도로 수행해야 한다(이 unit의 범위
밖 — 개발 환경 제약으로 이번 호출에서는 수행 불가).

**확신(구조적으로 안정적이라 판단하는 부분)**:
- HWPX는 zip 컨테이너이고, 내부는 XML 파트들로 구성된다(OWPML 자체가 공개 표준이며
  이 사실은 여러 공개 자료에서 일관되게 확인됨).
- `mimetype` 엔트리를 zip의 첫 번째 항목으로 비압축(``ZIP_STORED``) 저장하는 관례는
  ODF/EPUB 등 동일 계열 zip+XML 패키지 포맷에서 널리 쓰이는 규약이며, HWPX도 이
  계열로 분류된다(01보고서/03 §2-1 근거). 다만 한글이 실제로 이 규약을 강제하는지
  100% 확인된 것은 아니다.
- 본문(문단/표/그림)은 XML 파트 안에 담기고, 별도의 "헤더"류 파트가 글자모양/문단모양
  등 스타일 정의를 담당하는 구조(본문과 스타일 정의 분리)는 OWPML 계열 문서에서
  일반적이다.

**추정/미검증(파일명·네임스페이스·속성 이름 등 세부 사항)**:
- 정확한 파트 파일명(`content.hpf`, `header.xml`, `section0.xml`, `settings.xml`,
  `version.xml`, `META-INF/container.xml`, `META-INF/manifest.xml`) 및 그 안의
  XML 태그/속성 이름, 네임스페이스 URI(`NAMESPACES` 딕셔너리)는 전부 추정치다.
- 특히 네임스페이스 URI 문자열(`http://www.hancom.co.kr/hwpml/2011/...` 형태)은
  실제 한글이 쓰는 정확한 문자열과 다를 수 있다.
"""

from __future__ import annotations

import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from lxml import etree

from pdf_to_hwpx.common.exceptions import ContainerBuildError

# 아래 네임스페이스 URI는 전부 "추정(미검증)"이다 — 모듈 docstring 참고.
NAMESPACES = {
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",       # header.xml (스타일 정의)
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",     # section*.xml 루트
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",   # 문단/런/표/그림 등 본문 요소
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",        # 공용 코어 타입(예비, 현재 미사용)
    "ha": "http://www.hancom.co.kr/hwpml/2011/app",         # settings.xml
    "hv": "http://www.hancom.co.kr/hwpml/2011/version",     # version.xml
    "opf": "http://www.hancom.co.kr/hwpml/2011/package",    # Contents/content.hpf
    "ocf": "http://www.hancom.co.kr/hwpml/2011/container",  # META-INF/container.xml·manifest.xml
}

MIMETYPE_CONTENT = b"application/hwp+zip"  # 추정(미검증) — ODF의 mimetype 관례를 따른 값 추정

SECTION_DIR = "Contents"
DEFAULT_SECTION_NAME = "section0.xml"

# BinData(이미지 등 바이너리 파트) 저장 관례 — 아래 전부 "추정(미검증)"이다(모듈
# docstring 1절과 동일 사유). ODF(`Pictures/`)·OOXML(`media/`)류 zip+XML 패키지
# 포맷이 바이너리 리소스를 별도 디렉터리에 두고 manifest에 media-type을 등록하는
# 공통 관례를 따라, HWPX도 "BinData/" 하위에 "<bin_data_id>.<확장자>"로 저장하고
# manifest.xml/content.hpf에 등록하는 방식을 추정 채택했다. 실제 한글이 이 디렉터리명을
# 쓰는지는 확인되지 않았다 — unit-4-note.md "확장(2026-09-28)" 절 참고.
BIN_DATA_DIR = "BinData"

# unit-7(image_embedder.py)이 실제로 반환하는 image_format 값만 다룬다
# (ccitt/jbig2/unknown은 unit-7이 이미 걸러내고 이 함수에 넘기지 않는다는 계약).
_IMAGE_FORMAT_TO_EXTENSION = {
    "jpeg": "jpg",
    "jp2": "jp2",
    "png": "png",
    "tiff": "tif",
}
_IMAGE_FORMAT_TO_MEDIA_TYPE = {
    "jpeg": "image/jpeg",
    "jp2": "image/jp2",
    "png": "image/png",
    "tiff": "image/tiff",
}

# zip 엔트리 타임스탬프를 고정값으로 둔다 — 실제 생성 시각을 파일에 남기지 않기 위함
# (개인정보/재현성 목적. 03 §6-2 개인정보 최소화 원칙과 같은 방향).
_FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)


def _section_path(section_name: str) -> str:
    return f"{SECTION_DIR}/{section_name}"


def _serialize(root: etree._Element) -> bytes:
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True
    )


def _build_version_xml() -> bytes:
    """OWPML 버전 선언 파트. 태그/속성명 추정(미검증) — 모듈 docstring 참고."""
    root = etree.Element(f"{{{NAMESPACES['hv']}}}HCFVersion", nsmap={"hv": NAMESPACES["hv"]})
    root.set("tagID", "HWPX")
    root.set("major", "1")
    root.set("minor", "0")
    return _serialize(root)


def _build_container_xml() -> bytes:
    """META-INF/container.xml. EPUB/ODF류 "루트파일 포인터" 관례를 추정 적용."""
    root = etree.Element(f"{{{NAMESPACES['ocf']}}}container", nsmap={"ocf": NAMESPACES["ocf"]})
    root.set("version", "1.0")
    rootfiles = etree.SubElement(root, f"{{{NAMESPACES['ocf']}}}rootfiles")
    etree.SubElement(
        rootfiles,
        f"{{{NAMESPACES['ocf']}}}rootfile",
        attrib={
            "full-path": f"{SECTION_DIR}/content.hpf",
            "media-type": "application/hwpml-package+xml",
        },
    )
    return _serialize(root)


def _build_manifest_xml(section_names: Sequence[str]) -> bytes:
    """META-INF/manifest.xml. ODF manifest.xml 관례(파일별 media-type 목록)를 추정 적용."""
    root = etree.Element(f"{{{NAMESPACES['ocf']}}}manifest", nsmap={"ocf": NAMESPACES["ocf"]})
    entries: list[tuple[str, str]] = [
        ("/", MIMETYPE_CONTENT.decode("ascii")),
        ("version.xml", "application/xml"),
        ("settings.xml", "application/xml"),
        (f"{SECTION_DIR}/content.hpf", "application/xml"),
        (f"{SECTION_DIR}/header.xml", "application/xml"),
    ]
    entries.extend((_section_path(name), "application/xml") for name in section_names)
    for full_path, media_type in entries:
        etree.SubElement(
            root,
            f"{{{NAMESPACES['ocf']}}}file-entry",
            attrib={"full-path": full_path, "media-type": media_type},
        )
    return _serialize(root)


def _build_content_hpf(section_names: Sequence[str]) -> bytes:
    """Contents/content.hpf. OPF(Open Packaging Format)류 manifest+spine 구조를 추정 적용."""
    root = etree.Element(f"{{{NAMESPACES['opf']}}}package", nsmap={"opf": NAMESPACES["opf"]})
    root.set("version", "1.0")
    manifest = etree.SubElement(root, f"{{{NAMESPACES['opf']}}}manifest")
    etree.SubElement(
        manifest,
        f"{{{NAMESPACES['opf']}}}item",
        attrib={"id": "header", "href": f"{SECTION_DIR}/header.xml", "media-type": "application/xml"},
    )
    for idx, name in enumerate(section_names):
        etree.SubElement(
            manifest,
            f"{{{NAMESPACES['opf']}}}item",
            attrib={"id": f"section{idx}", "href": _section_path(name), "media-type": "application/xml"},
        )
    spine = etree.SubElement(root, f"{{{NAMESPACES['opf']}}}spine")
    for idx in range(len(section_names)):
        etree.SubElement(spine, f"{{{NAMESPACES['opf']}}}itemref", attrib={"idref": f"section{idx}"})
    return _serialize(root)


def _build_header_xml() -> bytes:
    """Contents/header.xml. 글자모양(charShape)/문단모양(paraShape) id=0 기본값만 정의한다.

    unit-5/6/7이 참조하는 최소 스타일 id(``charShapeIDRef="0"``, ``paraShapeIDRef="0"``)가
    이 헤더에 정의된 id와 반드시 일치해야 한다 — 인수조건 참고.
    """
    root = etree.Element(
        f"{{{NAMESPACES['hh']}}}head",
        nsmap={"hh": NAMESPACES["hh"], "hc": NAMESPACES["hc"]},
    )
    ref_list = etree.SubElement(root, f"{{{NAMESPACES['hh']}}}refList")
    char_shapes = etree.SubElement(ref_list, f"{{{NAMESPACES['hh']}}}charShapes")
    etree.SubElement(char_shapes, f"{{{NAMESPACES['hh']}}}charShape", attrib={"id": "0", "height": "1000"})
    para_shapes = etree.SubElement(ref_list, f"{{{NAMESPACES['hh']}}}paraShapes")
    etree.SubElement(para_shapes, f"{{{NAMESPACES['hh']}}}paraShape", attrib={"id": "0"})
    return _serialize(root)


def _build_settings_xml() -> bytes:
    """settings.xml. 실제 한글이 요구하는 필드는 불명 — 빈 루트 요소만 추정 작성."""
    root = etree.Element(f"{{{NAMESPACES['ha']}}}settings", nsmap={"ha": NAMESPACES["ha"]})
    return _serialize(root)


def _build_empty_section_xml() -> bytes:
    """0페이지(빈 문서) 최소 본문 섹션. 완전히 빈 ``<hs:sec>``가 유효한지 불명확해,
    안전 쪽으로 빈 문단(``hp:p``) 1개를 포함시켰다(추정 — 미검증)."""
    root = etree.Element(
        f"{{{NAMESPACES['hs']}}}sec",
        nsmap={"hs": NAMESPACES["hs"], "hp": NAMESPACES["hp"]},
    )
    p = etree.SubElement(root, f"{{{NAMESPACES['hp']}}}p", attrib={"paraShapeIDRef": "0"})
    run = etree.SubElement(p, f"{{{NAMESPACES['hp']}}}run", attrib={"charShapeIDRef": "0"})
    etree.SubElement(run, f"{{{NAMESPACES['hp']}}}t")
    return _serialize(root)


def _write_entry(zf: zipfile.ZipFile, arcname: str, data: bytes, *, compress: bool = True) -> None:
    info = zipfile.ZipInfo(arcname, date_time=_FIXED_DATE_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    info.external_attr = 0o644 << 16
    zf.writestr(info, data)


def build_empty_container(output_path: Path) -> None:
    """페이지 0개인 최소 유효 HWPX zip 골격을 ``output_path``에 생성한다.

    실패(디스크 공간 부족, 출력 디렉터리 생성 불가, 권한 없음 등)하면
    ``ContainerBuildError``를 던진다(03 §4-2).

    unit-5/6/7/8을 위한 인터페이스: 이 함수가 만든 파일은 이후
    ``add_section_xml()``로 본문(``Contents/section0.xml``)을 교체해 채우는
    대상이 된다. 이 함수 자체는 항상 "빈 문서"만 만든다.
    """
    output_path = Path(output_path)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, mode="w") as zf:
            _write_entry(zf, "mimetype", MIMETYPE_CONTENT, compress=False)
            _write_entry(zf, "version.xml", _build_version_xml())
            _write_entry(zf, "settings.xml", _build_settings_xml())
            _write_entry(zf, "META-INF/container.xml", _build_container_xml())
            _write_entry(zf, "META-INF/manifest.xml", _build_manifest_xml([DEFAULT_SECTION_NAME]))
            _write_entry(zf, f"{SECTION_DIR}/header.xml", _build_header_xml())
            _write_entry(zf, _section_path(DEFAULT_SECTION_NAME), _build_empty_section_xml())
            _write_entry(zf, f"{SECTION_DIR}/content.hpf", _build_content_hpf([DEFAULT_SECTION_NAME]))
    except OSError as exc:
        raise ContainerBuildError(
            f"HWPX 컨테이너 골격 생성 실패: {output_path} ({exc})"
        ) from exc


def add_section_xml(
    container_path: Path,
    xml_bytes: bytes,
    section_name: str = DEFAULT_SECTION_NAME,
) -> None:
    """기존 HWPX 컨테이너의 본문 섹션 XML(``Contents/<section_name>``)을 교체하거나
    없으면 새로 추가한다.

    ``zipfile``은 기존 zip 안의 항목을 제자리에서 교체하는 API를 제공하지 않으므로,
    임시 zip을 새로 만들어 나머지 항목을 그대로 복사하고 대상 항목만 교체한 뒤
    원자적으로(``Path.replace``) 원본 경로에 덮어쓴다.

    unit-8(orchestrator)을 위한 인터페이스: unit-5/6/7이 만든 XML 프래그먼트를
    (아직 이 unit 범위 밖인) 하나의 섹션 본문으로 조립한 뒤 이 함수를 호출해
    ``build_empty_container()``가 만든 골격에 실제 내용을 채워 넣는다.
    **현재 이 함수는 단일 섹션(``section0.xml``) 교체만 지원한다** — 여러 섹션으로
    나누는 경우 ``content.hpf``의 spine도 함께 갱신해야 하나, 이 unit의 확정 범위(03
    §1-3)가 문서당 섹션 1개를 전제로 하고 있어(§1-2 컴포넌트 다이어그램상 orchestrator가
    유일한 통합점) 그 이상의 다중 섹션 spine 갱신 로직은 구현하지 않았다.

    실패 시(파일 없음, 권한 문제, 손상된 zip 등) ``ContainerBuildError``를 던진다.
    """
    container_path = Path(container_path)
    if not container_path.exists():
        raise ContainerBuildError(f"HWPX 컨테이너 파일이 존재하지 않습니다: {container_path}")

    target_arcname = _section_path(section_name)
    tmp_path = container_path.with_name(container_path.name + ".tmp")
    try:
        with zipfile.ZipFile(container_path, mode="r") as src, zipfile.ZipFile(tmp_path, mode="w") as dst:
            replaced = False
            for item in src.infolist():
                data = src.read(item.filename)
                if item.filename == target_arcname:
                    data = xml_bytes
                    replaced = True
                dst.writestr(item, data)
            if not replaced:
                _write_entry(dst, target_arcname, xml_bytes)
        tmp_path.replace(container_path)
    except (OSError, zipfile.BadZipFile) as exc:
        tmp_path.unlink(missing_ok=True)
        raise ContainerBuildError(
            f"HWPX 섹션 XML 갱신 실패: {container_path} ({exc})"
        ) from exc


def add_bin_data(
    container_path: Path,
    entries: Mapping[str, tuple[bytes, str]],
) -> None:
    """이미지 등 바이너리(BinData) 파트를 기존 HWPX 컨테이너에 삽입/갱신한다.

    ``entries``는 ``{bin_data_id: (raw_bytes, image_format)}`` 형태로,
    ``hwpx_writer.image_embedder.EmbeddedImage``(unit-7)의 ``bin_data_id``/
    ``raw_bytes``/``image_format`` 3종을 그대로 딕셔너리로 옮긴 것을 그대로
    받도록 시그니처를 맞췄다(unit-7-note.md §6-1 제안 계약과 동일).

    각 항목을 ``BinData/<bin_data_id>.<확장자>``(확장자는 ``image_format``에서
    유도)로 zip에 쓰고, ``META-INF/manifest.xml``과 ``Contents/content.hpf``의
    manifest에 media-type을 등록한다(둘 다 well-formed XML로 재직렬화). **spine에는
    추가하지 않는다** — BinData는 문서 흐름의 일부(section)가 아니라 `hp:pic`이
    참조하는 리소스이므로, OPF류 포맷(EPUB 등)에서 바이너리 리소스를 manifest에는
    등록하되 spine(읽기 순서)에는 넣지 않는 관례를 그대로 따랐다(추정 — 미검증,
    모듈 docstring 1절과 동일한 성격의 불확실성).

    ``add_section_xml``과 동일한 "기존 zip 전체를 새 zip으로 재작성하며 대상
    항목만 교체, 나머지는 그대로 복사 후 ``Path.replace()``로 원자적 치환" 패턴을
    재사용한다. 이미 같은 ``bin_data_id``로 등록된 항목이 있으면(재호출 시) manifest/
    content.hpf에 중복 등록하지 않고 바이트만 덮어쓴다(멱등성 보장).

    ``image_format``이 unit-7이 이미 지원 포맷으로 분류한 값(``jpeg``/``jp2``/
    ``png``/``tiff``) 중 하나가 아니면 어떤 파일도 건드리지 않고 즉시
    ``ContainerBuildError``를 던진다(경계 검증 — 잘못된 확장자/미디어타입으로
    조용히 저장하는 사고를 방지).

    ``entries``가 비어 있으면 아무 것도 하지 않는다(파일 미접촉, 예외 없음).

    실패 시(대상 파일 없음, 필수 파트 없음, 손상된 zip, XML 파싱 실패 등)
    ``ContainerBuildError``를 던진다.
    """
    if not entries:
        return

    for bin_data_id, (_raw_bytes, image_format) in entries.items():
        if image_format not in _IMAGE_FORMAT_TO_EXTENSION:
            raise ContainerBuildError(
                f"지원하지 않는 이미지 포맷입니다: bin_data_id={bin_data_id!r}, "
                f"image_format={image_format!r}"
            )

    container_path = Path(container_path)
    if not container_path.exists():
        raise ContainerBuildError(f"HWPX 컨테이너 파일이 존재하지 않습니다: {container_path}")

    manifest_arcname = "META-INF/manifest.xml"
    content_hpf_arcname = f"{SECTION_DIR}/content.hpf"
    tmp_path = container_path.with_name(container_path.name + ".tmp")
    try:
        with zipfile.ZipFile(container_path, mode="r") as src:
            existing_entries = {item.filename: (item, src.read(item.filename)) for item in src.infolist()}

        try:
            manifest_bytes = existing_entries[manifest_arcname][1]
            content_hpf_bytes = existing_entries[content_hpf_arcname][1]
        except KeyError as exc:
            raise ContainerBuildError(
                f"HWPX 컨테이너에 필수 파트가 없습니다: {exc} ({container_path})"
            ) from exc

        manifest_root = etree.fromstring(manifest_bytes)
        content_root = etree.fromstring(content_hpf_bytes)
        content_manifest = content_root.find(f"{{{NAMESPACES['opf']}}}manifest")
        if content_manifest is None:
            raise ContainerBuildError(
                f"content.hpf에 manifest 요소가 없습니다: {container_path}"
            )

        existing_manifest_paths = {
            el.get("full-path") for el in manifest_root.findall(f"{{{NAMESPACES['ocf']}}}file-entry")
        }
        existing_content_hrefs = {
            el.get("href") for el in content_manifest.findall(f"{{{NAMESPACES['opf']}}}item")
        }

        updates: dict[str, bytes] = {}
        for bin_data_id, (raw_bytes, image_format) in entries.items():
            extension = _IMAGE_FORMAT_TO_EXTENSION[image_format]
            media_type = _IMAGE_FORMAT_TO_MEDIA_TYPE[image_format]
            arcname = f"{BIN_DATA_DIR}/{bin_data_id}.{extension}"
            updates[arcname] = raw_bytes

            if arcname not in existing_manifest_paths:
                etree.SubElement(
                    manifest_root,
                    f"{{{NAMESPACES['ocf']}}}file-entry",
                    attrib={"full-path": arcname, "media-type": media_type},
                )
                existing_manifest_paths.add(arcname)

            if arcname not in existing_content_hrefs:
                etree.SubElement(
                    content_manifest,
                    f"{{{NAMESPACES['opf']}}}item",
                    attrib={"id": bin_data_id, "href": arcname, "media-type": media_type},
                )
                existing_content_hrefs.add(arcname)

        updates[manifest_arcname] = _serialize(manifest_root)
        updates[content_hpf_arcname] = _serialize(content_root)

        with zipfile.ZipFile(tmp_path, mode="w") as dst:
            written: set[str] = set()
            for filename, (item, data) in existing_entries.items():
                if filename in updates:
                    data = updates[filename]
                    written.add(filename)
                dst.writestr(item, data)
            for arcname, data in updates.items():
                if arcname not in written:
                    _write_entry(dst, arcname, data)
        tmp_path.replace(container_path)
    except (OSError, zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
        tmp_path.unlink(missing_ok=True)
        raise ContainerBuildError(
            f"HWPX BinData 삽입 실패: {container_path} ({exc})"
        ) from exc
