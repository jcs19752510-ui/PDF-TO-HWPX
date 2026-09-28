"""PDF 이미지 추출 -> ``ImageBlockIR`` 변환 (unit-2).

(docs/harness/03-system-design.md §1-3 unit-2 행, §2-1 "PDF 파싱(이미지 원본
바이트 추출): pypdf" 선정 근거, §3-1 IR 정의, docs/harness/02-planning.md
REQ-003 참고.)

이 모듈의 입력은 ``pdf_reader/loader.py``(unit-0)가 반환한
``PdfDocument.pypdf_reader``의 개별 페이지(``pypdf_reader.pages[i]``,
``pypdf.PageObject``)다. 호출자(orchestrator, unit-8)가 페이지를 순회하며
이 모듈의 함수를 호출해 ``pdf_to_hwpx.pdf_reader.ir.PageIR.image_blocks``를
채우는 구조를 가정한다(unit-1의 ``text_extractor.extract_text_blocks``와
동일한 호출 패턴).

책임 범위 (03 §1-3 unit-2 행, REQ-003 그대로):
    - 페이지에 실제로 배치된 이미지를 찾아, **재인코딩 없이 원본 바이트
      그대로** ``ImageBlockIR.raw_bytes``에 담는다.
    - ``ImageBlockIR.image_format``에는 실제 PDF ``/Filter``에서 판별한
      원본 인코딩 표기를 담는다("jpeg"/"jp2"/"ccitt"/"jbig2"/"raw-flate" 등).

=======================================================================
재작업(2026-09-28) -- 06단계 DEF-001/DEF-002(Critical) 반려에 따른 재설계
=======================================================================

06-unit-tester가 실제 PDF로 재현한 두 결함(자세한 재현 절차는
``docs/harness/units/unit-2-test.md`` §6, ``tests/pdf_reader/
test_image_extractor.py``의 ``test_flate_encoded_raster_image_raw_bytes_are_
NOT_original_bytes_DEF001``/``test_dctdecode_jpeg_raw_bytes_can_silently_
diverge_from_original_DEF002`` 참고):

    - DEF-001: 이전 구현이 쓰던 ``pypdf_page.images``(``ImageFile.data``)는
      내부적으로 ``pypdf.generic._image_xobject._xobj_to_image()``를 거치는데,
      이 함수는 DCTDecode(JPEG)를 제외한 거의 모든 필터(FlateDecode/
      LZWDecode/CCITTFaxDecode/JBIG2Decode 등)에 대해 스트림을 디코드한 뒤
      **Pillow로 새 파일(주로 PNG/TIFF)을 재인코딩**해서 반환한다.
    - DEF-002: DCTDecode(JPEG) 경로조차 ``_xobj_to_image()``가 Pillow
      ``quality="keep"``으로 재인코딩을 시도하는데, 이 옵션이 "무손실을
      보장"하지 않는 best-effort 옵션이라 특정 이미지 내용에서 원본과 조용히
      달라질 수 있다(pypdf 6.19.0 소스 직접 확인, ``pypdf/generic/
      _image_xobject.py`` 최하단 ``img.save(..., **pillow_parameters)``).

이번 재작업에서 pypdf 6.19.0 소스(``pypdf/generic/_data_structures.py``의
``StreamObject``/``EncodedStreamObject``, ``pypdf/filters.py``의
``decode_stream_data``)를 직접 읽어 확인한 사실:

    1. ``StreamObject._data``는 PDF 파일에 물리적으로 저장된 스트림 바이트를
       **어떤 필터도 적용하지 않은 상태 그대로** 들고 있다(파싱 시
       ``StreamObject.initialize_from_dictionary``가 ``__streamdata__``를
       그대로 대입하는 지점, 필터 해석은 이 시점에 전혀 일어나지 않음).
    2. ``EncodedStreamObject.get_data()``(=``pypdf_page.images``가 호출하는
       ``x_object.get_data()``의 실체)만 ``decode_stream_data()``를 통해
       필터를 해석하고, DCTDecode/JPXDecode에 대해서는 ``decode_stream_data``
       조차 데이터를 그대로 반환한다(``DCTDecode.decode``/``JPXDecode.decode``
       는 항등함수, ``pypdf/filters.py`` 직접 확인) -- 즉 이 두 필터에서
       "재인코딩"은 ``get_data()`` 단계가 아니라 그 *이후* ``_xobj_to_image()``
       가 Pillow로 다시 저장하는 단계에서만 발생한다.
    3. CCITTFaxDecode는 ``decode_stream_data`` 단계에서 이미 pypdf가 직접
       합성한 TIFF 헤더를 덧붙이고, JBIG2Decode는 외부 ``jbig2dec`` 바이너리를
       호출해 PNG로 변환한다 -- 두 경우 모두 Pillow 이전 단계에서조차 이미
       "원본 그대로"가 아니게 된다.

**새 방식**: ``pypdf_page.images``(디코드 후 Pillow 재인코딩까지 포함하는
편의 API) 자체를 호출하지 않고, ``/Resources/XObject``를 직접 순회하며
각 이미지 XObject의 ``_data``(위 1번, 필터를 전혀 적용하지 않은 원본 스트림
바이트)를 그대로 꺼낸다. ``image_format``은 이 필터를 해석하지 않고
``/Filter`` 이름 자체에서만 결정한다(``_raw_bytes_and_format``). 이 방식은
DCTDecode/JPXDecode/CCITTFaxDecode/JBIG2Decode 어느 쪽이든 Pillow는 물론
pypdf 자신의 필터 디코더조차 거치지 않으므로, DEF-001과 DEF-002가 동시에
사라진다(4단계 로컬 확인 참고).

**필터별 처리와 남은 모호성/한계** (자세한 근거와 오케스트레이터에게 남기는
질문은 ``docs/harness/units/unit-2-note.md`` "재작업(2026-09-28)" 절 참고):

    - DCTDecode/JPXDecode/CCITTFaxDecode/JBIG2Decode: "그 자체로 완결된
      이미지 코덱" 필터라 raw_bytes가 항상 원본 스트림과 바이트 단위로
      동일함이 보장된다(모호함 없음, 06단계 재검증 대상).
    - FlateDecode/LZWDecode/RunLengthDecode/필터 없음: PDF 안에 "외부 이미지
      파일"이 원래 존재한 적이 없는 원시 픽셀 샘플이다. **(2026-09-28,
      DEC-028로 아래 "2차 재작업" 절 내용으로 대체됨 -- 이 문단은 1차
      재작업 당시의 잠정 처리를 이력 보존을 위해 그대로 남긴다)** 1차
      재작업은 이 스트림을 압축 해제도, 재인코딩도 하지 않고 PDF에 저장된
      그대로 반환했었다(``image_format``에 "raw-flate"/"raw-lzw"/
      "raw-runlength"/"raw-samples"로 명시) -- 이 값 자체는 뷰어가 열 수
      있는 이미지 파일이 아니라는 문제가 있었고, 이를 오케스트레이터에게
      질문(unit-2-note.md §7-7 Q1)으로 이관한 결과가 DEC-028이다. 아래
      "2차 재작업" 절 참고.
    - 필터 배열이 여러 개 연쇄된 경우(예: ``[/ASCII85Decode, /DCTDecode]``,
      실무에서 극히 드묾): 이번 구현은 배열의 **마지막** 필터만으로
      ``image_format``을 결정하고 ``raw_bytes``는 항상 가공 없는 원본
      스트림을 반환한다 -- 즉 이 드문 경우 raw_bytes는 아직 앞선 전송용
      필터(ASCII85 등)가 벗겨지지 않은 상태일 수 있다(알려진 한계, 테스트로
      재현된 사례 없어 추측성 처리 로직을 추가하지 않았다).
    - 인라인 이미지(BI/ID/EI)는 ``/Resources/XObject``에 선언되지 않으므로
      위 저수준 순회로는 찾을 수 없다 -- 이번 재작업 범위(DEF-001/002는 둘 다
      Do-참조 XObject로 재현됨)가 아니라 기존 방식(``pypdf_page`` 콘텐츠
      스트림 파서가 만든 ``ImageFile`` 캐시, 내부적으로 Pillow 경유)을 그대로
      유지한다 -- 즉 인라인 이미지는 DEF-001/002와 동일한 성격의 재인코딩
      위험이 여전히 남아 있는 **알려진 한계**다(unit-2-note.md 참고).

핵심 설계 한계(bbox 폴백, 03 §2-1이 pypdf를 선정한 이유 -- 이번 재작업과
무관, 그대로 유지):
    ``/Resources/XObject``를 직접 순회해도 그 이미지가 페이지 좌표계에서
    **어디에 얼마나 크게** 배치되는지(콘텐츠 스트림의 ``cm``/``Do`` 연산자가
    만드는 변환 행렬)는 알 수 없다. 이를 신뢰성 있게 얻으려면 콘텐츠 스트림
    연산자를 직접 해석하는 별도 파서를 새로 구현해야 하는데, 이는
    REQ-003(원본 바이트 보존)의 범위를 벗어난 별도 기능이라 지어내지 않는다.

    **대안(이 모듈이 실제로 하는 것)**: 각 ``ImageBlockIR.bbox``를 해당
    페이지의 ``MediaBox`` 전체 크기((0, 0, width_pt, height_pt))로
    폴백한다. 이 폴백은 IR 자체에는 "폴백 여부" 플래그가 없다(``ir.py``는
    공유 계약 파일이라 이 작업 단위 파일 범위 밖 -- 필드를 추가하지
    않았다). 대신 **이 모듈이 반환하는 모든 ``ImageBlockIR.bbox``는 항상
    페이지 전체 크기 폴백값**이라는 사실 자체가 계약이다.

명시적으로 다루지 않는 것:
    - 같은 이미지 리소스가 페이지 내 여러 위치에 반복 배치된 경우: 리소스당
      1개의 ``ImageBlockIR``만 만든다(리소스 딕셔너리 기준 순회이므로).
    - 리소스로 선언만 되고 실제 콘텐츠 스트림에서 그려지지 않는(눈에
      보이지 않는) 이미지는 제외한다 -- 이번 재작업과 무관, 그대로 유지.

=======================================================================
2차 재작업(2026-09-28) -- DEC-028(docs/harness/decisions.md) 반영
=======================================================================

1차 재작업(위 절)이 남긴 질문(unit-2-note.md §7-7 Q1: FlateDecode/
LZWDecode/RunLengthDecode/필터 없음 -- "원시 픽셀 샘플" 계열 이미지에서
REQ-003을 어떻게 해석할지)을 오케스트레이터가 DEC-028로 결정했다:
**PDF 표준 필터로 압축을 해제해 원시 픽셀 샘플을 얻고, XObject 딕셔너리의
``/Width``/``/Height``/``/BitsPerComponent``/``/ColorSpace``(``/Indexed``
팔레트 포함)/``/Decode``를 읽어 그 샘플을 올바르게 해석한 뒤, 무손실
PNG로 합성한다. 합성 직후 그 PNG를 다시 디코드해 우리가 만든 픽셀
배열과 바이트 단위로 동일한지 코드로 직접 검증하고, 하나라도 다르면
예외를 던진다**(조용히 반환하지 않는다 -- DEF-001/002 재발 방지 취지를
이 필터 계열에도 동일하게 적용).

DCTDecode/JPXDecode/CCITTFaxDecode/JBIG2Decode 경로(위 1차 재작업 절)는
이번에 전혀 건드리지 않았다 -- 그 경로는 이미 "원본 스트림과 바이트 단위로
항상 동일"이 보장되어 있어 재작업 대상이 아니다.

**핵심 함수**: ``_synthesize_lossless_png(xobj, resources)``가
``xobj.get_data()``(표준 필터 디코드, Predictor 포함 -- 손실 없는 표준
압축 해제, pypdf가 담당)로 원시 픽셀 바이트를 얻고,
``_resolve_pixel_layout()``으로 Pillow ``Image.frombytes()``에 필요한
mode/rawmode(및 인덱스 컬러면 팔레트)를 결정한 뒤, ``_maybe_apply_
inverted_decode()``로 ``/Decode`` 배열이 명시적 전체반전인 경우만 반영하고,
PNG로 저장한 다음 ``_verify_png_round_trip_or_raise()``로 왕복 검증한다.

**지원 범위(과설계 방지를 위해 의도적으로 한정, 근거는 unit-2-note.md
"2차 재작업" 절 참고)**:
    - ColorSpace: ``/DeviceGray``/``/CalGray``(1채널), ``/DeviceRGB``/
      ``/CalRGB``(3채널), ``/ICCBased``(``/N``으로 채널 수 판별해 위 둘 중
      하나로 취급), ``/Indexed [base hival lookup]``(base는 위 두 가지만
      지원). 리소스 이름으로 간접 참조된 ColorSpace(``/ColorSpace /CS0``
      형태)는 ``resources["/ColorSpace"]``에서 조회해 해석한다.
    - ``/DeviceCMYK``(직접이든 ``/Indexed``의 base든)는 **의도적으로
      지원하지 않는다** -- PNG 자체가 CMYK 색공간을 표현할 수 없어(Pillow로
      직접 확인, ``img.save(format="PNG")``가 CMYK 모드에서 ``OSError``),
      RGB로 변환하면 그 자체가 손실 있는 색 변환이라 "무손실 PNG" 요건과
      상충한다 -- 억지로 변환하기보다 명시적으로 실패시키는 쪽을 택했다.
    - BitsPerComponent: Gray/Indexed는 1/2/4/8, RGB는 8만 지원한다(16비트는
      미지원, 실무에서 이 경로로 들어오는 임베디드 래스터 이미지에 드묾).
    - ``/Decode``: 기본값(항등) 또는 전 채널 완전반전(``[1 0]`` 반복)만
      지원한다(비인덱스 Gray/RGB는 BitsPerComponent와 무관하게 지원 --
      ``Image.frombytes``가 이미 0..255로 선형 스케일링한 뒤이므로 반전이
      bpc와 무관하게 등가임을 로컬로 실측 확인했다). 그 외 임의의 선형
      재매핑과, 인덱스 컬러의 사용자정의 Decode는 지원하지 않는다.
    - 위 범위를 벗어나면(예: DeviceCMYK, 미지원 BitsPerComponent, 임의의
      Decode 배열, ColorSpace 자체가 없거나 알 수 없음) ``_UnsupportedRaw
      ImageEncodingError``를 던진다 -- 이 함수를 호출하는 ``extract_image_
      blocks``가 예외를 삼키지 않으므로(모듈 docstring 상단 "Raises"절)
      그대로 호출자에게 전파된다.

**왕복 검증 실패 시 처리 방식(지시문 필수 요건)**: ``_verify_png_round_
trip_or_raise()``가 크기/모드/픽셀 바이트(및 인덱스 컬러면 팔레트)가
하나라도 다르면 ``_PngRoundTripVerificationError``를 던진다 -- 이 이미지를
결과 목록에서 조용히 제외하는 방식이 아니라, 예외로 명시적으로 실패를
알리는 쪽을 택했다(근거는 unit-2-note.md "2차 재작업" 절 참고. 요약:
이 함수는 원래도 "예외를 삼키지 않는다"는 계약을 갖고 있었고(모듈
상단 "Raises"절), 이 계약과 일관되게 유지하는 것이 03 §4-2 예외체계
설계 의도와 상충하지 않는다).

=======================================================================
3차 재작업(2026-09-28) -- 07단계 DEF-INT-001(High) 반려에 따른 수정
=======================================================================

07단계(Feature A 통합테스트, ``docs/harness/feature-A-integration-test.md``)가
unit-0~8을 실제 구현끼리(monkeypatch 없이) 엮어 돌린 결과, reportlab로 생성한
지극히 평범한 PDF(``canvas.drawImage()``만 호출)에서 이미지 XObject의
``/Filter``가 ``[/ASCII85Decode, /DCTDecode]``(전송 필터 + 완결 코덱 필터
연쇄)로 나오는 것을 확인했다 -- 1차 재작업(위 "재작업(2026-09-28)" 절
"필터별 처리와 남은 모호성/한계")이 "실무에서 극히 드묾"으로 판단해 재현
테스트 없이 한계로만 남겼던 그 조합이, 실은 널리 쓰이는 PDF 생성 라이브러리의
**기본 동작**이라는 뜻이다. **이 판단을 여기서 정정한다**: 다중 필터 연쇄는
드문 예외가 아니라 흔한 입력이며, 재현 테스트 부재를 근거로 미해결 한계로
남겨 둔 것 자체가 부적절한 판단이었다.

**근본 원인(정확히)**: 기존 ``_raw_bytes_and_format``는 필터 배열의
**마지막** 필터만 보고 그것이 완결 코덱(DCTDecode 등)이면 ``xobj._data``
(어떤 필터도 해석하지 않은 원본 스트림)를 그대로 그 코덱의 바이트로
반환했다. 필터가 1개뿐일 때는 이것이 정확하지만, 앞에 다른 필터(예:
ASCII85Decode)가 있으면 ``_data``는 여전히 그 앞단 필터로 인코딩된 상태인데도
``image_format="jpeg"``로 잘못 라벨링됐다 -- 하류(unit-7/unit-4)는 포맷
**이름**만 보고 바이트 유효성을 검증하지 않아 이 오라벨링이 최종 ``.hwpx``
까지 조용히 흘러갔다(``success=True``, ``warnings=[]``).

**수정 내용**: ``_raw_bytes_and_format``가 이제 필터 배열 **전체**를 본다.
마지막 필터가 완결 코덱이고 그 앞에 다른 필터가 있으면, 그 앞선 필터들이
전부 ``_LEADING_FILTER_DECODERS``(ASCII85Decode/ASCIIHexDecode/FlateDecode/
LZWDecode/RunLengthDecode -- pypdf 표준 순수 파이썬 디코더, Pillow 미경유)에
있는 "안전하게 해석 가능한" 필터일 때만 실제로 디코드해 벗겨내고, 그 결과를
완결 코덱의 원본 바이트로 반환한다(``_decode_leading_transport_filters``).
앞선 필터 중 하나라도 이 표에 없거나(추측성 처리를 하지 않음) 디코딩 자체가
예외를 던지면, "안전하게 디코드할 수 없다"고 보고 **완결 코덱으로 잘못
라벨링해 반환하지 않고** 기존에 이미 존재하던 "미지원 포맷" 경로
(``image_format="unknown"``)로 명시적으로 빠진다 -- unit-7
``image_embedder.py``의 ``SUPPORTED_IMAGE_FORMATS`` 화이트리스트가 이 값을
이미 "제외 + ``IMAGE_FORMAT_UNSUPPORTED`` 경고"로 처리하므로(범위 밖 파일,
이번에 수정하지 않음, 기존 배선을 그대로 재사용), 조용히 손상된 바이트가
임베딩되는 경로 자체가 남지 않는다.

단일 필터 케이스(기존 06 PASS 대상, DEF-001/DEF-002 재발 방지 핵심)는
``leading_filter_names``가 빈 리스트가 되어 이번 변경 이전과 완전히 동일한
코드 경로(``_data`` 그대로 반환)를 탄다 -- 회귀 없음(로컬 확인, 아래 참고).
FlateDecode/LZWDecode/RunLengthDecode/필터 없음(원시 픽셀 샘플, DEC-028)
경로는 애초에 ``xobj.get_data()``로 필터 배열 전체를 pypdf가 표준 해석하므로
이번 결함과 무관했고(다중 필터가 있어도 원래부터 정확), 전혀 건드리지
않았다.

**남은 한계(지어내지 않고 명시)**: ``_LEADING_FILTER_DECODERS``에 없는
필터(예: ``/Crypt``, 완결 코덱이 비정상적으로 배열 중간에 낀 경우 등)가
완결 코덱 앞에 오면 여전히 ``"unknown"``으로 빠져 이미지가 통째로 제외된다
(부분적으로라도 복구하지 않음) -- 추측으로 근사 바이트를 만들어내는 것보다
안전한 실패를 택한 결과다. 인라인 이미지(BI/ID/EI) 경로는 이번에도 손대지
않았다(1차 재작업 한계 그대로 유지, ``_extract_inline_images`` 참고).
"""

