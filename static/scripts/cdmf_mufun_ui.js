// C:\CandyDungeonMusicForge\static\scripts\cdmf_mufun_ui.js

(function () {
  "use strict";

  window.CDMF = window.CDMF || {};
  var CDMF = window.CDMF;

  var urls = (window.CDMF_BOOT && window.CDMF_BOOT.urls) || {};
  var MUFUN_STATUS_URL = urls.mufunStatus || "/mufun/status";
  var MUFUN_ENSURE_URL = urls.mufunEnsure || "/mufun/ensure";
  var MUFUN_ANALYZE_URL = urls.mufunAnalyze || "/mufun/analyze_dataset";

  CDMF._mufunPollTimer = CDMF._mufunPollTimer || null;

  (function initMuFunUI() {
    try {
      var statusEl = document.getElementById("mufunStatusText");
      var ensureBtn = document.getElementById("btnMufunEnsure");
      var analyzeBtn = document.getElementById("btnMufunAnalyze");
      var datasetBrowseBtn = document.getElementById("btnMufunDatasetBrowse");
      var datasetPicker = document.getElementById("mufun_dataset_picker");
      var datasetPathInput = document.getElementById("mufun_dataset_path");
      var resultsEl = document.getElementById("mufun_results");
      var basePromptInput = document.getElementById("mufun_base_prompt");

      // MuFun-specific bar that lives directly above "Install / Check"
      var progressEl = document.getElementById("mufunBusyBar");

      if (!statusEl) {
        // MuFun card not present; nothing to do.
        return;
      }

      function showMuFunBar() {
        if (!progressEl) return;
        progressEl.style.display = "block";
        var inner = progressEl.querySelector(".loading-bar-inner");
        if (inner) {
          progressEl.classList.add("active");
          inner.style.width = "100%"; // full-width, indeterminate candystripe
        }
      }

      function hideMuFunBar() {
        if (!progressEl) return;
        progressEl.style.display = "none";
        progressEl.classList.remove("active");
        var inner = progressEl.querySelector(".loading-bar-inner");
        if (inner) {
          inner.style.width = "0%";
        }
      }

      CDMF.refreshMuFunStatus = function () {
        if (!window.fetch) {
          statusEl.textContent =
            "Fetch API is not available in this browser.";
          if (ensureBtn) ensureBtn.disabled = false;
          hideMuFunBar();
          return;
        }

        fetch(MUFUN_STATUS_URL, {
          method: "GET",
          headers: { Accept: "application/json" }
        })
          .then(function (resp) {
            return resp.json();
          })
          .then(function (data) {
            if (!data || !data.ok) return;

            var state = data.state || "unknown";
            var message = data.message || "";
            statusEl.textContent = message || "Status: " + state;
            CDMF._mufunState = state;

            if (state === "downloading") {
              if (ensureBtn) ensureBtn.disabled = true;
              showMuFunBar();

              if (!CDMF._mufunPollTimer) {
                CDMF._mufunPollTimer = setInterval(function () {
                  CDMF.refreshMuFunStatus();
                }, 5000);
              }
            } else {
              if (ensureBtn) ensureBtn.disabled = false;
              hideMuFunBar();

              if (CDMF._mufunPollTimer) {
                clearInterval(CDMF._mufunPollTimer);
                CDMF._mufunPollTimer = null;
              }
            }
          })
          .catch(function (err) {
            if (ensureBtn) ensureBtn.disabled = false;
            hideMuFunBar();
            if (window.console && console.error) {
              console.error("[CDMF] /mufun/status error", err);
            }
          });
      };

      CDMF.ensureMuFunModel = function () {
        if (!window.fetch) {
          alert(
            "This browser does not support fetch(); cannot install MuFun model."
          );
          return;
        }

        if (ensureBtn) {
          ensureBtn.disabled = true;
        }

        // Show bar immediately when user hits Install / Check
        showMuFunBar();
        statusEl.textContent =
          "Starting MuFun-ACEStep model download / check…";

        fetch(MUFUN_ENSURE_URL, {
          method: "POST",
          headers: { Accept: "application/json" }
        })
          .then(function (resp) {
            return resp.json();
          })
          .then(function (data) {
            if (!data || !data.ok) {
              if (ensureBtn) ensureBtn.disabled = false;
              hideMuFunBar();
              statusEl.textContent = "MuFun model ensure failed.";
              return;
            }
            // Let /mufun/status drive the long-running state + bar while downloading
            CDMF.refreshMuFunStatus();
          })
          .catch(function (err) {
            if (ensureBtn) ensureBtn.disabled = false;
            hideMuFunBar();
            statusEl.textContent =
              "MuFun model ensure failed (see console).";
            if (window.console && console.error) {
              console.error("[CDMF] /mufun/ensure error", err);
            }
          });
      };

      CDMF.runMuFunAnalysis = function () {
        if (!window.fetch) {
          alert(
            "This browser does not support fetch(); cannot run MuFun analysis."
          );
          return;
        }

        if (!datasetPathInput) {
          alert("Dataset path input not found in the page.");
          return;
        }

        var datasetPath = datasetPathInput.value.trim();
        if (!datasetPath) {
          alert(
            "Please enter/select the dataset folder name " +
              "(under training_datasets in the CDMF root directory) before running analysis. " +
              "ONLY subfolders within training_datasets will work."
          );
          return;
        }

        var basePrompt = "";
        if (basePromptInput) {
          basePrompt = basePromptInput.value.trim();
        }

        if (resultsEl) {
          resultsEl.value =
            "Running MuFun-ACEStep analysis…\n" +
            "This may take some time for large datasets.";
        }
        if (analyzeBtn) analyzeBtn.disabled = true;
        if (ensureBtn) ensureBtn.disabled = true;

        // Show the same MuFun bar while the dataset is being analyzed
        showMuFunBar();

        fetch(MUFUN_ANALYZE_URL, {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            dataset_path: datasetPath,
            overwrite: false,
            dataset_base_prompt: basePrompt
          })
        })
          .then(function (resp) {
            return resp.json();
          })
          .then(function (data) {
            if (analyzeBtn) analyzeBtn.disabled = false;
            if (ensureBtn) ensureBtn.disabled = false;
            hideMuFunBar();

            if (!data || !data.ok) {
              if (resultsEl) {
                resultsEl.value =
                  "MuFun analysis failed: " +
                  (data && data.error ? data.error : "unknown error");
              }
              return;
            }

            if (resultsEl) {
              var lines = [];
              if (data.summary) {
                var s = data.summary;
                lines.push("Summary:");
                lines.push(
                  "  Total audio files: " +
                    (s.total_files != null ? s.total_files : "?")
                );
                lines.push(
                  "  Processed: " +
                    (s.processed != null ? s.processed : "?")
                );
                lines.push(
                  "  Skipped (existing): " +
                    (s.skipped_existing != null
                      ? s.skipped_existing
                      : "?")
                );
                lines.push(
                  "  Errors: " + (s.errors != null ? s.errors : "?")
                );
                lines.push("");
              }
              if (data.results_text) {
                lines.push(data.results_text);
              } else if (data.files) {
                data.files.forEach(function (rec) {
                  var status = (rec.status || "ok").toUpperCase();
                  lines.push("[" + status + "] " + (rec.file || "?"));
                });
              }
              resultsEl.value = lines.join("\n");
            }
          })
          .catch(function (err) {
            if (analyzeBtn) analyzeBtn.disabled = false;
            if (ensureBtn) ensureBtn.disabled = false;
            hideMuFunBar();
            if (resultsEl) {
              resultsEl.value =
                "MuFun analysis failed (network / JS error). See console for details.";
            }
            if (window.console && console.error) {
              console.error("[CDMF] /mufun/analyze_dataset error", err);
            }
          });
      };

      if (ensureBtn) {
        ensureBtn.addEventListener("click", function () {
          CDMF.ensureMuFunModel();
        });
      }

      if (analyzeBtn) {
        analyzeBtn.addEventListener("click", function () {
          CDMF.runMuFunAnalysis();
        });
      }

      if (datasetBrowseBtn && datasetPicker) {
        datasetBrowseBtn.addEventListener("click", function () {
          datasetPicker.click();
        });

        datasetPicker.addEventListener("change", function () {
          if (!datasetPathInput) return;
          var files = datasetPicker.files;
          if (!files || !files.length) return;

          // If the user selects the training_datasets root, each file's
          // webkitRelativePath will look like "my_new_lora/track1.mp3".
          // Use the first path segment as the dataset folder name.
          var first = files[0];
          var rel =
            first.webkitRelativePath || first.name || "";
          var parts = rel.split("/");
          var datasetFolder = parts.length > 1 ? parts[0] : "";

          if (datasetFolder) {
            datasetPathInput.value = datasetFolder;
          }

          var summary =
            "Selected " +
            files.length +
            " file" +
            (files.length === 1 ? "" : "s") +
            (datasetFolder
              ? ' from folder "' + datasetFolder + '"'
              : "");
          datasetPathInput.placeholder = summary;
        });
      }

      // One-shot status probe on load.
      CDMF.refreshMuFunStatus();
    } catch (e) {
      if (window.console && console.error) {
        console.error("[CDMF] initMuFunUI error", e);
      }
    }
  })();
})();
