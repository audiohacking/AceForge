// cdmf_midi_generation_ui.js
// MIDI generation form submission and UI handling

(function () {
  "use strict";

  window.CDMF = window.CDMF || {};
  var CDMF = window.CDMF;

  // Update loading bar fraction
  function updateMidiGenLoadingBarFraction(fraction) {
    var bar = document.getElementById("midiGenLoadingBar");
    var inner = bar ? bar.querySelector(".loading-bar-inner") : null;
    if (inner) {
      var pct = Math.max(0, Math.min(100, fraction * 100));
      inner.style.width = pct + "%";
      if (bar) {
        bar.classList.add("active");
      }
    }
  }

  CDMF.onSubmitMidiGen = function (event) {
    event.preventDefault();

    // If basic-pitch model is not ready, trigger download (like ACE-Step "Download Models")
    var statusEl = document.getElementById("midiGenModelStatusNotice");
    var downloadBtn = document.getElementById("midiGenDownloadModelsBtn");
    if (downloadBtn && downloadBtn.style.display !== "none" && downloadBtn.offsetParent !== null) {
      CDMF.startMidiGenModelDownload();
      return false;
    }

    var form = event.target;
    var formData = new FormData(form);

    // Get output directory from Settings (sync with generate form)
    var outDirInput = document.getElementById("out_dir_settings");
    if (outDirInput) {
      formData.set("out_dir", outDirInput.value);
    }

    // Show loading bar
    var loadingBar = document.getElementById("midiGenLoadingBar");
    if (loadingBar) {
      loadingBar.style.display = "block";
      updateMidiGenLoadingBarFraction(0.0);
    }

    // Disable submit button
    var submitBtn = document.getElementById("midiGenButton");
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span class="icon">⏳</span><span>Generating MIDI...</span>';
    }

    // Make API call
    fetch("/midi_generate", {
      method: "POST",
      body: formData,
    })
      .then(function (response) {
        return response.json();
      })
      .then(function (data) {
        // Hide loading bar
        if (loadingBar) {
          loadingBar.style.display = "none";
        }

        // Re-enable submit button
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<span class="icon">🎹</span><span>Generate MIDI</span>';
        }

        if (data.error) {
          // Show error message
          var errorMsg = data.message || "MIDI generation failed";
          if (CDMF.showToast) {
            CDMF.showToast(errorMsg, "error");
          } else {
            alert(errorMsg);
          }
          if (data.details && window.console) {
            console.error("[MIDI Generation] Error details:", data.details);
          }
        } else {
          // Show success message
          var successMsg = data.message || "MIDI generation completed!";
          if (CDMF.showToast) {
            CDMF.showToast(successMsg, "success");
          } else {
            console.log("[MIDI Generation] " + successMsg);
          }

          // Refresh Music Player to show the new file
          if (window.CDMF && CDMF.refreshTracksAfterGeneration) {
            CDMF.refreshTracksAfterGeneration({ autoplay: false });
          } else if (data.tracks && window.CDMF && CDMF.updateTrackList) {
            CDMF.updateTrackList(data.tracks);
          }

          // Reset form (optional - keep values for convenience)
          // form.reset();
        }
      })
      .catch(function (error) {
        // Hide loading bar
        if (loadingBar) {
          loadingBar.style.display = "none";
        }

        // Re-enable submit button
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<span class="icon">🎹</span><span>Generate MIDI</span>';
        }

        // Show error
        var errorMsg = "MIDI generation failed: " + error.message;
        if (CDMF.showToast) {
          CDMF.showToast(errorMsg, "error");
        } else {
          alert(errorMsg);
        }
        if (window.console) {
          console.error("[MIDI Generation] Request failed:", error);
        }
      });

    return false;
  };

  // Sync output directory from Settings when MIDI generation form is shown
  CDMF.syncMidiGenOutputDir = function () {
    var outDirSettings = document.getElementById("out_dir_settings");
    var outDirMidiGen = document.getElementById("midi_gen_out_dir");

    if (outDirSettings && outDirMidiGen) {
      outDirMidiGen.value = outDirSettings.value;
    }
  };

  // Apply MIDI generation track metadata into the MIDI Generation form (used by "copy settings" in Music Player)
  CDMF.applyMidiGenSettingsToForm = function (settings) {
    if (!settings) return;

    if (typeof CDMF.switchMode === "function") {
      CDMF.switchMode("midi_gen");
    }

    function setVal(id, v) {
      var el = document.getElementById(id);
      if (el && v != null && v !== "") {
        el.value = String(v);
      }
    }

    function setNumPair(numId, rangeId, v) {
      if (v == null || Number.isNaN(v)) return;
      var s = String(v);
      var num = document.getElementById(numId);
      var rng = document.getElementById(rangeId);
      if (num) num.value = s;
      if (rng) rng.value = s;
    }

    function setCheckbox(id, v) {
      var el = document.getElementById(id);
      if (el && typeof v === "boolean") {
        el.checked = v;
      }
    }

    setVal("midi_gen_output_filename", settings.basename);
    setNumPair("midi_gen_onset_threshold", "midi_gen_onset_threshold_range", settings.onset_threshold);
    setNumPair("midi_gen_frame_threshold", "midi_gen_frame_threshold_range", settings.frame_threshold);
    setNumPair("midi_gen_minimum_note_length_ms", "midi_gen_minimum_note_length_ms_range", settings.minimum_note_length_ms);
    setVal("midi_gen_minimum_frequency", settings.minimum_frequency || "");
    setVal("midi_gen_maximum_frequency", settings.maximum_frequency || "");
    setCheckbox("midi_gen_multiple_pitch_bends", settings.multiple_pitch_bends);
    setCheckbox("midi_gen_melodia_trick", settings.melodia_trick);
    setNumPair("midi_gen_midi_tempo", "midi_gen_midi_tempo_range", settings.midi_tempo);
    setVal("midi_gen_out_dir", settings.out_dir);
  };

  // MIDI generation model status (like ACE-Step "Download Models")
  CDMF.refreshMidiGenModelStatus = async function () {
    try {
      var resp = await fetch("/models/midi_gen/status?_=" + Date.now(), { cache: "no-store" });
      if (!resp.ok) return;
      var data = await resp.json();
      if (!data || !data.ok) return;

      var notice = document.getElementById("midiGenModelStatusNotice");
      var submitBtn = document.getElementById("midiGenButton");
      var downloadBtn = document.getElementById("midiGenDownloadModelsBtn");

      var ready = !!data.ready;
      var state = data.state || "";
      var message = data.message || "";

      if (notice) {
        notice.style.display = ready ? "none" : "block";
        if (!ready && message) notice.textContent = message;
      }
      if (downloadBtn) {
        downloadBtn.style.display = ready ? "none" : "inline-flex";
      }
      if (submitBtn) {
        submitBtn.disabled = !ready && state !== "downloading";
        if (state === "downloading") {
          submitBtn.innerHTML = '<span class="icon">⏳</span><span>Downloading basic-pitch models…</span>';
        } else if (ready) {
          submitBtn.innerHTML = '<span class="icon">🎹</span><span>Generate MIDI</span>';
        }
      }
      return { ready: ready, state: state };
    } catch (e) {
      if (window.console) console.error("[MIDI Generation] refreshMidiGenModelStatus:", e);
      return { ready: false, state: "unknown" };
    }
  };

  CDMF.startMidiGenModelDownload = async function () {
    var submitBtn = document.getElementById("midiGenButton");
    var downloadBtn = document.getElementById("midiGenDownloadModelsBtn");
    var notice = document.getElementById("midiGenModelStatusNotice");
    var loadingBar = document.getElementById("midiGenLoadingBar");

    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span class="icon">⏳</span><span>Downloading basic-pitch models…</span>';
    }
    if (downloadBtn) downloadBtn.disabled = true;
    if (notice) {
      notice.style.display = "block";
      notice.textContent = "Downloading basic-pitch model (first use only). This may take several minutes. Keep this window open.";
    }
    if (loadingBar) {
      loadingBar.style.display = "block";
      updateMidiGenLoadingBarFraction(0);
    }

    try {
      var resp = await fetch("/models/midi_gen/ensure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      var data = await resp.json();
      if (!data || !data.ok) throw new Error(data.error || "Failed to start download");

      // Poll progress until done
      var poll = function () {
        fetch("/progress?_=" + Date.now(), { cache: "no-store" })
          .then(function (r) { return r.json(); })
          .then(function (prog) {
            var stage = prog.stage || "";
            var fraction = typeof prog.fraction === "number" ? prog.fraction : 0;
            var done = !!prog.done;
            var err = !!prog.error;

            updateMidiGenLoadingBarFraction(fraction);

            if (err) {
              if (loadingBar) loadingBar.style.display = "none";
              if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<span class="icon">🎹</span><span>Generate MIDI</span>';
              }
              if (downloadBtn) downloadBtn.disabled = false;
              CDMF.refreshMidiGenModelStatus();
              return;
            }
            if (done && (stage === "done" || stage === "midi_model_download" || fraction >= 0.999)) {
              if (loadingBar) loadingBar.style.display = "none";
              if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<span class="icon">🎹</span><span>Generate MIDI</span>';
              }
              if (downloadBtn) downloadBtn.disabled = false;
              CDMF.refreshMidiGenModelStatus();
              return;
            }
            setTimeout(poll, 500);
          })
          .catch(function () { setTimeout(poll, 1000); });
      };
      poll();
    } catch (err) {
      if (loadingBar) loadingBar.style.display = "none";
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<span class="icon">🎹</span><span>Generate MIDI</span>';
      }
      if (downloadBtn) downloadBtn.disabled = false;
      if (notice) notice.textContent = "Failed to start basic-pitch model download: " + err.message;
      if (CDMF.showToast) CDMF.showToast("Failed to start download: " + err.message, "error");
    }
  };

  // Initialize on DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      // Sync output directory when MIDI generation mode is activated
      var midiGenTab = document.querySelector('[data-mode="midi_gen"]');
      if (midiGenTab) {
        midiGenTab.addEventListener("click", function () {
          setTimeout(CDMF.syncMidiGenOutputDir, 100);
          setTimeout(CDMF.refreshMidiGenModelStatus, 150);
        });
      }

      var midiGenDownloadBtn = document.getElementById("midiGenDownloadModelsBtn");
      if (midiGenDownloadBtn) {
        midiGenDownloadBtn.addEventListener("click", function () {
          CDMF.startMidiGenModelDownload();
        });
      }
    });
  } else {
    // DOM already loaded
    var midiGenTab = document.querySelector('[data-mode="midi_gen"]');
    if (midiGenTab) {
      midiGenTab.addEventListener("click", function () {
        setTimeout(CDMF.syncMidiGenOutputDir, 100);
        setTimeout(CDMF.refreshMidiGenModelStatus, 150);
      });
    }
    var midiGenDownloadBtn = document.getElementById("midiGenDownloadModelsBtn");
    if (midiGenDownloadBtn) {
      midiGenDownloadBtn.addEventListener("click", function () {
        CDMF.startMidiGenModelDownload();
      });
    }
    CDMF.refreshMidiGenModelStatus();
  }
})();