from __future__ import annotations

import io
from pathlib import Path

import pypdf
from PIL import Image, ImageOps
from pypdf.errors import PdfReadError
from pypdf.filters import (
    ASCII85Decode,
    ASCIIHexDecode,
    FlateDecode,
    LZWDecode,
    RunLengthDecode,
)
from pypdf.generic import ArrayObject, DictionaryObject, NullObject

from pdf_to_hwpx.pdf_reader.ir import ImageBlockIR

# 인라인 이미지 전용 폴백 경로(``_extract_inline_images``)에서만 쓰인다 --
# pypdf가 ``ImageFile.name`` 뒤에 붙이는 확장자를 IR의 ``image_format``
# 표기로 정규화하는 표. pypdf 소스(6.19.0) 기준 실제로 등장하는 확장자만
# 반영했다(".jpg"/".png"/".tiff"/".jp2") -- 근거 없는 포맷을 지어내지 않는다.
_EXTENSION_TO_FORMAT = {
    "jpg": "jpeg",
    "jpeg": "jpeg",
    "png": "png",
    "tif": "tiff",
    "tiff": "tiff",
    "jp2": "jp2",
}

# "그 자체로 완결된 이미지 코덱" 필터 -> image_format. 이 필터들은 raw_bytes가
# 항상 원본 스트림과 바이트 단위로 동일함이 보장된다(모듈 docstring 재작업
# 절 참고, 모호함 없음).
_SELF_CONTAINED_CODEC_FILTER_TO_FORMAT = {
    "/DCTDecode": "jpeg",
    "/DCT": "jpeg",
    "/JPXDecode": "jp2",
    "/CCITTFaxDecode": "ccitt",
    "/CCF": "ccitt",
    "/JBIG2Decode": "jbig2",
}

