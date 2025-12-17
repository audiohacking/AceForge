// C:\CandyDungeonMusicForge\static\scripts\cdmf_generation_ui.js
(function () {
  "use strict";

  // ---------------------------------------------------------------------------
  // Shared state helper
  // ---------------------------------------------------------------------------
  function getState() {
    const CDMF = (window.CDMF = window.CDMF || {});
    if (!CDMF.state) {
      const initialReady = !!window.CANDY_MODELS_READY;
      const initialState = window.CANDY_MODEL_STATE || "unknown";
      const initialMessage = window.CANDY_MODEL_MESSAGE || "";

      CDMF.state = {
        // Model status
        candyModelsReady: initialReady,
        candyModelStatusState: initialState,
        candyModelStatusMessage: initialMessage,
        candyModelStatusTimer: null,

        // Button HTML snapshots (set on DOMContentLoaded in cdmf_main)
        candyGenerateButtonDefaultHTML: null,
        candyTrainButtonDefaultHTML: null,

        // Track list sort / filter state
        candyTrackSortKey: null,        // null = default (favorites first, then name)
        candyTrackSortDir: "asc",       // "asc" or "desc"
        candyTrackFilterCategories: new Set(),

        // Generation progress state
        progressTimer: null,
        candyIsGenerating: false,
        candyGenerationCounter: 0,
        candyActiveGenerationToken: 0,
        candyHasSeenWork: false,

        // Lyrics LLM status
        lyricsModelState: "unknown",        // "unknown" | "absent" | "downloading" | "ready" | "error"
        lyricsModelMessage: "",
        lyricsModelStatusTimer: null,
        autoPromptLyricsDefaultHTML: null
      };

      window.candyModelsReady = CDMF.state.candyModelsReady;
      window.candyModelStatusState = CDMF.state.candyModelStatusState;
      window.candyIsGenerating = CDMF.state.candyIsGenerating;
    }
    return CDMF.state;
  }

  const CDMF = (window.CDMF = window.CDMF || {});
  if (!CDMF.state) {
    getState();
  }

  // Lyrics LLM endpoints (allow override via CDMF_BOOT.urls, like MuFun)
  const lyricsUrls = (window.CDMF_BOOT && window.CDMF_BOOT.urls) || {};
  const LYRICS_STATUS_URL = lyricsUrls.lyricsStatus || "/lyrics/status";
  const LYRICS_ENSURE_URL = lyricsUrls.lyricsEnsure || "/lyrics/ensure";
  const LYRICS_GENERATE_URL = lyricsUrls.lyricsGenerate || "/lyrics/generate";

  // ---------------------------------------------------------------------------
  // Global guard: suppress play() during generation
  // ---------------------------------------------------------------------------
  (function patchMediaPlayGuard() {
    const OriginalPlay = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function (...args) {
      try {
        if (window.candyIsGenerating) {
          console.log(
            "[Candy Dungeon Music Forge] Suppressed play() during generation."
          );
          return Promise.resolve();
        }
      } catch (e) {
        // If anything goes wrong, fall back to normal behavior.
      }
      return OriginalPlay.apply(this, args);
    };
  })();

  // ---------------------------------------------------------------------------
  // Loading bar
  // ---------------------------------------------------------------------------
  function updateLoadingBarFraction(fraction) {
    const bar = document.getElementById("loadingBar");
    const inner = bar ? bar.querySelector(".loading-bar-inner") : null;
    if (!bar || !inner) return;

    let clamped = Math.max(0, Math.min(1, fraction || 0));

    // When models are downloading, treat the bar as indeterminate:
    // once it becomes non-zero, pin it to 100% with candystripe animation.
    if (window.candyDownloadingModels) {
      clamped = clamped > 0 ? 1 : 0;
    }

    if (clamped <= 0) {
      bar.classList.remove("active");
    } else {
      bar.classList.add("active");
    }
    inner.style.width = (clamped * 100).toFixed(1) + "%";
  }

  // ---------------------------------------------------------------------------
  // Model status banner + buttons
  // ---------------------------------------------------------------------------
  function applyModelStatusToUI(status) {
    if (!status) return;

    const state = getState();

    state.candyModelsReady = !!status.ready;
    state.candyModelStatusState = status.state || "unknown";
    state.candyModelStatusMessage = status.message || "";

    window.candyModelsReady = state.candyModelsReady;
    window.candyModelStatusState = state.candyModelStatusState;

    const notice = document.getElementById("modelStatusNotice");
    if (notice) {
      if (state.candyModelsReady) {
        notice.style.display = "none";
      } else {
        notice.style.display = "block";
        notice.textContent =
          state.candyModelStatusMessage ||
          'ACE-Step model is not downloaded yet. Click "Download Models" to start.';
      }
    }

    const generateBtn = document.getElementById("generateButton");
    const trainBtn = document.getElementById("btnStartTraining");

    // Keep the Training button in sync with the model status as well.
    (function applyTrainingButtonState() {
      if (!trainBtn) return;

      const ready = state.candyModelsReady;
      const st = state.candyModelStatusState || "unknown";

      // If training is already in progress, CDMF.onSubmitTraining will have
      // disabled the button and set its label. Don't override that while the
      // model is in a healthy "ready" state.
      if (trainBtn.disabled && ready && st === "ready") {
        return;
      }

      if (!ready && st === "downloading") {
        // Training model download in progress.
        trainBtn.disabled = true;
        trainBtn.textContent = "Downloading Training Model…";
        return;
      }

      if (ready && st === "ready") {
        // Training model ready → restore default "Start Training" HTML if we have it.
        trainBtn.disabled = false;
        if (state.candyTrainButtonDefaultHTML != null) {
          trainBtn.innerHTML = state.candyTrainButtonDefaultHTML;
        } else {
          trainBtn.textContent = "Start Training";
        }
        return;
      }

      // Absent / unknown / error → treat as "Download Training Model"
      trainBtn.disabled = false;
      trainBtn.textContent = "Download Training Model";
    })();

    if (!generateBtn) return;

    // If we're in the middle of a generation run,
    // don't fight the "Generating…" state.
    if (window.candyIsGenerating) {
      return;
    }

    if (state.candyModelsReady) {
      // Model is ready: restore normal Generate behavior and clear the bar.
      generateBtn.disabled = false;
      if (state.candyGenerateButtonDefaultHTML != null) {
        generateBtn.innerHTML = state.candyGenerateButtonDefaultHTML;
      } else {
        generateBtn.innerText = "Generate";
      }
      if (state.candyModelStatusTimer) {
        clearInterval(state.candyModelStatusTimer);
        state.candyModelStatusTimer = null;
      }
      updateLoadingBarFraction(0.0);
      window.candyDownloadingModels = false;
      return;
    }

    // Models are NOT ready yet.
    if (state.candyModelStatusState === "downloading") {
      // Download in progress: lock the button and show a clear label.
      generateBtn.disabled = true;
      generateBtn.innerText = "Downloading models…";

      // Keep polling status so we know when it flips to "ready" or "error".
      if (!state.candyModelStatusTimer) {
        state.candyModelStatusTimer = setInterval(function () {
          refreshModelStatusFromServer();
        }, 3000);
      }

      // Indeterminate bar while downloading
      window.candyDownloadingModels = true;
      updateLoadingBarFraction(1.0);
    } else {
      // Idle / error states (no active download).
      generateBtn.disabled = false;
      generateBtn.innerText = "Download Models";

      if (state.candyModelStatusTimer) {
        clearInterval(state.candyModelStatusTimer);
        state.candyModelStatusTimer = null;
      }

      window.candyDownloadingModels = false;
      updateLoadingBarFraction(0.0);
    }
  }

  async function refreshModelStatusFromServer() {
    try {
      const resp = await fetch("/models/status?_=" + Date.now(), {
        cache: "no-store",
      });
      if (!resp.ok) return;
      const data = await resp.json();
      if (!data || !data.ok) return;
      applyModelStatusToUI(data);
    } catch (err) {
      console.error("Failed to refresh model status:", err);
    }
  }

  // ---------------------------------------------------------------------------
  // Model download
  // ---------------------------------------------------------------------------
  async function startModelDownload() {
    const btn = document.getElementById("generateButton");
    const notice = document.getElementById("modelStatusNotice");

    window.candyDownloadingModels = true;

    if (btn) {
      btn.disabled = true;
      btn.innerText = "Downloading models…";
    }
    if (notice) {
      notice.style.display = "block";
      notice.textContent =
        "Downloading ACE-Step model from Hugging Face. This is a large download " +
        "and may take several minutes.\n" +
        "Keep this window and the console open; the console will show detailed progress.";
    }

    // Immediately flip the bar into indeterminate candy-stripe mode.
    updateLoadingBarFraction(1.0);

    try {
      const resp = await fetch("/models/ensure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      if (!resp.ok) {
        throw new Error("HTTP " + resp.status);
      }

      // No more /progress polling for downloads.
      // Just keep the status banner and button state in sync.
      await refreshModelStatusFromServer();
    } catch (err) {
      console.error("Failed to start model download:", err);
      window.candyDownloadingModels = false;

      if (btn) {
        btn.disabled = false;
        btn.innerText = "Download Models";
      }
      if (notice) {
        notice.style.display = "block";
        notice.textContent = "Failed to start model download: " + err;
      }
      updateLoadingBarFraction(0.0);
    }
  }

  // ---------------------------------------------------------------------------
  // Generation progress polling (/progress)
  // ---------------------------------------------------------------------------
  async function pollGenerationProgress(token) {
    const state = getState();

    try {
      const resp = await fetch("/progress?_=" + Date.now(), {
        cache: "no-store",
      });
      if (!resp.ok) return;

      const data = await resp.json();
      if (!data) return;

      // Ignore stale responses from previous runs.
      if (token !== state.candyActiveGenerationToken) {
        return;
      }

      const fraction =
        typeof data.fraction === "number" ? data.fraction : 0;
      const stage = data.stage || "";
      const isModelDownload = stage === "ace_model_download";

      updateLoadingBarFraction(fraction);

      const btn = document.getElementById("generateButton");
      if (btn && !data.done && !data.error) {
        btn.disabled = true;
        btn.innerText = isModelDownload ? "Downloading models…" : "Generating…";
      }

      // Non-terminal progress = real work
      const sawNonterminal =
        !data.error &&
        !data.done &&
        stage !== "done" &&
        fraction < 0.999;

      if (sawNonterminal) {
        state.candyHasSeenWork = true;
      }

      const isFinished =
        !!data.error ||
        (state.candyHasSeenWork &&
          (data.done || stage === "done" || fraction >= 0.999));

      if (isFinished) {
        if (state.progressTimer) {
          clearInterval(state.progressTimer);
          state.progressTimer = null;
        }

        updateLoadingBarFraction(1.0);

        if (btn) {
          if (isModelDownload) {
            // Final state will be set by applyModelStatusToUI()
            btn.disabled = false;
          } else {
            btn.disabled = false;
            btn.innerText = "Generate";
          }
        }

        // Allow playback again now that generation has fully completed.
        if (!isModelDownload) {
          state.candyIsGenerating = false;
          window.candyIsGenerating = false;
        }

        if (isModelDownload) {
          // Model download finished (success or error): sync status so the
          // banner and button label are correct.
          window.candyDownloadingModels = false;
          await refreshModelStatusFromServer();
        } else {
          // Track generation finished: refresh tracks and auto-play newest.
          if (
            window.CDMF &&
            typeof window.CDMF.refreshTracksAfterGeneration === "function"
          ) {
            await window.CDMF.refreshTracksAfterGeneration({
              autoplay: true,
            });
          }
        }

        updateLoadingBarFraction(0.0);
      }
    } catch (err) {
      console.error("Error polling generation progress:", err);
    }
  }

  function startProgressPolling() {
    const state = getState();

    if (state.progressTimer) {
      clearInterval(state.progressTimer);
      state.progressTimer = null;
    }

    // New generation run → reset "has seen work" flag.
    state.candyHasSeenWork = false;

    // Bump generation token and start a fresh poll cycle tied to it.
    state.candyGenerationCounter += 1;
    state.candyActiveGenerationToken = state.candyGenerationCounter;
    const token = state.candyActiveGenerationToken;

    pollGenerationProgress(token);
    state.progressTimer = setInterval(function () {
      pollGenerationProgress(token);
    }, 800);
  }

  // ---------------------------------------------------------------------------
  // Main /generate form submit handler
  // ---------------------------------------------------------------------------
  function onSubmitForm(ev) {
    const state = getState();

    // If the ACE model is not ready yet, repurpose this submit as
    // a "Download Models" action instead of sending /generate.
    if (!state.candyModelsReady) {
      if (ev && ev.preventDefault) {
        ev.preventDefault();
      }
      startModelDownload();
      return false;
    }

    // Sync Audio2Audio flag with the file selector
    try {
      const form = ev && ev.target ? ev.target : document;
      const refFileInput =
        form.querySelector
          ? form.querySelector("#ref_audio_file")
          : document.getElementById("ref_audio_file");
      const a2aField =
        form.querySelector
          ? form.querySelector("#audio2audio_enable")
          : document.getElementById("audio2audio_enable");

      if (refFileInput && a2aField) {
        const hasFile =
          refFileInput.files && refFileInput.files.length > 0;

        if (a2aField.type === "hidden") {
          // Hidden flag: backend reads truthiness of the value.
          a2aField.value = hasFile ? "1" : "";
        } else {
          // Checkbox flag.
          a2aField.checked = hasFile;
        }
      }
    } catch (e) {
      console.warn(
        "[Candy Dungeon Music Forge] Failed to sync audio2audio flag:",
        e
      );
    }

    // Handle seed / random-seed behavior before submitting the form
    try {
      const seedInput = document.getElementById("seed");
      const randomCheckbox = document.getElementById("seed_random");

      if (seedInput) {
        if (randomCheckbox && randomCheckbox.checked) {
          // Pick a new random 32-bit-ish positive integer on each Generate
          const newSeed = Math.floor(Math.random() * 2147483647) + 1;
          seedInput.value = String(newSeed);
        } else {
          // Random is OFF: if the box is empty, default to 0
          const raw = String(seedInput.value || "").trim();
          if (!raw) {
            seedInput.value = "0";
          }
        }
      }
    } catch (e) {
      console.warn(
        "[Candy Dungeon Music Forge] Failed to prepare seed:",
        e
      );
    }

    const btn = document.getElementById("generateButton");
    if (btn) {
      btn.disabled = true;
      btn.innerText = "Generating…";
    }

    // Mark that we are generating; nothing should be playing now.
    state.candyIsGenerating = true;
    window.candyIsGenerating = true;

    // Stop any currently playing audio in the main page and clear its source
    try {
      const audio = document.getElementById("audioPlayer");
      if (audio) {
        audio.pause();
        audio.currentTime = 0;
        audio.removeAttribute("src");
        audio.load();
      }

      // Also stop any audio element inside the hidden iframe, if it exists.
      const iframe = document.getElementById("generation_frame");
      if (
        iframe &&
        iframe.contentWindow &&
        iframe.contentWindow.document
      ) {
        const iframeAudio =
          iframe.contentWindow.document.getElementById("audioPlayer");
        if (iframeAudio) {
          iframeAudio.pause();
          iframeAudio.currentTime = 0;
          iframeAudio.removeAttribute("src");
          iframeAudio.load();
        }
      }
    } catch (e) {
      console.warn(
        "[Candy Dungeon Music Forge] Failed to reset iframe audio:",
        e
      );
    }

    updateLoadingBarFraction(0.1); // immediate visual feedback
    startProgressPolling();

    return true;
  }

  // ---------------------------------------------------------------------------
  // Lyrics LLM status helpers (button label / download vs suggest)
  // ---------------------------------------------------------------------------
  function applyLyricsStatusToUI(status) {
    const state = getState();
    const btn = document.getElementById("btnAutoPromptLyrics");
		state.lyricsModelState = "downloading";
    if (!btn) return;

    const st = (status && status.state) || "unknown";
    const message = (status && status.message) || "";

    state.lyricsModelState = st;
    state.lyricsModelMessage = message;

    if (state.autoPromptLyricsDefaultHTML == null) {
      state.autoPromptLyricsDefaultHTML = btn.innerHTML;
    }

    if (st === "ready") {
      btn.disabled = false;
      btn.innerHTML =
        state.autoPromptLyricsDefaultHTML ||
        '<span class="icon">✨</span><span class="label">Suggest</span>';
    } else if (st === "downloading") {
      btn.disabled = true;
      btn.innerHTML =
        '<span class="icon">⬇</span><span class="label">Downloading…</span>';
    } else {
      // absent / unknown / error → act as "Download Lyrics Model"
      btn.disabled = false;
      btn.innerHTML =
        '<span class="icon">⬇</span><span class="label">Download Lyrics/Prompt Autogen Model</span>';
    }

    // Handle polling timer like MuFun does
    if (st === "downloading") {
      if (!state.lyricsModelStatusTimer) {
        state.lyricsModelStatusTimer = setInterval(function () {
          refreshLyricsStatusFromServer();
        }, 5000);
      }
    } else if (state.lyricsModelStatusTimer) {
      clearInterval(state.lyricsModelStatusTimer);
      state.lyricsModelStatusTimer = null;
    }
  }

  async function refreshLyricsStatusFromServer() {
    if (!window.fetch) return;

    try {
      const resp = await fetch(LYRICS_STATUS_URL, {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store"
      });
      if (!resp.ok) return;
      const data = await resp.json();
      if (!data || !data.ok) return;
      applyLyricsStatusToUI(data);
    } catch (err) {
      console.error("[CDMF] /lyrics/status error", err);
    }
  }

  async function ensureLyricsModel() {
    if (!window.fetch) {
      alert(
        "This browser does not support fetch(); cannot install lyrics model."
      );
      return;
    }

    const state = getState();
    const btn = document.getElementById("btnAutoPromptLyrics");

    if (btn) {
      if (state.autoPromptLyricsDefaultHTML == null) {
        state.autoPromptLyricsDefaultHTML = btn.innerHTML;
      }
      btn.disabled = true;
      btn.innerHTML =
        '<span class="icon">⬇</span><span class="label">Downloading…</span>';
    }

    try {
      const resp = await fetch(LYRICS_ENSURE_URL, {
        method: "POST",
        headers: { Accept: "application/json" }
      });
      const data = await resp.json().catch(function () { return null; });

      if (!resp.ok || !data || !data.ok) {
        throw new Error(
          (data && data.error) || "Lyrics model ensure failed."
        );
      }

      // Let /lyrics/status drive the button label while downloading / once ready.
      await refreshLyricsStatusFromServer();
    } catch (err) {
      console.error("[CDMF] /lyrics/ensure error", err);
      alert(
        "Failed to start lyrics model download.\n\n" + String(err)
      );
      state.lyricsModelState = "error";

      if (btn) {
        btn.disabled = false;
        btn.innerHTML =
          '<span class="icon">⬇</span><span class="label">Download Lyrics Model</span>';
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Concept → Prompt/Lyrics helper (modal-driven)
  // ---------------------------------------------------------------------------

  function showLyricsBusyOverlay() {
    var overlay = document.getElementById("lyricsBusyOverlay");
    if (overlay) {
      overlay.style.display = "flex";
    }
  }

  function hideLyricsBusyOverlay() {
    var overlay = document.getElementById("lyricsBusyOverlay");
    if (overlay) {
      overlay.style.display = "none";
    }
  }

  function _getAutoPromptLyricsMode() {
    // mode: "prompt", "lyrics", or "both"
    var mode = "both";
    var radios = document.getElementsByName("apl_mode");
    if (radios && radios.length) {
      for (var i = 0; i < radios.length; i++) {
        var r = radios[i];
        if (r.checked && r.value) {
          mode = r.value;
          break;
        }
      }
    }
    var doPrompt = mode === "prompt" || mode === "both";
    var doLyrics = mode === "lyrics" || mode === "both";
    return { mode: mode, doPrompt: doPrompt, doLyrics: doLyrics };
  }

  async function autoPromptLyricsFromConcept() {
    const conceptEl = document.getElementById("apl_concept");

    // Anchor to the main Generate form so we always hit the real fields,
    // not anything in the modal or hidden templates.
    const generateForm =
      document.getElementById("generateForm") || document;

    const promptEl =
      (generateForm.querySelector(
        "#prompt, textarea[name='prompt'], input[name='prompt']"
      )) || document.getElementById("prompt");

    const lyricsEl =
      (generateForm.querySelector(
        "#lyrics, textarea[name='lyrics'], input[name='lyrics']"
      )) || document.getElementById("lyrics");

    const basenameEl = document.getElementById("basename");

    if (!conceptEl) {
      alert("Prompt/lyrics modal is missing its concept field.");
      return;
    }

    const concept = conceptEl.value.trim();
    if (!concept) {
      alert(
        "Please enter a short song concept first.\n" +
          'For example: "melancholic SNES overworld at night".'
      );
      conceptEl.focus();
      return;
    }

    const modeInfo = _getAutoPromptLyricsMode();
    const doPrompt = modeInfo.doPrompt;
    const doLyrics = modeInfo.doLyrics;

    if (!doPrompt && !doLyrics) {
      alert("Nothing to generate. Please choose prompt, lyrics, or both.");
      return;
    }

    const existingPrompt = promptEl ? promptEl.value : "";
    const existingLyrics = lyricsEl ? lyricsEl.value : "";

    const urls = (window.CDMF && window.CDMF_BOOT && window.CDMF_BOOT.urls) || {};
    const endpoint =
      (urls && urls.promptLyricsGenerate) || "/prompt_lyrics/generate";

    const payload = {
      concept: concept,
      do_prompt: doPrompt,
      do_lyrics: doLyrics,
      existing_prompt: existingPrompt,
      existing_lyrics: existingLyrics
    };

    const targetSecondsEl = document.getElementById("target_seconds");
    if (targetSecondsEl && targetSecondsEl.value) {
      const v = parseFloat(targetSecondsEl.value);
      if (!Number.isNaN(v) && v > 0) {
        payload.target_seconds = v;
      }
    }

    // Use the **modal** Generate button here
    const btn = document.getElementById("apl_generate");
    const originalHTML = btn ? btn.innerHTML : null;

    // 🔸 START SPINNER + dim overlay (full-page overlay)
    showLyricsBusyOverlay();

    if (btn) {
      btn.disabled = true;
      btn.innerHTML =
        '<span class="icon">⏳</span><span class="label">Generating…</span>';
    }

    try {
      const resp = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json"
        },
        body: JSON.stringify(payload)
      });

      if (!resp.ok) {
        throw new Error("HTTP " + resp.status);
      }

      const data = await resp.json().catch(function () { return null; });

      console.log("[CDMF] autoPromptLyricsFromConcept response:", data);

      if (!data || !data.ok) {
        throw new Error(
          (data && data.error) || "Prompt/lyrics generation failed."
        );
      }

      if (doPrompt && promptEl && typeof data.prompt === "string") {
        promptEl.value = data.prompt;

        // Let any listeners know the field changed
        try {
          const evt = new Event("input", { bubbles: true });
          promptEl.dispatchEvent(evt);
        } catch (e) {
          // non-fatal
        }
      }

      if (doLyrics && lyricsEl && typeof data.lyrics === "string") {
        lyricsEl.value = data.lyrics;

        try {
          const evt = new Event("input", { bubbles: true });
          lyricsEl.dispatchEvent(evt);
        } catch (e) {
          // non-fatal
        }

        // Ensure the lyrics row is visible if we just populated it.
        const lyricsRow = document.getElementById("lyricsRow");
        if (lyricsRow) {
          lyricsRow.style.display = "flex";
        }
      }

      // NEW: populate Base filename from generated title if present
      if (basenameEl && typeof data.title === "string") {
        const rawTitle = data.title.trim();
        if (rawTitle) {
          // Basic Windows-safe cleanup (strip invalid filename chars)
          const safeTitle = rawTitle.replace(/[<>:"/\\|?*]/g, "").trim();
          if (safeTitle) {
            basenameEl.value = safeTitle;
            try {
              const evt = new Event("input", { bubbles: true });
              basenameEl.dispatchEvent(evt);
            } catch (e) {
              // non-fatal
            }
          }
        }
      }

      // Close modal on success
      CDMF.closeAutoPromptLyricsModal();
    } catch (err) {
      console.error(
        "[Candy Dungeon Music Forge] Auto prompt/lyrics error:",
        err
      );
      alert(
        "Failed to generate prompt/lyrics from concept.\n\n" +
          String(err)
      );
    } finally {
      // 🔸 STOP SPINNER + dim overlay
      hideLyricsBusyOverlay();

      if (btn) {
        btn.disabled = false;
        if (originalHTML != null) {
          btn.innerHTML = originalHTML;
        }
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Initial lyrics status probe (so button label is correct on load)
  // ---------------------------------------------------------------------------
  try {
    if (window.fetch) {
      refreshLyricsStatusFromServer();
    }
  } catch (e) {
    // non-fatal
  }

  // ---------------------------------------------------------------------------
  // Modal open/close helpers for auto prompt / lyrics
  // ---------------------------------------------------------------------------

  // Click handler for the *panel* button:
  // - If lyrics model is not ready -> start download and disable button.
  // - If ready -> open the modal.
  function onAutoPromptLyricsButtonClick() {
    const state = getState();
    const st = state.lyricsModelState || "unknown";

    if (st !== "ready") {
      // Not installed / downloading / errored → trigger ensure.
      ensureLyricsModel();
      return;
    }

    openAutoPromptLyricsModal();
  }

  function openAutoPromptLyricsModal() {
    const modal = document.getElementById("autoPromptLyricsModal");
    if (!modal) {
      alert("Prompt/lyrics modal container not found in the page.");
      return;
    }

    const conceptEl = document.getElementById("apl_concept");
    if (conceptEl) {
      // Start with whatever text was last used in prompt, as a convenience,
      // or leave empty if you prefer a fresh concept each time.
      conceptEl.focus();
    }

    const instrumentalCheckbox = document.getElementById("instrumental");
    const promptOnly = document.getElementById("apl_mode_prompt");
    const lyricsOnly = document.getElementById("apl_mode_lyrics");
    const both = document.getElementById("apl_mode_both");

    if (promptOnly && lyricsOnly && both) {
      if (instrumentalCheckbox && instrumentalCheckbox.checked) {
        // Instrumental → default to prompt only
        promptOnly.checked = true;
        lyricsOnly.checked = false;
        both.checked = false;
      } else {
        // Vocal-capable → default to prompt + lyrics
        promptOnly.checked = false;
        lyricsOnly.checked = false;
        both.checked = true;
      }
    }

    modal.style.display = "flex";
  }

  function closeAutoPromptLyricsModal() {
    const modal = document.getElementById("autoPromptLyricsModal");
    if (modal) {
      modal.style.display = "none";
    }
  }

  // ---------------------------------------------------------------------------
  // Exports
  // ---------------------------------------------------------------------------
  CDMF.updateLoadingBarFraction = updateLoadingBarFraction;
  CDMF.applyModelStatusToUI = applyModelStatusToUI;
  CDMF.refreshModelStatusFromServer = refreshModelStatusFromServer;
  CDMF.startModelDownload = startModelDownload;
  CDMF.startProgressPolling = startProgressPolling;
  CDMF.onSubmitForm = onSubmitForm;
  CDMF.autoPromptLyricsFromConcept = autoPromptLyricsFromConcept;
  CDMF.onAutoPromptLyricsButtonClick = onAutoPromptLyricsButtonClick;
  CDMF.openAutoPromptLyricsModal = openAutoPromptLyricsModal;
  CDMF.closeAutoPromptLyricsModal = closeAutoPromptLyricsModal;

  // Optional: expose overlay spinner to other modules
  CDMF.showModalSpinner = showLyricsBusyOverlay;
  CDMF.hideModalSpinner = hideLyricsBusyOverlay;
})();
