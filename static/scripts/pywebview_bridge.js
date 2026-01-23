// pywebview_bridge.js - Bridge between JavaScript and pywebview API
// This replaces all fetch() calls with pywebview API calls

(function() {
  'use strict';

  // Check if we're running in pywebview
  const isPywebview = typeof window.pywebview !== 'undefined';
  
  if (!isPywebview) {
    console.warn('[PywebviewBridge] pywebview API not available, falling back to fetch');
  }

  // Get the pywebview API object
  function getAPI() {
    if (isPywebview && window.pywebview && window.pywebview.api) {
      return window.pywebview.api;
    }
    return null;
  }

  // ---------------------------------------------------------------------------
  // fetch() shim for serverless mode
  //
  // The existing AceForge UI modules (static/scripts/cdmf_*.js) were originally
  // written for a Flask server and use fetch('/some/endpoint').
  //
  // In serverless pywebview mode we map those fetch calls to window.pywebview.api
  // methods so we can reuse the UI without a local HTTP server.
  // ---------------------------------------------------------------------------

  function makeJsonResponse(obj, status = 200) {
    const body = JSON.stringify(obj ?? {});
    return Promise.resolve(
      new Response(body, {
        status,
        headers: { 'Content-Type': 'application/json' }
      })
    );
  }

  function parseUrl(input) {
    try {
      return new URL(input, window.location.href);
    } catch (_) {
      return null;
    }
  }

  async function readRequestBody(options) {
    const body = options && options.body;
    if (!body) return null;

    // FormData -> object
    if (typeof FormData !== 'undefined' && body instanceof FormData) {
      const obj = {};
      for (const [k, v] of body.entries()) obj[k] = v;
      return obj;
    }

    // JSON string
    if (typeof body === 'string') {
      try { return JSON.parse(body); } catch (_) { return body; }
    }

    // If it's already an object, pass through
    if (typeof body === 'object') return body;
    return null;
  }

  if (isPywebview) {
    const originalFetch = window.fetch ? window.fetch.bind(window) : null;
    window.fetch = async function(input, options = {}) {
      const api = getAPI();
      const u = parseUrl(input);
      const path = u ? u.pathname : (typeof input === 'string' ? input : '');
      const method = (options.method || 'GET').toUpperCase();
      const query = u ? u.searchParams : null;

      // If API isn't ready yet, fall back.
      if (!api) {
        if (originalFetch) return originalFetch(input, options);
        throw new Error('pywebview API not ready');
      }

      // Normalize cache-busters: /foo?_=
      const cleanPath = path.split('?')[0];

      try {
        // Health
        if (cleanPath === '/healthz') {
          return makeJsonResponse({ ok: true });
        }

        // Progress
        if (cleanPath === '/progress') {
          const data = await api.getProgress();
          return makeJsonResponse(data);
        }

        // Models
        if (cleanPath === '/models/status') {
          const data = await api.getModelStatus();
          return makeJsonResponse(data);
        }
        if (cleanPath === '/models/ensure' && method === 'POST') {
          const data = await api.downloadModels();
          return makeJsonResponse(data);
        }
        if (cleanPath === '/models/folder') {
          if (method === 'GET') {
            const data = await api.getModelsFolder();
            return makeJsonResponse(data);
          }
          if (method === 'POST') {
            const bodyObj = await readRequestBody(options);
            const folder = bodyObj && (bodyObj.folder || bodyObj.path || bodyObj.modelsFolder || bodyObj.value);
            const data = await api.setModelsFolder(folder || '');
            return makeJsonResponse(data);
          }
        }

        // Tracks
        if (cleanPath === '/tracks.json') {
          const data = await api.getTracks();
          return makeJsonResponse(data);
        }
        if (cleanPath === '/tracks/meta') {
          if (method === 'GET') {
            const name = query ? query.get('name') : null;
            const data = await api.getTrackMeta(name || '');
            return makeJsonResponse(data);
          }
          if (method === 'POST') {
            const bodyObj = await readRequestBody(options);
            const name = bodyObj && bodyObj.name;
            const updates = Object.assign({}, bodyObj || {});
            delete updates.name;
            const data = await api.updateTrackMeta(name || '', updates);
            return makeJsonResponse(data);
          }
        }
        if (cleanPath === '/tracks/rename' && method === 'POST') {
          const bodyObj = await readRequestBody(options);
          const data = await api.renameTrack(bodyObj.old_name || bodyObj.oldName || '', bodyObj.new_name || bodyObj.newName || '');
          return makeJsonResponse(data);
        }
        if (cleanPath === '/tracks/delete' && method === 'POST') {
          const bodyObj = await readRequestBody(options);
          const data = await api.deleteTrack(bodyObj.name || '');
          return makeJsonResponse(data);
        }

        // Presets
        if (cleanPath === '/user_presets') {
          if (method === 'GET') {
            const data = await api.listPresets();
            return makeJsonResponse(data);
          }
          if (method === 'POST') {
            const bodyObj = await readRequestBody(options);
            const data = await api.savePreset(bodyObj || {});
            return makeJsonResponse(data);
          }
        }

        // Lyrics / prompt helpers
        if (cleanPath === '/lyrics/status') {
          const data = await api.getLyricsModelStatus();
          return makeJsonResponse(data);
        }
        if (cleanPath === '/lyrics/ensure' && method === 'POST') {
          const data = await api.ensureLyricsModel();
          return makeJsonResponse(data);
        }
        if ((cleanPath === '/lyrics/generate' || cleanPath === '/prompt_lyrics/generate') && method === 'POST') {
          const bodyObj = await readRequestBody(options);
          const data = await api.generatePromptLyrics(bodyObj || {});
          return makeJsonResponse(data);
        }

        // MuFun
        if (cleanPath === '/mufun/status') {
          const data = await api.getMuFunStatus();
          return makeJsonResponse(data);
        }
        if (cleanPath === '/mufun/ensure' && method === 'POST') {
          const data = await api.ensureMuFun();
          return makeJsonResponse(data);
        }
        if (cleanPath === '/mufun/analyze_dataset' && method === 'POST') {
          const bodyObj = await readRequestBody(options);
          const data = await api.analyzeDataset(bodyObj || {});
          return makeJsonResponse(data);
        }

        // Training (best-effort compatibility; not all endpoints exist serverless yet)
        if (cleanPath === '/train_lora/status') {
          const data = await api.getLoraTrainingStatus();
          return makeJsonResponse(data);
        }

        // Generation
        if (cleanPath === '/generate' && method === 'POST') {
          const bodyObj = await readRequestBody(options);
          const data = await api.generate(bodyObj || {});
          return makeJsonResponse(data);
        }

        // Shutdown
        if (cleanPath === '/shutdown' && method === 'POST') {
          await api.exitApp();
          return makeJsonResponse({ ok: true });
        }

        // Fall back to real fetch (for file:// assets etc)
        if (originalFetch) return originalFetch(input, options);
        throw new Error('No fetch fallback available');
      } catch (err) {
        console.error('[PywebviewBridge] fetch shim error for', cleanPath, err);
        return makeJsonResponse({ ok: false, error: String(err) }, 500);
      }
    };
  }

  // Log message handler (called from Python)
  window.handleLogMessage = function(message) {
    const consoleOutput = document.getElementById('consoleOutput');
    if (consoleOutput && window.appendLogLine) {
      window.appendLogLine(message);
    }
  };

  // Progress update handler (called from Python)
  window.handleProgressUpdate = function(progress) {
    if (window.updateProgressBar) {
      window.updateProgressBar(progress);
    }
  };

  // API wrapper that handles both pywebview and fetch fallback
  window.AceForgeAPI = {
    // Window controls
    minimize: async function() {
      const api = getAPI();
      if (api && api.minimize) {
        try {
          return await api.minimize();
        } catch (error) {
          console.error('[API] Minimize error:', error);
          return { status: 'error', message: String(error) };
        }
      }
      return { status: 'error', message: 'Window control not available' };
    },
    
    restore: async function() {
      const api = getAPI();
      if (api && api.restore) {
        try {
          return await api.restore();
        } catch (error) {
          console.error('[API] Restore error:', error);
          return { status: 'error', message: String(error) };
        }
      }
      return { status: 'error', message: 'Window control not available' };
    },
    
    maximize: async function() {
      const api = getAPI();
      if (api && api.maximize) {
        try {
          return await api.maximize();
        } catch (error) {
          console.error('[API] Maximize error:', error);
          return { status: 'error', message: String(error) };
        }
      }
      return { status: 'error', message: 'Window control not available' };
    },
    
    // Generation
    generate: async function(params) {
      const api = getAPI();
      if (api && api.generate) {
        try {
          return await api.generate(params);
        } catch (error) {
          console.error('[API] Generate error:', error);
          return { status: 'error', message: String(error) };
        }
      }
      // Fallback to fetch
      const formData = new FormData();
      for (const [key, value] of Object.entries(params)) {
        if (value !== null && value !== undefined) {
          formData.append(key, value);
        }
      }
      const response = await fetch('/generate', { method: 'POST', body: formData });
      return await response.json();
    },

    // Tracks
    listTracks: async function() {
      const api = getAPI();
      if (api && api.listTracks) {
        try {
          return await api.listTracks();
        } catch (error) {
          console.error('[API] List tracks error:', error);
          return { tracks: [], current: null };
        }
      }
      const response = await fetch('/tracks.json');
      return await response.json();
    },

    getTrackMeta: async function(name) {
      const api = getAPI();
      if (api && api.getTrackMeta) {
        try {
          return await api.getTrackMeta(name);
        } catch (error) {
          return { error: String(error) };
        }
      }
      const response = await fetch(`/tracks/meta?name=${encodeURIComponent(name)}`);
      return await response.json();
    },

    updateTrackMeta: async function(name, updates) {
      const api = getAPI();
      if (api && api.updateTrackMeta) {
        try {
          return await api.updateTrackMeta(name, updates);
        } catch (error) {
          return { error: String(error) };
        }
      }
      const response = await fetch('/tracks/meta', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, ...updates })
      });
      return await response.json();
    },

    renameTrack: async function(oldName, newName) {
      const api = getAPI();
      if (api && api.renameTrack) {
        try {
          return await api.renameTrack(oldName, newName);
        } catch (error) {
          return { error: String(error) };
        }
      }
      const response = await fetch('/tracks/rename', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ old_name: oldName, new_name: newName })
      });
      return await response.json();
    },

    deleteTrack: async function(name) {
      const api = getAPI();
      if (api && api.deleteTrack) {
        try {
          return await api.deleteTrack(name);
        } catch (error) {
          return { error: String(error) };
        }
      }
      const response = await fetch('/tracks/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      });
      return await response.json();
    },

    // Progress
    getProgress: async function() {
      const api = getAPI();
      if (api && api.getProgress) {
        try {
          return await api.getProgress();
        } catch (error) {
          return { current: 0, total: 1, done: false, error: false, stage: '' };
        }
      }
      const response = await fetch('/progress');
      return await response.json();
    },

    // Models
    getModelStatus: async function() {
      const api = getAPI();
      if (api && api.getModelStatus) {
        try {
          return await api.getModelStatus();
        } catch (error) {
          return { state: 'unknown', message: String(error) };
        }
      }
      const response = await fetch('/models/status');
      const data = await response.json();
      return { state: data.state, message: data.message };
    },

    downloadModels: async function() {
      const api = getAPI();
      if (api && api.downloadModels) {
        try {
          return await api.downloadModels();
        } catch (error) {
          return { status: 'error', message: String(error) };
        }
      }
      const response = await fetch('/models/ensure', { method: 'POST' });
      return await response.json();
    },

    // Presets
    listPresets: async function() {
      const api = getAPI();
      if (api && api.listPresets) {
        try {
          return await api.listPresets();
        } catch (error) {
          return { ok: false, presets: [] };
        }
      }
      const response = await fetch('/user_presets');
      return await response.json();
    },

    savePreset: async function(presetData) {
      const api = getAPI();
      if (api && api.savePreset) {
        try {
          return await api.savePreset(presetData);
        } catch (error) {
          return { error: String(error) };
        }
      }
      const response = await fetch('/user_presets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(presetData)
      });
      return await response.json();
    },

    // Prompt/Lyrics
    generatePromptLyrics: async function(params) {
      const api = getAPI();
      if (api && api.generatePromptLyrics) {
        try {
          return await api.generatePromptLyrics(params);
        } catch (error) {
          return { error: String(error) };
        }
      }
      const response = await fetch('/prompt_lyrics/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params)
      });
      return await response.json();
    },

    // Utility
    getDefaults: async function() {
      const api = getAPI();
      if (api && api.getDefaults) {
        try {
          return await api.getDefaults();
        } catch (error) {
          return {};
        }
      }
      return {
        target_seconds: 90,
        fade_in: 0.5,
        fade_out: 0.5,
        steps: 55,
        guidance_scale: 6.0,
      };
    },

    shutdown: async function() {
      const api = getAPI();
      if (api && api.shutdown) {
        try {
          await api.shutdown();
          // Close window if in pywebview
          if (isPywebview && window.pywebview) {
            window.pywebview.window.close();
          }
          return { status: 'ok' };
        } catch (error) {
          return { error: String(error) };
        }
      }
      const response = await fetch('/shutdown', { method: 'POST' });
      return await response.json();
    }
  };

  // Start polling for progress updates if in pywebview
  if (isPywebview) {
    let progressInterval = null;
    
    function startProgressPolling() {
      if (progressInterval) return;
      
      progressInterval = setInterval(async () => {
        try {
          const progress = await window.AceForgeAPI.getProgress();
          if (window.handleProgressUpdate) {
            window.handleProgressUpdate(progress);
          }
        } catch (error) {
          // Ignore errors
        }
      }, 500); // Poll every 500ms
    }
    
    // Start polling when page loads
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', startProgressPolling);
    } else {
      startProgressPolling();
    }
  }

  console.log('[PywebviewBridge] Initialized', isPywebview ? '(pywebview mode)' : '(fallback mode)');
})();