# PDF 내부에 "완결된 이미지 파일"이 원래 존재한 적이 없는 원시 픽셀 샘플 계열
# 필터 -> image_format. 이 값들의 의미(원시 픽셀 그대로 둘지, 표준 이미지
# 컨테이너로 감쌀지)에 대한 설계 모호성은 unit-2-note.md "재작업" 절 질문
# 목록 참고.
_RAW_SAMPLE_FILTER_TO_FORMAT = {
    "/FlateDecode": "raw-flate",
    "/Fl": "raw-flate",
    "/LZWDecode": "raw-lzw",
    "/LZW": "raw-lzw",
    "/RunLengthDecode": "raw-runlength",
    "/RL": "raw-runlength",
}

# DEF-INT-001(07 통합테스트) 수정 -- 완결 코덱 필터(DCTDecode 등) 앞에 낀
# "전송/범용 압축" 필터를 pypdf 표준(순수 파이썬, Pillow 미경유) 디코더로
# 실제로 벗겨내는 데 쓰는 표. 이미지 전용 코덱(DCT/JPX/CCITT/JBIG2) 자신의
# decode()는 절대 포함하지 않는다 -- 그 바이트 자체가 보존해야 할 원본이라
# (배열의 마지막 자리에 있을 때) 손대면 안 되기 때문. 이 표에 없는 필터가
# 선행하면 안전하게 해석할 수 없다고 보고 명시적으로 실패 경로로 빠진다
# (아래 ``_decode_leading_transport_filters`` 참고, 모듈 docstring
# "DEF-INT-001 재작업" 절 근거).
_LEADING_FILTER_DECODERS = {
    "/ASCII85Decode": ASCII85Decode.decode,
    "/A85": ASCII85Decode.decode,
    "/ASCIIHexDecode": ASCIIHexDecode.decode,
    "/AHx": ASCIIHexDecode.decode,
    "/FlateDecode": FlateDecode.decode,
    "/Fl": FlateDecode.decode,
    "/LZWDecode": LZWDecode.decode,
    "/LZW": LZWDecode.decode,
    "/RunLengthDecode": RunLengthDecode.decode,
    "/RL": RunLengthDecode.decode,
}


