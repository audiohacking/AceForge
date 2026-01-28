// C:\CandyDungeonMusicForge\static\scripts\cdmf_presets_ui.js
(function () {
  "use strict";

  const CDMF = (window.CDMF = window.CDMF || {});

  // Local state for user presets
  let userPresets = [];

  // ---------------------------------------------------------------------------
  // Preset index from template-injected CANDY_PRESETS
  // ---------------------------------------------------------------------------

  function buildPresetIndex() {
    const idx = {};
    const presets = window.CANDY_PRESETS || { instrumental: [], vocal: [] };

    if (Array.isArray(presets.instrumental)) {
      presets.instrumental.forEach((p) => {
        if (p && p.id) idx[p.id] = p;
      });
    }
    if (Array.isArray(presets.vocal)) {
      presets.vocal.forEach((p) => {
        if (p && p.id) idx[p.id] = p;
      });
    }
    return idx;
  }

  const PRESET_INDEX = buildPresetIndex();

  // ---------------------------------------------------------------------------
  // Instrumental / vocal toggle + number/range sync
  // ---------------------------------------------------------------------------

  function onInstrumentalToggle() {
    const cb = document.getElementById("instrumental");
    const lyricsRow = document.getElementById("lyricsRow");
    const instGroup = document.getElementById("presetGroupInstrumental");
    const vocalGroup = document.getElementById("presetGroupVocal");
    if (!cb) return;

    const isInstrumental = cb.checked;

    if (lyricsRow) {
      lyricsRow.style.display = isInstrumental ? "none" : "flex";
    }
    if (instGroup) {
      instGroup.style.display = isInstrumental ? "flex" : "none";
    }
    if (vocalGroup) {
      vocalGroup.style.display = isInstrumental ? "none" : "flex";
    }
  }

  function syncRange(idNumber, idRange) {
    const num = document.getElementById(idNumber);
    const rng = document.getElementById(idRange);
    if (!num || !rng) return;
    num.value = rng.value;
  }

  function syncNumber(idNumber, idRange) {
    const num = document.getElementById(idNumber);
    const rng = document.getElementById(idRange);
    if (!num || !rng) return;
    rng.value = num.value;
  }

  // ---------------------------------------------------------------------------
  // Capture current form settings → user preset / recipes
  // ---------------------------------------------------------------------------

  function getCurrentFormSettingsForPreset() {
    const promptField = document.getElementById("prompt");
    const lyricsField = document.getElementById("lyrics");
    const instrumentalCheckbox = document.getElementById("instrumental");
    const basenameField = document.getElementById("basename");
    const seedField = document.getElementById("seed");
    const seedVibeField = document.getElementById("seed_vibe");
    const targetSecondsField = document.getElementById("target_seconds");
    const fadeInField = document.getElementById("fade_in");
    const fadeOutField = document.getElementById("fade_out");
    const vocalGainField = document.getElementById("vocal_gain_db");
    const instrumentalGainField = document.getElementById("instrumental_gain_db");
    const stepsField = document.getElementById("steps");
    const guidanceField = document.getElementById("guidance_scale");
    const bpmField = document.getElementById("bpm");
    const presetIdField = document.getElementById("preset_id");
    const presetCategoryField = document.getElementById("preset_category");

    // Advanced knob fields
    const schedulerField = document.getElementById("scheduler_type");
    const cfgTypeField = document.getElementById("cfg_type");
    const omegaField = document.getElementById("omega_scale");
    const guidanceIntervalField = document.getElementById("guidance_interval");
    const guidanceDecayField = document.getElementById("guidance_interval_decay");
    const minGuidanceField = document.getElementById("min_guidance_scale");
    const useErgTagField = document.getElementById("use_erg_tag");
    const useErgLyricField = document.getElementById("use_erg_lyric");
    const useErgDiffField = document.getElementById("use_erg_diffusion");
    const ossStepsField = document.getElementById("oss_steps");
    const taskField = document.getElementById("task");
    const repaintStartField = document.getElementById("repaint_start");
    const repaintEndField = document.getElementById("repaint_end");
    const retakeVarianceField = document.getElementById("retake_variance");
    const audio2audioEnableField = document.getElementById("audio2audio_enable");
    const refAudioStrengthField = document.getElementById("ref_audio_strength");
    const srcAudioPathField = document.getElementById("src_audio_path");
    const loraNameField = document.getElementById("lora_name_or_path");
    const loraWeightField = document.getElementById("lora_weight");

    function parseFloatSafe(el) {
      if (!el) return null;
      const v = String(el.value || "").trim();
      if (!v) return null;
      const n = Number(v);
      return Number.isNaN(n) ? null : n;
    }

    function parseIntSafe(el) {
      if (!el) return null;
      const v = String(el.value || "").trim();
      if (!v) return null;
      const n = parseInt(v, 10);
      return Number.isNaN(n) ? null : n;
    }

    return {
      prompt: promptField ? promptField.value : "",
      lyrics: lyricsField ? lyricsField.value : "",
      instrumental: instrumentalCheckbox ? !!instrumentalCheckbox.checked : true,
      basename: basenameField ? basenameField.value : "",
      seed: parseIntSafe(seedField),
      seed_vibe: seedVibeField ? seedVibeField.value : "any",
      target_seconds: parseFloatSafe(targetSecondsField),
      fade_in: parseFloatSafe(fadeInField),
      fade_out: parseFloatSafe(fadeOutField),
      vocal_gain_db: parseFloatSafe(vocalGainField),
      instrumental_gain_db: parseFloatSafe(instrumentalGainField),
      steps: parseIntSafe(stepsField),
      guidance_scale: parseFloatSafe(guidanceField),
      bpm: parseFloatSafe(bpmField),
      preset_id: presetIdField ? presetIdField.value : "",
      preset_category: presetCategoryField ? presetCategoryField.value : "",
      // Advanced knobs
      scheduler_type: schedulerField ? schedulerField.value : undefined,
      cfg_type: cfgTypeField ? cfgTypeField.value : undefined,
      omega_scale: parseFloatSafe(omegaField),
      guidance_interval: parseFloatSafe(guidanceIntervalField),
      guidance_interval_decay: parseFloatSafe(guidanceDecayField),
      min_guidance_scale: parseFloatSafe(minGuidanceField),
      use_erg_tag: useErgTagField ? !!useErgTagField.checked : undefined,
      use_erg_lyric: useErgLyricField ? !!useErgLyricField.checked : undefined,
      use_erg_diffusion: useErgDiffField ? !!useErgDiffField.checked : undefined,
      oss_steps: ossStepsField ? ossStepsField.value : "",
      task: taskField ? taskField.value : undefined,
      repaint_start: parseFloatSafe(repaintStartField),
      repaint_end: parseFloatSafe(repaintEndField),
      retake_variance: parseFloatSafe(retakeVarianceField),
      audio2audio_enable: audio2audioEnableField
        ? !!audio2audioEnableField.checked
        : undefined,
      ref_audio_strength: parseFloatSafe(refAudioStrengthField),
      src_audio_path: srcAudioPathField ? srcAudioPathField.value : "",
      lora_name_or_path: loraNameField ? loraNameField.value : "",
      lora_weight: parseFloatSafe(loraWeightField),
    };
  }

  // ---------------------------------------------------------------------------
  // Apply settings → form (used by presets + tracks)
  // ---------------------------------------------------------------------------

  function applySettingsToForm(settings) {
    if (!settings) return;

    // Voice Clone tracks: switch to Voice Clone tab and fill that form
    if (settings.generator === "voice_clone") {
      if (typeof CDMF.applyVoiceCloneSettingsToForm === "function") {
        CDMF.applyVoiceCloneSettingsToForm(settings);
        return;
      }
    }

    // Stem Split tracks: switch to Stem Splitting tab and fill that form
    if (settings.generator === "stem_split") {
      if (typeof CDMF.applyStemSplitSettingsToForm === "function") {
        CDMF.applyStemSplitSettingsToForm(settings);
        return;
      }
    }

    const promptField = document.getElementById("prompt");
    const lyricsField = document.getElementById("lyrics");
    const instrumentalCheckbox = document.getElementById("instrumental");
    const basenameField = document.getElementById("basename");
    const seedField = document.getElementById("seed");
    const seedRandomCheckbox = document.getElementById("seed_random");
    const seedVibeField = document.getElementById("seed_vibe");
    const targetSecondsField = document.getElementById("target_seconds");
    const targetSecondsRange = document.getElementById("target_seconds_range");
    const fadeInField = document.getElementById("fade_in");
    const fadeInRange = document.getElementById("fade_in_range");
    const fadeOutField = document.getElementById("fade_out");
    const fadeOutRange = document.getElementById("fade_out_range");
    const vocalGainField = document.getElementById("vocal_gain_db");
    const vocalGainRange = document.getElementById("vocal_gain_db_range");
    const instGainField = document.getElementById("instrumental_gain_db");
    const instGainRange = document.getElementById("instrumental_gain_db_range");
    const stepsField = document.getElementById("steps");
    const guidanceField = document.getElementById("guidance_scale");
    const bpmField = document.getElementById("bpm");
    const presetIdField = document.getElementById("preset_id");
    const presetCategoryField = document.getElementById("preset_category");

    // Advanced knob fields
    const schedulerField = document.getElementById("scheduler_type");
    const cfgTypeField = document.getElementById("cfg_type");
    const omegaField = document.getElementById("omega_scale");
    const guidanceIntervalField = document.getElementById("guidance_interval");
    const guidanceDecayField = document.getElementById("guidance_interval_decay");
    const minGuidanceField = document.getElementById("min_guidance_scale");
    const useErgTagField = document.getElementById("use_erg_tag");
    const useErgLyricField = document.getElementById("use_erg_lyric");
    const useErgDiffField = document.getElementById("use_erg_diffusion");
    const ossStepsField = document.getElementById("oss_steps");
    const taskField = document.getElementById("task");
    const repaintStartField = document.getElementById("repaint_start");
    const repaintEndField = document.getElementById("repaint_end");
    const retakeVarianceField = document.getElementById("retake_variance");
    const audio2audioEnableField = document.getElementById("audio2audio_enable");
    const refAudioStrengthField = document.getElementById("ref_audio_strength");
    const srcAudioPathField = document.getElementById("src_audio_path");
    const loraNameField = document.getElementById("lora_name_or_path");
    const loraWeightField = document.getElementById("lora_weight");

    if (promptField && typeof settings.prompt === "string") {
      promptField.value = settings.prompt;
    }
    if (lyricsField && typeof settings.lyrics === "string") {
      lyricsField.value = settings.lyrics;
    }

    if (instrumentalCheckbox && typeof settings.instrumental === "boolean") {
      if (instrumentalCheckbox.checked !== settings.instrumental) {
        instrumentalCheckbox.checked = settings.instrumental;
        onInstrumentalToggle();
      }
    }

    if (basenameField && typeof settings.basename === "string") {
      basenameField.value = settings.basename;
    }

    if (seedField && settings.seed != null) {
      seedField.value = String(settings.seed);
    }
    if (seedRandomCheckbox) {
      // When copying from a track / preset, we typically want deterministic behavior
      seedRandomCheckbox.checked = false;
    }

    if (seedVibeField && typeof settings.seed_vibe === "string") {
      seedVibeField.value = settings.seed_vibe;
    }

    function setNumPair(numEl, rngEl, value) {
      if (!numEl) return;
      if (value == null || Number.isNaN(value)) return;
      const v = String(value);
      numEl.value = v;
      if (rngEl) {
        rngEl.value = v;
      }
    }

    setNumPair(targetSecondsField, targetSecondsRange, settings.target_seconds);
    setNumPair(fadeInField, fadeInRange, settings.fade_in);
    setNumPair(fadeOutField, fadeOutRange, settings.fade_out);
    setNumPair(vocalGainField, vocalGainRange, settings.vocal_gain_db);
    setNumPair(instGainField, instGainRange, settings.instrumental_gain_db);

    if (stepsField && settings.steps != null) {
      stepsField.value = String(settings.steps);
    }
    if (guidanceField && settings.guidance_scale != null) {
      guidanceField.value = String(settings.guidance_scale);
    }

    if (bpmField && settings.bpm != null) {
      bpmField.value = String(settings.bpm);
    }

    if (presetIdField && typeof settings.preset_id === "string") {
      presetIdField.value = settings.preset_id;
    }
    if (presetCategoryField) {
      const cat = settings.preset_category || settings.category || "";
      presetCategoryField.value = cat;
    }

    // Advanced knobs --------------------------------------------------------
    if (schedulerField && typeof settings.scheduler_type === "string") {
      schedulerField.value = settings.scheduler_type;
    }
    if (cfgTypeField && typeof settings.cfg_type === "string") {
      cfgTypeField.value = settings.cfg_type;
    }
    if (omegaField && settings.omega_scale != null) {
      omegaField.value = String(settings.omega_scale);
    }
    if (guidanceIntervalField && settings.guidance_interval != null) {
      guidanceIntervalField.value = String(settings.guidance_interval);
    }
    if (guidanceDecayField && settings.guidance_interval_decay != null) {
      guidanceDecayField.value = String(settings.guidance_interval_decay);
    }
    if (minGuidanceField && settings.min_guidance_scale != null) {
      minGuidanceField.value = String(settings.min_guidance_scale);
    }

    if (useErgTagField && typeof settings.use_erg_tag === "boolean") {
      useErgTagField.checked = settings.use_erg_tag;
    }
    if (useErgLyricField && typeof settings.use_erg_lyric === "boolean") {
      useErgLyricField.checked = settings.use_erg_lyric;
    }
    if (useErgDiffField && typeof settings.use_erg_diffusion === "boolean") {
      useErgDiffField.checked = settings.use_erg_diffusion;
    }

    if (ossStepsField && typeof settings.oss_steps === "string") {
      ossStepsField.value = settings.oss_steps;
    }
    if (taskField && typeof settings.task === "string") {
      taskField.value = settings.task;
    }

    if (repaintStartField && settings.repaint_start != null) {
      repaintStartField.value = String(settings.repaint_start);
    }
    if (repaintEndField && settings.repaint_end != null) {
      repaintEndField.value = String(settings.repaint_end);
    }
    if (retakeVarianceField && settings.retake_variance != null) {
      retakeVarianceField.value = String(settings.retake_variance);
    }

    if (audio2audioEnableField && typeof settings.audio2audio_enable === "boolean") {
      audio2audioEnableField.checked = settings.audio2audio_enable;
    }
    if (refAudioStrengthField && settings.ref_audio_strength != null) {
      refAudioStrengthField.value = String(settings.ref_audio_strength);
    }
    if (srcAudioPathField && typeof settings.src_audio_path === "string") {
      srcAudioPathField.value = settings.src_audio_path;
    }
    if (loraNameField && typeof settings.lora_name_or_path === "string") {
      loraNameField.value = settings.lora_name_or_path;
    }
    if (loraWeightField && settings.lora_weight != null) {
      loraWeightField.value = String(settings.lora_weight);
    }
  }

  // ---------------------------------------------------------------------------
  // Built-in presets (including random_*)
  // ---------------------------------------------------------------------------

  function setPreset(id) {
    const promptField = document.getElementById("prompt");
    if (!promptField) return;

    const negativeField = document.getElementById("negative_prompt");
    const lyricsField = document.getElementById("lyrics");
    const instrumentalCheckbox = document.getElementById("instrumental");
    const basenameField = document.getElementById("basename");
    const bpmField = document.getElementById("bpm");
    const presetIdField = document.getElementById("preset_id");
    const presetCategoryField = document.getElementById("preset_category");

    function pick(arr) {
      return arr[Math.floor(Math.random() * arr.length)];
    }

    // As of ACE-Step v0.1 we do not use a negative prompt at all.
    if (negativeField) {
      negativeField.value = "";
    }

    function applyPreset(preset) {
      if (!preset) return;

      const mode = preset.mode || "instrumental";

      // Flip instrumental checkbox + show/hide lyrics + preset banks
      if (instrumentalCheckbox) {
        const shouldBeInstrumental = mode === "instrumental";
        if (instrumentalCheckbox.checked !== shouldBeInstrumental) {
          instrumentalCheckbox.checked = shouldBeInstrumental;
          onInstrumentalToggle();
        }
      }

      if (promptField && preset.prompt) {
        promptField.value = preset.prompt;
      }

      // Negative prompt is intentionally disabled.
      if (negativeField) {
        negativeField.value = "";
      }

      if (lyricsField) {
        if (mode === "vocal" && preset.lyrics) {
          const raw = String(preset.lyrics);
          lyricsField.value = raw.replace(/\\n/g, "\n");
        } else {
          lyricsField.value = "";
        }
      }

      if (basenameField) {
        if (preset.basename) {
          basenameField.value = preset.basename;
        } else if (preset.label) {
          basenameField.value = preset.label;
        }
      }

      if (bpmField) {
        if (typeof preset.bpm === "number") {
          bpmField.value = String(preset.bpm);
        }
      }

      if (presetIdField) {
        presetIdField.value = preset.id || "";
      }
      if (presetCategoryField) {
        presetCategoryField.value = preset.category || "";
      }
    }

    // Random instrumental preset
    if (id === "random_instrumental") {
      const tempos = [
        "slow tempo",
        "medium-slow tempo",
        "medium tempo",
        "medium-fast tempo",
        "fast tempo",
      ];
      const styles = [
        "retro game-inspired soundtrack with bright synth lead melody",
        "fantasy adventure score with soaring flute or string melody",
        "dungeon synth piece with haunting pads and simple lead melody",
        "hip hop-inspired groove with warm electric piano melody",
        "minimal retro electronic sketch with gentle synth melody",
        "RPG overworld-style theme with strong, memorable lead melody",
        "dramatic boss battle score with powerful synth lead",
        "ambient electronic piece with soft, drifting melody",
      ];
      const moods = [
        "moody and melancholic",
        "dark and gritty",
        "bright and adventurous",
        "relaxed and cozy",
        "tense and suspenseful",
        "mysterious and dreamy",
        "playful and bouncy",
        "cold and atmospheric",
      ];
      const instruments = [
        "clear synth lead melody",
        "gentle piano melody",
        "soft flute melody",
        "expressive guitar melody",
        "bell-like melody with light mallet instruments",
        "airy pad melody with slow evolving notes",
        "plucked synth melody with subtle echo",
        "smooth bassline supporting a tuneful lead",
      ];
      const contexts = [
        "background music for a neon-lit dungeon hub",
        "theme for exploring a fantasy overworld",
        "background music for an underground cyberpunk city",
        "safe-room theme in a haunted castle",
        "exploration music for ancient ruins",
        "background music for a cozy fantasy tavern",
        "late-night hacking theme in a futuristic city",
        "ambient music for drifting through deep space",
      ];

      const base = pick(styles);
      const tempo = pick(tempos);
      const mood = pick(moods);
      const instr = pick(instruments);
      const ctx = pick(contexts);

      if (promptField) {
        promptField.value =
          base +
          ", " +
          tempo +
          ", " +
          mood +
          ", " +
          instr +
          ", " +
          ctx +
          ", clean mix, focus on a tuneful lead melody";
      }
      if (negativeField) {
        negativeField.value = "";
      }
      if (lyricsField) {
        lyricsField.value = "";
      }
      if (basenameField) {
        basenameField.value = "Random Instrumental";
      }
      if (bpmField) {
        bpmField.value = "";
      }
      if (presetIdField) {
        presetIdField.value = "random_instrumental";
      }
      if (presetCategoryField) {
        presetCategoryField.value = "";
      }
      if (instrumentalCheckbox && !instrumentalCheckbox.checked) {
        instrumentalCheckbox.checked = true;
        onInstrumentalToggle();
      }
      return;
    }

    // Random vocal preset
    if (id === "random_vocal") {
      const themes = [
        "lost hero in a ruined city",
        "wandering mage on a frozen mountain",
        "star-crossed lovers in a cyberpunk alley",
        "pilot singing to the stars between battles",
        "rogue standing on the walls of a besieged castle",
      ];
      const moods = [
        "bittersweet and hopeful",
        "dark but determined",
        "melancholic yet warm",
        "triumphant after long struggle",
        "lonely but resilient",
      ];

      const theme = pick(themes);
      const mood = pick(moods);

      if (promptField) {
        promptField.value =
          "emotional vocal game song, " +
          mood +
          ", about a " +
          theme +
          ", clear melodic singing over cinematic backing";
      }
      if (negativeField) {
        negativeField.value = "";
      }
      if (lyricsField) {
        lyricsField.value =
          "[Verse 1]\n" +
          "Write your own story here about " +
          theme +
          ".\n" +
          "Describe the scene, the conflict, and the feeling.\n\n" +
          "[Chorus]\n" +
          "Turn the main emotion of the song into a memorable hook.\n" +
          "Repeat one or two key lines.\n\n" +
          "[Verse 2]\n" +
          "Continue the story, show what changes after the chorus.\n\n" +
          "[Bridge]\n" +
          "Shift perspective or time, then return to the final chorus.";
      }
      if (basenameField) {
        basenameField.value = "Random Vocal";
      }
      if (bpmField) {
        bpmField.value = "";
      }
      if (presetIdField) {
        presetIdField.value = "random_vocal";
      }
      if (presetCategoryField) {
        presetCategoryField.value = "";
      }
      if (instrumentalCheckbox && instrumentalCheckbox.checked) {
        instrumentalCheckbox.checked = false;
        onInstrumentalToggle();
      }
      return;
    }

    // Normal preset from JSON
    const preset = PRESET_INDEX[id];
    if (!preset) {
      console.warn("[Ace Forge] Unknown preset id:", id);
      return;
    }
    applyPreset(preset);
  }

  // ---------------------------------------------------------------------------
  // User presets: dropdown + remote storage
  // ---------------------------------------------------------------------------

  function rebuildUserPresetSelect() {
    const select = document.getElementById("userPresetSelect");
    if (!select) return;

    while (select.firstChild) {
      select.removeChild(select.firstChild);
    }

    if (!userPresets.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "(No saved presets yet)";
      select.appendChild(opt);
      return;
    }

    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = "(Select a preset)";
    select.appendChild(empty);

    userPresets.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = String(p.id);
      opt.textContent = p.label || p.id;
      select.appendChild(opt);
    });
  }

  async function refreshUserPresets() {
    try {
      const resp = await fetch("/user_presets?_=" + Date.now(), {
        cache: "no-store",
      });
      if (!resp.ok) {
        console.warn(
          "[Ace Forge] /user_presets HTTP " + resp.status
        );
        return;
      }
      const data = await resp.json();
      if (!data || !Array.isArray(data.presets)) {
        console.warn(
          "[Ace Forge] /user_presets payload missing presets array:",
          data
        );
        return;
      }
      userPresets = data.presets.slice();
      rebuildUserPresetSelect();
    } catch (err) {
      console.error("Failed to refresh user presets:", err);
    }
  }

  function initPresetsUI() {
    const btnClearLyrics = document.getElementById("btnClearLyrics");
    if (btnClearLyrics) {
      btnClearLyrics.addEventListener("click", function () {
        const lyricsField = document.getElementById("lyrics");
        if (lyricsField) {
          lyricsField.value = "";
        }
      });
    }

    const btnLoadUserPreset = document.getElementById("btnLoadUserPreset");
    const btnSaveUserPreset = document.getElementById("btnSaveUserPreset");
    const btnDeleteUserPreset = document.getElementById("btnDeleteUserPreset");
    const userPresetSelect = document.getElementById("userPresetSelect");

    // Load user preset → apply its settings to the form
    if (btnLoadUserPreset && userPresetSelect) {
      btnLoadUserPreset.addEventListener("click", function () {
        const id = userPresetSelect.value;
        if (!id) return;
        const preset = userPresets.find((p) => String(p.id) === String(id));
        if (!preset) return;
        applySettingsToForm(preset);
      });
    }

    // Save current form as (new or updated) user preset
    if (btnSaveUserPreset && userPresetSelect) {
      btnSaveUserPreset.addEventListener("click", async function () {
        const currentId = userPresetSelect.value || "";
        const currentPreset =
          currentId &&
          userPresets.find((p) => String(p.id) === String(currentId));

        const basename =
          (document.getElementById("basename")?.value || "").trim();
        const defaultLabel =
          (currentPreset && currentPreset.label) || basename || "My preset";

        const label = window.prompt("Preset name:", defaultLabel);
        if (!label) return;

        const settings = getCurrentFormSettingsForPreset();

        const body = {
          mode: "save",
          id: currentPreset ? currentPreset.id : undefined,
          label: label.trim(),
          settings,
        };

        try {
          const resp = await fetch("/user_presets", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
          const data = await resp.json();
          if (!resp.ok || (data && data.error)) {
            const msg =
              (data && data.error) ||
              "Save failed with HTTP " + resp.status;
            window.alert(msg);
            return;
          }

          await refreshUserPresets();
          if (data && data.preset && data.preset.id && userPresetSelect) {
            userPresetSelect.value = String(data.preset.id);
          }
        } catch (err) {
          console.error("Failed to save user preset:", err);
          window.alert("Failed to save preset. See console for details.");
        }
      });
    }

    // Delete currently selected user preset
    if (btnDeleteUserPreset && userPresetSelect) {
      btnDeleteUserPreset.addEventListener("click", async function () {
        const id = userPresetSelect.value;
        if (!id) return;

        if (!window.confirm("Delete this preset? This cannot be undone.")) {
          return;
        }

        try {
          const resp = await fetch("/user_presets", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mode: "delete", id }),
          });
          const data = await resp.json();
          if (!resp.ok || (data && data.error)) {
            const msg =
              (data && data.error) ||
              "Delete failed with HTTP " + resp.status;
            window.alert(msg);
            return;
          }
          await refreshUserPresets();
        } catch (err) {
          console.error("Failed to delete user preset:", err);
          window.alert("Failed to delete preset. See console for details.");
        }
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Exports
  // ---------------------------------------------------------------------------

  CDMF.setPreset = setPreset;
  CDMF.onInstrumentalToggle = onInstrumentalToggle;
  CDMF.syncRange = syncRange;
  CDMF.syncNumber = syncNumber;
  CDMF.refreshUserPresets = refreshUserPresets;
  CDMF.getCurrentFormSettingsForPreset = getCurrentFormSettingsForPreset;
  CDMF.applySettingsToForm = applySettingsToForm;
  CDMF.initPresetsUI = initPresetsUI;
})();
