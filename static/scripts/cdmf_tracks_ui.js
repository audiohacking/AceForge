// C:\CandyDungeonMusicForge\static\scripts\cdmf_tracks_ui.js
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
        candyModelsReady: initialReady,
        candyModelStatusState: initialState,
        candyModelStatusMessage: initialMessage,
        candyModelStatusTimer: null,
        candyGenerateButtonDefaultHTML: null,
        candyTrainButtonDefaultHTML: null,
        candyTrackSortKey: "created",
        candyTrackSortDir: "desc",
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

  // Convenience to ensure filter set stays a Set
  function ensureCategoryFilterSet() {
    const state = getState();
    if (!(state.candyTrackFilterCategories instanceof Set)) {
      state.candyTrackFilterCategories = new Set();
    }
    return state.candyTrackFilterCategories;
  }

  // ---------------------------------------------------------------------------
  // Track selection + playback helper
  // ---------------------------------------------------------------------------
  function selectAndPlayTrack(trackName) {
    const list = document.getElementById("trackList");
    const audio = document.getElementById("audioPlayer");
    if (!list || !audio || !trackName) return;

    const url = "/music/" + encodeURIComponent(trackName);

    // Ensure the hidden <select> has an option for this track.
    let matched = false;
    for (let i = 0; i < list.options.length; i++) {
      const opt = list.options[i];
      if (opt.text === trackName || opt.value === url) {
        list.selectedIndex = i;
        matched = true;
        break;
      }
    }
    if (!matched) {
      const opt = document.createElement("option");
      opt.value = url;
      opt.textContent = (trackName || "").replace(/\.(wav|mp3)$/i, "");
      list.appendChild(opt);
      list.value = url;
    } else {
      list.value = url;
    }

    // Update the audio element.
    if (window.candyIsGenerating) {
      return;
    }
    audio.pause();
    audio.currentTime = 0;
    audio.src = url;
    audio.play().catch(function () {});

    // Highlight the active row.
    const panel = document.getElementById("trackListPanel");
    if (panel) {
      const rows = panel.querySelectorAll(".track-row");
      rows.forEach(function (row) {
        if (row.dataset.trackName === trackName) {
          row.classList.add("active");
        } else {
          row.classList.remove("active");
        }
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Track metadata mutation helpers
  // ---------------------------------------------------------------------------
  async function toggleFavorite(trackName, makeFavorite) {
    try {
      const resp = await fetch("/tracks/meta", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: trackName,
          favorite: !!makeFavorite,
        }),
      });
      if (!resp.ok) {
        console.warn(
          "[Ace Forge] /tracks/meta HTTP " + resp.status
        );
        return;
      }
      await resp.json();
      await refreshTracksAfterGeneration({ autoplay: false });
    } catch (err) {
      console.error("Failed to toggle favorite:", err);
    }
  }

  async function editCategory(trackName, currentCategory) {
    let hint = "";
    if (
      Array.isArray(window.candyKnownCategories) &&
      window.candyKnownCategories.length
    ) {
      hint =
        "\n\nExisting categories:\n - " +
        window.candyKnownCategories.join("\n - ") +
        "\n\n(Leave blank to remove the category.)";
    } else {
      hint = "\n\n(Leave blank to remove the category.)";
    }

    const value = window.prompt(
      'Category for "' + trackName + '":' + hint,
      currentCategory || ""
    );
    if (value === null) {
      // User hit Cancel
      return;
    }

    const trimmed = value.trim();

    try {
      const resp = await fetch("/tracks/meta", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: trackName,
          category: trimmed,
        }),
      });
      if (!resp.ok) {
        console.warn(
          "[Ace Forge] /tracks/meta HTTP " + resp.status
        );
        return;
      }
      await resp.json();
      await refreshTracksAfterGeneration({ autoplay: false });
    } catch (err) {
      console.error("Failed to update category:", err);
    }
  }

  async function renameTrack(trackName) {
    const currentBase = trackName.replace(/\.wav$/i, "");
    const value = window.prompt("Rename track:", currentBase);
    if (value === null) {
      return;
    }

    const trimmed = value.trim();
    if (!trimmed) {
      return;
    }

    // Disallow path separators
    if (/[\/\\]/.test(trimmed)) {
      window.alert("Track name cannot contain path separators.");
      return;
    }

    // Always store tracks as .wav on disk
    const newBase = trimmed.replace(/\.wav$/i, "");
    const newName = newBase + ".wav";

    try {
      const resp = await fetch("/tracks/rename", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ old_name: trackName, new_name: newName }),
      });
      const data = await resp.json();
      if (!resp.ok || !data || data.error) {
        const msg =
          (data && data.error) ||
          "Rename failed with HTTP " + resp.status;
        window.alert(msg);
        return;
      }
      await refreshTracksAfterGeneration({ autoplay: false });
    } catch (err) {
      console.error("Failed to rename track:", err);
      window.alert("Failed to rename track. See console for details.");
    }
  }

  async function deleteTrack(trackName) {
    if (
      !window.confirm(
        'Delete track "' +
          trackName +
          '" from disk? This cannot be undone.'
      )
    ) {
      return;
    }
    try {
      const resp = await fetch("/tracks/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: trackName }),
      });
      if (!resp.ok) {
        console.warn(
          "[Ace Forge] /tracks/delete HTTP " + resp.status
        );
        return;
      }
      await resp.json();
      await refreshTracksAfterGeneration({ autoplay: false });
    } catch (err) {
      console.error("Failed to delete track:", err);
    }
  }

  // ---------------------------------------------------------------------------
  // Copy settings / recipe from track
  // ---------------------------------------------------------------------------
  async function copySettingsFromTrack(trackName) {
    try {
      const resp = await fetch(
        "/tracks/meta?name=" + encodeURIComponent(trackName),
        { cache: "no-store" }
      );
      if (!resp.ok) {
        console.warn(
          "[Ace Forge] /tracks/meta GET HTTP " +
            resp.status
        );
        return;
      }
      const data = await resp.json();
      if (!data || !data.meta) {
        console.warn(
          "[Ace Forge] No meta for track",
          trackName
        );
        return;
      }

      const meta = data.meta || {};

      if (
        window.CDMF &&
        typeof window.CDMF.applySettingsToForm === "function"
      ) {
        window.CDMF.applySettingsToForm(meta);
      } else {
        console.warn(
          "[Ace Forge] CDMF.applySettingsToForm not available."
        );
      }
    } catch (err) {
      console.error("Failed to copy settings from track:", err);
    }
  }

  async function revealInFinder(trackName) {
    try {
      const resp = await fetch("/tracks/reveal-in-finder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: trackName }),
      });
      const data = await resp.json();
      if (!resp.ok || !data || !data.ok) {
        const msg = (data && data.error) || "Reveal in Finder failed";
        if (window.CDMF && CDMF.showToast) {
          CDMF.showToast(msg, "error");
        } else {
          window.alert(msg);
        }
      }
    } catch (err) {
      console.error("Failed to reveal in Finder:", err);
      if (window.CDMF && CDMF.showToast) {
        CDMF.showToast("Reveal in Finder failed", "error");
      } else {
        window.alert("Reveal in Finder failed");
      }
    }
  }

  async function copyRecipeFromTrack(trackName) {
    try {
      const resp = await fetch(
        "/tracks/meta?name=" + encodeURIComponent(trackName),
        { cache: "no-store" }
      );
      if (!resp.ok) {
        console.warn(
          "[Ace Forge] /tracks/meta GET HTTP " +
            resp.status
        );
        return;
      }
      const data = await resp.json();
      if (!data || !data.meta) {
        console.warn(
          "[Ace Forge] No meta for track",
          trackName
        );
        return;
      }

      const meta = data.meta || {};
      const recipe = {
        track: trackName,
        prompt: meta.prompt || "",
        lyrics: meta.lyrics || "",
        instrumental: !!meta.instrumental,
        seed: meta.seed,
        seed_vibe: meta.seed_vibe,
        bpm: meta.bpm,
        target_seconds: meta.target_seconds,
        fade_in: meta.fade_in,
        fade_out: meta.fade_out,
        vocal_gain_db: meta.vocal_gain_db,
        instrumental_gain_db: meta.instrumental_gain_db,
        steps: meta.steps,
        guidance_scale: meta.guidance_scale,
        basename: meta.basename,
        preset_id: meta.preset_id,
        preset_category: meta.preset_category || meta.category || "",
        out_dir: meta.out_dir,
        seconds: meta.seconds,
        created: meta.created,
        // Advanced knobs
        scheduler_type: meta.scheduler_type,
        cfg_type: meta.cfg_type,
        omega_scale: meta.omega_scale,
        guidance_interval: meta.guidance_interval,
        guidance_interval_decay: meta.guidance_interval_decay,
        min_guidance_scale: meta.min_guidance_scale,
        use_erg_tag: meta.use_erg_tag,
        use_erg_lyric: meta.use_erg_lyric,
        use_erg_diffusion: meta.use_erg_diffusion,
        oss_steps: meta.oss_steps,
        task: meta.task,
        repaint_start: meta.repaint_start,
        repaint_end: meta.repaint_end,
        retake_variance: meta.retake_variance,
        audio2audio_enable: meta.audio2audio_enable,
        ref_audio_strength: meta.ref_audio_strength,
        src_audio_path: meta.src_audio_path,
        lora_name_or_path: meta.lora_name_or_path,
        lora_weight: meta.lora_weight,
      };

      const jsonText = JSON.stringify(recipe, null, 2);

      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(jsonText);
        console.log(
          "[Ace Forge] Copied recipe JSON to clipboard for",
          trackName
        );
      } else {
        window.prompt("Recipe JSON (copy manually):", jsonText);
      }
    } catch (err) {
      console.error("Failed to copy recipe JSON from track:", err);
    }
  }

  // ---------------------------------------------------------------------------
  // Category chips
  // ---------------------------------------------------------------------------
  function buildCategoryFilters(categoriesSet) {
    const container = document.getElementById("categoryFilters");
    if (!container) return;

    const categoryFilterSet = ensureCategoryFilterSet();

    while (container.firstChild) {
      container.removeChild(container.firstChild);
    }

    // "All" chip
    const allChip = document.createElement("button");
    allChip.type = "button";
    allChip.className =
      "category-chip" +
      (categoryFilterSet.size === 0 ? " active" : "");
    allChip.textContent = "All";
    allChip.addEventListener("click", function () {
      categoryFilterSet.clear();
      refreshTracksAfterGeneration({ autoplay: false });
    });
    container.appendChild(allChip);

    const cats = Array.from(categoriesSet).filter(Boolean).sort();

    // Expose known categories globally so editCategory() can show them
    window.candyKnownCategories = cats.slice();

    cats.forEach(function (cat) {
      const chip = document.createElement("button");
      chip.type = "button";
      const isActive = categoryFilterSet.has(cat);
      chip.className = "category-chip" + (isActive ? " active" : "");
      chip.textContent = cat;
      chip.addEventListener("click", function () {
        if (categoryFilterSet.has(cat)) {
          categoryFilterSet.delete(cat);
        } else {
          categoryFilterSet.add(cat);
        }
        refreshTracksAfterGeneration({ autoplay: false });
      });
      container.appendChild(chip);
    });
  }

  // ---------------------------------------------------------------------------
  // Header sorting
  // ---------------------------------------------------------------------------
  function initTrackHeaderSorting() {
    const header = document.getElementById("trackListHeader");
    if (!header) return;

    header.addEventListener("click", function (ev) {
      const state = getState();
      const btn = ev.target.closest("[data-sort-key]");
      if (!btn) return;
      const key = btn.getAttribute("data-sort-key");
      if (!key) return;

      if (state.candyTrackSortKey === key) {
        // Toggle direction on repeated clicks
        state.candyTrackSortDir =
          state.candyTrackSortDir === "asc" ? "desc" : "asc";
      } else {
        state.candyTrackSortKey = key;
        // Reasonable defaults: name/category ascending, times descending
        if (key === "name" || key === "category") {
          state.candyTrackSortDir = "asc";
        } else {
          state.candyTrackSortDir = "desc";
        }
      }

      refreshTracksAfterGeneration({ autoplay: false });
    });

    // Delegated click for copy-settings (reuse prompt) on template-rendered rows
    // and any row where the direct handler might not be attached
    const panel = document.getElementById("trackListPanel");
    if (panel) {
      panel.addEventListener("click", function (ev) {
        const btn = ev.target?.closest?.("[data-role=\"copy-settings\"]");
        if (!btn) return;
        const row = btn.closest(".track-row");
        if (!row) return;
        const name = row.dataset.trackName || row.getAttribute("data-track-name");
        if (!name) return;
        ev.stopPropagation();
        copySettingsFromTrack(name);
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Track panel builder
  // ---------------------------------------------------------------------------
  function buildTrackPanel(data) {
    const panel = document.getElementById("trackListPanel");
    if (!panel) return;

    while (panel.firstChild) {
      panel.removeChild(panel.firstChild);
    }

    const rawTracks = data && Array.isArray(data.tracks) ? data.tracks : [];
    if (!rawTracks.length) {
      const empty = document.createElement("div");
      empty.className = "small";
      empty.textContent = "(No tracks yet)";
      panel.appendChild(empty);

      // Also clear filters if nothing exists
      buildCategoryFilters(new Set());
      return;
    }

    const state = getState();
    const currentName = data.current || null;

    // Collect unique categories from tracks
    const categorySet = new Set();
    rawTracks.forEach(function (t) {
      if (t && typeof t === "object" && t.category) {
        categorySet.add(t.category);
      }
    });
    buildCategoryFilters(categorySet);

    const categoryFilterSet = ensureCategoryFilterSet();

    // Apply category filters (if any)
    let tracks = rawTracks.filter(function (entry) {
      if (!(entry && typeof entry === "object")) return false;
      const name = entry.name || "";
      if (!name) return false;

      if (categoryFilterSet.size === 0) {
        return true;
      }
      const cat = entry.category || "";
      return cat && categoryFilterSet.has(cat);
    });

    if (!tracks.length) {
      const empty = document.createElement("div");
      empty.className = "small";
      empty.textContent = "(No tracks match the current filter.)";
      panel.appendChild(empty);
      return;
    }

    // Sorting -------------------------------------------------------------
    function compareTracks(a, b) {
      const sortKey = state.candyTrackSortKey;
      const sortDir = state.candyTrackSortDir === "desc" ? -1 : 1;

      // Default sort: favorites first, then name
      if (!sortKey) {
        if (!!a.favorite !== !!b.favorite) {
          return a.favorite ? -1 : 1;
        }
        const an = (a.name || "").toLowerCase();
        const bn = (b.name || "").toLowerCase();
        if (an < bn) return -1;
        if (an > bn) return 1;
        return 0;
      }

      function cmpVals(av, bv) {
        if (av < bv) return -1 * sortDir;
        if (av > bv) return 1 * sortDir;
        return 0;
      }

      if (sortKey === "name" || sortKey === "category") {
        const av = (a[sortKey] || "").toLowerCase();
        const bv = (b[sortKey] || "").toLowerCase();
        const primary = cmpVals(av, bv);
        if (primary !== 0) return primary;
        // Tie-break on favorites then name
        if (!!a.favorite !== !!b.favorite) {
          return a.favorite ? -1 : 1;
        }
        const an = (a.name || "").toLowerCase();
        const bn = (b.name || "").toLowerCase();
        return cmpVals(an, bn);
      }

      if (
        sortKey === "seconds" ||
        sortKey === "created" ||
        sortKey === "bpm"
      ) {
        const av = Number(a[sortKey] || 0);
        const bv = Number(b[sortKey] || 0);
        const primary = cmpVals(av, bv);
        if (primary !== 0) return primary;
        const an = (a.name || "").toLowerCase();
        const bn = (b.name || "").toLowerCase();
        return cmpVals(an, bn);
      }

      // Fallback: behave like default
      if (!!a.favorite !== !!b.favorite) {
        return a.favorite ? -1 : 1;
      }
      const an = (a.name || "").toLowerCase();
      const bn = (b.name || "").toLowerCase();
      if (an < bn) return -1;
      if (an > bn) return 1;
      return 0;
    }

    tracks = tracks.slice().sort(compareTracks);

    // Update header sort state (visual)
    const header = document.getElementById("trackListHeader");
    if (header) {
      header.querySelectorAll("[data-sort-key]").forEach(function (btn) {
        const key = btn.getAttribute("data-sort-key");
        if (key && key === state.candyTrackSortKey) {
          btn.classList.add("sort-active");
        } else {
          btn.classList.remove("sort-active");
        }
      });
    }

    // Render rows ---------------------------------------------------------
    tracks.forEach(function (entry) {
      const name = entry.name || "";
      if (!name) return;

      const favorite = !!entry.favorite;
      const category = entry.category || "";
      const seconds =
        typeof entry.seconds === "number" ? entry.seconds : null;
      const created =
        typeof entry.created === "number" ? entry.created : null;

      const row = document.createElement("div");
      row.className = "track-row";
      row.dataset.trackName = name;
      if (currentName && name === currentName) {
        row.classList.add("active");
      }

      // ★ cell ------------------------------------------------------------
      const starCell = document.createElement("div");
      starCell.className = "track-cell track-star-cell";

      const favBtn = document.createElement("button");
      favBtn.type = "button";
      favBtn.className =
        "track-fav-btn" + (favorite ? " favorited" : "");
      favBtn.setAttribute("data-role", "favorite");
      favBtn.textContent = "★";

      starCell.appendChild(favBtn);

      // Name cell -------------------------------------------------------
      const nameCell = document.createElement("div");
      nameCell.className = "track-cell track-cell-name";

      const renameBtn = document.createElement("button");
      renameBtn.type = "button";
      renameBtn.className = "track-rename-btn";
      renameBtn.setAttribute("data-role", "rename");
      renameBtn.title = "Rename this track";
      renameBtn.textContent = "✏";

      const title = document.createElement("div");
      title.className = "track-name";
      const displayName = name.replace(/\.(wav|mp3)$/i, "");
      title.textContent = displayName;

      nameCell.appendChild(renameBtn);
      nameCell.appendChild(title);

      // Length cell -------------------------------------------------------
      const lengthCell = document.createElement("div");
      lengthCell.className = "track-cell track-cell-length";

      const lengthLabel = document.createElement("span");
      lengthLabel.className = "track-length";
      lengthLabel.setAttribute("data-role", "length-label");
      if (seconds && seconds > 0) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.round(seconds % 60);
        lengthLabel.textContent =
          mins + ":" + (secs < 10 ? "0" + secs : String(secs));
      } else {
        lengthLabel.textContent = "";
      }
      lengthCell.appendChild(lengthLabel);

      // Category cell -----------------------------------------------------
      const categoryCell = document.createElement("div");
      categoryCell.className = "track-cell track-cell-category";

      const catLabel = document.createElement("span");
      catLabel.className = "track-category";
      catLabel.setAttribute("data-role", "category-label");

      const hasCategory = !!category;
      if (hasCategory) {
        catLabel.textContent = category;
      } else {
        catLabel.textContent = "Set category…";
        catLabel.classList.add("track-category-empty");
      }

      categoryCell.appendChild(catLabel);

      // Created cell ------------------------------------------------------
      const createdCell = document.createElement("div");
      createdCell.className = "track-cell track-cell-created";

      const createdLabel = document.createElement("span");
      createdLabel.className = "track-created";
      createdLabel.setAttribute("data-role", "created-label");

      if (created && created > 0) {
        const d = new Date(created * 1000);
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, "0");
        const day = String(d.getDate()).padStart(2, "0");
        const hours = String(d.getHours()).padStart(2, "0");
        const minutes = String(d.getMinutes()).padStart(2, "0");
        createdLabel.textContent =
          year + "-" + month + "-" + day + " " + hours + ":" + minutes;
      } else {
        createdLabel.textContent = "";
      }
      createdCell.appendChild(createdLabel);

      // Actions cell ------------------------------------------------------
      const actions = document.createElement("div");
      actions.className = "track-cell track-actions";

      const copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "track-delete-btn";
      copyBtn.setAttribute("data-role", "copy-settings");
      copyBtn.title = "Copy generation settings back into the form";
      copyBtn.textContent = "⧉";

      const downloadLink = document.createElement("a");
      downloadLink.href = "/music/" + encodeURIComponent(name);
      downloadLink.setAttribute("download", name);
      downloadLink.className = "track-delete-btn";
      downloadLink.setAttribute("data-role", "download");
      downloadLink.title = "Download";
      downloadLink.textContent = "↓";

      const revealBtn = document.createElement("button");
      revealBtn.type = "button";
      revealBtn.className = "track-delete-btn";
      revealBtn.setAttribute("data-role", "reveal");
      revealBtn.title = "Show in Finder";
      revealBtn.textContent = "📂";

      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "track-delete-btn";
      deleteBtn.setAttribute("data-role", "delete");
      deleteBtn.textContent = "🗑";

      actions.appendChild(copyBtn);
      actions.appendChild(downloadLink);
      actions.appendChild(revealBtn);
      actions.appendChild(deleteBtn);

      // Assemble row ------------------------------------------------------
      row.appendChild(starCell);
      row.appendChild(nameCell);
      row.appendChild(lengthCell);
      row.appendChild(categoryCell);
      row.appendChild(createdCell);
      row.appendChild(actions);

      // Row click → select & play (ignore clicks on action buttons/links)
      row.addEventListener("click", function (ev) {
        const roleEl = ev.target && ev.target.closest && ev.target.closest("[data-role]");
        const role = roleEl ? roleEl.getAttribute("data-role") : null;
        if (
          role === "favorite" ||
          role === "delete" ||
          role === "category-label" ||
          role === "copy-settings" ||
          role === "download" ||
          role === "reveal" ||
          role === "rename"
        ) {
          return;
        }
        selectAndPlayTrack(name);
      });

      // Right-click → quick category edit
      row.addEventListener("contextmenu", function (ev) {
        ev.preventDefault();
        editCategory(name, category);
      });

      favBtn.addEventListener("click", function (ev) {
        ev.stopPropagation();
        toggleFavorite(name, !favorite);
      });

      copyBtn.addEventListener("click", function (ev) {
        ev.stopPropagation();
        copySettingsFromTrack(name);
      });

      revealBtn.addEventListener("click", function (ev) {
        ev.stopPropagation();
        revealInFinder(name);
      });

      renameBtn.addEventListener("click", function (ev) {
        ev.stopPropagation();
        renameTrack(name);
      });

      deleteBtn.addEventListener("click", function (ev) {
        ev.stopPropagation();
        deleteTrack(name);
      });

      catLabel.addEventListener("click", function (ev) {
        ev.stopPropagation();
        editCategory(name, category);
      });

      panel.appendChild(row);
    });
  }

  // ---------------------------------------------------------------------------
  // Refresh tracks from /tracks.json
  // ---------------------------------------------------------------------------
  async function refreshTracksAfterGeneration(options) {
    options = options || {};
    const autoplay = !!options.autoplay;

    try {
      const resp = await fetch("/tracks.json?_=" + Date.now(), {
        cache: "no-store",
      });
      if (!resp.ok) {
        console.warn(
          "[Ace Forge] /tracks.json HTTP " +
            resp.status
        );
        return;
      }

      const data = await resp.json();
      if (!data || !Array.isArray(data.tracks)) {
        console.warn(
          "[Ace Forge] /tracks.json payload missing tracks array:",
          data
        );
        return;
      }

      const list = document.getElementById("trackList");
      const audio = document.getElementById("audioPlayer");
      if (!list) return;

      // Rebuild the dropdown from scratch
      while (list.firstChild) {
        list.removeChild(list.firstChild);
      }

      if (data.tracks.length === 0) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "(No tracks yet)";
        list.appendChild(opt);
        buildTrackPanel(data);
      } else {
        let currentName = data.current || null;

        data.tracks.forEach(function (entry) {
          // Support either raw strings or {name, url} objects.
          let trackName = entry;
          if (entry && typeof entry === "object") {
            trackName = entry.name || "";
          }

          if (!trackName) return;

          const url = "/music/" + encodeURIComponent(trackName);

          const opt = document.createElement("option");
          opt.value = url;
          opt.textContent = (trackName || "").replace(/\.(wav|mp3)$/i, "");

          if (currentName && trackName === currentName) {
            opt.selected = true;
          }

          list.appendChild(opt);
        });

        // Compute the URL for the current track (if any).
        let currentUrl = "";
        if (currentName) {
          currentUrl = "/music/" + encodeURIComponent(currentName);
        }

        if (currentUrl) {
          list.value = currentUrl;
        }

        // Build / refresh the richer track list panel
        buildTrackPanel(data);

        // Optionally auto-play the current track (used only after generation).
        if (audio && currentUrl && autoplay) {
          audio.pause();
          audio.src = currentUrl;
          if (!window.candyIsGenerating) {
            audio.play().catch(function () {});
          }
        }
      }
    } catch (err) {
      console.error("Failed to refresh tracks after generation:", err);
    }
  }

  // ---------------------------------------------------------------------------
  // Exports
  // ---------------------------------------------------------------------------
  CDMF.refreshTracksAfterGeneration = refreshTracksAfterGeneration;
  CDMF.initTrackHeaderSorting = initTrackHeaderSorting;
  CDMF.selectAndPlayTrack = selectAndPlayTrack;
})();