class _UnsupportedRawImageEncodingError(PdfReadError):
    """DEC-028 지원 범위(모듈 docstring "2차 재작업" 절) 밖의 ColorSpace/
    BitsPerComponent/Decode 조합을 만났을 때 던진다 -- 임의로 근사치를
    지어내지 않고 명시적으로 실패시키기 위함(그대로 호출자에게 전파됨,
    삼키지 않음)."""


class _PngRoundTripVerificationError(PdfReadError):
    """DEC-028 필수 요건 -- 합성한 PNG를 다시 디코드해 원본 픽셀 샘플과
    바이트 단위로 동일한지 검증했는데 하나라도 다를 때 던진다. 이 예외가
    발생했다는 것은 "무손실이어야 할 합성 과정에서 실제로는 손실/버그가
    있었다"는 뜻이므로, 이 이미지를 조용히 누락시키지 않고 명시적으로
    실패를 알린다(그대로 호출자에게 전파됨, 삼키지 않음)."""


# DEC-028 지원 대상 ColorSpace -> 채널 수. /DeviceCMYK은 의도적으로 목록에
# 있지만 아래 조회 지점에서 "지원 안 함"으로 처리한다(PNG가 CMYK을 표현할
# 수 없어 RGB 변환이 필요한데, 그 변환 자체가 손실 있는 색 변환이라 "무손실
# PNG" 요건과 상충하기 때문 -- 모듈 docstring "2차 재작업" 절 참고).
_DEVICE_COLORSPACE_TO_COMPONENTS = {
    "/DeviceGray": 1,
    "/CalGray": 1,
    "/DeviceRGB": 3,
    "/CalRGB": 3,
    "/DeviceCMYK": 4,
}

