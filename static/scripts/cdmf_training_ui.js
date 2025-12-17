// C:\CandyDungeonMusicForge\static\scripts\cdmf_training_ui.js

(function () {
  "use strict";

  window.CDMF = window.CDMF || {};
  var CDMF = window.CDMF;

  var urls = (window.CDMF_BOOT && window.CDMF_BOOT.urls) || {};
  var TRAIN_STATUS_URL = urls.trainStatus || "/train_lora/status";
  var DATASET_MASS_TAG_URL = urls.datasetMassTag || "/dataset_mass_tag";
  var CONFIG_LIST_URL = urls.trainConfigs || "/train_lora/configs";

  // Called by the training form on submit.
  // When the ACE-Step model is not present, this behaves like a
  // "Download Training Model" button instead of starting trainer.py.
  CDMF.onSubmitTraining = function (event) {
    try {
      var startBtn = document.getElementById("btnStartTraining");

      // Use the same model state that the Generate button relies on.
      var ready = !!window.candyModelsReady;
      var state = window.candyModelStatusState || "unknown";

      // If the model is absent / unknown / errored, turn this into a
      // "Download Training Model" action instead of submitting /train_lora.
      if (!ready || state === "absent" || state === "unknown" || state === "error") {
        if (event && event.preventDefault) {
          event.preventDefault();
        }

        // Repurpose this submit as "Download Models" and let the
        // shared model-status machinery (applyModelStatusToUI) drive
        // the button label and disabled state, just like Generate.
        if (typeof window.startModelDownload === "function") {
          window.startModelDownload();
        }

        return false;
      }

      // If the model is currently downloading, block the submit entirely:
      // we don't want to queue another download or start a run yet.
      if (state === "downloading") {
        if (event && event.preventDefault) {
          event.preventDefault();
        }
        return false;
      }

      // At this point the model is ready: normal training behaviour.
      var datasetInput = document.getElementById("dataset_path");
      var folderInput = document.getElementById("dataset_folder_picker");
      var statusEl = document.getElementById("trainingStatus");
      var barEl = document.getElementById("loraLoadingBar");

      var hasText = datasetInput && datasetInput.value.trim().length > 0;
      var hasFolder =
        folderInput &&
        folderInput.files &&
        folderInput.files.length > 0;

      if (!hasText && !hasFolder) {
        alert(
          "Please select a dataset folder or enter a dataset path before starting training. " +
          "Dataset folders MUST be created as subdirectories beneath the training_datasets " +
          "directory within CDMF's root path."
        );
        if (event && event.preventDefault) {
          event.preventDefault();
        }
        return false;
      }

      if (statusEl) {
        statusEl.dataset.state = "running";
        statusEl.classList.add("training-status-running");
        var textEl = statusEl.querySelector(".training-status-text");
        if (textEl) {
          textEl.textContent =
            "LoRA training is running… check the console window for logs.";
        }
      }

      if (barEl) {
        barEl.style.display = "block";
        barEl.classList.add("active");
        var inner = barEl.querySelector(".loading-bar-inner");
        if (inner) {
          inner.style.width = "100%"; // indeterminate full-width candystripe
        }
      }

      if (startBtn) {
        startBtn.disabled = true;
      }

      if (typeof CDMF.startTrainStatusPolling === "function") {
        CDMF.startTrainStatusPolling();
      }

      return true;
    } catch (e) {
      if (window.console && console.error) {
        console.error("[CDMF] onSubmitTraining error", e);
      }
      // Fail open so the form can still submit.
      return true;
    }
  };

  // Wire up the folder/config "Browse…" buttons to their hidden file inputs.
  CDMF._trainPollTimer = null;

  CDMF._updateTrainStatusUI = function (state) {
    try {
      var statusEl = document.getElementById("trainingStatus");
      var barEl = document.getElementById("loraLoadingBar");
      var startBtn = document.getElementById("btnStartTraining");
      if (!statusEl) return;

      var isRunning = !!(state && state.running);
      var textEl = statusEl.querySelector(".training-status-text");

      // ------------------------------------------------------------
      //  Figure out if we have usable numeric progress.
      //  We support:
      //    * state.progress in [0, 1]
      //    * or current_step / max_steps
      //    * or current_epoch / max_epochs
      //  If nothing looks sane, we fall back to "indeterminate"
      //  full-width candy stripe.
      // ------------------------------------------------------------
      var progress = null;
      var hasProgress = false;
      var pctLabel = "";

      if (state) {
        if (typeof state.progress === "number" && !isNaN(state.progress)) {
          progress = state.progress;
        } else if (
          typeof state.current_step === "number" &&
          typeof state.max_steps === "number" &&
          state.max_steps > 0
        ) {
          progress = state.current_step / state.max_steps;
        } else if (
          typeof state.current_epoch === "number" &&
          typeof state.max_epochs === "number" &&
          state.max_epochs > 0
        ) {
          progress = state.current_epoch / state.max_epochs;
        }
      }

      if (typeof progress === "number" && !isNaN(progress)) {
        if (progress < 0) progress = 0;
        if (progress > 1) progress = 1;
        // We treat >0 and <1 as determinate; 0 is "indeterminate"
        if (progress > 0 && progress < 1) {
          hasProgress = true;
          pctLabel = Math.round(progress * 100) + "%";
        }
      }

      // Base message
      var msg =
        (state && state.last_message) ||
        (isRunning
          ? "LoRA training is running… check the console window for logs."
          : "Idle – no training in progress. When you start a LoRA run, this will show an animated “candycane” indicator.");

      // Enrich message while running if we know a fraction
      if (isRunning && hasProgress) {
        var extraBits = [];

        if (
          typeof state.current_step === "number" &&
          typeof state.max_steps === "number" &&
          state.max_steps > 0
        ) {
          extraBits.push(
            "step " + state.current_step + " / " + state.max_steps
          );
        }

        if (
          typeof state.current_epoch === "number" &&
          typeof state.max_epochs === "number" &&
          state.max_epochs > 0
        ) {
          extraBits.push(
            "epoch " + state.current_epoch + " / " + state.max_epochs
          );
        }

        var suffix = pctLabel;
        if (extraBits.length) {
          suffix += " (" + extraBits.join(", ") + ")";
        }

        msg =
          "LoRA training is running… " +
          suffix +
          ". See the console window for detailed logs.";
      }

      // Finished / error messaging
      if (!isRunning && state && typeof state.returncode === "number") {
        if (state.returncode === 0) {
          msg =
            state.last_message ||
            "LoRA training finished successfully.";
        } else {
          msg =
            state.last_message ||
            ("LoRA training finished with errors (return code " +
              state.returncode +
              "). See trainer.log for details.");
        }
      }

      // Bar + button behaviour
      if (isRunning) {
        statusEl.dataset.state = "running";
        statusEl.classList.add("training-status-running");

        if (barEl) {
          barEl.style.display = "block";
          barEl.classList.add("active");
          var inner = barEl.querySelector(".loading-bar-inner");
          if (inner) {
            if (hasProgress) {
              inner.style.width = String(progress * 100) + "%";
            } else {
              // No numeric progress → indeterminate full-width candystripe
              inner.style.width = "100%";
            }
          }
        }

        if (startBtn) startBtn.disabled = true;
      } else {
        statusEl.dataset.state = "idle";
        statusEl.classList.remove("training-status-running");

        if (barEl) {
          barEl.style.display = "none";
          barEl.classList.remove("active");
          var inner2 = barEl.querySelector(".loading-bar-inner");
          if (inner2) inner2.style.width = "0%";
        }

        if (startBtn) startBtn.disabled = false;
      }

      if (textEl) {
        textEl.textContent = msg;
      }
    } catch (e) {
      if (window.console && console.error) {
        console.error("[CDMF] _updateTrainStatusUI error", e);
      }
    }
  };

  CDMF.refreshTrainStatus = function () {
    if (!window.fetch) {
      return;
    }
    fetch(TRAIN_STATUS_URL, {
      method: "GET",
      headers: { "Accept": "application/json" }
    })
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        CDMF._updateTrainStatusUI(data || {});
      })
      .catch(function (err) {
        if (window.console && console.error) {
          console.error("[CDMF] /train_lora/status error", err);
        }
      });
  };

  CDMF.startTrainStatusPolling = function () {
    if (CDMF._trainPollTimer) {
      return;
    }
    // Immediate sync, then poll every few seconds.
    CDMF.refreshTrainStatus();
    CDMF._trainPollTimer = setInterval(function () {
      CDMF.refreshTrainStatus();
    }, 5000);
  };

  CDMF.runDatasetMassTag = function (mode) {
    try {
      var dsInput = document.getElementById("tag_dataset_path");
      var folderInput = document.getElementById("tag_dataset_picker");
      var basePromptInput = document.getElementById("tag_base_prompt");
      var overwriteInput = document.getElementById("tag_overwrite");
      var statusEl = document.getElementById("tagStatusText");
      var busyBar = document.getElementById("tagBusyBar");
      var promptBtn = document.getElementById("btnTagCreatePrompts");
      var lyricsBtn = document.getElementById("btnTagCreateInstLyrics");

      if (!dsInput && !folderInput) {
        return;
      }

      var datasetPath = "";

      if (dsInput && dsInput.value) {
        datasetPath = dsInput.value.trim();
      }

      // If user only used the folder picker, derive the dataset folder name.
      if (!datasetPath && folderInput && folderInput.files && folderInput.files.length > 0) {
        var first = folderInput.files[0];
        var rel = first.webkitRelativePath || first.name || "";
        var parts = rel.split("/");
        var datasetFolder = parts.length > 1 ? parts[0] : "";
        if (datasetFolder) {
          datasetPath = datasetFolder;
          if (dsInput) {
            dsInput.value = datasetFolder;
          }
        }
      }

      if (!datasetPath) {
        alert(
          "Please select a dataset folder or enter a dataset path before running mass tagging. " +
          "Dataset folders MUST live under the training_datasets directory within CDMF's root path."
        );
        return;
      }

      var basePrompt = basePromptInput ? basePromptInput.value.trim() : "";
      if ((mode === "prompt" || mode === "both") && !basePrompt) {
        alert(
          "Please enter base tags before creating prompt files, " +
          "e.g. '16-bit, 8-bit, SNES, retro RPG BGM, looping instrumental'."
        );
        return;
      }

      var overwrite = !!(overwriteInput && overwriteInput.checked);

      if (!window.fetch) {
        if (statusEl) {
          statusEl.textContent =
            "Error: this browser does not support fetch(); mass tagging is unavailable.";
        }
        return;
      }

      if (busyBar) {
        busyBar.style.display = "block";
        busyBar.classList.add("active");
        var inner = busyBar.querySelector(".loading-bar-inner");
        if (inner) {
          inner.style.width = "100%"; // indeterminate full-width candystripe
        }
      }
      if (statusEl) {
        statusEl.textContent = "Running dataset mass tagging…";
      }
      if (promptBtn) promptBtn.disabled = true;
      if (lyricsBtn) lyricsBtn.disabled = true;

      function cleanup() {
        if (busyBar) {
          busyBar.style.display = "none";
          busyBar.classList.remove("active");
          var inner2 = busyBar.querySelector(".loading-bar-inner");
          if (inner2) {
            inner2.style.width = "0%";
          }
        }
        if (promptBtn) promptBtn.disabled = false;
        if (lyricsBtn) lyricsBtn.disabled = false;
      }

      fetch(DATASET_MASS_TAG_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json"
        },
        body: JSON.stringify({
          dataset_path: datasetPath,
          base_prompt: basePrompt,
          mode: mode,
          overwrite: overwrite
        })
      })
        .then(function (resp) {
          if (!resp.ok) {
            // Try to parse JSON error; if that fails, throw a generic one.
            return resp.json()
              .catch(function () {
                throw new Error("HTTP " + resp.status + " from /dataset_mass_tag");
              })
              .then(function (data) {
                if (!data || typeof data.ok === "undefined") {
                  throw new Error("HTTP " + resp.status + " from /dataset_mass_tag");
                }
                return data;
              });
          }
          return resp.json();
        })
        .then(function (data) {
          if (!data) {
            throw new Error("Empty response from /dataset_mass_tag");
          }

          if (data.ok) {
            var msg =
              "Mass tagging complete for \"" + (data.dataset || datasetPath) + "\".";
            var partsMsg = [];

            if (typeof data.prompt_files_created === "number") {
              partsMsg.push(
                data.prompt_files_created + " prompt file" +
                (data.prompt_files_created === 1 ? "" : "s") +
                (typeof data.prompt_files_skipped === "number"
                  ? " (" + data.prompt_files_skipped + " skipped)"
                  : "")
              );
            }

            if (typeof data.lyrics_files_created === "number") {
              partsMsg.push(
                data.lyrics_files_created + " lyrics file" +
                (data.lyrics_files_created === 1 ? "" : "s") +
                (typeof data.lyrics_files_skipped === "number"
                  ? " (" + data.lyrics_files_skipped + " skipped)"
                  : "")
              );
            }

            if (partsMsg.length) {
              msg += " " + partsMsg.join(", ") + ".";
            }

            if (statusEl) {
              statusEl.textContent = msg;
            }
          } else {
            if (statusEl) {
              statusEl.textContent =
                "Error during mass tagging: " + (data.error || "unknown error.");
            }
          }

          cleanup();
        })
        .catch(function (err) {
          if (window.console && console.error) {
            console.error("[CDMF] /dataset_mass_tag error", err);
          }
          if (statusEl) {
            statusEl.textContent =
              "Error during mass tagging: " +
              (err && err.message ? err.message : String(err));
          }
          cleanup();
        });
    } catch (e) {
      if (window.console && console.error) {
        console.error("[CDMF] runDatasetMassTag error", e);
      }
    }
  };

  function initLoraConfigUI() {
    var selectEl = document.getElementById("lora_config_select");
    var hiddenPathInput = document.getElementById("lora_config_path");
    var helpBtn = document.getElementById("btnLoraConfigHelp");
    var modal = document.getElementById("loraConfigModal");
    var modalClose = document.getElementById("btnLoraConfigModalClose");

    // --- Modal wiring -----------------------------------------------------
    if (helpBtn && modal) {
      helpBtn.addEventListener("click", function () {
        modal.style.display = "block";
      });
    }

    if (modal) {
      if (modalClose) {
        modalClose.addEventListener("click", function () {
          modal.style.display = "none";
        });
      }
      // Click on backdrop closes modal
      modal.addEventListener("click", function (evt) {
        if (evt.target === modal) {
          modal.style.display = "none";
        }
      });
    }

    if (!selectEl) {
      return;
    }

    // Keep hidden input in sync with dropdown selection.
    if (hiddenPathInput) {
      selectEl.addEventListener("change", function () {
        hiddenPathInput.value = selectEl.value || "";
      });
    }

    // If fetch is unavailable, just keep whatever the template rendered.
    if (!window.fetch) {
      if (hiddenPathInput && selectEl.value) {
        hiddenPathInput.value = selectEl.value;
      }
      return;
    }

    fetch(CONFIG_LIST_URL, {
      method: "GET",
      headers: { "Accept": "application/json" }
    })
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        if (!data || !data.ok || !Array.isArray(data.configs)) {
          // Fall back to whatever the template rendered.
          if (hiddenPathInput && selectEl.value) {
            hiddenPathInput.value = selectEl.value;
          }
          return;
        }

        // Clear any placeholder options.
        while (selectEl.firstChild) {
          selectEl.removeChild(selectEl.firstChild);
        }

        var defaultName = data["default"] || "";
        data.configs.forEach(function (cfg) {
          var opt = document.createElement("option");
          opt.value = cfg.file;
          opt.textContent = cfg.label || cfg.file;
          if (defaultName && cfg.file === defaultName) {
            opt.selected = true;
          }
          selectEl.appendChild(opt);
        });

        if (hiddenPathInput) {
          hiddenPathInput.value = selectEl.value || "";
        }
      })
      .catch(function (err) {
        if (window.console && console.error) {
          console.error("[CDMF] /train_lora/configs error", err);
        }
        // On error, keep whatever the template rendered.
        if (hiddenPathInput && selectEl.value) {
          hiddenPathInput.value = selectEl.value;
        }
      });
  }

  function initTrainingUI() {
    var folderBtn = document.getElementById("btnDatasetBrowse");
    var folderInput = document.getElementById("dataset_folder_picker");
    var datasetInput = document.getElementById("dataset_path");

    if (folderBtn && folderInput) {
      folderBtn.addEventListener("click", function () {
        folderInput.click();
      });

      folderInput.addEventListener("change", function () {
        if (!datasetInput) return;
        var files = folderInput.files;
        if (!files || !files.length) return;

        var first = files[0];
        var rel = first.webkitRelativePath || first.name || "";
        var parts = rel.split("/");
        var datasetFolder = parts.length > 1 ? parts[0] : "";

        if (datasetFolder) {
          datasetInput.value = datasetFolder;
        }

        var summary =
          "Selected " + files.length + " file" +
          (files.length === 1 ? "" : "s") +
          (datasetFolder ? ' from folder "' + datasetFolder + '"' : "");
        datasetInput.placeholder = summary;
      });
    }

    // ------------------------------
    // Dataset Mass Tagging UI wiring
    // ------------------------------
    var tagFolderBtn = document.getElementById("btnTagDatasetBrowse");
    var tagFolderInput = document.getElementById("tag_dataset_picker");
    var tagDatasetInput = document.getElementById("tag_dataset_path");

    if (tagFolderBtn && tagFolderInput) {
      tagFolderBtn.addEventListener("click", function () {
        tagFolderInput.click();
      });

      tagFolderInput.addEventListener("change", function () {
        if (!tagDatasetInput) return;
        var files = tagFolderInput.files;
        if (!files || !files.length) return;

        var first = files[0];
        var rel = first.webkitRelativePath || first.name || "";
        var parts = rel.split("/");
        var datasetFolder = parts.length > 1 ? parts[0] : "";

        if (datasetFolder) {
          tagDatasetInput.value = datasetFolder;
        }

        var summary =
          "Selected " + files.length + " file" +
          (files.length === 1 ? "" : "s") +
          (datasetFolder ? ' from folder "' + datasetFolder + '"' : "");
        tagDatasetInput.placeholder = summary;
      });
    }

    var btnTagPrompts = document.getElementById("btnTagCreatePrompts");
    var btnTagLyrics = document.getElementById("btnTagCreateInstLyrics");

    if (btnTagPrompts && CDMF && typeof CDMF.runDatasetMassTag === "function") {
      btnTagPrompts.addEventListener("click", function () {
        CDMF.runDatasetMassTag("prompt");
      });
    }

    if (btnTagLyrics && CDMF && typeof CDMF.runDatasetMassTag === "function") {
      btnTagLyrics.addEventListener("click", function () {
        CDMF.runDatasetMassTag("lyrics_inst");
      });
    }

    // LoRA config dropdown + modal
    initLoraConfigUI();

    // Keep the LoRA training status in sync even if the page is reloaded
    // while a run is in progress.
    if (window.CDMF && typeof CDMF.startTrainStatusPolling === "function") {
      CDMF.startTrainStatusPolling();
    }
  }

  function initTrainingStatusPoll() {
    // Legacy helper: just delegate to the central polling logic above so
    // we only have one place that interprets TRAIN_STATE (and progress).
    try {
      var statusEl = document.getElementById("trainingStatus");
      if (!statusEl) return;

      if (window.CDMF && typeof CDMF.startTrainStatusPolling === "function") {
        CDMF.startTrainStatusPolling();
      }
    } catch (e) {
      if (window.console && console.error) {
        console.error("[CDMF] initTrainingStatusPoll error", e);
      }
    }
  }

  function _cdmfTrainingOnReady() {
    try {
      initTrainingUI();
      initTrainingStatusPoll();
    } catch (e) {
      if (window.console && console.error) {
        console.error("[CDMF] training UI init error", e);
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _cdmfTrainingOnReady);
  } else {
    _cdmfTrainingOnReady();
  }
})();
