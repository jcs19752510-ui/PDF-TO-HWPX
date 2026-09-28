# 테스트 결과서 (Test Result Report) — unit-2 (v2 + §12, 3차 재작업 재검증)

> v1(FAIL, DEF-001/DEF-002)은 이 문서의 이전 버전이었다. 05단계가 1차
> 재작업(DEF-001/002 해소, `docs/harness/units/unit-2-note.md` §7)과 2차
> 재작업(DEC-028 반영, §9)을 완료한 뒤 이 v2로 전면 갱신한다. v1의 내용은
> git 이력으로 보존되며, 이 문서는 v1을 대체(supersede)한다.
>
> **§12 추가(2026-09-28, 3차 재작업 재검증)**: 07단계가 발견한
> DEF-INT-001(High, 다중 필터 연쇄에서 완결 코덱 오라벨링)에 대한 05단계
> 3차 재작업(`unit-2-note.md` §12)을 이 06단계가 재검증한 결과를 **§12**로
> 추가했다. 1~11절(v2 + recheck2b, DEC-028까지의 상태)은 그 시점 기준으로
> 여전히 유효하며 재작성하지 않는다(이력 보존) — §12만 새로 읽으면 이번
> 재검증의 전체 그림을 파악할 수 있도록 §12 자체를 자기완결적으로 작성했다.

## 1. 개요
- 테스트 대상: `pdf_to_hwpx/pdf_reader/image_extractor.py`의 `extract_image_blocks(pypdf_page)` 함수 (unit-2, Feature A "PDF 판독 계열"), REQ-003
- 테스트 유형: 단위
- 적용 Tier: **Standard** (06·07 병합 없음, 규칙 B 원문 그대로 최소 2회 독립 검증)
- 적용 속도 트랙: **L3(일반)** — 본 결과서 1~10절 전 섹션 정식 작성
- 병렬 실행 정보: **단독 실행**(이번 호출 프롬프트에 "병렬 웨이브" 명시 없음 — 동시에 03-system-designer가 `03-system-design.md` 리비전을 진행 중이었으나 이 unit과 파일이 전혀 겹치지 않음)
- 테스트 목적: 05단계의 1차 재작업(DEF-001/DEF-002 해소, `/Resources/XObject` 직접 순회 + Pillow/필터디코더 완전 우회)과 2차 재작업(DEC-028, FlateDecode류 원시 픽셀 샘플 → 무손실 PNG 합성 + 왕복검증)이 실제로 REQ-003을 만족하는지, 그리고 v1이 발견한 DEF-001/DEF-002가 정말로 해소됐는지를 06단계가 **독립적으로** 재현·검증
- 관련 산출물:
  - `docs/harness/units/unit-2-note.md` §7(1차 재작업)·§9(2차 재작업, DEC-028)·§9-8(갱신된 AC-1)
  - `docs/harness/units/unit-2-test.md` v1(이 문서 이전 버전, FAIL 판정, DEF-001/DEF-002 재현 조건의 출처)
  - `docs/harness/decisions.md` DEC-028(FlateDecode류 원시 픽셀 샘플 → 무손실 PNG 합성 + 왕복검증 확정)
  - `docs/harness/03-system-design.md` §1-3(unit-2 행), §2-1(pypdf 선정 근거), §3-1(`ImageBlockIR` 정의)
  - `pdf_to_hwpx/pdf_reader/ir.py`(`ImageBlockIR`, 참고용, 미수정), `pdf_to_hwpx/pdf_reader/loader.py`(unit-0, 참고용, 미수정)
- 테스트 수행자(에이전트): 06-unit-tester
- 테스트 일시: 2026-09-28 (최초 작성), 2026-09-28 (11절 — API 레이트리밋으로 중단된 세션의 재개·독립 재확인)

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope):
  - `unit-2-note.md` §9-8이 정의한 AC-1(2차 개정, 6개 세부 조건) 전체
  - §7-8/§9-8이 "변경 없음"으로 확정한 AC-2(bbox)~AC-6(안정성/범위) 전체
  - DEF-001/DEF-002 v1 재현 픽스처를 그대로 재사용한 회귀 확인(해소 여부 직접 재현)
  - DEC-028의 지원 범위 표(9-2절: ColorSpace/DeviceCMYK/BitsPerComponent/Decode 조합)에 나열된 **모든** 지원/미지원 조합을 개별 테스트로 커버(v1이 "1차 06단계 결과서 리스크"로 남겼던 JPX/CCITT/JBIG2 개별 미검증 공백도 이번에 해소)
  - 왕복검증(`_verify_png_round_trip_or_raise`)이 실제로 실패를 탐지하는지 화이트박스로 직접 재현(픽셀 불일치/크기 불일치/팔레트 불일치 3종)
  - 내부 헬퍼 `_detect_image_format`의 화이트박스 검증(변경 없음)
  - 위험 입력: 손상된 스트림(기대치 변경 확인), `_data` 속성 자체가 없는 비정상 구조
  - **뮤테이션 검증(신규, 10절 참고)**: 테스트 스위트가 실제로 DEF-001/DEF-002 유형의 회귀를 잡아내는지, 코드를 일부러 되돌려 확인
- 제외 범위 (Out-of-Scope) 및 사유:
  - `/LZWDecode` 전용 케이스 — `_synthesize_lossless_png`는 `xobj.get_data()`(필터 해석은 pypdf 책임)로 원시 픽셀을 얻은 **이후**의 로직(메타데이터 해석/PNG 합성/왕복검증)이 필터 종류와 무관하게 완전히 동일한 코드 경로이므로, FlateDecode/무필터/RunLengthDecode 3종으로 이미 이 공통 로직이 충분히 검증된다고 판단했다. LZW 인코더를 테스트 전용으로 새로 구현하는 비용 대비 한계효용이 낮음(테스트 파일 모듈 docstring에 동일 근거 명시).
  - `ir.py`/`loader.py` 자체 로직 — 공유 계약 파일(수정 없음) 및 unit-0 소관(이미 PASS 완료). `extract_image_blocks`가 이 두 모듈을 수정 없이 import만 하는지는 AC-6-9로 코드 리뷰 검증함(범위 내).
  - 인라인 이미지(BI/ID/EI) 경로의 바이트 동일성 — note §7-4-1/§9-8-6이 명시한 **알려진 한계**(여전히 Pillow 경유, DEF-001/002와 동일 성격의 위험이 남아 있음). 포함 여부(`is_inline` 분기)만 회귀 확인하고, 바이트 동일성은 요구하지 않음(범위 밖으로 명시).
  - unit-7(HWPX 이미지 임베딩)·unit-8(오케스트레이터) — 이 함수의 호출자 책임. 다만 "예외를 삼키지 않고 전파하는가"는 위험 케이스로 확인(범위 내 최소 확인).
  - 실제 한글(한컴오피스) 뷰어에서의 시각적 검증 — unit-5/6/7/8 이후 단계 소관.