# (채널 수, BitsPerComponent) -> (Pillow mode, Image.frombytes rawmode).
# RGB는 8비트만 지원(DEC-028 범위 한정), CMYK(4채널)은 어떤 bpc든 이 표에
# 없어(=None) 아래 _resolve_pixel_layout에서 명시적으로 실패한다.
_GRAY_RGB_MODE_TABLE: dict[tuple[int, int], tuple[str, str]] = {
    (1, 1): ("1", "1"),
    (1, 2): ("L", "L;2"),
    (1, 4): ("L", "L;4"),
    (1, 8): ("L", "L"),
    (3, 8): ("RGB", "RGB"),
}

# 인덱스 컬러(/Indexed) BitsPerComponent -> Image.frombytes rawmode.
_INDEXED_BPC_TO_RAWMODE = {1: "P;1", 2: "P;2", 4: "P;4", 8: "P"}


def _dereference(obj):
    return obj.get_object() if hasattr(obj, "get_object") else obj


def _resolve_named_colorspace(color_space_obj, resources):
    """``/ColorSpace`` 값이 리소스 이름(예: ``/CS0``)으로 간접 참조된
    경우, 페이지 ``/Resources/ColorSpace``에서 실제 정의를 찾아 반환한다.
    ``/DeviceGray``/``/DeviceRGB``/``/DeviceCMYK``/``/Pattern`` 같은
    내장 이름은 그대로 반환한다."""
    color_space_obj = _dereference(color_space_obj)
    if isinstance(color_space_obj, ArrayObject):
        return color_space_obj
    name = str(color_space_obj)
    if name in ("/DeviceGray", "/DeviceRGB", "/DeviceCMYK", "/Pattern"):
        return color_space_obj
    if resources is not None:
        cs_resources = resources.get("/ColorSpace")
        if cs_resources is not None:
            cs_resources = _dereference(cs_resources)
            if name in cs_resources:
                return _dereference(cs_resources[name])
    raise _UnsupportedRawImageEncodingError(f"ColorSpace 리소스를 찾을 수 없음: {name!r}")


def _base_colorspace_name(color_space_obj) -> str | None:
    """``/DeviceGray``/``/DeviceRGB``/``/DeviceCMYK``/``/CalGray``/
    ``/CalRGB``/``/ICCBased`` 표현을 ``_DEVICE_COLORSPACE_TO_COMPONENTS``
    키 형태(``"/DeviceGray"`` 등)로 정규화한다. 지원하지 않는 형태면
    ``None``을 반환한다(호출자가 명시적으로 실패시킴)."""
    color_space_obj = _dereference(color_space_obj)
    if isinstance(color_space_obj, ArrayObject):
        if len(color_space_obj) == 0:
            return None
        head = str(_dereference(color_space_obj[0]))
        if head == "/ICCBased" and len(color_space_obj) >= 2:
            stream = _dereference(color_space_obj[1])
            component_count = int(stream.get("/N", 0)) if stream is not None else 0
            return {1: "/DeviceGray", 3: "/DeviceRGB", 4: "/DeviceCMYK"}.get(component_count)
        if head in _DEVICE_COLORSPACE_TO_COMPONENTS:
            return head
        return None
    name = str(color_space_obj)
    return name if name in _DEVICE_COLORSPACE_TO_COMPONENTS else None


def _convert_gray_or_rgb_palette_to_rgb(lookup_bytes: bytes, base_components: int) -> bytes:
    if base_components == 3:
        return bytes(lookup_bytes)
    if base_components == 1:
        return bytes(value for gray in lookup_bytes for value in (gray, gray, gray))
    raise _UnsupportedRawImageEncodingError(
        f"/Indexed 팔레트의 base ColorSpace 채널 수({base_components})를 지원하지 않음"
        " -- DeviceCMYK base는 DEC-028 범위에서 의도적으로 제외됨"
    )


def _resolve_indexed_layout(color_space_obj: ArrayObject, bits_per_component: int, resources):
    if len(color_space_obj) != 4:
        raise _UnsupportedRawImageEncodingError(
            f"/Indexed 배열 형식이 예상(4개 항목)과 다름: {color_space_obj!r}"
        )
    if bits_per_component not in _INDEXED_BPC_TO_RAWMODE:
        raise _UnsupportedRawImageEncodingError(
            f"/Indexed에서 지원하지 않는 BitsPerComponent={bits_per_component}"
        )

    base_obj = _resolve_named_colorspace(_dereference(color_space_obj[1]), resources)
    base_name = _base_colorspace_name(base_obj)
    base_components = _DEVICE_COLORSPACE_TO_COMPONENTS.get(base_name) if base_name else None
    if base_components is None or base_name == "/DeviceCMYK":
        raise _UnsupportedRawImageEncodingError(
            f"/Indexed의 base ColorSpace를 지원하지 않음: {base_obj!r}"
        )

    hival = int(_dereference(color_space_obj[2]))
    lookup_obj = _dereference(color_space_obj[3])
    if hasattr(lookup_obj, "get_data"):
        # 팔레트가 별도 스트림 객체(자체 필터를 가질 수 있음, 예: 압축된
        # 팔레트)로 저장된 경우 -- get_data()가 그 필터까지 표준 해석한다.
        lookup_bytes = bytes(lookup_obj.get_data())
    elif hasattr(lookup_obj, "get_original_bytes"):
        # 팔레트가 PDF 문자열 리터럴(짧은 팔레트에 흔함)로 저장된 경우 --
        # pypdf가 파싱 시 ``TextStringObject``(str 서브클래스)와
        # ``ByteStringObject``(bytes 서브클래스) 중 어느 쪽으로 판별할지는
        # 내용에 따라 달라져(실측 확인) ``bytes(lookup_obj)``가
        # TextStringObject에서 "encoding 없이 문자열" 오류로 실패할 수
        # 있다 -- 두 타입 모두 갖고 있는 ``get_original_bytes()``(가공되지
        # 않은 원본 바이트)로 통일해 꺼낸다.
        lookup_bytes = bytes(lookup_obj.get_original_bytes())
    else:
        lookup_bytes = bytes(lookup_obj)

    entry_count = hival + 1
    expected_len = entry_count * base_components
    if len(lookup_bytes) < expected_len:
        raise _UnsupportedRawImageEncodingError(
            "/Indexed 팔레트 lookup 테이블 길이가 /Hival과 맞지 않음"
            f"(필요 {expected_len}바이트, 실제 {len(lookup_bytes)}바이트)"
        )
    lookup_bytes = lookup_bytes[:expected_len]

    palette_rgb = _convert_gray_or_rgb_palette_to_rgb(lookup_bytes, base_components)
    rawmode = _INDEXED_BPC_TO_RAWMODE[bits_per_component]
    return "P", rawmode, palette_rgb


