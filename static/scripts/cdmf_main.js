// C:\CandyDungeonMusicForge\static\scripts\cdmf_main.js
// High-level orchestration + knob tabs + training controls.
(function () {
  "use strict";

  const IS_EMBEDDED = !!window.frameElement;

  // ---------------------------------------------------------------------------
  // Shared state helper (same shape as other modules)
  // ---------------------------------------------------------------------------
  function getState() {
    const CDMF = (window.CDMF = window.CDMF || {});
    if (!CDMF.state) {
      const initialReady = !!window.CANDY_MODELS_READY;
      const initialState = window.CANDY_MODEL_STATE || "unknown";
      const initialMessage = window.CANDY_MODEL_MESSAGE || "";

      CDMF.state = {
        candyModelsReady: initialReady,
        candyModelStatusState: initialState,
        candyModelStatusMessage: initialMessage,
        candyModelStatusTimer: null,
        candyGenerateButtonDefaultHTML: null,
        candyTrainButtonDefaultHTML: null,
        candyTrackSortKey: null,
        candyTrackSortDir: "asc",
        candyTrackFilterCategories: new Set(),
        progressTimer: null,
        candyIsGenerating: false,
        candyGenerationCounter: 0,
        candyActiveGenerationToken: 0,
        candyHasSeenWork: false,
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

  // ---------------------------------------------------------------------------
  // Knob tabs + details toggle (core vs advanced, details accordion)
  // ---------------------------------------------------------------------------
  function switchKnobTab(which) {
    const core = document.getElementById("coreKnobs");
    const adv = document.getElementById("advancedKnobs");
    const tabCore = document.getElementById("tab_core");
    const tabAdv = document.getElementById("tab_advanced");

    const showAdvanced = which === "advanced";

    if (core) core.style.display = showAdvanced ? "none" : "";
    if (adv) adv.style.display = showAdvanced ? "" : "none";

    if (tabCore) {
      if (showAdvanced) tabCore.classList.remove("tab-btn-active");
      else tabCore.classList.add("tab-btn-active");
    }
    if (tabAdv) {
      if (showAdvanced) tabAdv.classList.add("tab-btn-active");
      else tabAdv.classList.remove("tab-btn-active");
    }
  }

  function toggleDetails() {
    const panel = document.getElementById("detailsPanel");
    if (!panel) return;
    const current = panel.style.display || "";
    panel.style.display =
      current === "none" || !current ? "block" : "none";
  }

  CDMF.switchKnobTab = switchKnobTab;
  CDMF.toggleDetails = toggleDetails;

  // Optional helper if anything ever calls switchKnobTab() directly
  window.switchKnobTab = function (which) {
    if (window.CDMF && typeof window.CDMF.switchKnobTab === "function") {
      window.CDMF.switchKnobTab(which);
    }
  };

  // ---------------------------------------------------------------------------
  // Training: Pause / Resume / Cancel controls
  // ---------------------------------------------------------------------------
  function initTrainingControls() {
    const btnPause = document.getElementById("btnPauseTraining");
    const btnResume = document.getElementById("btnResumeTraining");
    const btnCancel = document.getElementById("btnCancelTraining");

    if (!btnPause && !btnResume && !btnCancel) {
      return;
    }

    async function postTrainingCommand(endpoint) {
      try {
        const resp = await fetch(endpoint, { method: "POST" });
        const data = await resp.json();
        if (!data.ok) throw new Error(data.error || "Unknown error");
        alert(data.message || "OK");
        await refreshTrainingStatus();
      } catch (err) {
        console.error("Training command failed:", err);
        alert("Error: " + err.message);
      }
    }

    if (btnPause) {
      btnPause.addEventListener("click", function () {
        postTrainingCommand("/train_lora/pause");
      });
    }

    if (btnResume) {
      btnResume.addEventListener("click", function () {
        postTrainingCommand("/train_lora/resume");
      });
    }

    if (btnCancel) {
      btnCancel.addEventListener("click", function () {
        if (
          confirm(
            "Cancel this training run? Unsaved progress will be lost."
          )
        ) {
          postTrainingCommand("/train_lora/cancel");
        }
      });
    }

    async function refreshTrainingStatus() {
      try {
        const resp = await fetch("/train_lora/status");
        const state = await resp.json();
        const running = !!state.running;
        const paused = !!state.paused;

        if (btnPause) btnPause.disabled = !running || paused;
        if (btnCancel) btnCancel.disabled = !running;

        if (btnResume) {
          btnResume.style.display = paused ? "inline-flex" : "none";
        }
      } catch (e) {
        console.error("Failed to refresh training status:", e);
      }
    }

    setInterval(refreshTrainingStatus, 3000);
    refreshTrainingStatus();
  }

  // ---------------------------------------------------------------------------
  // DOMContentLoaded orchestration
  // ---------------------------------------------------------------------------
  function initOnDomReady() {
    if (IS_EMBEDDED) {
      // Rendered inside the hidden /generate iframe – skip full UI wiring.
      return;
    }

    const state = getState();

    try {
      // Start on the Core tab.
      if (typeof CDMF.switchKnobTab === "function") {
        CDMF.switchKnobTab("core");
      }
    } catch (e) {
      console.warn(
        "[Candy Dungeon Music Forge] Failed to init knob tabs:",
        e
      );
    }

    try {
      // Snapshot the initial button HTML so model-status UI can restore it.
      const btnGenerate = document.getElementById("generateButton");
      if (
        btnGenerate &&
        state.candyGenerateButtonDefaultHTML == null
      ) {
        state.candyGenerateButtonDefaultHTML = btnGenerate.innerHTML;
      }

      const btnTrain = document.getElementById("btnStartTraining");
      if (btnTrain && state.candyTrainButtonDefaultHTML == null) {
        state.candyTrainButtonDefaultHTML = btnTrain.innerHTML;
      }

      // Apply initial model status from template-injected globals.
      if (typeof CDMF.applyModelStatusToUI === "function") {
        CDMF.applyModelStatusToUI({
          ready: state.candyModelsReady,
          state: state.candyModelStatusState,
          message: state.candyModelStatusMessage,
        });
      }

      // If models weren't ready at launch, poll once to sync with backend.
      if (
        !state.candyModelsReady &&
        typeof CDMF.refreshModelStatusFromServer === "function"
      ) {
        CDMF.refreshModelStatusFromServer();
      }
    } catch (e) {
      console.error(
        "[Candy Dungeon Music Forge] Model status init error:",
        e
      );
    }

    try {
      if (typeof CDMF.initPlayerUI === "function") {
        CDMF.initPlayerUI();
      }
      if (typeof CDMF.initTrackHeaderSorting === "function") {
        CDMF.initTrackHeaderSorting();
      }
      if (typeof CDMF.onInstrumentalToggle === "function") {
        CDMF.onInstrumentalToggle();
      }

      // On first load, auto-pick a random instrumental preset so the app feels alive.
      if (typeof CDMF.setPreset === "function") {
        CDMF.setPreset("random_vocal");
      }

      // Refresh track list (favorites/categories) without auto-play.
      if (typeof CDMF.refreshTracksAfterGeneration === "function") {
        CDMF.refreshTracksAfterGeneration({ autoplay: false });
      }

      // Preset UI wiring + initial user presets from disk.
      if (typeof CDMF.initPresetsUI === "function") {
        CDMF.initPresetsUI();
      }
      if (typeof CDMF.refreshUserPresets === "function") {
        CDMF.refreshUserPresets();
      }
    } catch (e) {
      console.error("[Candy Dungeon Music Forge] Init error:", e);
    }

    // Training pause / resume / cancel controls
    try {
      initTrainingControls();
    } catch (e) {
      console.error(
        "[Candy Dungeon Music Forge] Training controls init error:",
        e
      );
    }
  }

  document.addEventListener("DOMContentLoaded", initOnDomReady);
})();
