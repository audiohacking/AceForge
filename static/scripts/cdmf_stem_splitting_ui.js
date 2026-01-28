// cdmf_stem_splitting_ui.js
// Stem splitting form submission and UI handling

(function () {
  "use strict";

  window.CDMF = window.CDMF || {};
  var CDMF = window.CDMF;

  // Update loading bar fraction (similar to generation)
  function updateStemSplitLoadingBarFraction(fraction) {
    var bar = document.getElementById("stemSplitLoadingBar");
    var inner = bar ? bar.querySelector(".loading-bar-inner") : null;
    if (inner) {
      var pct = Math.max(0, Math.min(100, fraction * 100));
      inner.style.width = pct + "%";
      if (bar) {
        bar.classList.add("active");
      }
    }
  }

  // Poll progress during stem splitting
  async function pollStemSplitProgress(token) {
    var state = window.CDMF && window.CDMF.state ? window.CDMF.state : {};
    if (!state.stemSplitActiveToken || state.stemSplitActiveToken !== token) {
      return;
    }

    try {
      var resp = await fetch("/progress?_=" + Date.now(), {
        cache: "no-store",
      });
      if (!resp.ok) return;

      var data = await resp.json();
      if (!data) return;

      // Ignore stale responses
      if (token !== state.stemSplitActiveToken) {
        return;
      }

      var fraction = typeof data.fraction === "number" ? data.fraction : 0;
      var stage = data.stage || "";
      var isStemSplit = stage.indexOf("stem_split") === 0;

      if (isStemSplit) {
        updateStemSplitLoadingBarFraction(fraction);

        var btn = document.getElementById("stemSplitButton");
        if (btn && !data.done && !data.error) {
          btn.disabled = true;
          btn.innerHTML = '<span class="icon">⏳</span><span>Splitting...</span>';
        }
      }

      var isFinished = !!data.error || (data.done && (stage === "stem_split_done" || stage === "stem_split_error"));

      if (isFinished) {
        if (state.stemSplitProgressTimer) {
          clearInterval(state.stemSplitProgressTimer);
          state.stemSplitProgressTimer = null;
        }

        updateStemSplitLoadingBarFraction(data.error ? 0 : 1.0);

        var btn = document.getElementById("stemSplitButton");
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<span class="icon">🎚️</span><span>Split Stems</span>';
        }

        state.stemSplitActiveToken = null;
      } else {
        // Continue polling
        setTimeout(function () {
          pollStemSplitProgress(token);
        }, 500);
      }
    } catch (error) {
      if (window.console) {
        console.error("[Stem Splitting] Progress poll error:", error);
      }
      // Continue polling even on error
      setTimeout(function () {
        pollStemSplitProgress(token);
      }, 1000);
    }
  }

  CDMF.onSubmitStemSplit = function (event) {
    event.preventDefault();

    // If Demucs model is not ready, trigger download (like ACE-Step "Download Models")
    var statusEl = document.getElementById("stemSplitModelStatusNotice");
    var downloadBtn = document.getElementById("stemSplitDownloadModelsBtn");
    if (downloadBtn && downloadBtn.style.display !== "none" && downloadBtn.offsetParent !== null) {
      CDMF.startStemSplitModelDownload();
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
    var loadingBar = document.getElementById("stemSplitLoadingBar");
    if (loadingBar) {
      loadingBar.style.display = "block";
      updateStemSplitLoadingBarFraction(0.0);
    }
    
    // Disable submit button
    var submitBtn = document.getElementById("stemSplitButton");
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span class="icon">⏳</span><span>Splitting...</span>';
    }
    
    // Set up progress polling
    var state = window.CDMF && window.CDMF.state ? window.CDMF.state : {};
    state.stemSplitActiveToken = Date.now();
    if (state.stemSplitProgressTimer) {
      clearInterval(state.stemSplitProgressTimer);
    }
    state.stemSplitProgressTimer = setInterval(function () {
      pollStemSplitProgress(state.stemSplitActiveToken);
    }, 500);
    
    // Make API call
    fetch("/stem_split", {
      method: "POST",
      body: formData,
    })
      .then(function (response) {
        return response.json();
      })
      .then(function (data) {
        // Stop progress polling
        var state = window.CDMF && window.CDMF.state ? window.CDMF.state : {};
        if (state.stemSplitProgressTimer) {
          clearInterval(state.stemSplitProgressTimer);
          state.stemSplitProgressTimer = null;
        }
        state.stemSplitActiveToken = null;
        
        // Hide loading bar
        if (loadingBar) {
          loadingBar.style.display = "none";
        }
        
        // Re-enable submit button
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<span class="icon">🎚️</span><span>Split Stems</span>';
        }
        
        if (data.error) {
          // Show error message
          var errorMsg = data.message || "Stem splitting failed";
          if (CDMF.showToast) {
            CDMF.showToast(errorMsg, "error");
          } else {
            alert(errorMsg);
          }
          if (data.details && window.console) {
            console.error("[Stem Splitting] Error details:", data.details);
          }
        } else {
          // Show success message
          var successMsg = data.message || "Stem splitting completed!";
          if (CDMF.showToast) {
            CDMF.showToast(successMsg, "success");
          } else {
            console.log("[Stem Splitting] " + successMsg);
          }
          
          // Refresh Music Player to show the new files
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
        // Stop progress polling
        var state = window.CDMF && window.CDMF.state ? window.CDMF.state : {};
        if (state.stemSplitProgressTimer) {
          clearInterval(state.stemSplitProgressTimer);
          state.stemSplitProgressTimer = null;
        }
        state.stemSplitActiveToken = null;
        
        // Hide loading bar
        if (loadingBar) {
          loadingBar.style.display = "none";
        }
        
        // Re-enable submit button
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<span class="icon">🎚️</span><span>Split Stems</span>';
        }
        
        // Show error
        var errorMsg = "Stem splitting failed: " + error.message;
        if (CDMF.showToast) {
          CDMF.showToast(errorMsg, "error");
        } else {
          alert(errorMsg);
        }
        if (window.console) {
          console.error("[Stem Splitting] Request failed:", error);
        }
      });
    
    return false;
  };

  // Stem split model status (like ACE-Step "Download Models")
  CDMF.refreshStemSplitModelStatus = async function () {
    try {
      var resp = await fetch("/models/stem_split/status?_=" + Date.now(), { cache: "no-store" });
      if (!resp.ok) return;
      var data = await resp.json();
      if (!data || !data.ok) return;

      var notice = document.getElementById("stemSplitModelStatusNotice");
      var submitBtn = document.getElementById("stemSplitButton");
      var downloadBtn = document.getElementById("stemSplitDownloadModelsBtn");

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
          submitBtn.innerHTML = '<span class="icon">⏳</span><span>Downloading Demucs models…</span>';
        } else if (ready) {
          submitBtn.innerHTML = '<span class="icon">🎚️</span><span>Split Stems</span>';
        }
      }
      return { ready: ready, state: state };
    } catch (e) {
      if (window.console) console.error("[Stem Splitting] refreshStemSplitModelStatus:", e);
      return { ready: false, state: "unknown" };
    }
  };

  CDMF.startStemSplitModelDownload = async function () {
    var submitBtn = document.getElementById("stemSplitButton");
    var downloadBtn = document.getElementById("stemSplitDownloadModelsBtn");
    var notice = document.getElementById("stemSplitModelStatusNotice");
    var loadingBar = document.getElementById("stemSplitLoadingBar");

    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span class="icon">⏳</span><span>Downloading Demucs models…</span>';
    }
    if (downloadBtn) downloadBtn.disabled = true;
    if (notice) {
      notice.style.display = "block";
      notice.textContent = "Downloading Demucs model (first use only). This may take several minutes. Keep this window open.";
    }
    if (loadingBar) {
      loadingBar.style.display = "block";
      updateStemSplitLoadingBarFraction(0);
    }

    try {
      var resp = await fetch("/models/stem_split/ensure", {
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

            updateStemSplitLoadingBarFraction(fraction);

            if (err) {
              if (loadingBar) loadingBar.style.display = "none";
              if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<span class="icon">🎚️</span><span>Split Stems</span>';
              }
              if (downloadBtn) downloadBtn.disabled = false;
              CDMF.refreshStemSplitModelStatus();
              return;
            }
            if (done && (stage === "done" || stage === "stem_split_done" || fraction >= 0.999)) {
              if (loadingBar) loadingBar.style.display = "none";
              if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<span class="icon">🎚️</span><span>Split Stems</span>';
              }
              if (downloadBtn) downloadBtn.disabled = false;
              CDMF.refreshStemSplitModelStatus();
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
        submitBtn.innerHTML = '<span class="icon">🎚️</span><span>Split Stems</span>';
      }
      if (downloadBtn) downloadBtn.disabled = false;
      if (notice) notice.textContent = "Failed to start Demucs model download: " + err.message;
      if (CDMF.showToast) CDMF.showToast("Failed to start download: " + err.message, "error");
    }
  };

  // Sync output directory from Settings when stem splitting form is shown
  CDMF.syncStemSplitOutputDir = function () {
    var outDirSettings = document.getElementById("out_dir_settings");
    var outDirStemSplit = document.getElementById("stem_split_out_dir");

    if (outDirSettings && outDirStemSplit) {
      outDirStemSplit.value = outDirSettings.value;
    }
  };

  // Apply stem split track metadata into the Stem Splitting form (used by "copy settings" in Music Player)
  CDMF.applyStemSplitSettingsToForm = function (settings) {
    if (!settings) return;

    if (typeof CDMF.switchMode === "function") {
      CDMF.switchMode("stem_split");
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

    setVal("stem_split_stem_count", settings.stem_count);
    setVal("stem_split_device", settings.device_preference);
    setVal("stem_split_mode", settings.mode || "");
    setVal("stem_split_export_format", settings.export_format);
    setVal("stem_split_out_dir", settings.out_dir);
  };

  // Update mode-specific UI when stem_count or mode changes
  CDMF.updateStemSplitModeUI = function () {
    var stemCountSelect = document.getElementById("stem_split_stem_count");
    var modeSelect = document.getElementById("stem_split_mode");
    
    if (!stemCountSelect || !modeSelect) return;
    
    var stemCount = parseInt(stemCountSelect.value, 10);
    var mode = modeSelect.value;
    
    // Enable/disable mode options based on stem_count
    // Mode options are only relevant for 2-stem mode
    if (stemCount === 2) {
      modeSelect.disabled = false;
    } else {
      // For 4-stem and 6-stem, clear mode selection
      if (mode) {
        modeSelect.value = "";
      }
      modeSelect.disabled = true;
    }
  };

  // Initialize on DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      // Sync output directory when stem splitting mode is activated
      var stemSplitTab = document.querySelector('[data-mode="stem_split"]');
      if (stemSplitTab) {
        stemSplitTab.addEventListener("click", function () {
          setTimeout(CDMF.syncStemSplitOutputDir, 100);
          setTimeout(CDMF.refreshStemSplitModelStatus, 150);
        });
      }

      var stemSplitDownloadBtn = document.getElementById("stemSplitDownloadModelsBtn");
      if (stemSplitDownloadBtn) {
        stemSplitDownloadBtn.addEventListener("click", function () {
          CDMF.startStemSplitModelDownload();
        });
      }
      
      // Wire up stem_count and mode change handlers
      var stemCountSelect = document.getElementById("stem_split_stem_count");
      var modeSelect = document.getElementById("stem_split_mode");
      if (stemCountSelect) {
        stemCountSelect.addEventListener("change", CDMF.updateStemSplitModeUI);
      }
      if (modeSelect) {
        modeSelect.addEventListener("change", CDMF.updateStemSplitModeUI);
      }
      
      // Initial UI update
      CDMF.updateStemSplitModeUI();
      CDMF.refreshStemSplitModelStatus();
    });
  } else {
    // DOM already loaded
    var stemSplitTab = document.querySelector('[data-mode="stem_split"]');
    if (stemSplitTab) {
      stemSplitTab.addEventListener("click", function () {
        setTimeout(CDMF.syncStemSplitOutputDir, 100);
        setTimeout(CDMF.refreshStemSplitModelStatus, 150);
      });
    }
    var stemSplitDownloadBtn = document.getElementById("stemSplitDownloadModelsBtn");
    if (stemSplitDownloadBtn) {
      stemSplitDownloadBtn.addEventListener("click", function () {
        CDMF.startStemSplitModelDownload();
      });
    }
    CDMF.refreshStemSplitModelStatus();
    
    // Wire up stem_count and mode change handlers
    var stemCountSelect = document.getElementById("stem_split_stem_count");
    var modeSelect = document.getElementById("stem_split_mode");
    if (stemCountSelect) {
      stemCountSelect.addEventListener("change", CDMF.updateStemSplitModeUI);
    }
    if (modeSelect) {
      modeSelect.addEventListener("change", CDMF.updateStemSplitModeUI);
    }
    
    // Initial UI update
    CDMF.updateStemSplitModeUI();
  }
})();