def _resolve_pixel_layout(color_space_obj, bits_per_component: int, resources):
    """``ImageBlockIR``이 아니라 Pillow ``Image.frombytes()`` 호출에 필요한
    ``(mode, rawmode, palette_or_None)``을 반환한다. 지원 범위는 모듈
    docstring "2차 재작업" 절 참고, 범위 밖이면 명시적으로 실패한다."""
    if color_space_obj is None:
        raise _UnsupportedRawImageEncodingError("이미지 XObject에 /ColorSpace가 없음")

    color_space_obj = _resolve_named_colorspace(color_space_obj, resources)

    if isinstance(color_space_obj, ArrayObject) and len(color_space_obj) and str(
        _dereference(color_space_obj[0])
    ) == "/Indexed":
        return _resolve_indexed_layout(color_space_obj, bits_per_component, resources)

    base_name = _base_colorspace_name(color_space_obj)
    components = _DEVICE_COLORSPACE_TO_COMPONENTS.get(base_name) if base_name else None
    if components is None or base_name == "/DeviceCMYK":
        raise _UnsupportedRawImageEncodingError(f"지원하지 않는 ColorSpace: {color_space_obj!r}")

    mode_and_rawmode = _GRAY_RGB_MODE_TABLE.get((components, bits_per_component))
    if mode_and_rawmode is None:
        raise _UnsupportedRawImageEncodingError(
            f"지원하지 않는 BitsPerComponent={bits_per_component}(채널 수={components})"
        )
    mode, rawmode = mode_and_rawmode
    return mode, rawmode, None


def _maybe_apply_inverted_decode(image, mode: str, bits_per_component: int, decode_array, is_indexed: bool):
    """``/Decode`` 배열이 기본값(항등)이면 그대로 두고, 전 채널 완전반전
    (``[1 0]`` 반복)이면 반전을 적용한다. 그 외(인덱스 컬러의 사용자정의
    반전 포함)는 명시적으로 실패시킨다(DEC-028 지원 범위 한정)."""
    if decode_array is None:
        return image

    decode_values = [float(_dereference(v)) for v in decode_array]

    if is_indexed:
        default_indexed = [0.0, float((2**bits_per_component) - 1)]
        if decode_values == default_indexed:
            return image
        raise _UnsupportedRawImageEncodingError(
            f"인덱스 컬러 이미지의 사용자정의 /Decode 배열은 지원하지 않음: {decode_array!r}"
        )

    component_count = len(decode_values) // 2
    if decode_values == [0.0, 1.0] * component_count:
        return image
    if decode_values == [1.0, 0.0] * component_count:
        # Image.frombytes 시점에 이미 0..255 범위로 선형 스케일링되어 있어
        # (예: 2bpc는 0/85/170/255, 4bpc는 17 단위) bpc와 무관하게 0..255
        # 도메인에서의 반전이 PDF Decode[1 0] 반전과 정확히 등가다(로컬
        # 동작 확인으로 1/2/4/8bpc 전부 실측 검증, unit-2-note.md 참고).
        return ImageOps.invert(image)
    raise _UnsupportedRawImageEncodingError(
        f"지원하지 않는 /Decode 배열: {decode_array!r}(mode={mode}, BitsPerComponent={bits_per_component})"
    )


def _verify_png_round_trip_or_raise(png_bytes: bytes, source_image) -> None:
    """DEC-028 필수 요건 -- 방금 합성한 PNG를 다시 디코드해 ``source_image``
    (원본 스트림을 해석해 만든, 우리가 의도한 픽셀 배열)와 바이트 단위로
    동일한지 검증한다. 하나라도 다르면 조용히 넘어가지 않고 예외를 던진다."""
    reopened = Image.open(io.BytesIO(png_bytes))
    reopened.load()

    if reopened.size != source_image.size or reopened.mode != source_image.mode:
        raise _PngRoundTripVerificationError(
            "PNG 왕복 검증 실패: 크기 또는 모드가 원본과 다름 "
            f"(원본 {source_image.size}/{source_image.mode} vs PNG {reopened.size}/{reopened.mode})"
        )
    if reopened.tobytes() != source_image.tobytes():
        raise _PngRoundTripVerificationError(
            "PNG 왕복 검증 실패: 픽셀 데이터가 원본과 바이트 단위로 다름"
        )
    if source_image.mode == "P":
        original_palette = source_image.getpalette() or []
        reopened_palette = reopened.getpalette() or []
        prefix_len = min(len(original_palette), len(reopened_palette))
        if original_palette[:prefix_len] != reopened_palette[:prefix_len]:
            raise _PngRoundTripVerificationError(
                "PNG 왕복 검증 실패: 인덱스 팔레트(RGB 값)가 원본과 다름"
            )


def _synthesize_lossless_png(xobj, resources) -> bytes:
    """FlateDecode/LZWDecode/RunLengthDecode/필터 없음 이미지(원시 픽셀
    샘플)를 표준 필터로 압축 해제하고, XObject 딕셔너리의 메타데이터로
    픽셀을 해석해 무손실 PNG로 합성한다(DEC-028). 반환 직전 반드시
    왕복 검증을 통과해야 한다."""
    if "/Width" not in xobj or "/Height" not in xobj:
        raise _UnsupportedRawImageEncodingError("이미지 XObject에 /Width 또는 /Height가 없음")

    decoded = bytes(xobj.get_data())
    width = int(_dereference(xobj["/Width"]))
    height = int(_dereference(xobj["/Height"]))
    bits_per_component = int(_dereference(xobj.get("/BitsPerComponent", 8)))
    color_space_obj = xobj.get("/ColorSpace")
    decode_array = xobj.get("/Decode")

    mode, rawmode, palette = _resolve_pixel_layout(color_space_obj, bits_per_component, resources)

    try:
        image = Image.frombytes(mode, (width, height), decoded, "raw", rawmode)
    except ValueError as exc:
        raise _UnsupportedRawImageEncodingError(
            f"픽셀 데이터를 mode={mode}/rawmode={rawmode}(width={width}, height={height})로"
            f" 해석하지 못함: {exc}"
        ) from exc

    if palette is not None:
        image.putpalette(palette)

    image = _maybe_apply_inverted_decode(
        image, mode, bits_per_component, decode_array, is_indexed=palette is not None
    )

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    png_bytes = buffer.getvalue()

    _verify_png_round_trip_or_raise(png_bytes, image)

    return png_bytes


