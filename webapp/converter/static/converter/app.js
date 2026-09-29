/**
 * converter 앱 프런트엔드 (04-ux-design.md §1-2/§1-3/§2, unit-20).
 *
 * 단일 페이지 안의 4개 패널(A 업로드/B 진행/C 결과/D 조회불가)을 전환하며,
 * 서버와는 POST /convert, GET /api/jobs/<job_id>/, GET /download/<job_id>/
 * 세 엔드포인트로만 통신한다(03 §4-4). 다운로드는 반드시 fetch+blob 방식이며
 * 직접 URL 이동을 쓰지 않는다(04 §1-3 필수 요구사항).
 */
(function () {
  "use strict";

  var MAX_UPLOAD_MB = JSON.parse(document.getElementById("max-upload-mb").textContent);
  var SOFT_TIMEOUT_MS =
    JSON.parse(document.getElementById("soft-timeout-seconds").textContent) * 1000;
  var POLL_INTERVAL_MS = 750; // 04 §1-2: 0.5~1초 간격
  var SLOW_RESPONSE_MS = 5000; // 04 §1-2/§2 Panel A/B: 5초 초과 시 콜드스타트/지연 안내
  var MAX_POLL_RETRIES = 3; // 04 §6-3: 폴링 실패 시 지수 백오프 최대 3회

  var panels = {
    a: document.getElementById("panel-a"),
    b: document.getElementById("panel-b"),
    c: document.getElementById("panel-c"),
    d: document.getElementById("panel-d"),
  };

  var els = {
    form: document.getElementById("upload-form"),
    fileInput: document.getElementById("file-input"),
    fileInfo: document.getElementById("file-info"),
    fileSizeError: document.getElementById("file-size-error"),
    enableOcr: document.getElementById("enable-ocr"),
    ocrLangGroup: document.getElementById("ocr-lang-group"),
    ocrLangKor: document.getElementById("ocr-lang-kor"),
    ocrLangEng: document.getElementById("ocr-lang-eng"),
    ocrLangError: document.getElementById("ocr-lang-error"),
    submitButton: document.getElementById("submit-button"),
    submitStatus: document.getElementById("submit-status"),
    panelAError: document.getElementById("panel-a-error"),

    progressFilename: document.getElementById("progress-filename"),
    progressStageLabel: document.getElementById("progress-stage-label"),
    progressBar: document.getElementById("progress-bar"),
    progressPageCounter: document.getElementById("progress-page-counter"),
    progressElapsed: document.getElementById("progress-elapsed"),
    progressSlowResponse: document.getElementById("progress-slow-response"),
    progressTimeoutBanner: document.getElementById("progress-timeout-banner"),
    progressOfflineBanner: document.getElementById("progress-offline-banner"),

    resultBadge: document.getElementById("result-badge"),
    resultIssueList: document.getElementById("result-issue-list"),
    downloadButton: document.getElementById("download-button"),
    downloadError: document.getElementById("download-error"),
    retryButton: document.getElementById("retry-button"),

    newUploadButton: document.getElementById("new-upload-button"),
  };

  var state = {
    jobId: null,
    submittedAt: null,
    pollTimer: null,
    elapsedTimer: null,
    pollFailureCount: 0,
  };

  // ---- 단계 라벨(03 §4-1 ProgressEvent.stage, 04 §2 Panel B) ----
  var STAGE_LABELS = {
    loading: "PDF 읽는 중",
    extracting: "내용 추출 중",
    building: "HWPX 작성 중",
    saving: "저장 중",
    done: "완료",
  };

  // ---- 경고 코드 접두사 -> 아이콘(04 §2 Panel C, v2 계승) ----
  var WARNING_ICON_PREFIXES = [
    ["TABLE_", "▦"],
    ["TOUNICODE_", "🔤"],
    ["FORMULA_", "∑"],
    ["PAGE_SKIPPED", "⚠"],
    ["LARGE_FILE_SLOW", "⏱"],
  ];

  // ---- result_errors 코드 -> 사용자 메시지(04 §2 Panel C 재해석 표) ----
  var ERROR_MESSAGES = {
    EncryptedPdfError:
      "비밀번호로 보호된 PDF는 지원하지 않습니다. 암호를 해제한 뒤 다시 업로드해주세요.",
    CorruptedPdfError: "PDF 파일을 읽을 수 없습니다. 파일이 손상되었을 수 있습니다.",
    EmptyPdfError: "빈 PDF 파일입니다(0페이지).",
    OutputPathError: "서버 처리 중 문제가 발생했습니다. 다시 시도해주세요.",
    ContainerBuildError: "HWPX 파일 생성 중 문제가 발생했습니다. 다시 시도해주세요.",
    TesseractNotFoundError:
      "OCR 처리 중 서버에 문제가 발생했습니다. OCR을 끄고 다시 시도하시거나 잠시 후 다시 시도해주세요.",
    INTERNAL_ERROR:
      "예상치 못한 문제가 발생했습니다. 같은 문제가 계속되면 GitHub Issue로 알려주세요.",
  };

  function iconFor(code) {
    for (var i = 0; i < WARNING_ICON_PREFIXES.length; i++) {
      if (code && code.indexOf(WARNING_ICON_PREFIXES[i][0]) === 0) {
        return WARNING_ICON_PREFIXES[i][1];
      }
    }
    return "ℹ"; // info 기본 아이콘
  }

  function messageFor(code, fallbackDetail) {
    return ERROR_MESSAGES[code] || fallbackDetail || "알 수 없는 문제가 발생했습니다.";
  }

  function showPanel(name) {
    Object.keys(panels).forEach(function (key) {
      panels[key].classList.toggle("is-active", key === name);
    });
    var heading = panels[name].querySelector("h1");
    if (heading) {
      heading.focus();
    }
  }

  function formatBytes(bytes) {
    return (bytes / (1024 * 1024)).toFixed(1) + "MB";
  }

  // ---- Panel A: 파일 선택/유효성 ----

  function selectedFileValidSize() {
    var file = els.fileInput.files[0];
    if (!file) return false;
    return file.size <= MAX_UPLOAD_MB * 1024 * 1024;
  }

  function ocrSelectionValid() {
    if (!els.enableOcr.checked) return true;
    return els.ocrLangKor.checked || els.ocrLangEng.checked;
  }

  function updateSubmitButtonState() {
    var file = els.fileInput.files[0];
    var hasFile = !!file;
    var sizeOk = !hasFile || selectedFileValidSize();
    var ocrOk = ocrSelectionValid();
    els.submitButton.disabled = !(hasFile && sizeOk && ocrOk);
  }

  els.fileInput.addEventListener("change", function () {
    var file = els.fileInput.files[0];
    if (!file) {
      els.fileInfo.hidden = true;
      els.fileSizeError.hidden = true;
      updateSubmitButtonState();
      return;
    }
    els.fileInfo.hidden = false;
    els.fileInfo.textContent = file.name + " (" + formatBytes(file.size) + ")";

    if (!selectedFileValidSize()) {
      els.fileSizeError.hidden = false;
      els.fileSizeError.textContent =
        "파일이 너무 큽니다(선택한 파일: " +
        formatBytes(file.size) +
        ", 최대 " +
        MAX_UPLOAD_MB +
        "MB)";
    } else {
      els.fileSizeError.hidden = true;
    }

    // DEC-036/04 §1-3: 원본 파일명은 서버 전송 전에 클라이언트가 먼저 기억해둔다.
    sessionStorage.setItem("job:pending:filename", file.name);
    updateSubmitButtonState();
  });

  els.enableOcr.addEventListener("change", function () {
    els.ocrLangGroup.hidden = !els.enableOcr.checked;
    updateSubmitButtonState();
  });

  [els.ocrLangKor, els.ocrLangEng].forEach(function (checkbox) {
    checkbox.addEventListener("change", function () {
      els.ocrLangError.hidden = ocrSelectionValid();
      updateSubmitButtonState();
    });
  });

  function resetPanelA() {
    els.form.reset();
    els.fileInfo.hidden = true;
    els.fileSizeError.hidden = true;
    els.ocrLangGroup.hidden = true;
    els.ocrLangError.hidden = true;
    els.panelAError.hidden = true;
    els.submitStatus.hidden = true;
    els.submitButton.disabled = true;
    els.submitButton.textContent = "변환 시작";
  }

  function showPanelAError(message) {
    els.panelAError.hidden = false;
    els.panelAError.textContent = message;
  }

  els.form.addEventListener("submit", function (event) {
    event.preventDefault();
    var file = els.fileInput.files[0];
    if (!file) return;

    els.panelAError.hidden = true;
    els.submitButton.disabled = true;
    els.submitButton.textContent = "업로드 중…";
    els.submitStatus.hidden = false;
    els.submitStatus.textContent = "업로드 중…";

    var coldStartTimer = setTimeout(function () {
      els.submitStatus.textContent =
        "서버를 깨우는 중입니다. 첫 접속 시 최대 1분 정도 걸릴 수 있습니다(무료 서버 특성)";
    }, SLOW_RESPONSE_MS);

    // 폼 엘리먼트에서 직접 만들면 CSRF 히든 필드({% csrf_token %})와 체크된
    // 체크박스만 자동으로 포함된다(수동 재조립 불필요, 03 §6-1 CSRF 표준 적용).
    var formData = new FormData(els.form);

    fetch("/convert", { method: "POST", body: formData })
      .then(function (response) {
        clearTimeout(coldStartTimer);
        if (response.status === 202) {
          return response.json().then(function (data) {
            startJob(data.job_id, file.name);
          });
        }
        if (response.status === 413) {
          throw new UserFacingError(
            "파일이 너무 큽니다. 최대 " + MAX_UPLOAD_MB + "MB까지 업로드할 수 있습니다"
          );
        }
        if (response.status === 429) {
          throw new UserFacingError(
            "요청이 제한되었습니다. 시간당 업로드 횟수를 초과했거나 이미 진행 중인 작업이 있습니다. 잠시 후 다시 시도해주세요"
          );
        }
        if (response.status === 503) {
          throw new UserFacingError(
            "지금은 이용자가 많아 서버가 바쁩니다. 1~2분 후 다시 시도해주세요"
          );
        }
        throw new UserFacingError("문제가 발생했습니다. 다시 시도해주세요.");
      })
      .catch(function (error) {
        clearTimeout(coldStartTimer);
        els.submitStatus.hidden = true;
        els.submitButton.disabled = false;
        els.submitButton.textContent = "변환 시작";
        showPanelAError(
          error instanceof UserFacingError
            ? error.message
            : "문제가 발생했습니다. 다시 시도해주세요."
        );
      });
  });

  function UserFacingError(message) {
    this.message = message;
  }
  UserFacingError.prototype = Object.create(Error.prototype);

  // ---- Panel B: 진행/폴링 ----

  function startJob(jobId, filename) {
    var pendingFilename = sessionStorage.getItem("job:pending:filename");
    sessionStorage.setItem(
      "job:" + jobId + ":filename",
      filename || pendingFilename || ""
    );
    sessionStorage.removeItem("job:pending:filename");

    state.jobId = jobId;
    state.submittedAt = Date.now();
    state.pollFailureCount = 0;

    history.replaceState(null, "", "/?job=" + jobId);

    els.progressFilename.textContent = filename || "선택한 파일";
    els.progressStageLabel.textContent = "대기열에서 순서를 기다리는 중입니다";
    els.progressBar.removeAttribute("value");
    els.progressBar.removeAttribute("max");
    els.progressPageCounter.hidden = true;
    els.progressSlowResponse.hidden = true;
    els.progressTimeoutBanner.hidden = true;
    els.progressOfflineBanner.hidden = true;

    showPanel("b");
    startElapsedTimer();
    poll();
  }

  function startElapsedTimer() {
    stopElapsedTimer();
    state.elapsedTimer = setInterval(function () {
      var elapsedMs = Date.now() - state.submittedAt;
      var seconds = Math.floor(elapsedMs / 1000);
      els.progressElapsed.textContent =
        "경과 시간: " + Math.floor(seconds / 60) + "분 " + (seconds % 60) + "초";
      if (elapsedMs > SOFT_TIMEOUT_MS && !els.progressTimeoutBanner.dataset.shown) {
        // 실제로 계속 processing 상태일 때만 보여준다 — poll()이 상태를 갱신한다.
      }
    }, 1000);
  }

  function stopElapsedTimer() {
    if (state.elapsedTimer) {
      clearInterval(state.elapsedTimer);
      state.elapsedTimer = null;
    }
  }

  function poll() {
    if (!state.jobId) return;
    var jobId = state.jobId;
    var requestStart = Date.now();
    var slowTimer = setTimeout(function () {
      els.progressSlowResponse.hidden = false;
    }, SLOW_RESPONSE_MS);

    fetch("/api/jobs/" + jobId + "/")
      .then(function (response) {
        clearTimeout(slowTimer);
        els.progressSlowResponse.hidden = true;
        els.progressOfflineBanner.hidden = true;
        state.pollFailureCount = 0;

        if (response.status === 404) {
          stopElapsedTimer();
          showPanel("d");
          return;
        }
        if (!response.ok) {
          throw new Error("polling failed with status " + response.status);
        }
        return response.json().then(handlePollResult);
      })
      .catch(function () {
        clearTimeout(slowTimer);
        state.pollFailureCount += 1;
        if (state.pollFailureCount > MAX_POLL_RETRIES) {
          els.progressOfflineBanner.hidden = false;
        }
        // job_id 자체는 여전히 유효하므로 폴링은 계속 재개한다(04 §6-3).
        schedulePoll();
      });
  }

  function schedulePoll() {
    if (state.pollTimer) clearTimeout(state.pollTimer);
    state.pollTimer = setTimeout(poll, POLL_INTERVAL_MS);
  }

  function handlePollResult(data) {
    if (data.status === "pending") {
      els.progressStageLabel.textContent = "대기열에서 순서를 기다리는 중입니다";
      schedulePoll();
      return;
    }
    if (data.status === "processing") {
      var stage = data.progress && data.progress.stage;
      els.progressStageLabel.textContent = STAGE_LABELS[stage] || "변환 처리 중";
      var total = (data.progress && data.progress.total_pages) || 0;
      var current = (data.progress && data.progress.current_page) || 0;
      if (total > 0) {
        els.progressBar.max = total;
        els.progressBar.value = current;
        els.progressPageCounter.hidden = false;
        els.progressPageCounter.textContent = current + "/" + total + "페이지";
      } else {
        els.progressBar.removeAttribute("value");
        els.progressPageCounter.hidden = true;
      }
      if (Date.now() - state.submittedAt > SOFT_TIMEOUT_MS) {
        els.progressTimeoutBanner.hidden = false;
      }
      schedulePoll();
      return;
    }
    // done | failed -> Panel C로 전이
    stopElapsedTimer();
    renderResult(data);
    showPanel("c");
  }

  // ---- Panel C: 결과 ----

  function renderResult(data) {
    els.resultIssueList.innerHTML = "";
    els.resultIssueList.hidden = true;
    els.downloadButton.hidden = true;
    els.downloadError.hidden = true;

    if (data.status === "failed") {
      els.resultBadge.className = "badge danger";
      els.resultBadge.textContent = "문제가 발생했습니다";
      return;
    }

    // status === "done"
    var errors = data.errors || [];
    var warnings = data.warnings || [];

    if (errors.length > 0) {
      els.resultBadge.className = "badge danger";
      els.resultBadge.textContent = "변환할 수 없습니다";
      renderIssueList(errors, true);
      return;
    }

    if (warnings.length > 0) {
      els.resultBadge.className = "badge warning";
      els.resultBadge.textContent = "⚠ 경고 " + warnings.length + "건과 함께 완료";
      renderIssueList(warnings, false);
    } else {
      els.resultBadge.className = "badge success";
      els.resultBadge.textContent = "✓ 변환 완료";
    }
    els.downloadButton.hidden = false;
  }

  function renderIssueList(issues, isError) {
    els.resultIssueList.hidden = false;
    issues.forEach(function (issue) {
      var li = document.createElement("li");
      var icon = document.createElement("span");
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = iconFor(issue.code) + " ";
      var text = document.createElement("span");
      text.textContent = isError
        ? messageFor(issue.code, issue.message)
        : issue.detail || issue.code;
      li.appendChild(icon);
      li.appendChild(text);
      els.resultIssueList.appendChild(li);
    });
  }

  els.downloadButton.addEventListener("click", function () {
    if (!state.jobId) return;
    els.downloadError.hidden = true;
    els.downloadButton.disabled = true;
    var originalLabel = els.downloadButton.textContent;
    els.downloadButton.textContent = "다운로드 중…";

    fetch("/download/" + state.jobId + "/")
      .then(function (response) {
        if (!response.ok) {
          if (response.status === 409) {
            throw new UserFacingError("아직 처리 중입니다. 잠시 후 다시 시도해주세요.");
          }
          throw new UserFacingError("다운로드에 실패했습니다. 다시 시도해주세요.");
        }
        return response.blob();
      })
      .then(function (blob) {
        var storedName = sessionStorage.getItem("job:" + state.jobId + ":filename");
        var downloadName = "converted.hwpx";
        if (storedName) {
          downloadName = storedName.toLowerCase().endsWith(".pdf")
            ? storedName.slice(0, -4) + ".hwpx"
            : storedName + ".hwpx";
        }
        var objectUrl = URL.createObjectURL(blob);
        var link = document.createElement("a");
        link.href = objectUrl;
        link.download = downloadName;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(objectUrl);
      })
      .catch(function (error) {
        els.downloadError.hidden = false;
        els.downloadError.textContent =
          error instanceof UserFacingError
            ? error.message
            : "다운로드에 실패했습니다. 다시 시도해주세요.";
      })
      .finally(function () {
        els.downloadButton.disabled = false;
        els.downloadButton.textContent = originalLabel;
      });
  });

  function resetToPanelA() {
    stopElapsedTimer();
    if (state.pollTimer) clearTimeout(state.pollTimer);
    state.jobId = null;
    state.submittedAt = null;
    history.replaceState(null, "", "/");
    resetPanelA();
    showPanel("a");
  }

  els.retryButton.addEventListener("click", resetToPanelA);
  els.newUploadButton.addEventListener("click", resetToPanelA);

  // ---- 초기 진입: URL의 ?job=<job_id>로 재방문/새로고침 복원(04 §1-1, Could-have) ----
  (function init() {
    resetPanelA();
    var params = new URLSearchParams(window.location.search);
    var jobId = params.get("job");
    if (jobId) {
      var storedFilename = sessionStorage.getItem("job:" + jobId + ":filename");
      startJob(jobId, storedFilename || "");
    } else {
      showPanel("a");
    }
  })();
})();