## 3. 테스트 환경
- 실행 환경: Windows 11 Pro (10.0.26100), Python 3.13.15
- 격리 실행 환경: `.harness-tmp/venv_06_unit2_recheck2/`(2차 재검증 식별자 포함, 단독 실행이지만 v1의 `venv_06_unit2/`와 구분하기 위해 별도 이름 사용) — `pip install -e ".[dev]"`로 런타임 의존성(pdfplumber/pypdf 6.19.0/lxml/pytesseract/platformdirs/**Pillow 11.3.0**) + `pytest`(9.1.1)를 설치했고, `tests/conftest.py`가 요구하는 `reportlab`(테스트 전용)과 커버리지 측정용 `pytest-cov`를 추가 설치함. 테스트 완료 후 이 venv는 완전히 삭제함(7절 참고).
- 테스트 데이터: `tests/pdf_reader/test_image_extractor.py`를 이번 재검증을 위해 전면 재작성했다(v1의 테스트 파일을 그대로 신뢰하지 않고, note §9-8이 지적한 "AND 조건 논리적 모순" 문제를 반영해 새로 설계 — 아래 4절 근거). `pypdf.PdfWriter` + `pypdf.generic` 저수준 API로 이미지 XObject/콘텐츠 스트림을 직접 구성하는 방식(mock 없음, 실제 PDF 파싱 경로를 전부 통과)은 v1과 동일하게 유지. 생성 위치는 `.harness-tmp/pdf_fixtures_06_unit2_recheck2/`(모듈 스코프 fixture, 테스트 세션 종료 시 자동 삭제).
- 전제 조건 (Preconditions):
  - `pyproject.toml`에 `Pillow>=10.0.0,<12.0`이 이미 반영되어 있음을 재확인(AC-5-7 테스트로 정적 확인, TC-501).
  - 05단계 gate 1(정적 분석/린트)·gate 2(자체 코드 리뷰) 통과 여부는 `unit-2-note.md` §9-5/§9-6에서 확인함 — 프로젝트에 lint/type-check 설정이 없음을 독립적으로 재확인(`ruff`/`flake8`/`mypy`/`pylint`/`.pre-commit-config.yaml` 없음), `python -m py_compile pdf_to_hwpx/pdf_reader/image_extractor.py` 재실행하여 컴파일 성공 재확인함(아래 4절 실행 로그와 함께 수행).

## 4. 테스트 케이스 및 결과

**설계 원칙(v1 대비 변경, 근거)**: v1의 `test_flate_encoded_raster_image_raw_bytes_are_NOT_original_bytes_DEF001`은 "raw_bytes가 압축 스트림과 동일" AND "raw_bytes가 압축 해제된 픽셀과 동일"을 동시에 요구했는데, note §9-8-2/§9-8-7이 지적한 대로 이 두 조건은 이제(PNG 컨테이너로 합성되므로) **논리적으로 동시에 참일 수 없다**. 이번 재검증은 이 문제를 반영해, 원시 픽셀 샘플 계열(FlateDecode 등)은 "PNG로 디코드한 뒤 픽셀이 원본 해석 결과와 일치하는가"로 검증 방식 자체를 교체했다(AC-1-2, DEC-028 근거).

| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-101 | 표시되는 이미지 1개 페이지에서 기본 추출 | 40x30 JPEG(DCTDecode) 페이지 전체 배치 | `extract_image_blocks(page)` | `list[ImageBlockIR]`, 길이 1 | 길이 1, 타입 일치 | PASS | AC-1-1. `test_extract_image_blocks_returns_one_block_for_displayed_image` |
| TC-102 | JPEG 원본 바이트 동일성 | 위와 동일 | `raw_bytes` vs 원본 JPEG 비교 | 바이트 단위 완전 동일 | 동일 | PASS | AC-1-1-2 |
| TC-103 | 그라디언트 JPEG(64x48)도 바이트 동일성 유지 | 그라디언트 JPEG | 동일 절차 | 완전 동일 | 동일 | PASS | AC-1-1-2 보강 |
| TC-104 | **[DEF-002 재검증]** v1이 재현했던 정확히 동일한 10x10 그라디언트 JPEG 픽스처 | def002_jpeg 픽스처(v1과 동일 바이트 생성 로직) | `raw_bytes` vs 원본 비교, 길이까지 확인 | 바이트 단위 완전 동일(REQ-003) | **동일 확인 — DEF-002 해소됨** | **PASS** | `test_dctdecode_jpeg_raw_bytes_no_longer_diverges_DEF002_resolved` — 05단계 1차 재작업(Pillow 완전 우회)이 실제로 해소했음을 06이 독립 재현 |
| TC-105 | 서로 다른 두 이미지가 모두 카운트됨 | 10x10/15x15 단색 JPEG 2장 | `extract_image_blocks(page)` | 길이 2, 각 raw_bytes 원본과 일치 | 길이 2, 둘 다 일치 | PASS | AC-1-1 다중 |
| TC-106 | **완결된 코덱 4종 전부** 유효성 검증 없이 그대로 통과 (파라미터화) | `/DCTDecode`/`/JPXDecode`/`/CCITTFaxDecode`/`/JBIG2Decode`에 임의(비유효) 바이트 | `extract_image_blocks(page)` | raw_bytes==원본, image_format이 각각 jpeg/jp2/ccitt/jbig2 | 4종 전부 일치 | PASS(4/4) | AC-1-1-2 보강 — v1이 "JPX/CCITT/JBIG2 개별 미검증"으로 남긴 리스크 해소. `test_self_contained_codec_filters_pass_through_bytes_unconditionally` |
| TC-107 | 인식 못하는 필터는 `unknown`으로 안전하게 폴백 | 임의 필터명 | `extract_image_blocks(page)` | raw_bytes 그대로, format="unknown" | 일치 | PASS | `test_unrecognized_filter_falls_back_to_unknown_format_and_raw_bytes` |
| TC-108 | `/Filter`가 배열(`[/ASCII85Decode /DCTDecode]`)일 때 마지막 항목으로 포맷 결정 | 필터 배열 | `extract_image_blocks(page)` | format="jpeg", raw_bytes는 여전히 가공 없는 원본(알려진 한계) | 일치 | PASS | 화이트박스, 배열 dereference 분기 커버 |
| TC-109 | `/Filter`가 명시적 PDF `null`인 극희귀 케이스 | `/Filter`=NullObject | `extract_image_blocks(page)` | 예외가 삼켜지지 않고 전파(구체 타입은 보장 안 함) | `NotImplementedError` 전파 확인 | PASS | **잔여 리스크로 8절에 Low 심각도 기록** — AC 범위 밖, 계약 위반 아님(상세 사유는 아래 8절) |
| TC-110 | 인식 못하는 필터 + `_data` 없는 비정상 구조 | 화이트박스(`_raw_bytes_and_format` 직접 호출) | 호출 | `PdfReadError` | 발생 확인 | PASS | 삼키는 except 없음 검증 |
| TC-111 | Form XObject가 섞여 있어도 무시되고 이미지만 추출 | Form + Image XObject 혼재 | `extract_image_blocks(page)` | 길이 1(이미지만) | 길이 1 | PASS | `/Subtype != /Image` 분기 커버 |
| TC-112 | `/Resources` 키 자체가 없는 페이지 | 구조적으로 드문 케이스 | `extract_image_blocks(page)` | 예외 없이 `[]` | `[]` | PASS | `resources is None` 분기 커버 |
| TC-201 | **[DEF-001 재검증, 갱신판]** FlateDecode 원시 픽셀(DeviceRGB 8bpc) → 무손실 PNG 합성 | 4x3 RGB 원시 픽셀 zlib 압축 | `extract_image_blocks(page)` 후 PNG 디코드해 픽셀 비교 | format="png", PNG 시그니처, **디코드 픽셀이 원본 원시 픽셀과 완전 동일**(압축스트림/원시픽셀과의 직접 `==` 비교는 요구하지 않음 — 위 "설계 원칙" 근거) | 전부 일치 — **DEF-001 해소됨** | **PASS** | `test_flate_raster_image_synthesizes_lossless_png_matching_original_pixels` |
| TC-202 | 필터 없음(원시 그대로) 이미지도 동일 경로 | 무필터 RGB8 | 동일 | 픽셀 완전 보존 | 일치 | PASS | |
| TC-203 | RunLengthDecode 인코딩 이미지도 동일 경로 | RLE 인코딩(테스트 전용 인코더, pypdf 디코더와 별도 왕복 검증됨) | 동일 | 픽셀 완전 보존 | 일치 | PASS | 필터 종류 다양성 보강 |
| TC-204 | DeviceGray 1bpc + `/Decode [1 0]`(전체반전) | 2x1, MSB 비트 0/1 | PNG 디코드 후 getpixel | 반전 반영(0↔255) | 일치 | PASS | 9-2절 Decode 반전 지원 검증 |
| TC-205 | 명시적 항등 `/Decode [0 1]`(Gray 8bpc) | 2x1 | 동일 | 픽셀 원본과 동일 | 일치 | PASS | "명시적 항등" 분기(None과 구분) 커버 |
| TC-206 | Indexed 4bpc 팔레트(DeviceRGB base) 보존 | 3엔트리 팔레트, 4bpc 인덱스 | PNG 디코드 후 인덱스/팔레트 확인 | 인덱스·팔레트 완전 보존 | 일치 | PASS | 9-3절 |
| TC-207 | Indexed 명시적 기본 Decode(`[0, 2^bpc-1]`) | 8bpc 인덱스 | 동일 | 정상 처리(반전 없음) | 일치 | PASS | 최초 작성 시 `[0,1]`을 기본값으로 잘못 가정해 FAIL → PDF 스펙(기본값은 `[0, 2^BPC-1]`)에 맞게 즉시 수정, 재실행 PASS(10절 1차 검증에서 자가 발견) |
| TC-208 | Indexed lookup이 (문자열이 아니라) 자체 필터를 가진 별도 스트림 | 압축된 팔레트 스트림 | 동일 | 팔레트 올바르게 해석 | 일치 | PASS | 9-3절 "팔레트가 스트림일 수도" |
| TC-209 | 리소스 이름 간접참조 ColorSpace(`/CS0`) | `resources["/ColorSpace"]["/CS0"]=/DeviceGray` | 동일 | 정상 해석 | 일치 | PASS | |
| TC-210 | `/ICCBased`(N=3) → RGB 취급 | ICC 스트림 `/N=3` | 동일 | RGB로 정상 해석 | 일치 | PASS | |
| TC-211 | Indexed base가 DeviceGray → 팔레트 RGB 확장 | 그레이 팔레트 | 동일 | (g,g,g) 확장 정확 | 일치 | PASS | `_convert_gray_or_rgb_palette_to_rgb` gray 분기 커버 |
| TC-212 | Indexed base가 배열형(`[/CalRGB <<>>]`) | CalRGB 배열 표현 | 동일 | head 이름만으로 인식 | 일치 | PASS | `_base_colorspace_name` 배열 head 인식 분기 커버 |
| TC-301 | DeviceCMYK 원시 픽셀 → 명시적 실패 | FlateDecode + DeviceCMYK | `extract_image_blocks(page)` | `_UnsupportedRawImageEncodingError` | 발생 확인 | PASS | 9-2절 "PNG는 CMYK 표현 불가" |
| TC-302 | Indexed의 base가 DeviceCMYK → 명시적 실패 | Indexed[DeviceCMYK] | 동일 | 동일 예외 | 발생 확인 | PASS | |
| TC-303 | RGB 16bpc(미지원) → 명시적 실패 | RGB, bpc=16 | 동일 | 동일 예외 | 발생 확인 | PASS | |
| TC-304 | 임의 `/Decode [0.2 0.8]`(항등도 반전도 아님) → 명시적 실패 | Gray 8bpc | 동일 | 동일 예외 | 발생 확인 | PASS | |
| TC-305 | Indexed + 사용자정의 Decode → 명시적 실패 | Indexed + `[1 0]` | 동일 | 동일 예외 | 발생 확인 | PASS | |
| TC-306 | `/ColorSpace` 자체가 없음 → 명시적 실패 | 키 생략 | 동일 | 동일 예외 | 발생 확인 | PASS | |
| TC-307 | 리소스에도 없는 이름 참조 ColorSpace → 명시적 실패 | `/CSNotDeclaredAnywhere` | 동일 | 동일 예외 | 발생 확인 | PASS | `_resolve_named_colorspace` 최종 실패 분기 |
| TC-308 | 빈 배열 ColorSpace(`[]`) → 명시적 실패 | 구조적 비정상 | 동일 | 동일 예외 | 발생 확인 | PASS | |
| TC-309 | `/Separation` 등 미지원 계열 → 명시적 실패 | Separation 배열 | 동일 | 동일 예외 | 발생 확인 | PASS | |
| TC-310 | Indexed 배열 길이 이상(4개 아님) → 명시적 실패 | 2개 항목만 | 동일 | 동일 예외 | 발생 확인 | PASS | |
| TC-311 | Indexed 미지원 BitsPerComponent(16) → 명시적 실패 | Indexed bpc=16 | 동일 | 동일 예외 | 발생 확인 | PASS | |
| TC-312 | Indexed 팔레트 lookup 길이가 hival보다 짧음 → 명시적 실패 | 팔레트 3바이트만(9바이트 필요) | 동일 | 동일 예외 | 발생 확인 | PASS | |
| TC-313 | `/Width`/`/Height` 누락 → 명시적 실패 | `/Width` 생략 | 동일 | 동일 예외 | 발생 확인 | PASS | |
| TC-314 | 압축 해제된 픽셀 길이가 W×H×채널과 불일치 → 명시적 실패 | 4x4 RGB인데 1바이트만 | `Image.frombytes` `ValueError` → 재변환 | `_UnsupportedRawImageEncodingError`(원인 체인 보존) | 발생 확인 | PASS | 9-6절 "ValueError 재변환" 분기 |
| TC-315 | (화이트박스, 방어적 이중검증) `_convert_gray_or_rgb_palette_to_rgb`에 채널수 2 강제 주입 | 직접 함수 호출 | 호출 | `_UnsupportedRawImageEncodingError` | 발생 확인 | PASS | 현재 공개 API로는 도달 불가능한 dead code임을 확인하면서, 방어 로직 자체는 실재하고 정상 동작함을 증명(코드 리뷰 보강) |
| TC-401 | **[DEC-028 필수 요건]** 왕복검증 강제 실패 시 예외가 `extract_image_blocks` 밖으로 전파 | `_verify_png_round_trip_or_raise` 몽키패치(항상 실패) | `extract_image_blocks(page)` | `_PngRoundTripVerificationError` | 발생 확인 | PASS | 06이 note의 "몽키패치로 확인했다"를 독립 재구성(지시문 3번 요구사항) |
| TC-402 | 왕복검증 함수 자체가 실제 픽셀 불일치를 탐지 | 실제로 다른 픽셀을 가진 PNG 주입 | `_verify_png_round_trip_or_raise` 직접 호출 | 불일치 시 예외, 일치 시 예외 없음(오탐 아님도 함께 확인) | 둘 다 예상대로 | PASS | 몽키패치가 아니라 실함수 호출 |
| TC-403 | 왕복검증의 크기/모드 불일치 탐지 | 크기가 다른 PNG 주입 | 동일 | 예외 발생 | 발생 확인 | PASS | |
| TC-404 | 왕복검증의 인덱스 팔레트 불일치 탐지 | 팔레트 색이 다른 PNG 주입 | 동일 | 예외 발생 | 발생 확인 | PASS | |
| TC-501 | 인라인 이미지(is_inline) 포함 여부(바이트 동일성은 요구 안 함) | BI/ID/EI 2x2 DeviceGray | `extract_image_blocks(page)` | 길이 1, bbox 폴백 정상 | 일치 | PASS | AC-1-1/AC-3 `is_inline or is_displayed` |
| TC-502 | bbox는 항상 페이지 전체 크기(알려진 근사치, 결함 아님) | 300x150 페이지, 20x20pt에만 배치 | `extract_image_blocks(page)` | `(0,0,300,150)` | 일치 | PASS | AC-2, 변경 없음 재확인 |
| TC-503 | 비정방형 페이지 width/height 순서 | 동일 | bbox 성분별 확인 | x1≈300, y1≈150 | 일치 | PASS | |
| TC-504 | 미표시 리소스 제외 | Do 없음 | `extract_image_blocks(page)` | `[]` | `[]` | PASS | AC-3, 변경 없음 |
| TC-505 | 빈 페이지 | 이미지 없음 | `extract_image_blocks(page)` | 예외 없이 `[]` | `[]` | PASS | AC-4, 변경 없음 |
| TC-506 | Pillow가 매니페스트에 선언됨(정적 확인) | `pyproject.toml` | tomllib 파싱 | Pillow 항목 존재 | 존재 확인 | PASS | AC-5-7 |
| TC-507 | Pillow가 테스트 환경에 실제 설치됨 | 격리 venv | `import PIL` | 성공 | 성공 | PASS | |
| TC-508 | 동일 페이지 반복 호출 시 결과 동일(안정성) | two_images | 2회 호출 비교 | 값 동일, 별개 객체 | 일치 | PASS | AC-6-8 |
| TC-509 | 범위 외 파일 미접촉(코드 리뷰 보강) | 소스 텍스트 검사 | import문/재정의 여부 확인 | 조건 충족 | 충족 | PASS | AC-6-9 |
| TC-510 | 함수 시그니처가 `pypdf_page` 단일 인자만 | `inspect.signature` | 확인 | `["pypdf_page"]` | 일치 | PASS | |
| TC-511 | `_detect_image_format` 정상/대소문자/미등록/경계값(10 서브케이스) | 화이트박스 | 파라미터화 호출 | 각각 jeg/jpeg/…/unknown/unknown | 전부 일치 | PASS(10/10) | 변경 없음 재확인 |
| TC-021갱신 | **[기대치 변경, 회귀 아님]** 손상된 DCTDecode 스트림 | 유효하지 않은 JPEG 바이트 | `extract_image_blocks(page)` | v1: 예외 기대 → **이번: 예외 없이 그대로 통과가 의도된 동작**(note §7-3/§9-8-9 근거) | 예외 없음, raw_bytes==입력 그대로 | PASS | v1의 TC-021을 "예외 발생"에서 "예외 없음"으로 기대치 갱신(구현 결함 아님) |
| TC-999 | `_data` 속성 자체가 없는 비정상 구조 | 화이트박스 | `_raw_bytes_and_format` 직접 호출 | `PdfReadError` | 발생 확인 | PASS | 위험 케이스, 범위 외지만 유지 |

> 정상 경로(TC-101~108, 201~212, 501~511), 경계값(Indexed bpc/hival 경계, 필터 배열, ICCBased N 값 등), 예외 입력(TC-301~314, 401, 021갱신, 999)을 모두 포함했다. 동시성/부하, 권한 경계는 이 함수의 계약(순수 함수, 파일시스템/네트워크 미접근)상 해당 사항 없음.

**집계**: 총 68개 테스트 항목(파라미터화 포함, `test_self_contained_codec_filters_pass_through_bytes_unconditionally` 4종 + `_detect_image_format` 10종 포함) 전부 **PASS** (2회 독립 실행 모두 68/68, 아래 10절 로그 참고). AC-1(2차 개정) 6개 세부 조건, AC-2~AC-6 전부 최소 1개 이상의 테스트 케이스로 커버됨(1:1 이상 추적 가능). DEC-028 9-2절 지원 범위 표의 **모든** 행(지원/미지원 양쪽)이 개별 테스트로 커버됨.

## 5. 커버리지
- 커버리지 지표: `pytest-cov`로 측정, `pdf_to_hwpx/pdf_reader/image_extractor.py` **라인 커버리지 100%**(208/208 statements, `Missing` 없음 — 아래 10절 검증 로그에 원문 첨부).
- 커버되지 않은 부분과 사유: 없음. 다만 100%에 도달하기까지의 경위를 투명하게 밝힌다 — 초기 측정 시 88%(26줄 누락)였고, 이후 목적성 테스트를 추가하며 94%→95%→98%→99%→100%로 단계적으로 끌어올렸다(10절 1차 검증 참고). 마지막까지 남았던 두 줄(`_convert_gray_or_rgb_palette_to_rgb`의 방어적 `else` 분기)은 **현재 호출 그래프상 공개 API로는 도달 불가능한 방어적 이중검증(dead code)**임을 확인했고, 이 사실 자체를 화이트박스 테스트(TC-315)로 명시적으로 증명해 커버리지 수치와 실제 도달 가능성 사이의 괴리를 감추지 않았다. "100% 커버리지 = 결함 없음"이 아니라는 원칙(v1과 동일 기조)에 따라, 9절 뮤테이션 검증으로 이 스위트가 실제로 회귀를 잡아내는지 별도로 증명했다(10절 참고).

## 6. 결함(Defect) 목록
- **결함 없음.** DEF-001/DEF-002는 05단계 재작업으로 해소되었음을 이번 재검증(TC-104, TC-201)이 독립적으로 재현·확인했다.
- 근거: 4절의 68개 테스트 케이스 전부 PASS, 5절의 라인 커버리지 100%, 그리고 아래 뮤테이션 검증(9절 원본은 10절에 기록)에서 스위트가 실제로 회귀를 탐지함을 확인했다 — "실행해보니 통과함"이 아니라 "일부러 되돌려도 실패로 잡아냄"까지 확인했다는 점에서 근거 없는 "이상 없음" 선언이 아니다.
- 06단계 테스트 작성 과정에서 발견되어 **즉시 수정한 테스트 설계 실수**(제품 코드 결함 아님, 10절 1차 검증에 상세 기록):
  1. `test_null_filter_object_is_treated_as_no_filter`: `/Filter`가 PDF `null`로 명시된 경우를 "필터 없음"과 동일하게 성공적으로 처리될 것으로 잘못 가정했다가, 실제로는 pypdf 자신의 `decode_stream_data`가 `NotImplementedError`를 던진다는 것을 발견 — 테스트를 "예외가 삼켜지지 않고 전파되는지"만 확인하도록 수정하고, 이 발견 자체를 8절 잔여 리스크(Low)로 남겼다(TC-109).
  2. `test_flate_indexed_with_explicit_default_decode_array_is_accepted`: 인덱스 컬러의 기본 `/Decode` 값을 `[0, 1]`로 잘못 가정했다가(PDF 스펙상 정답은 `[0, 2^BitsPerComponent-1]`), 코드가 오히려 `_UnsupportedRawImageEncodingError`를 정확하게 던지는 것을 보고 테스트 쪽 가정이 틀렸음을 확인 → `decode=[0, 255]`로 수정(TC-207).
  - 두 건 모두 제품 코드(`image_extractor.py`)의 결함이 아니라 06단계가 테스트를 작성하며 가진 잘못된 사전 가정이었고, 코드가 오히려 스펙대로 정확하게 동작하고 있음을 확인하는 계기가 되었다.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록: `.harness-tmp/venv_06_unit2_recheck2/`(격리 venv), `.harness-tmp/pdf_fixtures_06_unit2_recheck2/`(pytest 모듈 fixture 자동 생성/자동 삭제), `.harness-tmp/image_extractor_backup_for_mutation_check.py`(9절 뮤테이션 검증용 백업), 그리고 v1과 동일하게 `--cov` 실행 시 리포지토리 루트에 재생성된 `.coverage`(규칙 K 위반 재발 — 즉시 삭제 조치, 아래 참고).
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): **[x] 아니오** — v1과 동일한 원인(`pytest-cov` 기본 출력 경로가 현재 작업 디렉터리)으로 `.coverage`가 리포지토리 루트에 재생성됨을 발견했다. 발견 즉시 `rm -f .coverage`로 삭제했다(아래 git status로 부재 확인). 아울러 이번에는 `.pytest_cache/`도 루트에 생성된 것을 확인해 `rm -rf .pytest_cache`로 함께 정리했다(`.pytest_cache/`는 `.gitignore`에 이미 등록돼 있어 git status에는 나타나지 않았으나, 규칙 K 1번의 "venv/임시 DB/임시 설정 파일 등은 `.harness-tmp/` 하위에만" 원칙에 따라 루트에 남기지 않는 것이 안전하다고 판단해 정리했다).
- 정리(삭제) 완료 여부: 완료 — `.harness-tmp/venv_06_unit2_recheck2/`, `.harness-tmp/image_extractor_backup_for_mutation_check.py` 전체 삭제, 리포지토리 루트 `.coverage`/`.pytest_cache` 삭제. `.harness-tmp/pdf_fixtures_06_unit2_recheck2/`는 pytest fixture 자체 teardown으로 자동 삭제됨(`tests/.harness-tmp/`가 빈 디렉터리만 남고 하위 내용 없음을 확인 — 이 빈 부모 디렉터리 자체는 unit-0/unit-1 등 이전 unit들의 테스트가 이미 만들어 둔 공유 관례 디렉터리라 삭제하지 않았다. `.gitignore`의 `.harness-tmp/` 규칙이 경로 깊이와 무관하게 적용되어 git status에도 나타나지 않는다).
- 정리 후 `git status` 실행 결과 (그대로 첨부):
```
On branch PROD
Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   docs/harness/02-planning.md
	modified:   docs/harness/03-system-design.md
	modified:   docs/harness/decisions.md
	modified:   docs/harness/traceability.md
	modified:   docs/harness/verify-log_02-planning.md
	modified:   docs/harness/verify-log_03-system-design.md
	modified:   pdf_to_hwpx/pdf_reader/text_extractor.py
	modified:   pyproject.toml

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	docs/harness/units/unit-1-note.md
	docs/harness/units/unit-1-test.md
	docs/harness/units/unit-2-note.md
	docs/harness/units/unit-2-test.md
	docs/harness/units/unit-3-note.md
	docs/harness/units/unit-3-test.md
	docs/harness/units/unit-4-note.md
	docs/harness/units/unit-4-test.md
	docs/harness/verify-log_unit-2-test.md
	docs/harness/verify-log_unit-4-test.md
	pdf_to_hwpx/hwpx_kernel/schema.py
	pdf_to_hwpx/pdf_reader/image_extractor.py
	pdf_to_hwpx/pdf_reader/table_recognizer.py
	tests/hwpx_kernel/
	tests/pdf_reader/test_table_recognizer.py
	tests/pdf_reader/test_text_extractor.py

no changes added to commit (use "git add" and/or "git commit -a")
```
- 병렬 실행이었다면: **해당 없음(단독 실행)** — 이번 호출은 병렬 웨이브가 아니었다. 다만 위 git status에 보이는 항목 중 이 unit(unit-2) 소유가 아닌 것을 참고용으로 밝힌다: `docs/harness/02-planning.md`/`03-system-design.md`/`decisions.md`/`traceability.md`/`verify-log_02-planning.md`/`verify-log_03-system-design.md`/`pyproject.toml`은 다른 에이전트(03-system-designer 등)의 진행 중인 리비전 산출물이며, `pdf_to_hwpx/pdf_reader/text_extractor.py`/`unit-1-*`/`unit-3-*`/`unit-4-*`/`verify-log_unit-4-test.md`/`pdf_to_hwpx/hwpx_kernel/schema.py`/`pdf_to_hwpx/pdf_reader/table_recognizer.py`/`tests/hwpx_kernel/`/`tests/pdf_reader/test_table_recognizer.py`/`tests/pdf_reader/test_text_extractor.py`는 다른 unit(unit-1/3/4)의 산출물이다. 이 unit이 이번 호출에서 만들거나 수정한 것은 `docs/harness/units/unit-2-test.md`(이 문서), `docs/harness/verify-log_unit-2-test.md`, `tests/pdf_reader/test_image_extractor.py` 뿐이며(`pdf_to_hwpx/pdf_reader/image_extractor.py`는 05단계 산출물, 이번 호출에서 전혀 수정하지 않음 — `diff` 없음을 확인), 이 unit이 만든 임시 아티팩트는 위에서 이미 전부 정리·부재 확인됨.
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음
- 규칙 K 2번(`git status` 깨끗함 확인) 판정: **PASS** — 정리 완료, 이 unit 소유 기준으로 미추적 잔여물 없음.

## 8. 리스크 및 잔존 이슈
- 이번 테스트로 커버되지 않는 알려진 리스크:
  - **[신규 발견, Low 심각도, AC 범위 밖]** `/Filter`가 PDF `null` 키워드로 명시된(키 부재가 아니라) 극희귀 케이스에서, 우리 코드의 필터 분류 로직(`_raw_bytes_and_format`)은 이를 "필터 없음"으로 분류해 `_synthesize_lossless_png` 경로로 보내지만, 그 안에서 호출하는 pypdf 자신의 `xobj.get_data()`는 이 경우를 처리하지 못해 `NotImplementedError`를 던진다(TC-109). 예외가 삼켜지지 않고 전파되므로 모듈의 일반 계약("Raises: pypdf 내부 예외를 그대로 전파")은 위반하지 않지만, `_UnsupportedRawImageEncodingError`로 통일되지 않는 비일관성이 있다. 실무에서 PDF 생성기가 `/Filter null`을 명시하는 사례는 사실상 없어(필터가 없으면 키 자체를 생략하는 것이 표준 관행) 5단계 반려 대상은 아니라고 판단했으나, unit-8(오케스트레이터) 착수 시 참고할 수 있도록 여기 기록한다.
  - 인라인 이미지(BI/ID/EI) 경로는 여전히 Pillow를 경유하며, DEF-001/DEF-002와 동일한 성격의 바이트 불일치 위험이 남아 있다(note §7-4-1, 변경 없음 — 이번 재검증 범위에 포함되지 않음, 5절/2절에 명시).
  - CCITTFaxDecode/JBIG2Decode의 원본 비트스트림은 그 자체로 완결된 "파일"이 아니라는 note §7-4-2의 지적은 이번 unit(REQ-003, 바이트 보존)의 책임 범위를 벗어나며, unit-7(HWPX 이미지 임베딩) 착수 전 인지가 필요하다(변경 없음, 재확인만 함).
  - 필터 배열이 여러 개 연쇄된 드문 경우(`[/ASCII85Decode /DCTDecode]`) raw_bytes가 전송용 필터가 벗겨지지 않은 상태일 수 있다는 note §7-4-3의 한계는 TC-108로 그 동작 자체(마지막 필터로 포맷 결정, raw_bytes는 원본 그대로)를 검증했으나, 이 상태의 데이터를 실제로 사용 가능한 형태로 만드는 것은 이 unit 범위 밖이다(변경 없음).
- 후속 조치가 필요한 항목:
  - unit-7/unit-8은 이제 unit-2의 출력(DCT/JPX/CCITT/JBIG2 완결 코덱 경로 + FlateDecode류 무손실 PNG 합성 경로)을 신뢰하고 착수할 수 있다(v1의 "착수 금지 권고"를 해제).
  - note §9-4가 명시한 "이미지 1개 실패(`_UnsupportedRawImageEncodingError`/`_PngRoundTripVerificationError`)가 현재는 페이지 전체 스킵으로 이어진다"는 알려진 트레이드오프는 unit-8 설계 시 "해당 이미지만 제외 + 이미지 단위 경고"로 세분화하는 것을 권장(변경 없음, note 인계사항 재확인 전달).
  - 위 "Filter null" 잔여 리스크는 심각도가 낮아 즉시 조치가 필요하지 않으나, unit-8이 예외 타입별로 분기 처리를 설계할 때 `NotImplementedError`도 함께 고려 대상에 넣을 것을 권장.

## 9. 결론 및 판정
- [x] **PASS** — 다음 단계 진행 가능(7절 Teardown 확인 완료, 11절 재확인으로 재차 확정).
  - 사유: DEF-001/DEF-002 둘 다 05단계 재작업(1차: Pillow/필터디코더 완전 우회, 2차: DEC-028 무손실 PNG 합성 + 왕복검증)으로 해소되었음을 06단계가 v1과 동일한 재현 픽스처로 **독립적으로 재현·확인**했다(TC-104, TC-201). DEC-028의 지원 범위 표 전 항목(9-2절)을 개별 테스트로 커버했고(TC-206~212 지원, TC-301~314 미지원), 왕복검증이 실제로 실패를 탐지하는 로직을 갖추고 있음을 화이트박스로 증명했다(TC-401~404). 68개 테스트 전부 PASS, 라인 커버리지 100%, 결함 0건.
  - 발견된 잔여 리스크(`/Filter null` 극희귀 케이스, Low 심각도)는 AC 범위 밖이고 실무 발생 가능성이 사실상 없어 PASS 판정을 막지 않되, 8절에 투명하게 기록해 은폐하지 않았다.
- [ ] CONDITIONAL PASS
- [ ] FAIL

## 10. 내부 검증 (최소 2회, `verification-log-template.md` 사용)
- 1차 검증 결과 요약: AC-1(2차 개정) 6개 세부 조건, AC-2~AC-6 전부 테스트 케이스로 1:1 이상 매핑됨을 확인. 테스트 작성 중 자체 발견·수정한 2건(TC-109의 NullObject 가정 오류, TC-207의 인덱스 기본 Decode 값 가정 오류 — 6절에 상세)을 포함해 커버리지를 88%→100%까지 단계적으로 끌어올렸다(누락 분기를 하나씩 찾아 목적성 테스트를 추가하는 방식, 방어적 dead code 1곳은 화이트박스로 별도 증명).
- 2차 검증 결과 요약: "이 테스트를 통과시켜 07로 넘겨도 되는가"를 의심하며 재검토 — 특히 "커버리지 100%가 실제로 회귀를 잡아내는가"라는 v1이 제기한 문제의식을 이어받아, **뮤테이션 검증**을 수행했다(1. 왕복검증 호출 자체를 주석 처리 → `test_png_round_trip_failure_propagates_as_explicit_exception`이 즉시 FAIL로 잡아냄. 2. 완결 코덱 경로를 `xobj._data` 대신 `xobj.get_data()`로 되돌림(DEF-002 유형 회귀 재현) → CCITT/JBIG2 파라미터화 케이스 등 4건이 즉시 FAIL로 잡아냄). 두 뮤테이션 모두 원본으로 정확히 복구한 뒤(`diff` 결과 완전 동일 확인) 최종 2회 독립 실행에서 68/68 PASS를 재확인했다. 이 재검토를 통해 "테스트 스위트가 결함을 놓칠 가능성"을 코드 실행으로 직접 반증(=놓치지 않음을 증명)했다.
- 검증 로그 파일 경로: `docs/harness/verify-log_unit-2-test.md`(v2, 이 재검증 세션 기록 추가)

## 11. 06단계 독립 재확인 (2026-09-28, recheck2b — API 레이트리밋으로 중단된 세션의 재개)

**배경**: 위 1~10절(v2)을 작성한 세션이 7절 Teardown 직전(정확히는 "venv/픽스처 정리 후 최종 git status 확인" 직전)에 API 레이트리밋(세션 한도)으로 중단되었다는 보고를 오케스트레이터로부터 인계받았다. 이 절은 그 뒤를 이어받은 **별도 세션**이, 위 1~10절의 모든 주장(테스트 통과 수, 커버리지, 뮤테이션 검증 결과)을 **처음부터 다시 읽고 신뢰하지 않은 채** 독립적으로 재실행·재현한 기록이다("돌아가는 것 같다"가 아니라 실제로 재현했다는 근거를 남기기 위함).

**0단계 — 중단 잔여물 확인 (규칙 K)**: 재개 직후 `.harness-tmp/`를 확인한 결과 **완전히 비어 있었다**(`ls -la .harness-tmp/` 결과 `.`/`..`만 존재). 즉 v2를 작성한 세션은 실제로는 7절이 기록한 대로 `.harness-tmp/venv_06_unit2_recheck2/` 등을 이미 정리한 뒤, 정리 이후 마지막 `git status` 확인 명령 자체만 실행하지 못하고 중단된 것으로 판단된다. 이 세션이 처리해야 할 이전 세션의 잔여 임시 아티팩트는 없었다.

**1단계 — 산출물 현황 재확인**: `git status`(변경 없음, 인계 시점과 동일), `docs/harness/units/unit-2-note.md` §7~§9(1차/2차 재작업 상세), `docs/harness/verify-log_unit-2-test.md`(v2 검증 로그), `pdf_to_hwpx/pdf_reader/image_extractor.py`(659줄, 재작업 반영본), `tests/pdf_reader/test_image_extractor.py`(1699줄, 68 테스트)를 전체 다시 읽어 위 1~10절의 서술과 실제 코드/테스트 내용이 일치함을 확인했다(허위 기재 없음).

**2단계 — 독립 재실행 (별도 격리 환경, `.harness-tmp/venv_06_unit2_recheck2b/`)**: v2와 겹치지 않는 새 이름으로 격리 venv를 새로 만들어(`python -m venv`) `pip install -e ".[dev]"` + `reportlab` + `pytest-cov`를 설치(pypdf 6.19.0, Pillow 11.3.0, pytest 9.1.1, reportlab 5.0.1 확인)한 뒤:
  - `python -m py_compile pdf_to_hwpx/pdf_reader/image_extractor.py` → 컴파일 성공 재확인.
  - `pytest tests/pdf_reader/test_image_extractor.py -v` → **68 passed**(1회차). 68개 테스트 이름과 4절 표의 TC-ID 대응을 육안으로 대조해 표에 기재된 테스트명과 실제 실행된 테스트명이 정확히 일치함을 확인(허위 테스트명 기재 없음).
  - `pytest tests/pdf_reader/test_image_extractor.py --cov=pdf_to_hwpx.pdf_reader.image_extractor --cov-report=term-missing` → **208/208 statements, 100% (Missing 없음)** — 5절의 커버리지 주장과 정확히 일치.
  - `pytest tests/ -q`(리포지토리 전체) → **257 passed** — unit-1/3/4가 같은 시점에 병행 진행 중이었음에도 unit-2 변경으로 인한 교차 회귀가 없음을 확인(참고용, 이 unit의 판정 범위 밖).
  - `pytest tests/pdf_reader/test_image_extractor.py -q`를 동일 조건으로 **2회 추가 반복 실행**(규칙 B 최소 2회 요건, 10절의 v2 자체 2회와는 별개로 이 세션이 독립적으로 다시 수행) → 두 번 모두 **68 passed**, 결과 안정적(플레이키 없음).

**3단계 — 뮤테이션 검증 독립 재구성 (10절의 주장을 신뢰하지 않고 직접 재현)**: 10절 2차 검증이 보고한 두 뮤테이션을, v2가 쓴 것과 무관하게 이 세션이 직접 새로 작성해 재현했다.
  1. `image_extractor.py`를 `.harness-tmp/image_extractor_backup_06_unit2_recheck2b.py`로 백업한 뒤, 완결 코덱 분기의 `raw_bytes = getattr(xobj, "_data", None)`를 `raw_bytes = xobj.get_data()`로 바꿔 DEF-002 유형 회귀(원본 그대로 반환 대신 pypdf 표준 디코더 경로를 타게 함)를 재현 → `pytest tests/pdf_reader/test_image_extractor.py -q` 실행 결과 **4 failed, 64 passed**(`test_self_contained_codec_filters_pass_through_bytes_unconditionally[/CCITTFaxDecode-ccitt]`, 동일 테스트의 `[/JBIG2Decode-jbig2]` 파라미터, `test_filter_array_last_entry_determines_format_dctdecode_case`, `test_extract_image_blocks_raises_for_structurally_broken_xobject_missing_data`) — 스위트가 실제로 이 회귀를 잡아냄을 확인. (DCTDecode/JPXDecode 파라미터는 이 특정 뮤테이션으로는 실패하지 않았는데, 이는 pypdf의 `decode_stream_data`가 이 두 필터에 대해서는 항등함수이기 때문(모듈 docstring 7-1절 근거)이라 예상된 결과이며, 그 대신 CCITT/JBIG2/필터배열/구조손상 4건에서 실제 회귀 탐지 능력이 증명되었다.)
  2. 백업에서 원본을 복구(`diff` 결과 완전 동일 확인)한 뒤, `_synthesize_lossless_png`의 `_verify_png_round_trip_or_raise(png_bytes, image)` 호출 자체를 주석 처리해 왕복검증 누락을 재현 → 실행 결과 **1 failed, 67 passed**(`test_png_round_trip_failure_propagates_as_explicit_exception`) — 스위트가 이 회귀도 즉시 잡아냄을 확인.
  3. 두 번째 뮤테이션도 백업에서 원본으로 복구한 뒤 `diff`로 완전 동일함을 재확인했고, 이후 `pytest tests/pdf_reader/test_image_extractor.py -q`를 다시 실행해 **68 passed**로 원상 복귀를 재확인했다.
  - 이 3단계는 10절이 "이미 했다"고 보고한 것과 **동일한 결론**(스위트가 두 유형의 회귀를 모두 탐지)에 도달했으나, 이 세션이 직접 새로 작성한 코드로 재현한 것이므로 v2의 주장을 그대로 베낀 것이 아니라 독립적으로 검증한 것이다.

**4단계 — Teardown 재확인 (규칙 K)**: 뮤테이션 검증 중 생성한 `.coverage`가 이번에도 리포지토리 루트에 재생성됨을 확인(v1/v2와 동일한 재발 패턴, `pytest-cov` 기본 동작 — 근본 원인은 알려져 있으나 이 unit 파일 범위 밖이라 `--cov` 실행마다 매번 사후 삭제로 대응) → `rm -f .coverage`, `rm -rf .pytest_cache`로 즉시 삭제. `.harness-tmp/venv_06_unit2_recheck2b/`와 `.harness-tmp/image_extractor_backup_06_unit2_recheck2b.py`를 전부 삭제해 `.harness-tmp/`를 다시 빈 상태로 되돌렸다(`ls -la .harness-tmp/` → `.`/`..`만 존재, 재확인 완료). 최종 `git status`는 아래와 같이 이 세션 진입 시점과 **완전히 동일**함을 확인했다(이 unit이 남긴 미추적 잔여물 없음, `pdf_to_hwpx/pdf_reader/image_extractor.py`는 diff 없음 — 이번 재확인 세션에서 제품 코드를 전혀 수정하지 않았다):
```
On branch PROD
Changes not staged for commit:
	modified:   docs/harness/02-planning.md
	modified:   docs/harness/03-system-design.md
	modified:   docs/harness/decisions.md
	modified:   docs/harness/traceability.md
	modified:   docs/harness/verify-log_02-planning.md
	modified:   docs/harness/verify-log_03-system-design.md
	modified:   pdf_to_hwpx/pdf_reader/text_extractor.py
	modified:   pyproject.toml

Untracked files:
	docs/harness/units/unit-1-note.md
	docs/harness/units/unit-1-test.md
	docs/harness/units/unit-2-note.md
	docs/harness/units/unit-2-test.md
	docs/harness/units/unit-3-note.md
	docs/harness/units/unit-3-test.md
	docs/harness/units/unit-4-note.md
	docs/harness/units/unit-4-test.md
	docs/harness/verify-log_unit-2-test.md
	docs/harness/verify-log_unit-4-test.md
	pdf_to_hwpx/hwpx_kernel/schema.py
	pdf_to_hwpx/pdf_reader/image_extractor.py
	pdf_to_hwpx/pdf_reader/table_recognizer.py
	tests/hwpx_kernel/
	tests/pdf_reader/test_image_extractor.py
	tests/pdf_reader/test_table_recognizer.py
	tests/pdf_reader/test_text_extractor.py
```
(위 목록 중 `docs/harness/02-planning.md`~`pyproject.toml`/`text_extractor.py`/`unit-1/3/4-*`/`hwpx_kernel/schema.py`/`table_recognizer.py`/`tests/hwpx_kernel`/`tests/pdf_reader/test_table_recognizer.py`/`tests/pdf_reader/test_text_extractor.py`는 이 unit-2 재확인 세션이 만든 것이 아니라 동시에 진행 중인 03-system-designer 및 unit-1/3/4 담당 에이전트의 산출물이다 — 이 세션은 `unit-2-test.md`, `verify-log_unit-2-test.md`, `tests/pdf_reader/test_image_extractor.py`, `pdf_to_hwpx/pdf_reader/image_extractor.py`만 열람/실행했고 그중 마지막 둘은 수정하지 않았다.)

**최종 결론(재확정)**: 위 1~10절이 기록한 PASS 판정은 이 독립 재확인 세션이 **처음부터 다시 실행**하여 동일한 결과(68/68 PASS, 커버리지 100%, 뮤테이션 검증에서 회귀 탐지 성공, git status 정리 완료)에 도달했으므로 그대로 유지한다. **PASS — 07단계(통합 테스트) handoff 가능.**

---

## 12. 3차 재작업(2026-09-28) 재검증 — DEF-INT-001(High) 수정 확인

### 12-1. 개요 (템플릿 1절)
- 테스트 대상: `pdf_to_hwpx/pdf_reader/image_extractor.py`의 `extract_image_blocks(pypdf_page)`, 특히 `_raw_bytes_and_format`/`_decode_leading_transport_filters`/`_normalize_filter_names`/`_normalize_decode_parms`(unit-2, Feature A), REQ-003, DEF-INT-001
- 테스트 유형: 단위
- 적용 Tier: **High**(DEC-021, 완화 없음 — 호출 지시문에 명시된 그대로)
- 적용 속도 트랙: **L3(일반)** — 본 §12 전 섹션 정식 작성
- 병렬 실행 정보: **단독 실행**(호출 프롬프트에 "병렬 웨이브" 명시 없음). 단, 동시에 별도 세션에서 Feature B unit-19(`webapp/`)가 진행 중이었음 — 파일 범위가 전혀 겹치지 않아(이 unit은 `pdf_to_hwpx/pdf_reader/`와 `tests/`만 다룸) 상호 영향 없음(아래 12-6절 git status에서 재확인).
- 테스트 목적: 07단계(`docs/harness/feature-A-integration-test.md`)가 실제 파이프라인(monkeypatch 없음)에서 발견한 **DEF-INT-001**(reportlab 기본 산출물 `/Filter [/ASCII85Decode /DCTDecode]`에서 완결 코덱이 잘못 라벨링되어 손상된 이미지가 조용히 최종 `.hwpx`까지 흘러감)에 대한 05단계 3차 재작업(`docs/harness/units/unit-2-note.md` §12)이, AC-1(3차 개정 추가분, §12-8) 1~4번을 실제로 만족하는지 06단계가 **독립적으로** pytest로 재현·검증
- 관련 산출물:
  - `docs/harness/units/unit-2-note.md` §12(3차 재작업, §12-1~§12-9), 특히 §12-8(AC-1 3차 개정 추가분)
  - `docs/harness/feature-A-integration-test.md`(DEF-INT-001 원 발견 리포트, 07 소유)
  - `pdf_to_hwpx/pdf_reader/image_extractor.py`(3차 재작업 반영본, 820줄)
  - `tests/pdf_reader/test_image_extractor.py`(이번 06 재검증에서 갱신)
- 테스트 수행자(에이전트): 06-unit-tester
- 테스트 일시: 2026-09-28

### 12-2. 테스트 범위 및 제외 범위 (템플릿 2절)
- 범위(In-Scope):
  - AC-1(3차 개정 추가분, note §12-8) 1~4번 전체: 완결 코덱 앞에 안전하게 해석 가능한 선행 필터(ASCII85Decode 등)가 있을 때의 디코드 성공, 안전하게 해석 불가능/디코딩 실패 시 `"unknown"` 폴백, 단일 필터 케이스 무변화(회귀), `test_filter_array_last_entry_determines_format_dctdecode_case`의 갱신
  - `_normalize_decode_parms`의 신규 분기(간접참조 `ArrayObject`, 단일 `DictionaryObject`) 화이트박스 커버리지
  - 05단계가 `tests/integration/test_feature_a_pipeline.py`(07 소유, 이번에 수정하지 않음)를 직접 실행해 종단간(end-to-end) 확인한 내용(note §12-7-4)을 06이 **독립적으로 재실행**해 동일 결론(테스트 자신의 회귀가드 assert가 뒤집혀 실패 — 즉 결함이 실제로 고쳐졌음)에 도달하는지 확인
  - 전체 회귀(단일 필터·DEC-028 PNG 합성·bbox·인라인 이미지 등 기존 68개 테스트가 이번 변경 이후에도 그대로 PASS하는지)
  - 뮤테이션 검증(신규): 3차 재작업이 되돌려졌을 때(선행 필터 디코드 로직 제거) 새로 추가한 테스트가 실제로 실패로 잡아내는지 직접 재현
- 제외 범위(Out-of-Scope) 및 사유:
  - `tests/integration/test_feature_a_pipeline.py`(07 소유, 호출 지시문이 명시적으로 수정 금지) — 이 테스트를 실행해 상태만 확인하고(12-5절), 파일 자체는 손대지 않았다. DEF-INT-001을 Closed로 전환하는 것은 07 책임(note §12-9-3).
  - `/DeviceCMYK`, 미지원 BitsPerComponent 등 DEC-028 지원 범위(9-2절) 관련 케이스 — 1~11절(v2)에서 이미 전 항목 검증 완료, 이번 3차 재작업이 그 경로를 건드리지 않았음을 코드 리뷰로 확인(note §12-3 "단일 필터/DEC-028 경로는 변경 없음")했으므로 재실행만 하고(전체 회귀) 신규 케이스를 추가하지 않았다.
  - 인라인 이미지(BI/ID/EI) 경로 — 3차 재작업이 건드리지 않음(note §12-6, `_extract_inline_images` 변경 없음), 기존 알려진 한계 그대로 유지.
  - `unit-7`(`image_embedder.py`)/`unit-4`(`container.py`)가 포맷 이름이 아니라 매직넘버까지 검증하는 2중 방어 계층 — note §12-9-4가 "지금 당장 필수는 아님"으로 판단한 항목이며, 이 unit(파일 범위: `image_extractor.py`)의 책임 밖이라 검증 대상에서 제외.

### 12-3. 05단계 게이트 확인 (필수 원칙 — 05의 린트/코드리뷰 게이트 통과 여부)
- `unit-2-note.md` §12-5(게이트 1)/§12-6(게이트 2)에서 확인함: 프로젝트에 lint/type-check 설정이 없음(재확인 완료), `python -m py_compile pdf_to_hwpx/pdf_reader/image_extractor.py` 컴파일 성공, 자체 코드 리뷰 체크리스트 6개 항목 전부 `[x]`로 근거와 함께 기재됨(범위 외 변경 없음 포함). 06이 독립적으로도 컴파일을 재확인했다(아래 12-5절).

### 12-4. 테스트 환경 (템플릿 3절)
- 실행 환경: Windows 11 Pro (10.0.26100), Python 3.13.15
- 이 세션의 로컬 전역(global) Python 환경에 이미 `pypdf` 6.19.0/`Pillow` 12.3.0/`pytest` 9.1.1/`reportlab` 5.0.1/`lxml` 6.1.3/`pdfplumber`가 설치되어 있음을 확인(`pip show` 대신 `import`+`__version__` 직접 확인)했다 — 이 환경으로 우선 신규/전체 테스트를 반복 실행했다. 커버리지 측정(`pytest-cov`)만 전역에 없어, 격리 venv `.harness-tmp/venv_06_unit2_rework3/`를 `python -m venv --system-site-packages`로 만들어(이미 설치된 런타임 의존성을 재설치하지 않고 재사용, `pytest-cov`만 추가 설치) 커버리지 측정과 최종 반복 실행에 사용했다.
- 테스트 데이터: 기존 `pdf_fixtures`(모듈 스코프 fixture, `.harness-tmp/pdf_fixtures_06_unit2_recheck2/`, 변경 없음)에 더해, 이번 재검증 전용으로 즉석 생성되는 PDF(모듈 레벨 `FIXTURE_DIR`, 개별 테스트가 생성 직후 `finally`에서 즉시 삭제)를 `_add_multi_filter_image_xobject` 신규 헬퍼로 만들었다(mock 없음, `PdfWriter`+`pypdf.generic` 저수준 API로 실제 PDF 파싱 경로를 전부 통과).
- 전제 조건: 05단계 게이트 1·2 통과(12-3절), `image_extractor.py`가 이 세션 진입 시점에 이미 3차 재작업 반영본(820줄)임을 `sha256sum`으로 재작업 전후 동일성 확인에 사용(12-7절 뮤테이션 검증 참고).

### 12-5. 테스트 케이스 및 결과 (템플릿 4절)

| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-601 | **[DEF-INT-001 핵심 재현/해소 확인]** 유효한 ASCII85로 인코딩된 실제 JPEG를 `[/ASCII85Decode /DCTDecode]`로 감싼 이미지 | 20x15 JPEG를 `base64.a85encode(..., adobe=True)`로 인코딩 | `extract_image_blocks(page)` | `image_format=="jpeg"`, `raw_bytes`가 ASCII85 디코드 후 원본 JPEG와 바이트 단위 완전 동일, `PIL.Image.open(...).load()` 예외 없이 성공 | 전부 일치 — **DEF-INT-001 해소됨** | **PASS** | AC-1(3차 개정 추가분) 1번. `test_leading_ascii85_filter_before_dctdecode_decodes_to_original_jpeg_bytes_DEF_INT_001_resolved` |
| TC-602 | 완결 코덱 앞에 안전하게 해석 불가능한 필터(`/Crypt`, `_LEADING_FILTER_DECODERS`에 없음) | 임의 바이트 | `extract_image_blocks(page)` | `image_format=="unknown"`(완결 코덱으로 잘못 라벨링되지 않음), `raw_bytes`는 원본 그대로 | 일치 | PASS | AC-1(3차 개정 추가분) 2번(파라미터화 1/2) |
| TC-603 | 선언은 `/ASCII85Decode`지만 실제로 유효하지 않은 페이로드(디코딩 자체가 실패) | 손상된 바이트 | `extract_image_blocks(page)` | `image_format=="unknown"`(예외로 죽지 않고 안전 경로로 빠짐) | 일치 | PASS | AC-1(3차 개정 추가분) 2번(파라미터화 2/2). `test_leading_unsafe_or_undecodable_filter_before_dctdecode_falls_back_to_unknown_format` |
| TC-604 | 단일 필터(배열 아님) DCTDecode 케이스 무변화 확인(회귀) | `single_jpeg` 기존 픽스처 | `extract_image_blocks(page)` | `image_format=="jpeg"`, `raw_bytes`가 원본과 완전 동일(3차 재작업 이전과 동일한 결과) | 일치 | PASS | AC-1(3차 개정 추가분) 3번. `test_single_filter_dctdecode_unaffected_by_leading_filter_handling_no_regression` |
| TC-605 | `/DecodeParms`가 간접참조(`IndirectObject`)된 `ArrayObject`(`_normalize_decode_parms` 신규 분기 화이트박스) | FlateDecode로 압축한 JPEG, `[/FlateDecode /DCTDecode]` | `extract_image_blocks(page)` | `image_format=="jpeg"`, `raw_bytes`==원본 JPEG(FlateDecode가 정상 해제됨) | 일치 | PASS | 커버리지 보강(710/712줄). `test_leading_flatedecode_filter_before_dctdecode_with_array_decodeparms_is_decoded` |
| TC-606 | `/DecodeParms`가 배열이 아닌 단일 `DictionaryObject`(`_normalize_decode_parms`의 else 분기) | 동일 | `extract_image_blocks(page)` | 동일 | 일치 | PASS | 커버리지 보강(716줄). `test_leading_flatedecode_filter_before_dctdecode_with_single_dict_decodeparms_is_decoded` |
| TC-607 | **[기존 06 테스트 교체, 결함 아님]** `test_filter_array_last_entry_determines_format_dctdecode_case`(2차 재작업 이전의 버그 있던 동작을 "화이트박스 커버리지" 명목으로 고정하던 테스트) | 임의(비유효) ASCII85-wrapped 바이트 | 삭제 후 TC-601/602/603/604로 대체 | note §12-4/§12-8-4가 요청한 대로, 이 옛 기대치(전송필터가 안 벗겨진 채 "jpeg"로 라벨링)를 검증하는 테스트를 **제거**하고 새 AC에 맞는 테스트로 교체 | 교체 완료, 옛 기대치를 검증하는 코드가 스위트에 더 이상 존재하지 않음(코드 리뷰로 확인) | PASS(교체 완료로 판정) | 05가 예측한 "의도적 실패"를 06이 직접 재현하지 않고(옛 코드를 남겨뒀다면 실패했을 것이 자명 — 로직 변경 없음, 12-1절 근본원인 분석과 동일 근거), 곧바로 새 AC에 맞는 테스트로 교체하는 쪽을 택함(제거된 테스트의 회귀 탐지 능력은 12-7절 뮤테이션 검증으로 별도 증명) |
| TC-608 | 전체 회귀(기존 68개, 1개 교체) | 변경 없음 | `pytest tests/pdf_reader/test_image_extractor.py -q` | 71~73 passed(68 - 1 교체 + 6 신규) | **73 passed**(3회 독립 반복 모두 동일) | PASS | 12-5-실행로그 참고 |
| TC-609 | **[07단계 종단간 확인 재현]** `test_reportlab_generated_jpeg_is_silently_corrupted_in_final_hwpx_DEF_INT_001`(07 소유, 수정하지 않음)을 그대로 재실행 | orchestrator→unit-2→unit-7→unit-4 실제 파이프라인(mock 없음) | `pytest tests/integration/test_feature_a_pipeline.py -q` | 이 테스트 자신의 회귀가드 assert(`is_valid_image is False`)가 **뒤집혀 실패**해야 함(=BinData 이미지가 이제 유효 = DEF-INT-001 해소, note §12-7-4가 예측한 그대로) | **정확히 예측대로 실패**(`assert True is False`, 즉 `is_valid_image`가 `True`로 나옴). TC-INT-002/004는 그대로 PASS 유지 | PASS(이 실패가 곧 해소 증거) | 이 테스트를 PASS로 뒤집는 것은 07의 책임(note §12-9-3), 06은 "예측된 실패"가 실제로 재현되는지만 독립 확인 |
| TC-610 | **[뮤테이션 검증]** 선행 필터 디코드 로직(3차 재작업의 핵심)을 되돌렸을 때 TC-601~603/605/606이 실제로 실패로 잡아내는가 | `image_extractor.py` 백업 후 해당 분기를 "선행 필터 무시, `_data` 그대로 반환"으로 되돌림 | `pytest tests/pdf_reader/test_image_extractor.py -q` | 새로 추가한 5개 테스트가 즉시 FAIL | **5 failed**(TC-601/602/603x2/TC-605/TC-606), 나머지 68 passed. 원본 복구 후 `sha256sum` 완전 동일 확인, 재실행 73 passed | PASS | 아래 12-7절 상세 |

> 정상 경로(TC-601, TC-604~606), 경계값/예외입력(TC-602/603, "안전하게 해석 불가능"/"디코딩 실패" 두 하위 유형), 회귀(TC-604, TC-608), 종단간(TC-609), 뮤테이션(TC-610)을 모두 포함했다. 동시성/부하, 권한 경계는 이 함수의 계약(순수 함수, 파일시스템/네트워크 미접근)상 해당 사항 없음(1~11절과 동일 결론).

**실행 로그(원문)**:
```
$ python -m pytest tests/pdf_reader/test_image_extractor.py -q
........................................................................ [ 98%]
.                                                                        [100%]
73 passed in 1.36s / 0.99s / 1.01s (3회 독립 반복, 모두 동일)

$ python -m pytest tests/pdf_reader tests/hwpx_writer tests/hwpx_kernel -q
........................................................................ [ 21%]
........................................................................ [ 43%]
........................................................................ [ 65%]
........................................................................ [ 87%]
........................................                                 [100%]
328 passed in 3.24s

$ python -m pytest tests/ -q  (리포지토리 전체, webapp/unit-19 동시 진행 중)
1 failed, 455 passed in 25.71s
  FAILED tests/integration/test_feature_a_pipeline.py::test_reportlab_generated_jpeg_is_silently_corrupted_in_final_hwpx_DEF_INT_001
  (TC-609, 예측된 의도적 실패 — 07 소유, 이번에 수정하지 않음)
```

**집계**: `tests/pdf_reader/test_image_extractor.py` 신규 73개 테스트(기존 68 - 옛 테스트 1개 제거 + 신규 6개) 전부 PASS(3회 독립 반복). AC-1(3차 개정 추가분) 1~4번 전부 테스트 케이스로 1:1 이상 추적 가능. 리포지토리 전체 테스트(`tests/`) 455 passed, 07 소유의 의도된 1건 실패(TC-609, 해소 증거) 외 회귀 없음.

### 12-6. 테스트 환경 정리(Teardown) 확인 — 규칙 K (템플릿 7절)
- 이번 재검증에서 생성한 임시 아티팩트 목록: `.harness-tmp/venv_06_unit2_rework3/`(격리 venv, `--system-site-packages`), `.harness-tmp/scratch_06_unit2_verify/`(probe.py/probe2.py 및 생성된 PDF, 사전 검증용), `.harness-tmp/image_extractor_backup_06_unit2_rework3.py`(12-7절 뮤테이션 검증용 백업), 리포지토리 루트에 재생성된 `.coverage`/`.pytest_cache`(pytest-cov 기본 동작, v1/v2/recheck2b와 동일한 재발 패턴).
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): **[x] 아니오** — 이번에도 `.coverage`/`.pytest_cache`가 리포지토리 루트에 생성됨(1~11절과 동일한 pytest-cov 기본 경로 문제, 이 unit의 파일 범위 밖이라 근본 수정은 하지 않고 매번 사후 삭제로 대응). 발견 즉시 `rm -f .coverage`, `rm -rf .pytest_cache`로 삭제.
- 정리(삭제) 완료 여부: 완료 — `.harness-tmp/venv_06_unit2_rework3/`, `.harness-tmp/scratch_06_unit2_verify/`, `.harness-tmp/image_extractor_backup_06_unit2_rework3.py` 전부 삭제, 루트 `.coverage`/`.pytest_cache` 삭제. 삭제 후 `.harness-tmp/`를 재확인한 결과 이 세션이 만든 항목은 없고, 동시 진행 중인 unit-19(webapp) 세션이 만든 `venv_05_unit19/`, `.gitignore`/`CACHEDIR.TAG`/`README.md`/`v` 등만 남아 있음(이 unit 소유 아님, 건드리지 않음).
- 정리 후 `git status` 실행 결과 (그대로 첨부):
```
On branch PROD
Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   .gitignore
	modified:   docs/harness/traceability.md
	modified:   docs/harness/units/unit-2-note.md
	modified:   docs/harness/units/unit-2-test.md
	modified:   tests/pdf_reader/test_image_extractor.py

Untracked files:
	webapp/

no changes added to commit (use "git add" and/or "git commit -a")
```
- 병렬 실행이었다면(참고용 — 이번 호출 자체는 단독 실행이나, 동시에 Feature B unit-19가 별도 세션에서 진행 중이었음을 프롬프트가 명시): 위 목록 중 `.gitignore`(webapp 관련 ignore 추가)와 `webapp/`(신규 디렉터리)는 이 unit-2 세션이 만든 것이 아니라 unit-19 세션의 산출물이다(`git diff -- .gitignore`로 webapp 관련 3줄 추가만 확인, image_extractor.py/이 unit 소유 파일과 무관함을 확인). 이 세션이 실제로 수정한 파일은 `tests/pdf_reader/test_image_extractor.py`(신규 6개 테스트 추가+1개 교체), `docs/harness/units/unit-2-test.md`(이 문서, §12), `docs/harness/traceability.md`(REQ-003 단위테스트 컬럼)뿐이며, `pdf_to_hwpx/pdf_reader/image_extractor.py`는 12-7절 뮤테이션 검증 중 일시적으로 수정했다가 `sha256sum`으로 완전 동일함을 확인하며 원상 복구했다(diff 없음, 아래 12-7절).
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음
- 규칙 K 2번(`git status` 깨끗함 확인) 판정: **PASS** — 이 unit 소유 기준으로 미추적 잔여물 없음(정리 완료).

### 12-7. 뮤테이션 검증 상세 (TC-610, 규칙: "테스트가 실제로 회귀를 잡아내는가")
1. `pdf_to_hwpx/pdf_reader/image_extractor.py`를 `.harness-tmp/image_extractor_backup_06_unit2_rework3.py`로 백업.
2. `_raw_bytes_and_format`의 완결 코덱 분기에서 "선행 필터를 실제로 디코드하는" 로직 전체(leading_filter_names 처리, `_decode_leading_transport_filters` 호출)를 제거하고, 3차 재작업 **이전**과 동일하게 `_data`를 무조건 그대로 반환하도록 되돌림(DEF-INT-001 재현).
3. `pytest tests/pdf_reader/test_image_extractor.py -q` 실행 → **5 failed, 68 passed**:
   - `test_leading_ascii85_filter_before_dctdecode_decodes_to_original_jpeg_bytes_DEF_INT_001_resolved`(TC-601)
   - `test_leading_unsafe_or_undecodable_filter_before_dctdecode_falls_back_to_unknown_format[unrecognized_leading_filter-...]`(TC-602)
   - `test_leading_unsafe_or_undecodable_filter_before_dctdecode_falls_back_to_unknown_format[undecodable_ascii85_payload-...]`(TC-603)
   - `test_leading_flatedecode_filter_before_dctdecode_with_array_decodeparms_is_decoded`(TC-605)
   - `test_leading_flatedecode_filter_before_dctdecode_with_single_dict_decodeparms_is_decoded`(TC-606)
   - 나머지 68개(기존 회귀 스위트 + TC-604 단일 필터)는 전부 PASS 유지 — 즉 이번에 추가한 뮤테이션이 단일 필터 경로에는 영향을 주지 않는다는 것도 함께 확인됨(격리성 재확인).
4. 원본을 복구한 뒤 `sha256sum image_extractor.py .harness-tmp/image_extractor_backup_06_unit2_rework3.py`로 **완전히 동일한 해시**임을 확인(바이트 단위 원상 복구 증명, diff 도구가 아니라 해시로 증명해 더 엄격하게 확인).
5. 복구 후 `pytest tests/pdf_reader/test_image_extractor.py -q` 재실행 → **73 passed**로 원상 복귀 재확인.
6. 결론: 이번에 추가한 5개 테스트(TC-601/602/603/605/606)가 DEF-INT-001 유형의 회귀를 **정확히, 그리고 격리되어(다른 케이스를 오염시키지 않고)** 탐지함을 직접 반증했다 — "테스트를 통과했다"가 아니라 "일부러 결함을 되돌려도 잡아낸다"까지 증명.

### 12-8. 리스크 및 잔존 이슈 (템플릿 8절)
- 새로 발견된 리스크: 없음. 기존(1~11절) 리스크는 이번 3차 재작업 범위 밖이라 변경 없이 유지된다 — 인라인 이미지 잔존 위험(note §12-6 "인라인 이미지 경로는 이번에도 손대지 않음" 재확인), CCITT/JBIG2 원본 비트스트림이 그 자체로 완결 파일이 아니라는 한계, `_LEADING_FILTER_DECODERS`에 없는 필터가 완결 코덱 앞에 오면 여전히 이미지가 통째로 제외된다는 알려진 트레이드오프(note §12-6 "남은 한계").
- 후속 조치가 필요한 항목:
  - **최우선**: 07단계가 `tests/integration/test_feature_a_pipeline.py::test_reportlab_generated_jpeg_is_silently_corrupted_in_final_hwpx_DEF_INT_001`을 공식적으로 뒤집어(assert를 `is_valid_image is True`로) DEF-INT-001을 Closed로 전환해야 한다(이 06은 예측된 실패를 재현만 했을 뿐 파일을 수정하지 않음, note §12-9-3/07 소유).
  - unit-2-note.md §12-7-5가 지적한 07 테스트 docstring과 실제 데코레이터(`xfail` 누락) 간 불일치는 07이 재실행 시 함께 바로잡는 것을 권장(정보 전달, 이번 06 반려 사유 아님).
  - unit-7/unit-4의 매직넘버 검증 2중 방어(note §12-9-4)는 "지금 당장 필수는 아님"이라는 05의 판단에 06도 동의한다(근본 원인이 unit-2에 있었고 이번에 해소됨) — 다만 오케스트레이터가 이견이 있다면 별도 작업 단위로 검토 요청.

### 12-9. 결론 및 판정 (템플릿 9절)
- [x] **PASS** — 다음 단계(07단계 재실행) 진행 가능(12-6절 Teardown 확인 완료가 전제조건, 충족).
  - 사유: AC-1(3차 개정 추가분) 1~4번 전부 테스트로 검증되어 PASS(TC-601~607). 전체 회귀 68→73개 테스트 전부 PASS(3회 독립 반복, TC-608). 07이 발견한 종단간 증거(TC-609)가 예측대로 재현되어 DEF-INT-001이 실제 파이프라인에서도 해소되었음을 간접 확인. 뮤테이션 검증(TC-610)으로 신규 테스트가 실제로 이 결함 유형을 탐지함을 증명. 결함 0건.
  - 라인 커버리지: `pdf_to_hwpx/pdf_reader/image_extractor.py` **100%**(244/244 statements, `Missing` 없음 — 3차 재작업으로 208→244 statements로 늘어난 것 포함 전부 커버). 초기 측정 시 99%(3줄 누락, `_normalize_decode_parms`의 간접참조/ArrayObject/else 분기)였고, TC-605/606을 추가해 100%로 끌어올렸다(88%→100%로 단계적으로 올렸던 1~11절과 같은 방식 — 도달 경위를 감추지 않음).
- [ ] CONDITIONAL PASS
- [ ] FAIL

### 12-10. 내부 검증 (최소 2회, 템플릿 10절)
- 1차 검증(작성자 관점): AC-1(3차 개정 추가분) 1~4번이 TC-601~607로 1:1 이상 매핑됨을 확인. `_normalize_decode_parms`의 신규 분기(간접참조/ArrayObject/else)가 처음에는 커버리지 99%로 누락돼 있었음을 발견해 TC-605/606을 추가로 설계·실행해 100%로 채웠다(누락을 발견하고 고친 과정 자체를 감추지 않음).
- 2차 검증(독립 심사자 관점, "이 테스트가 결함을 놓쳤을 가능성을 재검토"): 커버리지 100%가 "실제로 회귀를 잡아내는가"라는 이 unit의 반복된 원칙(1~11절과 동일 기조)에 따라 12-7절 뮤테이션 검증을 수행 — 3차 재작업의 핵심 로직(선행 필터 디코드)을 되돌렸을 때 정확히 5개 신규 테스트만 실패하고 나머지 68개는 영향받지 않음을 확인해, "테스트가 이 결함 유형을 격리되어 정확히 탐지한다"를 코드 실행으로 직접 반증했다. 추가로 "혹시 옛 테스트(`test_filter_array_last_entry_determines_format_dctdecode_case`)를 제거만 하고 대체 검증이 부실한 것 아닌가"를 의심해 재검토한 결과, 제거된 테스트가 커버하던 "필터 배열의 ArrayObject 처리 분기" 자체는 TC-601~603이 더 엄밀한 조건(실제 유효 데이터 왕복, 실패 유형 2가지 분리)으로 대체했음을 코드 대조로 확인했다 — 커버리지 손실 없음.
- 검증 로그 파일 경로: `docs/harness/verify-log_unit-2-test.md`(§4, 이번 재검증 세션 기록 추가)

**최종 결론(§12 요약)**: DEF-INT-001(High)은 05단계 3차 재작업으로 해소되었으며, 06단계가 이를 신규 pytest 케이스(TC-601~607)와 뮤테이션 검증(TC-610)으로 독립적으로 재현·확인했다. **PASS — 07단계(통합 테스트) 재실행 가능.**