def extract_image_blocks(pypdf_page: pypdf.PageObject) -> list[ImageBlockIR]:
    """페이지 하나에서 실제로 배치된 이미지를 원본 바이트 그대로 추출한다.

    Args:
        pypdf_page: ``PdfDocument.pypdf_reader.pages[i]`` (unit-0 산출물).
            이 함수는 이 객체를 읽기 전용으로만 소비한다.

    Returns:
        페이지에서 실제로 그려지는(``is_displayed``, 또는 인라인) 이미지들의
        ``ImageBlockIR`` 목록. 이미지가 없으면 빈 리스트. 모든 항목의
        ``bbox``는 모듈 docstring이 명시한 대로 페이지 전체 크기 폴백값이다.

    Raises:
        Exception: 이미지 XObject 구조가 예상과 다르거나(예: ``_data``
            속성 자체가 없는 비정상 스트림 객체) pypdf 내부에서 던지는
            예외를 그대로 전파한다 -- 삼켜서 무시하지 않는다. 03 §5가
            정의한 "페이지 단위 격리(벌크헤드)"는 이 함수를 호출하는
            orchestrator(unit-8)의 책임이라, 여기서 임의로 실패를 흡수하면
            그 설계 의도(사용자에게 부분 실패를 알림, REQ-009)를 어기게
            된다.
    """
    width_pt = float(pypdf_page.mediabox.width)
    height_pt = float(pypdf_page.mediabox.height)
    fallback_bbox = (0.0, 0.0, width_pt, height_pt)

    blocks: list[ImageBlockIR] = []
    blocks.extend(_extract_resource_xobject_images(pypdf_page, fallback_bbox))
    blocks.extend(_extract_inline_images(pypdf_page, fallback_bbox))
    return blocks


def _extract_resource_xobject_images(
    pypdf_page: pypdf.PageObject, fallback_bbox: tuple[float, float, float, float]
) -> list[ImageBlockIR]:
    """``/Resources/XObject``를 직접 순회해 Do-참조 이미지를 재인코딩 없이
    추출한다(DEF-001/DEF-002 재작업의 핵심 경로)."""
    blocks: list[ImageBlockIR] = []
    resources = pypdf_page.get("/Resources")
    if resources is None:
        return blocks
    resources = resources.get_object()
    xobject_dict = resources.get("/XObject")
    if xobject_dict is None:
        return blocks
    xobject_dict = xobject_dict.get_object()

    displayed_names = _get_content_stream_image_cache(pypdf_page)

    for name, ref in xobject_dict.items():
        xobj = ref.get_object()
        if xobj.get("/Subtype") != "/Image":
            continue
        if name not in displayed_names:
            continue  # 리소스로만 선언되고 실제로 그려지지 않음 (AC-3, 그대로 유지)
        raw_bytes, image_format = _raw_bytes_and_format(xobj, resources)
        blocks.append(
            ImageBlockIR(bbox=fallback_bbox, raw_bytes=raw_bytes, image_format=image_format)
        )
    return blocks


def _extract_inline_images(
    pypdf_page: pypdf.PageObject, fallback_bbox: tuple[float, float, float, float]
) -> list[ImageBlockIR]:
    """인라인(BI/ID/EI) 이미지는 ``/Resources/XObject``에 선언되지 않으므로
    위 저수준 순회로는 찾을 수 없다 -- pypdf의 콘텐츠 스트림 파서가 이미
    만들어 둔 ``ImageFile`` 캐시를 그대로 재사용한다(추가 Pillow 호출 없음,
    이미 계산된 값 재사용). 알려진 한계(모듈 docstring 재작업 절 참고): 이
    경로는 여전히 Pillow 재인코딩을 거치므로 DEF-001/002와 동일한 성격의
    바이트 불일치 위험이 남아 있다."""
    blocks: list[ImageBlockIR] = []
    for image_file in _get_content_stream_image_cache(pypdf_page).values():
        if image_file is None or not image_file.is_inline:
            continue
        blocks.append(
            ImageBlockIR(
                bbox=fallback_bbox,
                raw_bytes=image_file.data,
                image_format=_detect_image_format(image_file.name),
            )
        )
    return blocks


def _get_content_stream_image_cache(pypdf_page: pypdf.PageObject) -> dict:
    """pypdf.PageObject._content_stream_images 캐시(콘텐츠 스트림을 스캔해
    Do-참조 이름과 인라인 ``ImageFile``을 모아 둔 dict)를 채워서 반환한다.
    pypdf 6.19.0 소스(``pypdf/_page.py::PageObject._get_ids_image``/
    ``_get_image``)가 "그려지는지" 여부를 판별하는 것과 동일한 방식(이름이
    이 dict에 있는지)이라 그대로 재사용한다 -- Pillow를 트리거하는
    ``pypdf_page.images``/``_get_image()``는 호출하지 않는다."""
    if pypdf_page._content_stream_images is None:
        pypdf_page._content_stream_images = pypdf_page._parse_images_from_content_stream()
    return pypdf_page._content_stream_images


def _normalize_filter_names(xobj) -> list[str]:
    """``/Filter``를 항상 이름 문자열 리스트로 정규화한다(필터 없음 ->
    빈 리스트, 단일 필터 -> 원소 1개 리스트, 배열 -> 순서 보존한 리스트).
    배열의 개별 항목이 간접참조(``IndirectObject``)일 수 있어 각 항목마다
    ``get_object()``를 해석한다(기존 로직과 동일한 처리, DEF-INT-001
    재작업에서 다중 필터를 온전히 다루기 위해 리스트 전체를 보존하도록
    확장했다)."""
    filters = xobj.get("/Filter")
    if filters is not None and hasattr(filters, "get_object"):
        filters = filters.get_object()
    if isinstance(filters, ArrayObject):
        return [
            str(f.get_object() if hasattr(f, "get_object") else f) for f in filters
        ]
    if filters is None or isinstance(filters, NullObject):
        return []
    return [str(filters)]


