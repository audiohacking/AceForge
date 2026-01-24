# C:\AceForge\cdmf_template.py
#
# HTML template for AceForge.
# Refactored so CSS/JS live in static files instead of a giant inline blob.

HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>AceForge{% if version %} ({{ version }}){% endif %}</title>
  <link rel="icon" type="image/png" href="{{ url_for('static', filename='aceforge_logo.png') }}">

  <!-- External CSS instead of inline <style> -->
  <link rel="stylesheet" href="{{ url_for('static', filename='scripts/cdmf.css') }}">
</head>
<body>
  <div class="page">
  
    <div class="cd-titlebar">
      <div class="cd-titlewrap">
        <span class="cd-logo">
          <img
            src="{{ url_for('static', filename='aceforge_logo.png') }}"
            alt="AceForge logo"
          >
        </span>
      </div>
      <div style="display:flex;align-items:center;gap:8px;">
        <span class="cd-alpha">{{ version or 'v0.1' }}</span>
        <button type="button" class="btn danger exit" id="btnExitApp" title="Exit AceForge">
          <span class="icon">🚪</span><span class="label">Exit</span>
        </button>
      </div>
    </div>


    <!-- Two-column layout container -->
    <div class="two-column-layout">
      <!-- Left column: Generation and Training -->
      <div class="column-left">
        <!-- Mode tabs: Generate vs Training vs Voice Cloning ---------------------------------- -->
        <div class="tab-row" style="margin-top:16px;">
          <button
            type="button"
            class="tab-btn tab-btn-active mode-tab-btn"
            data-mode="generate"
            onclick="window.CDMF && CDMF.switchMode && CDMF.switchMode('generate');">
            Generate
          </button>
          <button
            type="button"
            class="tab-btn mode-tab-btn"
            data-mode="train"
            onclick="window.CDMF && CDMF.switchMode && CDMF.switchMode('train');">
            Training
          </button>
          <button
            type="button"
            class="tab-btn mode-tab-btn"
            data-mode="voice_clone"
            onclick="window.CDMF && CDMF.switchMode && CDMF.switchMode('voice_clone');">
            Voice Cloning
          </button>
        </div>

        <!-- Generation form card (mode: generate) ----------------------------- -->
        <form
          id="generateForm"
          class="card card-mode"
          data-mode="generate"
          method="post"
          action="{{ url_for('cdmf_generation.generate') }}"
          target="generation_frame"
          enctype="multipart/form-data"
          onsubmit="return CDMF.onSubmitForm(event)">
      <div class="card-header-row">
        <div style="flex:1;min-width:0;">
          <h2>Generate Track</h2>
          <div id="loadingBar" class="loading-bar">
            <div class="loading-bar-inner"></div>
          </div>
        </div>
        <div style="display:flex;gap:8px;align-items:center;">
          <button id="generateButton" type="submit" class="btn primary">
            <span class="icon">🎧</span><span>Generate</span>
          </button>
        </div>
      </div>

      <div
        id="modelStatusNotice"
        class="toast"
        style="margin-top:8px; {{ 'display:none;' if models_ready else 'display:block;' }}">
        {% if not models_ready %}
          ACE-Step model is not downloaded yet. Click "Download Models" to start the download.
          This is a large download (multiple GB) and may take several minutes. Keep the console
          window open; it will show detailed progress.
        {% endif %}
      </div>

      <!-- Hidden preset metadata used to auto-tag generated tracks -->
      <input id="preset_id" name="preset_id" type="hidden" value="">
      <input id="preset_category" name="preset_category" type="hidden" value="">

      <!-- Core vs Advanced control tabs -->
      <div class="tab-row">
        <button
          type="button"
          id="tab_core"
          class="tab-btn tab-btn-active"
          onclick="CDMF.switchKnobTab('core')">
          Core
        </button>
        <button
          type="button"
          id="tab_advanced"
          class="tab-btn"
          onclick="CDMF.switchKnobTab('advanced')">
          Advanced
        </button>
      </div>

      <!-- Core knobs: everything you already had -->
      <div id="coreKnobs">
        <div class="row">
          <label for="basename">Base filename</label>
          <input id="basename" name="basename" type="text" value="{{ basename or 'Candy Dreams' }}">
        </div>

        <div class="row" id="autoPromptLyricsRow">
          <label>Auto prompt / lyrics</label>
          <div style="flex:1;display:flex;flex-wrap:wrap;align-items:center;gap:8px;min-width:0%;">
            <button
              type="button"
              class="btn"
              id="btnAutoPromptLyrics"
              onclick="CDMF.onAutoPromptLyricsButtonClick()">
              <span class="icon">✨</span><span class="label">Generate prompt / lyrics…</span>
            </button>
          </div>
        </div>
        <div class="small" style="margin-top:-4px;margin-bottom:8px;">
          Opens a small dialog where you can type a song concept and choose whether to
          generate a <strong>prompt</strong>, <strong>lyrics</strong>, or <strong>both</strong>.
          Lyrics only affect audio when <strong>Instrumental</strong> is <em>unchecked</em>.
        </div>

        <div class="row">
          <label for="prompt">Genre / Style Prompt</label>
          <textarea id="prompt" name="prompt" placeholder="Describe the genre, mood, instruments, and vibe...">{{ prompt or "" }}</textarea>
        </div>

        <!-- Preset banks: instrumental vs vocal (toggled by Instrumental checkbox) -->
        <div>
          <!-- Instrumental presets -->
          <div class="preset-buttons" id="presetGroupInstrumental">
            {% for p in presets.instrumental %}
            <button type="button" class="btn" onclick="CDMF.setPreset('{{ p.id }}')">
              <span class="icon">{{ p.icon }}</span><span>{{ p.label }}</span>
            </button>
            {% endfor %}
            <button type="button" class="btn" onclick="CDMF.setPreset('random_instrumental')">
              <span class="icon">🎲</span><span>Random</span>
            </button>
          </div>

          <!-- Vocal presets -->
          <div class="preset-buttons" id="presetGroupVocal" style="display:none;">
            {% for p in presets.vocal %}
            <button type="button" class="btn" onclick="CDMF.setPreset('{{ p.id }}')">
              <span class="icon">{{ p.icon }}</span><span>{{ p.label }}</span>
            </button>
            {% endfor %}
            <button type="button" class="btn" onclick="CDMF.setPreset('random_vocal')">
              <span class="icon">🎲</span><span>Random Vocal</span>
            </button>
          </div>
        </div>

        <div class="row">
          <label for="instrumental">Instrumental</label>
          <div style="display:flex;align-items:center;gap:8px;flex:1;">
            <input id="instrumental"
                   name="instrumental"
                   type="checkbox"
                   autocomplete="off"
                   {% if instrumental is defined and instrumental %}checked{% endif %}
                   onchange="CDMF.onInstrumentalToggle()">
            <span class="small">
              Instrumental only (no vocals, no lyrics, no spoken word). Turn off to allow lyrics.
            </span>
          </div>
        </div>

        <div class="row" id="lyricsRow" style="display:none; flex-direction:column; align-items:stretch;">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;">
            <label for="lyrics" style="margin:0;">Lyrics (optional)</label>
            <button type="button" class="btn" id="btnClearLyrics">
              <span class="icon">🧹</span><span class="label">Clear</span>
            </button>
          </div>
          <textarea id="lyrics"
                    name="lyrics"
                    placeholder="Add lyrics here when Instrumental is off. You can use [verse], [chorus], [solo], [outro] markers. For instrumentals the backend automatically uses [inst].">{{ lyrics or "" }}</textarea>
        </div>

        <!-- Negative prompt is currently unused by ACE-Step.
             Keep a hidden, always-empty field so the form stays stable. -->
        <input id="negative_prompt" name="negative_prompt" type="hidden" value="">

        <hr style="border:none;border-top:1px solid #111827;margin:12px 0;">

        <!-- Seed vibe is now an internal knob (used by presets only).
             Keep it as a hidden field so JS and the backend can still use it. -->
        <input
          id="seed_vibe"
          name="seed_vibe"
          type="hidden"
          value="{{ seed_vibe or 'any' }}"
        >

        <div class="slider-row">
          <label for="target_seconds">Target length (seconds)</label>
          <input id="target_seconds_range" type="range" min="15" max="240" step="5"
                 value="{{ target_seconds or UI_DEFAULT_TARGET_SECONDS }}" oninput="CDMF.syncRange('target_seconds', 'target_seconds_range')">
          <input id="target_seconds" name="target_seconds" type="number" min="15" max="240" step="5"
                 value="{{ target_seconds or UI_DEFAULT_TARGET_SECONDS }}" oninput="CDMF.syncNumber('target_seconds', 'target_seconds_range')">
        </div>
        <div class="small">
          ACE-Step is asked for this length; the actual duration can be approximate.
        </div>

        <div class="slider-row">
          <label for="fade_in">Fade in (seconds)</label>
          <input id="fade_in_range" type="range" min="0" max="5" step="0.1"
                 value="{{ fade_in or UI_DEFAULT_FADE_IN }}" oninput="CDMF.syncRange('fade_in', 'fade_in_range')">
          <input id="fade_in" name="fade_in" type="number" min="0" max="5" step="0.1"
                 value="{{ fade_in or UI_DEFAULT_FADE_IN }}" oninput="CDMF.syncNumber('fade_in', 'fade_in_range')">
        </div>

        <div class="slider-row">
          <label for="fade_out">Fade out (seconds)</label>
          <input id="fade_out_range" type="range" min="0" max="5" step="0.1"
                 value="{{ fade_out or UI_DEFAULT_FADE_OUT }}" oninput="CDMF.syncRange('fade_out', 'fade_out_range')">
          <input id="fade_out" name="fade_out" type="number" min="0" max="5" step="0.1"
                 value="{{ fade_out or UI_DEFAULT_FADE_OUT }}" oninput="CDMF.syncNumber('fade_out', 'fade_out_range')">
        </div>

        <div class="slider-row">
          <label for="steps">Inference steps</label>
          <input id="steps" name="steps" type="number" min="10" max="300" step="1"
                 value="{{ steps or UI_DEFAULT_STEPS }}">
          <span class="small">50 - 125 is a good range; higher is slower but sometimes richer. Very high is likely to degrade quality/produce strange results.</span>
        </div>

        <div class="slider-row">
          <label for="guidance_scale">Guidance scale</label>
          <input id="guidance_scale" name="guidance_scale" type="number" min="0.5" max="20" step="0.5"
                 value="{{ guidance_scale or UI_DEFAULT_GUIDANCE }}">
          <span class="small">How strongly ACE-Step follows your text tags. High values may lead to noise/artifacts.</span>
        </div>

        <div class="slider-row">
          <label for="bpm">Beats per minute (optional)</label>
          <input id="bpm" name="bpm" type="number" min="40" max="240" step="1"
                 value="{{ bpm or '' }}">
          <span class="small">
            Leave blank for auto tempo. If set, a hint like "tempo 120 bpm"
            is added to the tags.
          </span>
        </div>

        <div class="slider-row">
          <label for="seed">Seed</label>
          <div style="display:flex;align-items:center;gap:8px;flex:1;">
            <input
              id="seed"
              name="seed"
              type="number"
              step="1"
              value="{{ seed or 0 }}"
              style="width:120px;"
            >
            <label class="small" style="display:flex;align-items:center;gap:4px;cursor:pointer;">
              <input
                id="seed_random"
                name="seed_random"
                type="checkbox"
                checked
              >
              Random
            </label>
          </div>
          <span class="small">
            When Random is checked, a new seed is chosen each time you generate.
            Uncheck to lock and reuse a specific seed.
          </span>
        </div>
        
        <hr style="border:none;border-top:1px solid #111827;margin:16px 0 8px;">
        
        <div class="small" style="font-weight:600;opacity:0.9;margin-bottom:4px;">
          <b>Vocal vs. instrumental levels</b>
        </div>
        
        <div class="small">
          <br>Post-mix adjustment for vocals and instrumentals after ACE-Step finishes the track.
          0 dB leaves a track as-is; negative values push them back, positive values bring them forward.
          
          <br><br><strong>Note:</strong> Be aware that adjusting track volume will require downloading a new model on the first run and that it will cause generation to take significantly longer. It is recommended to generate a song at normal volumes first, then turn off Random Seed, leave all generation settings as preferred, and THEN adjust volumes if desired.
        </div>
        
        <!-- Final mix: vocal vs instrumental levels (post-process in dB) -->
        <div class="slider-row">
          <label for="vocal_gain_db">Vocals level (dB)</label>
          <input
            id="vocal_gain_db_range"
            type="range"
            min="-24"
            max="12"
            step="0.5"
            value="{{ vocal_gain_db or UI_DEFAULT_VOCAL_GAIN_DB }}"
            oninput="CDMF.syncRange('vocal_gain_db', 'vocal_gain_db_range')">
          <input
            id="vocal_gain_db"
            name="vocal_gain_db"
            type="number"
            min="-24"
            max="12"
            step="0.5"
            value="{{ vocal_gain_db or UI_DEFAULT_VOCAL_GAIN_DB }}"
            oninput="CDMF.syncNumber('vocal_gain_db', 'vocal_gain_db_range')">
        </div>

        <div class="slider-row">
          <label for="instrumental_gain_db">Instrumental level (dB)</label>
          <input
            id="instrumental_gain_db_range"
            type="range"
            min="-24"
            max="12"
            step="0.5"
            value="{{ instrumental_gain_db or UI_DEFAULT_INSTRUMENTAL_GAIN_DB }}"
            oninput="CDMF.syncRange('instrumental_gain_db', 'instrumental_gain_db_range')">
          <input
            id="instrumental_gain_db"
            name="instrumental_gain_db"
            type="number"
            min="-24"
            max="12"
            step="0.5"
            value="{{ instrumental_gain_db or UI_DEFAULT_INSTRUMENTAL_GAIN_DB }}"
            oninput="CDMF.syncNumber('instrumental_gain_db', 'instrumental_gain_db_range')">
        </div>
        <div class="small">
          Post-mix adjustment for the backing track / instrumental stem.
          0 dB is neutral; negative values make the backing quieter, positive values make it louder.
        </div>
        
      </div> <!-- /coreKnobs -->

      <!-- Advanced ACE-Step knobs -->
      <div id="advancedKnobs" style="display:none;">
        <div class="small tab-hint">
          Advanced ACE-Step controls. Defaults are usually fine; tweak sparingly.
        </div>

        <div class="row">
          <label for="scheduler_type">Scheduler</label>
          <select id="scheduler_type" name="scheduler_type">
            <option value="euler">Euler</option>
            <option value="heun">Heun</option>
            <option value="pingpong">Ping-pong</option>
          </select>
        </div>

        <div class="row">
          <label for="cfg_type">CFG mode</label>
          <select id="cfg_type" name="cfg_type">
            <option value="apg">APG (recommended)</option>
            <option value="cfg">CFG</option>
            <option value="cfg_star">CFG★</option>
          </select>
        </div>

        <div class="slider-row">
          <label for="omega_scale">Omega scale</label>
          <input id="omega_scale" name="omega_scale" type="number" min="1" max="30" step="0.5" value="5">
          <span class="small">
            Controls granularity; higher can add detail but may hurt stability.
          </span>
        </div>

        <div class="slider-row">
          <label for="guidance_interval">Guidance interval</label>
          <input id="guidance_interval" name="guidance_interval" type="number" min="0" max="1" step="0.05" value="1.0">
          <span class="small">
            How often guidance is applied during diffusion (0–1).
          </span>
        </div>

        <div class="slider-row">
          <label for="guidance_interval_decay">Interval decay</label>
          <input id="guidance_interval_decay" name="guidance_interval_decay" type="number" min="0" max="1" step="0.05" value="0.0">
          <span class="small">
            Lets guidance back off over time (0 = no decay).
          </span>
        </div>

        <div class="slider-row">
          <label for="min_guidance_scale">Min guidance</label>
          <input id="min_guidance_scale" name="min_guidance_scale" type="number" min="0" max="20" step="0.5" value="3.0">
          <span class="small">
            Lower bound for guidance when using intervals/decay.
          </span>
        </div>

        <div class="row">
          <label>ERG switches</label>
          <div class="checkbox-row">
            <label class="small">
              <input type="checkbox" id="use_erg_tag" name="use_erg_tag" checked>
              Tag
            </label>
            <label class="small">
              <input type="checkbox" id="use_erg_lyric" name="use_erg_lyric" checked>
              Lyric
            </label>
            <label class="small">
              <input type="checkbox" id="use_erg_diffusion" name="use_erg_diffusion" checked>
              Diffusion
            </label>
          </div>
        </div>

        <div class="row">
          <label for="oss_steps">Custom steps (optional)</label>
          <input id="oss_steps" name="oss_steps" type="text"
                 placeholder="Comma-separated sigma steps, e.g. 0, 10, 20, 30">
        </div>

        <!-- Repainting / Extend subsection -------------------------------- -->
        <hr style="border:none;border-top:1px solid #111827;margin:12px 0 8px;">
        <div class="small" style="font-weight:600;opacity:0.9;margin-bottom:4px;">
          Repainting / extend tasks -- (under construction)
        </div>

        <div class="row">
          <label for="task">Task</label>
          <select id="task" name="task">
            <option value="text2music">Text → music (default)</option>
            <option value="retake">Retake / variation</option>
            <option value="repaint">Repaint segment</option>
            <option value="extend">Extend tail</option>
          </select>
        </div>

        <div class="slider-row">
          <label for="repaint_start">Repaint start (sec)</label>
          <input id="repaint_start" name="repaint_start" type="number" min="0" step="0.1" value="0">
        </div>

        <div class="slider-row">
          <label for="repaint_end">Repaint end (sec)</label>
          <input id="repaint_end" name="repaint_end" type="number" min="0" step="0.1" value="0">
        </div>

        <div class="slider-row">
          <label for="retake_variance">Retake variance</label>
          <input id="retake_variance" name="retake_variance" type="number" min="0" max="1" step="0.05" value="0.5">
        </div>

        <!-- Audio2Audio subsection ----------------------------------------- -->
        <hr style="border:none;border-top:1px solid #111827;margin:16px 0 8px;">
        <div class="small" style="font-weight:600;opacity:0.9;margin-bottom:4px;">
          Audio2Audio remix (reference track)
        </div>

        <!-- Hidden flag; JS will flip this based on whether a ref file is provided -->
        <input
          type="hidden"
          id="audio2audio_enable"
          name="audio2audio_enable"
          value=""
        >

        <div class="slider-row">
          <label for="ref_audio_strength">Ref strength</label>
          <input id="ref_audio_strength" name="ref_audio_strength" type="number" min="0" max="1" step="0.05" value="0.7">
          <span class="small">
            0 = mostly ignore reference, 1 = strongly follow its groove / texture.
          </span>
        </div>

        <div class="row">
          <label for="ref_audio_file">Ref audio</label>
          <div style="flex:1;display:flex;flex-direction:column;gap:6px;min-width:0;">
            <input
              id="ref_audio_file"
              name="ref_audio_file"
              type="file"
              accept=".wav,.mp3,audio/*"
            >
            <input
              id="src_audio_path"
              name="src_audio_path"
              type="text"
              placeholder="Optional manual path on disk (advanced)"
            >
            <span class="small">
              Drop in an existing track to use as a style / groove reference.
              ACE-Step will analyse the reference and blend it with your prompt.
              MP3s are automatically converted to WAV before processing.
            </span>
          </div>
        </div>

        <!-- LoRA subsection ------------------------------------------------ -->
        <hr style="border:none;border-top:1px solid #111827;margin:16px 0 8px;">
        <div class="small" style="font-weight:600;opacity:0.9;margin-bottom:4px;">
          LoRA adapter (fine-tuning)
        </div>

        <div class="row">
          <label for="lora_select">Installed LoRAs</label>
          <div style="flex:1;display:flex;align-items:center;gap:6px;min-width:0;">
            <select id="lora_select" style="flex:1;min-width:0;">
              <option value="">(None)</option>
              {% for a in lora_adapters %}
              <option value="{{ a.path }}">
                {{ a.name }}{% if a.size_bytes %} ({{ "%.1f"|format(a.size_bytes / (1024*1024)) }} MB){% endif %}
              </option>
              {% endfor %}
            </select>
            <button type="button" class="btn" id="btnApplyLora">
              <span class="icon">⬇</span><span class="label">Use</span>
            </button>
            <button type="button" class="btn" id="btnClearLora">
              <span class="icon">✖</span><span class="label">Clear</span>
            </button>
          </div>
        </div>

        <div class="row">
          <label>LoRA adapter</label>
          <div style="flex:1;display:flex;flex-direction:column;gap:6px;min-width:0;">
            <div style="display:flex;gap:8px;align-items:center;min-width:0;">
              <input
                id="lora_name_or_path"
                name="lora_name_or_path"
                type="text"
                placeholder="Name of LoRA subfolder within <root>\\custom_lora"
                style="flex:1;min-width:0;">
              <button
                type="button"
                class="btn"
                id="btnLoraBrowse">
                <span class="icon">📂</span><span class="label">Browse…</span>
              </button>
            </div>
            <span class="small">
              Click <strong>Browse…</strong>, then select the subfolder that contains your trained LoRA.
              The folder must contain a file such as
              <code>pytorch_lora_weights.safetensors</code>.
              If left empty, ACE-Step will use the base model only.
              <br><br>
              Advanced users can also type a full local folder path or a Hugging Face LoRA repository ID.
            </span>

            <!-- Hidden folder picker -->
            <input
              id="lora_folder_picker"
              type="file"
              name="lora_folder"
              style="display:none;"
              webkitdirectory
              directory
              multiple>
          </div>
        </div>

        <div class="slider-row">
          <label for="lora_weight">LoRA weight</label>
          <input id="lora_weight" name="lora_weight" type="number" min="0" max="10" step="0.05" value="0.5">
          <span class="small">
            0 = disable adapter, 1 = full effect, &gt;1 = exaggerate its effect (likely to produce artifacts at high levels).
          </span>
        </div>
      </div> <!-- /advancedKnobs -->

      <!-- Saved presets --------------------------------------------------- -->
      <hr style="border:none;border-top:1px solid #111827;margin:16px 0 8px;">
      <div class="small" style="font-weight:600;opacity:0.9;margin-bottom:4px;">
        <b>Saved presets</b>
      </div>

      <div class="row">
        <label for="userPresetSelect">My presets</label>
        <div style="flex:1;display:flex;align-items:center;gap:6px;min-width:0;">
          <select id="userPresetSelect" style="flex:1;min-width:0;">
            <option value="">(No saved presets yet)</option>
          </select>
          <button type="button" class="btn" id="btnLoadUserPreset">
            <span class="icon">⬇</span><span class="label">Load</span>
          </button>
          <button type="button" class="btn" id="btnSaveUserPreset">
            <span class="icon">💾</span><span class="label">Save</span>
          </button>
          <button type="button" class="btn" id="btnDeleteUserPreset">
            <span class="icon">🗑</span><span class="label">Delete</span>
          </button>
        </div>
      </div>
      <div class="small">
        Save and reuse your favorite prompt / knob combinations. Select a preset and click Load,
        or click Save to capture the current settings. Delete removes the selected preset.
      </div>

      <!-- Hidden output directory field (synced with Settings panel) -->
      <input id="out_dir" name="out_dir" type="hidden" value="{{ out_dir or default_out_dir }}">

      {% if short_message %}
      <div class="toast {{ 'error' if error else '' }}">
        {{ short_message }}
        {% if details %}
          <button type="button" class="btn" style="margin-left:8px;padding-inline:10px;"
                  onclick="CDMF.toggleDetails()">
            <span class="icon">📄</span><span>Details</span>
          </button>
        {% endif %}
      </div>
      {% endif %}

      {% if details %}
      <div id="detailsPanel" class="details-panel" style="{{ 'display:block;' if (error and details) else 'display:none;' }}">
        {{ details }}
      </div>
      {% endif %}

      <div class="footer">
        Tip: Start with 0.5–2.0s fade in/out. When “Instrumental” is checked, AceForge sends [inst] as the ACE-Step lyrics token so the model focuses on backing tracks. ACE-Step can generate up to ~4 minutes in one shot, so you don't need tiling or stitching here.
      </div>
        </form>

        <!-- Modal: Generate prompt / lyrics from concept -->
        <div
          id="autoPromptLyricsModal"
      style="
        position:fixed;
        inset:0;
        display:none;
        align-items:center;
        justify-content:center;
        background:rgba(0,0,0,0.55);
        z-index:2000;
      ">
      <div
        class="card"
        style="max-width:560px;width:100%;box-shadow:0 20px 45px rgba(0,0,0,0.55);">
        <div class="card-header-row">
          <h3>Generate prompt / lyrics</h3>
        </div>

        <div class="row">
          <label for="apl_concept">Song concept</label>
          <textarea
            id="apl_concept"
            rows="4"
            placeholder="e.g. melancholic SNES overworld at night, soft chiptune pads, distant city lights..."></textarea>
        </div>

        <div class="row">
          <label>Generate</label>
          <div style="flex:1;display:flex;flex-wrap:wrap;gap:8px;align-items:center;min-width:0;">
            <label class="small" style="display:flex;align-items:center;gap:4px;cursor:pointer;">
              <input
                type="radio"
                name="apl_mode"
                id="apl_mode_prompt"
                value="prompt">
              Prompt only
            </label>
            <label class="small" style="display:flex;align-items:center;gap:4px;cursor:pointer;">
              <input
                type="radio"
                name="apl_mode"
                id="apl_mode_lyrics"
                value="lyrics">
              Lyrics only
            </label>
            <label class="small" style="display:flex;align-items:center;gap:4px;cursor:pointer;">
              <input
                type="radio"
                name="apl_mode"
                id="apl_mode_both"
                value="both">
              Prompt + lyrics
            </label>
          </div>
        </div>

        <div class="small" style="margin-top:-4px;margin-bottom:8px;">
          Defaults to <strong>Prompt only</strong> when <strong>Instrumental</strong> is checked,
          or <strong>Prompt + lyrics</strong> when it is unchecked.
          Lyrics only affect audio when <strong>Instrumental</strong> is <em>unchecked</em>.
        </div>

        <div class="row" style="justify-content:flex-end;gap:8px;">
          <button
            type="button"
            class="btn"
            onclick="CDMF.closeAutoPromptLyricsModal()">
            <span class="icon">✖</span><span class="label">Cancel</span>
          </button>
          <button
            type="button"
            class="btn primary"
            id="apl_generate"
            onclick="CDMF.autoPromptLyricsFromConcept()">
            <span class="icon">✨</span><span class="label">Generate</span>
          </button>
        </div>
      </div>
    </div>

        <!-- Voice Cloning form card (mode: voice_clone) ----------------------------- -->
        <form
          id="voiceCloneForm"
          class="card card-mode"
          data-mode="voice_clone"
          method="post"
          action="{{ url_for('cdmf_voice_cloning.voice_clone') }}"
          enctype="multipart/form-data"
          onsubmit="return CDMF.onSubmitVoiceClone(event)"
          style="display:none;">
          <div class="card-header-row">
            <div style="flex:1;min-width:0;">
              <h2>Voice Cloning</h2>
              <div id="voiceCloneLoadingBar" class="loading-bar" style="display:none;">
                <div class="loading-bar-inner"></div>
              </div>
            </div>
            <div style="display:flex;gap:8px;align-items:center;">
              <button id="voiceCloneButton" type="submit" class="btn primary">
                <span class="icon">🎤</span><span>Clone Voice</span>
              </button>
            </div>
          </div>

          <div class="small" style="margin-top:8px;margin-bottom:16px;">
            Clone a voice from a reference audio file using XTTS v2. Upload a reference audio file (MP3/WAV) and enter text to synthesize.
          </div>

          <div class="row">
            <label for="voice_clone_text">Text to Synthesize</label>
            <textarea
              id="voice_clone_text"
              name="text"
              rows="4"
              placeholder="Enter the text you want to synthesize in the cloned voice..."
              required></textarea>
          </div>

          <div class="row">
            <label for="speaker_wav">Reference Audio File</label>
            <input
              id="speaker_wav"
              name="speaker_wav"
              type="file"
              accept="audio/*,.mp3,.wav,.m4a,.flac"
              required>
            <div class="small">
              Upload a reference audio file (MP3, WAV, M4A, or FLAC) containing the voice you want to clone.
            </div>
          </div>

          <div class="row">
            <label for="voice_clone_output_filename">Output Filename</label>
            <input
              id="voice_clone_output_filename"
              name="output_filename"
              type="text"
              placeholder="voice_clone_output"
              value="voice_clone_output">
            <div class="small">
              Output filename (without extension). Will be saved as .wav in the output directory.
            </div>
          </div>

          <div class="row">
            <label for="voice_clone_language">Language</label>
            <select id="voice_clone_language" name="language">
              <option value="en" selected>English</option>
              <option value="es">Spanish</option>
              <option value="fr">French</option>
              <option value="de">German</option>
              <option value="it">Italian</option>
              <option value="pt">Portuguese</option>
              <option value="pl">Polish</option>
              <option value="tr">Turkish</option>
              <option value="ru">Russian</option>
              <option value="nl">Dutch</option>
              <option value="cs">Czech</option>
              <option value="ar">Arabic</option>
              <option value="zh-cn">Chinese (Simplified)</option>
              <option value="ja">Japanese</option>
              <option value="hu">Hungarian</option>
              <option value="ko">Korean</option>
            </select>
          </div>

          <div class="row">
            <label for="voice_clone_device">Device</label>
            <select id="voice_clone_device" name="device_preference">
              <option value="auto" selected>Auto (MPS if available, else CPU)</option>
              <option value="mps">Apple Silicon GPU (MPS)</option>
              <option value="cpu">CPU</option>
            </select>
            <div class="small">
              Device selection for voice cloning. On M2/M3 Macs, CPU can be surprisingly fast and may avoid MPS artifacts.
              First generation is slower (compiles execution graph), subsequent generations are faster.
            </div>
          </div>

          <hr style="border:none;border-top:1px solid #111827;margin:16px 0 8px;">

          <div class="small" style="font-weight:600;opacity:0.9;margin-bottom:8px;">
            Advanced Parameters
          </div>

          <div class="slider-row">
            <label for="voice_clone_temperature">Temperature</label>
            <input id="voice_clone_temperature_range" type="range" min="0.0" max="1.0" step="0.01"
                   value="0.75" oninput="CDMF.syncRange('voice_clone_temperature', 'voice_clone_temperature_range')">
            <input id="voice_clone_temperature" name="temperature" type="number" min="0.0" max="1.0" step="0.01"
                   value="0.75" oninput="CDMF.syncNumber('voice_clone_temperature', 'voice_clone_temperature_range')">
            <div class="small">Sampling temperature. Lower values produce more deterministic output.</div>
          </div>

          <div class="slider-row">
            <label for="voice_clone_length_penalty">Length Penalty</label>
            <input id="voice_clone_length_penalty_range" type="range" min="0.0" max="2.0" step="0.1"
                   value="1.0" oninput="CDMF.syncRange('voice_clone_length_penalty', 'voice_clone_length_penalty_range')">
            <input id="voice_clone_length_penalty" name="length_penalty" type="number" min="0.0" max="2.0" step="0.1"
                   value="1.0" oninput="CDMF.syncNumber('voice_clone_length_penalty', 'voice_clone_length_penalty_range')">
            <div class="small">Length penalty for generation.</div>
          </div>

          <div class="slider-row">
            <label for="voice_clone_repetition_penalty">Repetition Penalty</label>
            <input id="voice_clone_repetition_penalty_range" type="range" min="0.0" max="10.0" step="0.1"
                   value="5.0" oninput="CDMF.syncRange('voice_clone_repetition_penalty', 'voice_clone_repetition_penalty_range')">
            <input id="voice_clone_repetition_penalty" name="repetition_penalty" type="number" min="0.0" max="10.0" step="0.1"
                   value="5.0" oninput="CDMF.syncNumber('voice_clone_repetition_penalty', 'voice_clone_repetition_penalty_range')">
            <div class="small">Penalty for repeating tokens. Higher values reduce repetition.</div>
          </div>

          <div class="slider-row">
            <label for="voice_clone_top_k">Top-K</label>
            <input id="voice_clone_top_k" name="top_k" type="number" min="1" max="100" step="1"
                   value="50">
            <div class="small">Top-K sampling parameter.</div>
          </div>

          <div class="slider-row">
            <label for="voice_clone_top_p">Top-P</label>
            <input id="voice_clone_top_p_range" type="range" min="0.0" max="1.0" step="0.01"
                   value="0.85" oninput="CDMF.syncRange('voice_clone_top_p', 'voice_clone_top_p_range')">
            <input id="voice_clone_top_p" name="top_p" type="number" min="0.0" max="1.0" step="0.01"
                   value="0.85" oninput="CDMF.syncNumber('voice_clone_top_p', 'voice_clone_top_p_range')">
            <div class="small">Nucleus sampling parameter.</div>
          </div>

          <div class="slider-row">
            <label for="voice_clone_speed">Speed</label>
            <input id="voice_clone_speed_range" type="range" min="0.25" max="4.0" step="0.05"
                   value="1.0" oninput="CDMF.syncRange('voice_clone_speed', 'voice_clone_speed_range')">
            <input id="voice_clone_speed" name="speed" type="number" min="0.25" max="4.0" step="0.05"
                   value="1.0" oninput="CDMF.syncNumber('voice_clone_speed', 'voice_clone_speed_range')">
            <div class="small">Speech speed multiplier (0.25x to 4.0x).</div>
          </div>

          <div class="row">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
              <input
                id="voice_clone_enable_text_splitting"
                name="enable_text_splitting"
                type="checkbox"
                checked>
              Enable Text Splitting
            </label>
            <div class="small">Automatically split long text into sentences for better quality.</div>
          </div>

          <!-- Hidden field for output directory (synced from Settings) -->
          <input id="voice_clone_out_dir" name="out_dir" type="hidden" value="{{ default_out_dir or '' }}">

        </form>

        <!-- Training card: ACE-Step LoRA skeleton (mode: train) --------------- -->
        <form
          id="trainForm"
          class="card card-mode"
          data-mode="train"
      method="post"
      action="{{ url_for('cdmf_training.train_lora') }}"
      target="training_frame"
      enctype="multipart/form-data"
      onsubmit="return CDMF.onSubmitTraining(event)"
      style="display:none;">
      <div class="card-header-row">
        <div style="flex:1;min-width:0;">
          <h2>Train Custom LoRA</h2>
        </div>
        <div style="display:flex;gap:8px;align-items:center;">
          <button type="submit" class="btn" id="btnStartTraining">
            <span class="icon">🧠</span><span>Start Training</span>
          </button>
          <button type="button" class="btn secondary" id="btnPauseTraining" disabled>
            ⏸ Pause
          </button>
          <button type="button" class="btn secondary" id="btnResumeTraining" style="display:none;">
            ▶ Resume
          </button>
          <button type="button" class="btn danger" id="btnCancelTraining" disabled>
            ✖ Cancel
          </button>
        </div>
      </div>

      <!-- Simple status banner we can toggle to "running" in JS -->
      <div
        id="trainingStatus"
        class="training-status small"
        data-state="idle"
        style="margin-bottom:8px;">
        <!-- You can style these classes in cdmf.css however you like -->
        <span class="training-status-indicator"></span>
        <span class="training-status-text">
          Idle – no training in progress. When you start a LoRA run, this will
          show an animated “candycane” indicator.
        </span>
      </div>

      <!-- LoRA training progress bar (indeterminate candycane style) -->
      <div class="row row-progress" style="flex-direction:column;align-items:stretch;">
        <div class="small" style="margin-bottom:8px;color:#999;">
          Pausing will stop training and allow resuming later from the last saved checkpoint.
          If you restart the server, the paused state will persist until you Resume or Cancel.
        </div>
        <div class="row-progress-body" style="width:100%;margin-top:4px;">
          <div
            id="loraLoadingBar"
            class="loading-bar"
            style="display:none;width:100%;">
            <div class="loading-bar-inner"></div>
          </div>
        </div>
      </div>

      <div class="small" style="margin-bottom:8px;">
        Run the LoRA training process. This may take a long time depending on your GPU(s) / system setup / dataset size. If you see the rainbow candystripe bar above and there are no errors in the console or trainer.log inside \ace_training\<adapter name>, training is still ongoing and you should keep waiting.
      </div>

      <div class="row">
        <label>&nbsp;</label>
        <div style="flex:1;min-width:0;">
          <div
            id="mufunLoadingBar"
            class="loading-bar"
            style="display:none;">
            <div class="loading-bar-inner"></div>
          </div>
        </div>
      </div>

      <div class="row">
        <label>Dataset Setup / Formatting</label>
        <div style="flex:1;display:flex;flex-direction:column;gap:6px;min-width:0;">
          <div style="display:flex;gap:8px;align-items:center;min-width:0;">
            <input
              id="dataset_path"
              name="dataset_path"
              type="text"
              placeholder="Name of dataset subfolder within <root>\training_datasets"
              style="flex:1;min-width:0;">
            <button
              type="button"
              class="btn"
              id="btnDatasetBrowse">
              <span class="icon">📂</span><span class="label">Browse…</span>
            </button>
          </div>
          <span class="small">
            Click <strong>Browse…</strong>, then select the subfolder that contains your curated training dataset. The dataset folder MUST be a subfolder within <CDMF root>\training_datasets. If you haven't created prompt and lyric text files for your songs yet, you must do that first.<br><br><strong>You can try using the MuFun-ACEStep model below this section to do that automatically, if you don't want to do it by hand.</strong> This will require a separate download ~16.5GB download.
            <br><br>
            The folder contents should consist of .mp3 files and corresponding .txt files, one for lyrics and one for prompt/tags for each song.
            <br><br><strong>Example for a file named "foo.mp3":</strong><br><br>
            <ul>
            <li>Lyrics file name: "foo_lyrics.txt"<br>
            <li>Lyrics should be formatted in a manner that ACE-Step can understand. See examples at <a href=https://ace-step.github.io/>https://ace-step.github.io/</a>.<br>
            <li>For instrumental tracks, *_lyrics.txt should contain only the bracketed tag "<strong>[inst]</strong>".<br><br>
            <li>Prompt file name: "foo_prompt.txt"<br>
            <li>Example prompt file contents: "16-bit RPG snowfield, SNES-style chiptune, looping BGM, gentle square wave lead, soft noise drums, melancholic but hopeful"</ul>
            <br><br>
            <strong>NOTE:</strong> After you select a folder and press "Upload", your browser may warn you that the contents will be uploaded. That dialog is just about giving the browser
            access to the folder. CDMF does not actually upload anything to the Internet, and none of the training files will be processed until you click <strong>Start Training</strong>.
          </span>
          <!-- Hidden folder picker; only used to let the user pick a folder.
               Files are only sent on form submit. -->
          <input
            id="dataset_folder_picker"
            type="file"
            name="dataset_files"
            style="display:none;"
            webkitdirectory
            directory
            multiple>
        </div>
      </div>

      <div class="row">
        <label for="exp_name">Experiment / adapter name</label>
        <input
          id="exp_name"
          name="exp_name"
          type="text"
          placeholder="Short name for this LoRA (e.g. lofi_chiptunes_v1)">
      </div>

      <div class="row">
        <label for="lora_config_select">LoRA config (JSON)</label>
        <div style="flex:1;display:flex;flex-direction:column;gap:6px;min-width:0;">
          <div style="display:flex;gap:8px;align-items:center;min-width:0;">
            <select
              id="lora_config_select"
              style="flex:1;min-width:0;">
              <option value="">Loading configs…</option>
            </select>
            <button
              type="button"
              class="btn secondary"
              id="btnLoraConfigHelp"
              title="What do these configs do?">
              ❓
            </button>
          </div>
          <span class="small">
            Choose a LoRA configuration preset. All <code>.json</code> files
            placed in the <code>training_config</code> folder under the CDMF
            root will appear here after you reload this page.
            <br><br>
            <code>default_config.json</code> is written as the same settings as
            <code>light_base_layers.json</code>, which is a safe, conservative
            default.
          </span>
          <!-- Hidden field actually submitted to the backend. JS keeps this
               in sync with the selected option above. -->
          <input
            id="lora_config_path"
            name="lora_config_path"
            type="hidden"
            value="">
        </div>
      </div>

      <div class="slider-row">
        <label for="max_steps">Max training steps</label>
        <input
          id="max_steps"
          name="max_steps"
          type="number"
          min="100"
          step="100"
          value="50000">
        <span class="small">
          Rough upper bound on how many optimisation steps to run. Training will
          stop once <em>either</em> this or the max epochs below is reached.
          If you're unsure, leave this high and control run length with
          max epochs. The default value (50,000) is too high to realistically
          control a run.
        </span>
      </div>

      <div class="slider-row">
        <label for="max_epochs">Max epochs</label>
        <input
          id="max_epochs"
          name="max_epochs"
          type="number"
          min="1"
          step="1"
          value="20">
        <span class="small">
          Number of full passes over your dataset (defaults to 20).
        </span>
      </div>

      <div class="slider-row">
        <label for="learning_rate">Learning rate</label>
        <input
          id="learning_rate"
          name="learning_rate"
          type="number"
          step="1e-6"
          value="1e-4">
        <span class="small">
          Smaller is safer; 1e-4–1e-5 are typical LoRA learning rates. If you have the GPU power, a setting like 5e-5 may produce better results.
        </span>
      </div>

      <div class="slider-row">
        <label for="max_audio_seconds">Max clip seconds</label>
        <input
          id="max_audio_seconds"
          name="max_audio_seconds"
          type="number"
          min="4"
          max="120"
          step="1"
          value="60">
        <span class="small">
          Upper bound on per-example audio length fed into ACE-Step (in seconds).
          Shorter clips train faster and may be fine for BGM. 
          Try turning this setting down if you encounter memory/VRAM errors.
        </span>
      </div>

      <div class="slider-row">
        <label for="ssl_coeff">SSL loss weight</label>
        <input
          id="ssl_coeff"
          name="ssl_coeff"
          type="number"
          min="0"
          max="2"
          step="0.1"
          value="1.0">
        <span class="small">
          Weight for the MERT / mHuBERT self-supervised losses. Set to 0 to
          disable SSL (recommended for pure instrumental / chiptune datasets).
        </span>
      </div>

      <div class="row">
        <label for="instrumental_only">Instrumental dataset</label>
        <div style="flex:1;min-width:0;display:flex;align-items:center;gap:8px;">
          <input
            id="instrumental_only"
            name="instrumental_only"
            type="checkbox"
            value="1">
          <span class="small">
            Check this if your dataset is purely instrumental / has no vocals.
            LoRA layers attached to lyric and speaker-specific blocks will be
            frozen so only music/texture layers are trained. You can combine
            this with an SSL weight of 0 for chiptune or BGM-style runs.
          </span>
        </div>
      </div>

      <div class="slider-row">
        <label for="lora_save_every">Save LoRA every N steps</label>
        <input
          id="lora_save_every"
          name="lora_save_every"
          type="number"
          min="0"
          step="10"
          value="50">
        <span class="small">
          How often to write lightweight LoRA checkpoints during training.
          0 disables periodic saves; a final adapter is still written at the end.
        </span>
      </div>

      <hr style="border:none;border-top:1px solid #111827;margin:12px 0 8px;">
      <div class="small" style="font-weight:600;opacity:0.9;margin-bottom:4px;">
        Advanced trainer settings (optional)
      </div>

      <div class="row">
        <label for="precision">Precision</label>
        <div style="flex:1;min-width:0;">
          <select id="precision" name="precision" style="width:100%;">
            <option value="32" selected>32-bit (safe default)</option>
            <option value="16-mixed">16-mixed (faster, less VRAM)</option>
            <option value="bf16-mixed">bf16-mixed (modern GPUs only)</option>
          </select>
          <span class="small">
            Controls numerical precision for training. Leave at 32 unless you
            know your GPU and PyTorch stack support mixed precision safely.
          </span>
        </div>
      </div>

      <div class="slider-row">
        <label for="accumulate_grad_batches">Grad accumulation</label>
        <input
          id="accumulate_grad_batches"
          name="accumulate_grad_batches"
          type="number"
          min="1"
          step="1"
          value="1">
        <span class="small">
          Virtual batch size multiplier. 1 = no accumulation; higher values
          simulate larger batches when VRAM is tight.
        </span>
      </div>

      <div class="slider-row">
        <label for="gradient_clip_val">Gradient clip (norm)</label>
        <input
          id="gradient_clip_val"
          name="gradient_clip_val"
          type="number"
          min="0"
          step="0.1"
          value="0.5">
        <span class="small">
          Max gradient norm. 0 disables clipping. Leave at 0.5 unless you are
          debugging instabilities.
        </span>
      </div>

      <div class="row">
        <label for="gradient_clip_algorithm">Clip algorithm</label>
        <div style="flex:1;min-width:0;">
          <select
            id="gradient_clip_algorithm"
            name="gradient_clip_algorithm"
            style="width:100%;">
            <option value="norm" selected>norm (recommended)</option>
            <option value="value">value</option>
          </select>
        </div>
      </div>

      <div class="slider-row">
        <label for="reload_dataloaders_every_n_epochs">Reload DataLoader every</label>
        <input
          id="reload_dataloaders_every_n_epochs"
          name="reload_dataloaders_every_n_epochs"
          type="number"
          min="0"
          step="1"
          value="1">
        <span class="small">
          Epochs between DataLoader rebuilds. 1 = reload each epoch. 0 = never
          reload. You can usually leave this at 1.
        </span>
      </div>

      <div class="slider-row">
        <label for="val_check_interval">Val check interval</label>
        <input
          id="val_check_interval"
          name="val_check_interval"
          type="number"
          min="0"
          step="1"
          value="">
        <span class="small">
          Optional validation frequency (in training batches). Leave blank to
          use Lightning's default (typically once per epoch).
        </span>
      </div>

      <div class="slider-row">
        <label for="devices">Devices</label>
        <input
          id="devices"
          name="devices"
          type="number"
          min="1"
          step="1"
          value="1">
        <span class="small">
          Number of GPUs to use when training (future hook; currently passed
          through to the ACE-Step trainer as-is).
        </span>
      </div>

      <!-- LoRA config help modal -->
      <div
        id="loraConfigModal"
        style="display:none;position:fixed;z-index:1000;left:0;top:0;width:100%;height:100%;overflow:auto;background-color:rgba(0,0,0,0.6);">
        <div
          style="background-color:#111827;margin:10% auto;padding:16px;border-radius:12px;max-width:640px;color:#e5e7eb;box-shadow:0 10px 40px rgba(0,0,0,0.6);">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <h3 style="margin:0;font-size:1.1rem;">LoRA config presets</h3>
            <button
              type="button"
              id="btnLoraConfigModalClose"
              class="btn secondary">
              ✖
            </button>
          </div>
          <div class="small" style="line-height:1.5;">
            <p>
              <strong>Light / Medium / Heavy</strong> control how many LoRA
              parameters are trained for each target module. Roughly:
              <em>light</em> = smallest adapters (more subtle, safer),
              <em>medium</em> = stronger effect,
              <em>heavy</em> = largest adapters (more aggressive, more VRAM /
              overfit risk).
            </p>

            <p>
              <strong>base_layers</strong> – Focuses mostly on the main
              self-attention query/key/value and output layers in the ACE-Step
              transformer. Good starting point for gentle style or timbre
              nudges.
            </p>

            <p>
              <strong>extended_attn</strong> – Trains both the base attention
              and the cross-attention side projections (extra Q/K/V and
              <code>to_add_out</code> layers). This gives stronger control over
              how prompts and conditioning shape the sound.
            </p>

            <p>
              <strong>heavy transformer / transformer_deep</strong> – Extends
              into the transformer projectors, timestep embeddings, and final
              mixing layers. These presets produce larger LoRA files and much
              stronger style capture, and are what we mean by a “heavy
              transformer” config family.
            </p>

            <p>
              <strong>full_stack</strong> – In addition to the transformer core,
              this also trains the conditioning stack (speaker / genre
              embeddings plus lyric encoder and projector). This has the most
              “identity rewriting” power, but also the highest risk of
              overfitting and dataset imprinting.
            </p>

            <p>
              <strong>Note:</strong>
              <code>default_config.json</code> is written with the same
              settings as <code>light_base_layers.json</code>, so either one is
              a safe default for early runs.
            </p>
          </div>
        </div>
      </div>

      <div class="small">
        Note: this UI is still an early stub. Training is heavy and will keep
        your GPU busy for a while. Keep the server console window open and watch
        it for detailed logs and errors.
      </div>
        </form>

        <!-- Dataset Mass Tagging card ----------------------------------------- -->
        <div
          id="datasetTagCard"
          class="card card-mode"
          data-mode="train"
          style="display:none;">
      <div class="card-header-row">
        <div style="flex:1;min-width:0;">
          <h2>Dataset Mass Tagging (Prompt / Lyrics Templates)</h2>
        </div>
      </div>

      <div class="small" style="margin-bottom:8px;">
        Quickly create <code>_prompt.txt</code> and / or <code>_lyrics.txt</code>
        files for every <code>.mp3</code> / <code>.wav</code> in a training
        dataset. This is useful if you just want a consistent tag set and
        default lyrics like <code>[inst]</code> without waiting for MuFun.
      </div>

      <div class="row">
        <label for="tag_dataset_path">Dataset folder</label>
        <div style="flex:1;display:flex;flex-direction:column;gap:6px;min-width:0;">
          <div style="display:flex;gap:8px;align-items:center;min-width:0;">
            <input
              id="tag_dataset_path"
              name="tag_dataset_path"
              type="text"
              placeholder="Name of dataset subfolder within &lt;root&gt;\training_datasets"
              style="flex:1;min-width:0;">
            <button
              type="button"
              class="btn"
              id="btnTagDatasetBrowse">
              <span class="icon">📂</span><span class="label">Browse…</span>
            </button>
          </div>
          <span class="small">
            Click <strong>Browse…</strong>, then select the folder that contains
            your training tracks. The folder MUST live under the
            <code>training_datasets</code> directory in the AceForge root.
            Only <code>.mp3</code> / <code>.wav</code> files in that folder will
            be touched.
          </span>
          <input
            id="tag_dataset_picker"
            type="file"
            name="tag_dataset_files"
            style="display:none;"
            webkitdirectory
            directory
            multiple>
        </div>
      </div>

      <div class="row">
        <label for="tag_base_prompt">Base tags</label>
        <div style="flex:1;min-width:0;">
          <textarea
            id="tag_base_prompt"
            name="tag_base_prompt"
            rows="2"
            placeholder="e.g. '16-bit, 8-bit, SNES, retro RPG BGM, looping instrumental'"
            style="width:100%;resize:vertical;font-size:0.85rem;"></textarea>
          <span class="small">
            Written into each <code>_prompt.txt</code> when you click
            <strong>Create prompt files</strong>. You can still hand-edit
            individual prompt files later, or combine this with MuFun for
            lyrics only.
          </span>
        </div>
      </div>

      <div class="row">
        <label>Actions</label>
        <div style="flex:1;display:flex;flex-direction:column;gap:6px;min-width:0;">
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
            <button
              type="button"
              class="btn"
              id="btnTagCreatePrompts">
              <span class="icon">🏷️</span><span class="label">Create prompt files</span>
            </button>
            <button
              type="button"
              class="btn"
              id="btnTagCreateInstLyrics">
              <span class="icon">🎵</span><span class="label">Create [inst] lyrics files</span>
            </button>
            <label class="small" style="display:flex;align-items:center;gap:4px;">
              <input
                id="tag_overwrite"
                type="checkbox"
                name="tag_overwrite">
              <span>Overwrite existing files</span>
            </label>
          </div>

          <div
            id="tagBusyBar"
            class="loading-bar"
            style="display:none;margin-top:4px;">
            <div class="loading-bar-inner"></div>
          </div>

          <span id="tagStatusText" class="small">
            Ready. Choose a dataset, enter base tags, then run one of the actions above.
          </span>
        </div>
      </div>
        </div>

        <div
          id="mufunCard"
          class="card card-mode"
          data-mode="train"
          style="display:none;">
      <div class="card-header-row">
        <div style="flex:1;min-width:0;">
          <h2>Experimental - Analyze Dataset with MuFun-ACEStep (Auto-Create Prompt/Lyric Files)</h2>
        </div>
        <div style="display:flex;gap:8px;align-items:center;">
          <button
            type="button"
            class="btn"
            id="btnMufunAnalyze">
            <span class="icon">🔍</span><span>Analyze Folder</span>
          </button>
        </div>
      </div>

      <div class="small" style="margin-bottom:8px;">
        Run the MuFun-ACEStep analysis model over a folder of .mp3 / .wav files.
        For each track, this will create <code>_prompt.txt</code> and
        <code>_lyrics.txt</code> files next to the audio if they are missing.
      </div>

      <!-- MuFun busy bar: full-width candystripe -->
      <div class="row">
        <div style="flex:1;min-width:0;">
          <div
            id="mufunBusyBar"
            class="loading-bar"
            style="display:none; margin-bottom:8px;">
            <div class="loading-bar-inner"></div>
          </div>
        </div>
      </div>

      <!-- MuFun controls / label row -->
      <div class="row">
        <label>MuFun model</label>
        <div style="flex:1;display:flex;flex-direction:column;gap:6px;min-width:0;">

          <div style="display:flex;gap:8px;align-items:center;min-width:0;">
            <span id="mufunStatusText" class="small">
              Checking MuFun model status…
            </span>
            <button
              type="button"
              class="btn"
              id="btnMufunEnsure">
              <span class="icon">⬇️</span><span class="label">Install / Check</span>
            </button>
          </div>

          <span class="small">
            The MuFun-ACEStep model is large and will be stored locally under
            the AceForge <code>models</code> folder. Once installed, you can
            reuse it for multiple datasets.
          </span>
        </div>
      </div>

      <div class="row">
        <label for="mufun_dataset_path">Dataset folder</label>
        <div style="flex:1;display:flex;flex-direction:column;gap:6px;min-width:0;">
          <div style="display:flex;gap:8px;align-items:center;min-width:0;">
            <input
              id="mufun_dataset_path"
              name="mufun_dataset_path"
              type="text"
              placeholder="Name of dataset subfolder within <root>\training_datasets"
              style="flex:1;min-width:0;">
            <button
              type="button"
              class="btn"
              id="btnMufunDatasetBrowse">
              <span class="icon">📂</span><span class="label">Browse…</span>
            </button>
          </div>
          <span class="small">
            Click <strong>Browse…</strong>, then select the subfolder that contains your training dataset. The dataset folder MUST be a subfolder within <CDMF root>\training_datasets. Just name the subfolder whatever you want and drop .mp3 or .wav files inside. These will be your training files.
          </span>
          <input
            id="mufun_dataset_picker"
            type="file"
            name="mufun_dataset_files"
            style="display:none;"
            webkitdirectory
            directory
            multiple>
        </div>
      </div>

      <div class="row">
        <label for="mufun_base_prompt">Base tags</label>
        <div style="flex:1;min-width:0;">
          <textarea
            id="mufun_base_prompt"
            name="mufun_base_prompt"
            rows="2"
            placeholder="Optional base tags for this dataset, e.g. '16-bit, 8-bit, SNES, retro RPG BGM, looping instrumental'. It's recommended that you organize datasets by tags and make sure you apply these as the MuFun analyzer is not always consistent."
            style="width:100%;resize:vertical;font-size:0.85rem;"></textarea>
          <span class="small">
            These tags are prepended to MuFun's tags for each track when
            writing <code>_prompt.txt</code>. Leave blank to use only MuFun's tags.
          </span>
        </div>
      </div>

      <div class="row">
        <label for="mufun_instrumental_only">Instrumental</label>
        <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:6px;">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
            <input
              type="checkbox"
              id="mufun_instrumental_only"
              name="mufun_instrumental_only">
            <span>All tracks in this dataset are instrumental</span>
          </label>
          <span class="small">
            If checked, the analyzer will treat every track as instrumental and
            override MuFun's lyrics output when writing <code>_lyrics.txt</code>,
            forcing the lyrics to <code>[inst]</code> even if MuFun predicts text
            or non-English content.
          </span>
        </div>
      </div>

      <div class="row">
        <label for="mufun_results">Results</label>
        <div style="flex:1;min-width:0;">
          <textarea
            id="mufun_results"
            name="mufun_results"
            readonly
            rows="8"
            style="width:100%;resize:vertical;font-family:ui-monospace,monospace;"></textarea>
        </div>
      </div>

        </div> <!-- /mufunCard -->
      </div> <!-- /column-left -->

      <!-- Right column: Music Player, Console, Settings -->
      <div class="column-right">
        <!-- Music player card -->
        <div class="card">
          <div class="card-header-row">
            <h2>Music Player</h2>
          </div>

          <div class="row">
            <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:6px;">

              <div class="track-filter-row small">
                <span>Filter by category:</span>
                <div id="categoryFilters" class="category-filter-chips"></div>
              </div>

              <div id="trackListHeader" class="track-list-header">
                <div class="track-header-cell track-header-fav">★</div>
                <button type="button"
                        class="track-header-cell track-header-name"
                        data-sort-key="name">
                  Name
                </button>
                <button type="button"
                        class="track-header-cell track-header-length"
                        data-sort-key="seconds">
                  Length
                </button>
                <button type="button"
                        class="track-header-cell track-header-category"
                        data-sort-key="category">
                  Category
                </button>
                <button type="button"
                        class="track-header-cell track-header-created"
                        data-sort-key="created">
                  Created
                </button>
                <div class="track-header-cell track-header-actions"></div>
              </div>

              <div id="trackListPanel" class="track-list-panel">
                {% if tracks %}
                  {% for name in tracks %}
                  <div class="track-row{% if current_track == name %} active{% endif %}"
                       data-track-name="{{ name }}">
                    <button type="button"
                            class="track-fav-btn"
                            data-role="favorite"
                            aria-label="Favorite">
                      ★
                    </button>
                    <div class="track-main">
                      <div class="track-name">
                        {{ name[:-4] if (name.lower().endswith('.wav') or name.lower().endswith('.mp3')) else name }}
                      </div>
                      <div class="track-meta">
                        <span class="track-length" data-role="length-label"></span>
                        <span class="track-category" data-role="category-label"></span>
                      </div>
                    </div>
                    <div class="track-actions">
                      <button type="button"
                              class="track-delete-btn"
                              data-role="copy-settings"
                              title="Copy generation settings back into the form"
                              aria-label="Reuse prompt">
                        ⧉
                      </button>
                      <button type="button"
                              class="track-delete-btn"
                              data-role="delete"
                              aria-label="Delete">
                        🗑
                      </button>
                    </div>
                  </div>
                  {% endfor %}
                {% else %}
                  <div class="small">(No tracks yet)</div>
                {% endif %}
              </div>

              <div class="small">
                Tip: Click ★ to favorite, click a category pill or right-click a row to edit category.
                Use the header to sort and the chips above to filter categories.
              </div>

              <!-- Hidden <select> used internally by the JS audio player logic -->
              <select id="trackList" name="trackList" class="track-select-hidden">
                {% if tracks %}
                  {% for name in tracks %}
                    <option value="{{ url_for('cdmf_tracks.serve_music', filename=name) }}"
                            {% if current_track == name %}selected{% endif %}>
                      {{ name[:-4] if (name.lower().endswith('.wav') or name.lower().endswith('.mp3')) else name }}
                    </option>
                  {% endfor %}
                {% else %}
                  <option value="">(No tracks yet)</option>
                {% endif %}
              </select>
            </div>
          </div>

          <div class="progress-container">
            <div class="time-row">
              <span id="currentTimeLabel">0:00</span>
              <span id="durationLabel">0:00</span>
            </div>
            <div class="seek-row">
              <input id="progressSlider" type="range" min="0" max="0" value="0" step="0.01">
            </div>
          </div>

          <div class="player-controls">
            <div class="player-btn-row">
              <button type="button" class="btn" id="btnRewind">
                <span class="icon">⏮</span><span class="label">Rewind</span>
              </button>
              <button type="button" class="btn" id="btnPlay">
                <span class="icon">▶</span><span class="label">Play</span>
              </button>
              <button type="button" class="btn" id="btnStop">
                <span class="icon">⏹</span><span class="label">Stop</span>
              </button>
              <button type="button" class="btn" id="btnLoop">
                <span class="icon">🔁</span><span class="label">Loop</span>
              </button>
              <button type="button" class="btn" id="btnMute">
                <span class="icon">🔇</span><span class="label">Mute</span>
              </button>
            </div>
            <div style="flex:1;display:flex;align-items:center;gap:6px;min-width:160px;">
              <span class="small">Volume</span>
              <input id="volumeSlider" type="range" min="0" max="1" step="0.02" value="0.9" style="flex:1;">
            </div>
          </div>

          <audio id="audioPlayer"></audio>
        </div>

        <!-- Console panel (collapsible) -->
        <div class="card" id="consoleCard">
          <div class="card-header-row" style="cursor:pointer;" onclick="CDMF.toggleConsole && CDMF.toggleConsole()">
            <h2 style="margin:0;">
              <span id="consoleToggleIcon">▼</span> Server Console
            </h2>
            <span class="small" style="opacity:0.7;">
              Click to expand/collapse
            </span>
          </div>
          <div id="consolePanel" style="display:none;">
            <div id="consoleOutput" class="console-output"></div>
            <div class="small" style="margin-top:8px;opacity:0.7;">
              Real-time server logs. Useful for troubleshooting errors.
            </div>
          </div>
        </div>

        <!-- Settings panel (collapsible) -->
        <div class="card" id="settingsCard">
          <div class="card-header-row" style="cursor:pointer;" onclick="CDMF.toggleSettings && CDMF.toggleSettings()">
            <h2 style="margin:0;">
              <span id="settingsToggleIcon">▶</span> Settings
            </h2>
            <span class="small" style="opacity:0.7;">
              Click to expand/collapse
            </span>
          </div>
          <div id="settingsPanel" style="display:none;">
            <div class="row">
              <label for="modelsFolderInput">Models Folder</label>
              <div style="flex:1;display:flex;flex-direction:column;gap:6px;min-width:0;">
                <div style="display:flex;gap:8px;align-items:center;min-width:0;">
                  <input
                    type="text"
                    id="modelsFolderInput"
                    placeholder="Path to models folder"
                    style="flex:1;min-width:0;">
                  <button type="button" class="btn secondary" onclick="CDMF.loadModelsFolder && CDMF.loadModelsFolder()">
                    Load Current
                  </button>
                  <button type="button" class="btn" onclick="CDMF.saveModelsFolder && CDMF.saveModelsFolder()">
                    Save
                  </button>
                </div>
                <div class="small" style="opacity:0.7;">
                  Specify where to store downloaded models. Changes take effect on next restart.
                  Leave empty to use default (<code>ace_models/</code> in the application directory).
                </div>
                <div id="modelsFolderStatus" class="small" style="display:none;margin-top:4px;"></div>
              </div>
            </div>

            <hr style="border:none;border-top:1px solid #111827;margin:16px 0 12px;">

            <div class="row">
              <label for="out_dir_settings">Output directory</label>
              <div style="flex:1;display:flex;flex-direction:column;gap:6px;min-width:0;">
                <input id="out_dir_settings" type="text" value="{{ out_dir or default_out_dir }}" style="flex:1;min-width:0;" onchange="CDMF.syncOutputDirectory && CDMF.syncOutputDirectory()" oninput="CDMF.syncOutputDirectory && CDMF.syncOutputDirectory()">
                <div class="small" style="opacity:0.7;">
                  Directory where generated tracks will be saved. Default: <code>{{ default_out_dir }}</code>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div> <!-- /column-right -->
    </div> <!-- /two-column-layout -->

    <iframe id="generation_frame" name="generation_frame" style="display:none;"></iframe>
    <iframe id="training_frame" name="training_frame" style="display:none;"></iframe>
  </div>

  <!-- Bootstrap data for JS; the heavy logic now lives in scripts/*.js -->
  <script>
    window.CDMF_BOOT = {
      presets: {{ presets | tojson | safe }},
      modelsReady: {{ models_ready | tojson | safe }},
      modelState: {{ model_state | tojson | safe }},
      modelMessage: {{ model_message | tojson | safe }},
      autoplayUrl: {{ autoplay_url or '' | tojson | safe }},
      urls: {
        trainStatus: "{{ url_for('cdmf_training.train_lora_status') }}",
        mufunStatus: "{{ url_for('cdmf_mufun.mufun_status') }}",
        mufunEnsure: "{{ url_for('cdmf_mufun.mufun_ensure') }}",
        mufunAnalyze: "{{ url_for('cdmf_mufun.mufun_analyze_dataset') }}"
      }
    };

    // Back-compat globals used by cdmf_main.js
    (function (boot) {
      boot = boot || {};
      window.CANDY_PRESETS = boot.presets || { instrumental: [], vocal: [] };
      window.CANDY_MODELS_READY = !!boot.modelsReady;
      window.CANDY_MODEL_STATE = boot.modelState || "unknown";
      window.CANDY_MODEL_MESSAGE = boot.modelMessage || "";
      window.CANDY_AUTOPLAY_URL = boot.autoplayUrl || "";
    })(window.CDMF_BOOT);
  </script>

    <!-- Full-page overlay while prompt / lyrics are being generated -->
    <div
      id="lyricsBusyOverlay"
      style="
        position:fixed;
        inset:0;
        display:none;
        align-items:center;
        justify-content:center;
        background:rgba(0,0,0,0.55);
        z-index:3001;
      ">
      <div
        style="
          display:flex;
          flex-direction:column;
          align-items:center;
          gap:8px;
          padding:16px 24px;
          border-radius:999px;
          background:rgba(0,0,0,0.85);
          box-shadow:0 12px 30px rgba(0,0,0,0.7);
        ">
        <div
          style="
            width:26px;
            height:26px;
            border-radius:50%;
            border:3px solid rgba(255,255,255,0.3);
            border-top-color:#fff;
            animation:cdmf-spin 0.9s linear infinite;
          ">
        </div>
        <div class="small" style="color:#fff;">
          Generating prompt / lyrics…
        </div>
      </div>
    </div>

  <!-- Main JS and UI helper modules -->
  <script src="{{ url_for('static', filename='scripts/cdmf_presets_ui.js') }}"></script>
  <script src="{{ url_for('static', filename='scripts/cdmf_tracks_ui.js') }}"></script>
  <script src="{{ url_for('static', filename='scripts/cdmf_player_ui.js') }}"></script>
  <script src="{{ url_for('static', filename='scripts/cdmf_generation_ui.js') }}"></script>
  <script src="{{ url_for('static', filename='scripts/cdmf_main.js') }}"></script>
  <script src="{{ url_for('static', filename='scripts/cdmf_mode_ui.js') }}"></script>
  <script src="{{ url_for('static', filename='scripts/cdmf_training_ui.js') }}"></script>
  <script src="{{ url_for('static', filename='scripts/cdmf_mufun_ui.js') }}"></script>
  <script src="{{ url_for('static', filename='scripts/cdmf_voice_cloning_ui.js') }}"></script>
  <script src="{{ url_for('static', filename='scripts/cdmf_lora_ui.js') }}"></script>
  <script src="{{ url_for('static', filename='scripts/cdmf_console.js') }}"></script>
</body>
</html>
"""