def _normalize_decode_parms(xobj, filter_count: int) -> list:
    """``/DecodeParms``를 ``/Filter`` 배열과 같은 길이의 리스트로 정규화한다
    (pypdf ``filters.py::decode_stream_data``와 동일한 정렬 규칙 -- 없는
    자리는 빈 ``DictionaryObject``로 채운다, pypdf 6.19.0 소스 직접 확인)."""
    parms = xobj.get("/DecodeParms")
    if parms is not None and hasattr(parms, "get_object"):
        parms = parms.get_object()
    if isinstance(parms, ArrayObject):
        items = [p.get_object() if hasattr(p, "get_object") else p for p in parms]
    elif parms is None:
        items = []
    else:
        items = [parms]

    normalized = []
    for i in range(filter_count):
        p = items[i] if i < len(items) else None
        if p is None or isinstance(p, NullObject):
            p = DictionaryObject()
        normalized.append(p)
    return normalized


def _decode_leading_transport_filters(
    data: bytes, filter_names: list[str], decode_parms: list
) -> bytes | None:
    """완결 코덱 필터(배열의 마지막 자리) 앞에 낀 전송/범용 압축 필터를
    pypdf 표준 디코더(순수 파이썬, Pillow 미경유)로 실제로 벗겨낸다
    (DEF-INT-001 수정 -- 07 통합테스트가 reportlab 기본 산출물
    ``[/ASCII85Decode, /DCTDecode]``로 재현한 결함).

    ``_LEADING_FILTER_DECODERS``에 없는 필터를 만나거나(추측으로 처리하지
    않음) 디코딩 자체가 예외를 던지면(손상/예상 밖 구조) ``None``을 반환해
    호출자가 "안전하게 디코드할 수 없음" 경로(기존 미지원 포맷 처리, 아래
    ``_raw_bytes_and_format`` 참고)로 명시적으로 빠지게 한다."""
    for name, params in zip(filter_names, decode_parms):
        decoder = _LEADING_FILTER_DECODERS.get(name)
        if decoder is None:
            return None
        try:
            data = decoder(data, params)
        except Exception:
            return None
    return data


def _raw_bytes_and_format(xobj, resources) -> tuple[bytes, str]:
    """이미지 XObject에서 ``(raw_bytes, image_format)``을 반환한다.

    - "그 자체로 완결된 이미지 코덱" 필터(DCTDecode/JPXDecode/
      CCITTFaxDecode/JBIG2Decode)가 필터 배열의 **마지막** 자리에 있으면,
      그 앞에 낀 필터가 없는 한(또는 전부 안전하게 벗겨낼 수 있는 한)
      **가공되지 않은(또는 전송/압축 필터만 벗겨낸) 원본 코덱 바이트**를
      반환한다(Pillow도, 그 코덱 자신의 필터 디코더도 거치지 않음 -- 1차
      재작업/DEF-001/DEF-002 재발 방지의 핵심, 이번 DEF-INT-001 재작업
      에서는 "앞에 낀 필터 처리"만 추가했다). 앞선 필터를 안전하게 해석할
      수 없으면 ``image_format="unknown"``으로 명시적으로 빠진다(아래
      DEF-INT-001 분기 참고 -- 조용히 잘못 라벨링해 반환하지 않는다).
    - FlateDecode/LZWDecode/RunLengthDecode/필터 없음(원시 픽셀 샘플)은
      ``_synthesize_lossless_png()``로 무손실 PNG를 합성해 반환한다
      (DEC-028, 모듈 docstring "2차 재작업" 절). 이 경로는 ``xobj.get_data()``
      로 필터 배열 전체를 pypdf가 표준 해석하므로 앞선 필터 유무와 무관하게
      원래부터 정확했다(DEF-INT-001과 무관, 변경 없음).
    - 그 외 인식하지 못하는 필터는 원본 스트림 바이트를 그대로 반환하고
      ``image_format="unknown"``으로 표기한다(추측성 처리를 하지 않음,
      1차 재작업과 동일한 안전한 기본값 유지)."""
    filter_names = _normalize_filter_names(xobj)
    last_filter_name = filter_names[-1] if filter_names else None

    if last_filter_name is not None and last_filter_name in _SELF_CONTAINED_CODEC_FILTER_TO_FORMAT:
        raw_bytes = getattr(xobj, "_data", None)
        if raw_bytes is None:
            raise PdfReadError(
                f"이미지 XObject 스트림에서 원본 바이트(_data)를 찾을 수 없음(비정상 구조): {xobj!r}"
            )
        raw_bytes = bytes(raw_bytes)

        leading_filter_names = filter_names[:-1]
        if leading_filter_names:
            leading_decode_parms = _normalize_decode_parms(xobj, len(filter_names))[:-1]
            decoded = _decode_leading_transport_filters(
                raw_bytes, leading_filter_names, leading_decode_parms
            )
            if decoded is None:
                # DEF-INT-001: 완결 코덱 앞에 안전하게 디코드할 수 없는
                # 필터가 있어 raw_bytes를 그 코덱의 원본 바이트라고 확신할
                # 수 없다 -- unit-7 image_embedder.py의
                # SUPPORTED_IMAGE_FORMATS 화이트리스트가 "unknown"을 이미
                # "제외 + IMAGE_FORMAT_UNSUPPORTED 경고"로 처리하므로, 그
                # 기존 미지원 포맷 경로로 명시적으로 빠진다(조용히 완결
                # 코덱으로 잘못 라벨링해 반환하지 않음).
                return raw_bytes, "unknown"
            raw_bytes = decoded

        return raw_bytes, _SELF_CONTAINED_CODEC_FILTER_TO_FORMAT[last_filter_name]

    if last_filter_name is None or last_filter_name in _RAW_SAMPLE_FILTER_TO_FORMAT:
        return _synthesize_lossless_png(xobj, resources), "png"

    raw_bytes = getattr(xobj, "_data", None)
    if raw_bytes is None:
        raise PdfReadError(
            f"이미지 XObject 스트림에서 원본 바이트(_data)를 찾을 수 없음(비정상 구조): {xobj!r}"
        )
    return bytes(raw_bytes), "unknown"


def _detect_image_format(image_name: str) -> str:
    """``ImageFile.name``의 확장자에서 원본 포맷을 판별한다(인라인 이미지
    전용 경로에서만 쓰인다 -- ``_extract_inline_images`` 참고).

    pypdf는 이미지 스트림을 디코드(압축 해제)할 때 결정한 원본 포맷의
    확장자를 그대로 ``name``에 붙여 반환한다(예: ``"~0~.png"``).
    """
    suffix = Path(image_name).suffix.lstrip(".").lower()
    return _EXTENSION_TO_FORMAT.get(suffix, suffix or "unknown")
