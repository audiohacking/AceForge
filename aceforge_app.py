#!/usr/bin/env python3
"""
AceForge - Serverless pywebview Application
Native macOS app with pywebview as the core, no Flask/terminal needed.
"""

from __future__ import annotations

import sys
import os
import threading
import queue
import logging
import time
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
import urllib.parse

# Set environment variables early
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
if 'PYTORCH_MPS_HIGH_WATERMARK_RATIO' not in os.environ:
    os.environ['PYTORCH_MPS_HIGH_WATERMARK_RATIO'] = '0.0'

# Critical: Import lzma EARLY (before any ACE-Step imports)
try:
    import lzma
    import _lzma
    test_data = b"test"
    compressed = lzma.compress(test_data)
    decompressed = lzma.decompress(compressed)
    if decompressed == test_data and getattr(sys, 'frozen', False):
        print("[AceForge] lzma module initialized successfully.", flush=True)
except Exception as e:
    print(f"[AceForge] WARNING: lzma initialization: {e}", flush=True)

# Import core modules
import cdmf_state
import cdmf_tracks
import cdmf_paths
from generate_ace import generate_track_ace, register_progress_callback
from ace_model_setup import ace_models_present, ensure_ace_models

# ---------------------------------------------------------------------------
# Log streaming for pywebview
# ---------------------------------------------------------------------------

LOG_QUEUE = queue.Queue(maxsize=1000)

class LogStreamHandler(logging.Handler):
    """Logging handler that queues messages for streaming to UI"""
    def emit(self, record):
        try:
            msg = self.format(record)
            msg_lower = msg.lower()
            
            # Filter unwanted messages
            if 'task queue depth' in msg_lower:
                return
            if 'client disconnected while serving' in msg_lower:
                return
            
            try:
                LOG_QUEUE.put_nowait(msg)
            except queue.Full:
                pass
        except Exception:
            pass

# Set up logging
log_handler = LogStreamHandler()
log_handler.setLevel(logging.INFO)
formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', 
                              datefmt='%Y-%m-%d %H:%M:%S')
log_handler.setFormatter(formatter)

root_logger = logging.getLogger()
root_logger.addHandler(log_handler)
root_logger.setLevel(logging.INFO)

# Redirect stdout/stderr for frozen apps
if getattr(sys, 'frozen', False):
    class StreamToLogger:
        def __init__(self, logger, log_level=logging.INFO):
            self.logger = logger
            self.log_level = log_level
            self.linebuf = ''
            self.last_progress = None

        def _should_filter(self, line):
            line_lower = line.lower()
            if 'task queue depth' in line_lower:
                return True
            if 'client disconnected while serving' in line_lower:
                return True
            return False

        def _extract_progress(self, line):
            import re
            progress_pattern = r'(\d+)%\s*\|\s*[#\s]+\|\s*(\d+)/(\d+)\s+\[([^\]]+)\]'
            match = re.search(progress_pattern, line)
            if match:
                percent = int(match.group(1))
                current = int(match.group(2))
                total = int(match.group(3))
                time_info = match.group(4)
                return f"[Progress] {percent}% ({current}/{total} steps) - {time_info}"
            return None

        def write(self, buf):
            temp_buf = self.linebuf + buf
            lines = temp_buf.splitlines(keepends=True)
            for line in lines[:-1]:
                if line.endswith(('\n', '\r\n', '\r')):
                    line_clean = line.rstrip()
                    if not line_clean:
                        continue
                    if self._should_filter(line_clean):
                        continue
                    progress_msg = self._extract_progress(line_clean)
                    if progress_msg:
                        if progress_msg != self.last_progress:
                            self.logger.log(logging.INFO, progress_msg)
                            self.last_progress = progress_msg
                        continue
                    self.logger.log(self.log_level, line_clean)
            if lines and not lines[-1].endswith(('\n', '\r\n', '\r')):
                self.linebuf = lines[-1]
            else:
                self.linebuf = ''

        def flush(self):
            if self.linebuf:
                line_clean = self.linebuf.rstrip()
                if line_clean and not self._should_filter(line_clean):
                    progress_msg = self._extract_progress(line_clean)
                    if progress_msg:
                        if progress_msg != self.last_progress:
                            self.logger.log(logging.INFO, progress_msg)
                            self.last_progress = progress_msg
                    else:
                        self.logger.log(self.log_level, line_clean)
                self.linebuf = ''

    sys.stdout = StreamToLogger(logging.getLogger('STDOUT'), logging.INFO)
    sys.stderr = StreamToLogger(logging.getLogger('STDERR'), logging.ERROR)

# Wire ACE-Step progress callback
register_progress_callback(cdmf_state.ace_progress_callback)

# Initialize model status
cdmf_state.init_model_status()

# ---------------------------------------------------------------------------
# AceForge API Class (exposed to JavaScript via pywebview)
# ---------------------------------------------------------------------------

class AceForgeAPI:
    """Main API class exposed to JavaScript via pywebview js_api"""
    
    def __init__(self):
        self.window = None  # Will be set by pywebview
        self._log_thread = None
        self._log_running = False
        
    def set_window(self, window):
        """Set the pywebview window reference"""
        self.window = window
        self._start_log_streaming()
    
    def _start_log_streaming(self):
        """Start streaming logs to the UI"""
        if self._log_running:
            return
        
        self._log_running = True
        
        def stream_logs():
            while self._log_running:
                try:
                    msg = LOG_QUEUE.get(timeout=1.0)
                    if self.window:
                        try:
                            # Use pywebview's evaluate_js to send log to UI
                            self.window.evaluate_js(f"""
                                if (window.handleLogMessage) {{
                                    window.handleLogMessage({json.dumps(msg)});
                                }}
                            """)
                        except Exception:
                            pass
                except queue.Empty:
                    continue
                except Exception:
                    break
        
        self._log_thread = threading.Thread(target=stream_logs, daemon=True)
        self._log_thread.start()
    
    def stop_log_streaming(self):
        """Stop log streaming"""
        self._log_running = False
        if self._log_thread:
            self._log_thread.join(timeout=1.0)
    
    # -----------------------------------------------------------------------
    # Generation API
    # -----------------------------------------------------------------------
    
    def generate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a track using ACE-Step.
        
        Args:
            params: Dictionary with generation parameters:
                - prompt: str
                - lyrics: str (optional)
                - instrumental: bool
                - target_seconds: float
                - steps: int
                - guidance_scale: float
                - seed: int (optional)
                - basename: str
                - out_dir: str (optional)
                - ... (all other ACE-Step parameters)
        
        Returns:
            Dict with status and result information
        """
        try:
            print(f"[AceForge] GENERATE request\n  Prompt: {params.get('prompt', '')!r}", flush=True)
            
            # Extract parameters with defaults
            prompt = params.get('prompt', '').strip()
            if not prompt:
                return {"status": "error", "message": "Prompt cannot be empty"}
            
            lyrics = params.get('lyrics', '').strip()
            instrumental = params.get('instrumental', False)
            target_seconds = float(params.get('target_seconds', 90))
            fade_in = float(params.get('fade_in', 0.5))
            fade_out = float(params.get('fade_out', 0.5))
            steps = int(params.get('steps', 55))
            guidance_scale = float(params.get('guidance_scale', 6.0))
            seed = params.get('seed')
            basename = params.get('basename', 'Candy Dreams').strip() or 'Candy Dreams'
            out_dir = params.get('out_dir', str(cdmf_paths.DEFAULT_OUT_DIR))
            
            # Advanced parameters
            scheduler_type = params.get('scheduler_type', 'euler').strip() or 'euler'
            cfg_type = params.get('cfg_type', 'apg').strip() or 'apg'
            omega_scale = float(params.get('omega_scale', 5.0))
            guidance_interval = float(params.get('guidance_interval', 0.75))
            guidance_interval_decay = float(params.get('guidance_interval_decay', 0.0))
            min_guidance_scale = float(params.get('min_guidance_scale', 7.0))
            use_erg_tag = params.get('use_erg_tag', False)
            use_erg_lyric = params.get('use_erg_lyric', False)
            use_erg_diffusion = params.get('use_erg_diffusion', False)
            oss_steps = params.get('oss_steps')
            task = params.get('task', 'text2music').strip() or 'text2music'
            repaint_start = float(params.get('repaint_start', 0.0))
            repaint_end = float(params.get('repaint_end', 0.0))
            retake_variance = float(params.get('retake_variance', 0.5))
            audio2audio_enable = params.get('audio2audio_enable', False)
            ref_audio_strength = float(params.get('ref_audio_strength', 0.7))
            lora_name_or_path = params.get('lora_name_or_path')
            lora_weight = float(params.get('lora_weight', 1.0))
            src_audio_path = params.get('src_audio_path')
            bpm = params.get('bpm')
            vocal_gain_db = float(params.get('vocal_gain_db', 0.0))
            instrumental_gain_db = float(params.get('instrumental_gain_db', 0.0))
            seed_vibe = params.get('seed_vibe', 'any').strip() or 'any'
            
            # Reset progress
            cdmf_state.reset_progress()
            with cdmf_state.PROGRESS_LOCK:
                cdmf_state.GENERATION_PROGRESS["current"] = 0.0
                cdmf_state.GENERATION_PROGRESS["total"] = 1.0
                cdmf_state.GENERATION_PROGRESS["stage"] = "ace_infer"
                cdmf_state.GENERATION_PROGRESS["done"] = False
                cdmf_state.GENERATION_PROGRESS["error"] = False
            
            # Call generate_track_ace (core ACE-Step functionality)
            result = generate_track_ace(
                genre_prompt=prompt,
                lyrics=lyrics,
                instrumental=instrumental,
                negative_prompt="",  # ACE-Step v0.1 doesn't use negative prompt
                target_seconds=target_seconds,
                fade_in_seconds=fade_in,
                fade_out_seconds=fade_out,
                seed=seed,
                out_dir=Path(out_dir),
                basename=basename,
                seed_vibe=seed_vibe,
                bpm=bpm,
                steps=steps,
                guidance_scale=guidance_scale,
                scheduler_type=scheduler_type,
                cfg_type=cfg_type,
                omega_scale=omega_scale,
                guidance_interval=guidance_interval,
                guidance_interval_decay=guidance_interval_decay,
                min_guidance_scale=min_guidance_scale,
                use_erg_tag=use_erg_tag,
                use_erg_lyric=use_erg_lyric,
                use_erg_diffusion=use_erg_diffusion,
                oss_steps=oss_steps,
                task=task,
                repaint_start=repaint_start,
                repaint_end=repaint_end,
                retake_variance=retake_variance,
                audio2audio_enable=audio2audio_enable,
                ref_audio_strength=ref_audio_strength,
                lora_name_or_path=lora_name_or_path,
                lora_weight=lora_weight,
                src_audio_path=src_audio_path,
                vocal_gain_db=vocal_gain_db,
                instrumental_gain_db=instrumental_gain_db,
            )
            
            return {
                "status": "success",
                "result": result,
                "output_path": str(result.get("output_path", "")),
            }
            
        except Exception as e:
            import traceback
            error_msg = str(e)
            error_trace = traceback.format_exc()
            print(f"[AceForge] Error during generation: {error_msg}", flush=True)
            logging.error(f"Generation error: {error_trace}")
            return {
                "status": "error",
                "message": error_msg,
                "traceback": error_trace if getattr(sys, 'frozen', False) else None,
            }
    
    # -----------------------------------------------------------------------
    # Tracks API
    # -----------------------------------------------------------------------
    
    def listTracks(self) -> Dict[str, Any]:
        """List all generated music files with metadata"""
        try:
            from cdmf_tracks import list_music_files, load_track_meta
            from cdmf_paths import DEFAULT_OUT_DIR
            
            tracks = list_music_files()
            meta = load_track_meta()
            music_dir = Path(DEFAULT_OUT_DIR)
            
            # Get last generated track
            with cdmf_state.PROGRESS_LOCK:
                last = cdmf_state.LAST_GENERATED_TRACK
            
            # Find current track (last generated or most recent)
            current = None
            latest_name = None
            latest_mtime = None
            mtimes: Dict[str, float] = {}
            
            if tracks:
                for name in tracks:
                    p = music_dir / name
                    try:
                        mtime = p.stat().st_mtime
                        mtimes[name] = mtime
                        if latest_mtime is None or mtime > latest_mtime:
                            latest_mtime = mtime
                            latest_name = name
                    except OSError:
                        continue
                
                if last and last in tracks:
                    current = last
                else:
                    current = latest_name or tracks[-1]
            
            # Build track items with metadata
            track_items = []
            for name in tracks:
                info = meta.get(name, {})
                track_items.append({
                    "name": name,
                    "favorite": bool(info.get("favorite", False)),
                    "category": info.get("category") or "",
                    "seconds": float(info.get("seconds") or 0.0),
                    "bpm": float(info.get("bpm")) if info.get("bpm") is not None else None,
                    "created": float(info.get("created") or mtimes.get(name) or 0.0),
                })
            
            return {"tracks": track_items, "current": current}
        except Exception as e:
            logging.error(f"Error listing tracks: {e}")
            return {"tracks": [], "current": None}
    
    def getTrackMeta(self, name: str) -> Dict[str, Any]:
        """Get metadata for a specific track"""
        try:
            from cdmf_tracks import load_track_meta
            from cdmf_paths import DEFAULT_OUT_DIR
            
            track_path = Path(DEFAULT_OUT_DIR) / name
            if not track_path.is_file():
                return {"error": "Track not found"}
            
            meta = load_track_meta()
            entry = meta.get(name)
            if not entry:
                return {"error": "No metadata for this track"}
            
            return {"ok": True, "meta": entry}
        except Exception as e:
            logging.error(f"Error getting track meta: {e}")
            return {"error": str(e)}
    
    def updateTrackMeta(self, name: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update metadata for a track (favorite, category, etc.)"""
        try:
            from cdmf_tracks import load_track_meta, save_track_meta
            from cdmf_paths import DEFAULT_OUT_DIR
            
            track_path = Path(DEFAULT_OUT_DIR) / name
            if not track_path.is_file():
                return {"error": "Track not found"}
            
            meta = load_track_meta()
            entry = meta.get(name, {})
            
            if "favorite" in updates:
                entry["favorite"] = bool(updates["favorite"])
            if "category" in updates:
                entry["category"] = str(updates.get("category") or "").strip()
            
            meta[name] = entry
            save_track_meta(meta)
            
            return {"ok": True, "meta": entry}
        except Exception as e:
            logging.error(f"Error updating track meta: {e}")
            return {"error": str(e)}
    
    def renameTrack(self, old_name: str, new_name: str) -> Dict[str, Any]:
        """Rename a track file"""
        try:
            from cdmf_tracks import load_track_meta, save_track_meta
            from cdmf_paths import DEFAULT_OUT_DIR
            
            old_path = Path(DEFAULT_OUT_DIR) / old_name
            new_path = Path(DEFAULT_OUT_DIR) / new_name
            
            if not old_path.is_file():
                return {"error": "Track not found"}
            if new_path.exists():
                return {"error": "Target name already exists"}
            
            # Rename file
            old_path.rename(new_path)
            
            # Update metadata
            meta = load_track_meta()
            if old_name in meta:
                meta[new_name] = meta.pop(old_name)
                save_track_meta(meta)
            
            return {"ok": True, "new_name": new_name}
        except Exception as e:
            logging.error(f"Error renaming track: {e}")
            return {"error": str(e)}
    
    def deleteTrack(self, name: str) -> Dict[str, Any]:
        """Delete a track file"""
        try:
            from cdmf_tracks import load_track_meta, save_track_meta
            from cdmf_paths import DEFAULT_OUT_DIR
            
            track_path = Path(DEFAULT_OUT_DIR) / name
            if not track_path.is_file():
                return {"error": "Track not found"}
            
            # Delete file
            track_path.unlink()
            
            # Remove from metadata
            meta = load_track_meta()
            if name in meta:
                del meta[name]
                save_track_meta(meta)
            
            return {"ok": True}
        except Exception as e:
            logging.error(f"Error deleting track: {e}")
            return {"error": str(e)}
    
    def getTrackFile(self, name: str) -> str:
        """Get file path for a track (for audio playback)"""
        try:
            from cdmf_paths import DEFAULT_OUT_DIR
            track_path = Path(DEFAULT_OUT_DIR) / name
            if track_path.is_file():
                return str(track_path)
            return ""
        except Exception as e:
            logging.error(f"Error getting track file: {e}")
            return ""
    
    # -----------------------------------------------------------------------
    # Models API
    # -----------------------------------------------------------------------
    
    def getModelStatus(self) -> Dict[str, Any]:
        """Get ACE-Step model status"""
        with cdmf_state.MODEL_LOCK:
            return {
                "state": cdmf_state.MODEL_STATUS["state"],
                "message": cdmf_state.MODEL_STATUS["message"],
            }
    
    def downloadModels(self) -> Dict[str, Any]:
        """Download ACE-Step models (runs in background thread)"""
        def download_worker():
            try:
                print("[AceForge] Starting model download...", flush=True)
                with cdmf_state.MODEL_LOCK:
                    cdmf_state.MODEL_STATUS["state"] = "downloading"
                    cdmf_state.MODEL_STATUS["message"] = "Downloading ACE-Step models..."
                
                ensure_ace_models()
                
                with cdmf_state.MODEL_LOCK:
                    cdmf_state.MODEL_STATUS["state"] = "ready"
                    cdmf_state.MODEL_STATUS["message"] = "ACE-Step model is ready."
                
                print("[AceForge] Model download complete", flush=True)
            except Exception as e:
                error_msg = str(e)
                logging.error(f"Model download error: {error_msg}")
                with cdmf_state.MODEL_LOCK:
                    cdmf_state.MODEL_STATUS["state"] = "error"
                    cdmf_state.MODEL_STATUS["message"] = f"Download failed: {error_msg}"
        
        # Start download in background thread
        thread = threading.Thread(target=download_worker, daemon=True)
        thread.start()
        
        return {"status": "started", "message": "Model download started in background"}
    
    def getModelsFolder(self) -> Dict[str, Any]:
        """Get the models folder path"""
        try:
            folder = cdmf_paths.get_models_folder()
            return {"ok": True, "models_folder": str(folder)}
        except Exception as e:
            return {"error": str(e)}
    
    def setModelsFolder(self, folder: str) -> Dict[str, Any]:
        """Set the models folder path"""
        try:
            if not folder or not folder.strip():
                return {"error": "Path cannot be empty"}
            success = cdmf_paths.set_models_folder(folder.strip())
            if success:
                return {
                    "ok": True,
                    "models_folder": str(cdmf_paths.get_models_folder()),
                    "message": "Models folder updated. Restart the application for changes to take effect."
                }
            else:
                return {"error": "Failed to set models folder. Check that the path is valid and writable."}
        except Exception as e:
            return {"error": str(e)}
    
    # -----------------------------------------------------------------------
    # Progress API
    # -----------------------------------------------------------------------
    
    def getProgress(self) -> Dict[str, Any]:
        """Get current generation progress"""
        with cdmf_state.PROGRESS_LOCK:
            return dict(cdmf_state.GENERATION_PROGRESS)
    
    # -----------------------------------------------------------------------
    # Presets API
    # -----------------------------------------------------------------------
    
    def listPresets(self) -> Dict[str, Any]:
        """List all presets"""
        try:
            from cdmf_tracks import load_user_presets
            data = load_user_presets()
            return {"ok": True, "presets": data.get("presets", [])}
        except Exception as e:
            logging.error(f"Error loading presets: {e}")
            return {"ok": False, "presets": []}
    
    def savePreset(self, preset_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save or delete a preset"""
        try:
            from cdmf_tracks import load_user_presets, save_user_presets
            
            mode = (preset_data.get("mode") or "save").strip().lower()
            data = load_user_presets()
            presets = data.get("presets", [])
            
            if mode == "delete":
                pid = (preset_data.get("id") or "").strip()
                if not pid:
                    return {"error": "Missing preset id"}
                presets = [p for p in presets if str(p.get("id")) != pid]
                data["presets"] = presets
                save_user_presets(data)
                return {"ok": True}
            
            # Save/upsert
            label = (preset_data.get("label") or "").strip()
            settings = preset_data.get("settings") or {}
            if not label:
                return {"error": "Preset label is required"}
            
            pid = (preset_data.get("id") or "").strip()
            if not pid:
                pid = f"u_{int(time.time() * 1000)}"
            
            # Upsert by id
            found = False
            for p in presets:
                if str(p.get("id")) == pid:
                    p["label"] = label
                    p.update(settings or {})
                    found = True
                    break
            
            if not found:
                presets.append({"id": pid, "label": label, **(settings or {})})
            
            data["presets"] = presets
            save_user_presets(data)
            return {"ok": True, "id": pid}
        except Exception as e:
            logging.error(f"Error saving preset: {e}")
            return {"error": str(e)}
    
    # -----------------------------------------------------------------------
    # Prompt/Lyrics Generation API
    # -----------------------------------------------------------------------
    
    def generatePromptLyrics(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate prompt tags and/or lyrics from a concept"""
        try:
            from lyrics_prompt_model import generate_prompt_lyrics
            
            concept = (params.get("concept") or "").strip()
            do_prompt = bool(params.get("do_prompt", True))
            do_lyrics = bool(params.get("do_lyrics", True))
            existing_prompt = (params.get("existing_prompt") or "").strip()
            existing_lyrics = (params.get("existing_lyrics") or "").strip()
            target_seconds = float(params.get("target_seconds", 90))
            
            if not concept:
                return {"error": "Concept cannot be empty"}
            
            result = generate_prompt_lyrics(
                concept=concept,
                do_prompt=do_prompt,
                do_lyrics=do_lyrics,
                existing_prompt=existing_prompt,
                existing_lyrics=existing_lyrics,
                target_seconds=target_seconds,
            )
            
            return {"ok": True, **result}
        except Exception as e:
            logging.error(f"Error generating prompt/lyrics: {e}")
            return {"error": str(e)}
    
    # -----------------------------------------------------------------------
    # Utility API
    # -----------------------------------------------------------------------
    
    def getDefaults(self) -> Dict[str, Any]:
        """Get UI defaults"""
        return {
            "target_seconds": 90,
            "fade_in": 0.5,
            "fade_out": 0.5,
            "steps": 55,
            "guidance_scale": 6.0,
        }
    
    def shutdown(self) -> Dict[str, Any]:
        """Shutdown the application"""
        print("[AceForge] Shutdown requested", flush=True)
        self.stop_log_streaming()
        return {"status": "ok"}


# ---------------------------------------------------------------------------
# Helper: Create minimal HTML if needed
# ---------------------------------------------------------------------------

def _create_minimal_html(html_path: Path):
    """Create a minimal HTML file that loads the UI"""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>AceForge - AI Music Generation</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            margin: 0;
            font-family: system-ui, -apple-system, sans-serif;
            background: #020617;
            color: #e5e7eb;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }
        .loading {
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="loading">
        <h1>AceForge</h1>
        <p>Loading...</p>
    </div>
    <script>
        // Load pywebview bridge first
        const script = document.createElement('script');
        script.src = 'scripts/pywebview_bridge.js';
        script.onload = function() {
            console.log('[AceForge] Pywebview bridge loaded');
            // Redirect to main UI when ready
            window.location.href = 'index.html';
        };
        document.head.appendChild(script);
    </script>
</body>
</html>"""
    html_path.write_text(html_content, encoding='utf-8')

# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def main():
    """Main entry point for serverless pywebview app"""
    import webview
    
    # Check model status
    if ace_models_present():
        print("[AceForge] ACE-Step model already present", flush=True)
        with cdmf_state.MODEL_LOCK:
            cdmf_state.MODEL_STATUS["state"] = "ready"
            cdmf_state.MODEL_STATUS["message"] = "ACE-Step model is present."
    else:
        print("[AceForge] ACE-Step model not downloaded yet", flush=True)
        with cdmf_state.MODEL_LOCK:
            if cdmf_state.MODEL_STATUS["state"] == "unknown":
                cdmf_state.MODEL_STATUS["state"] = "absent"
                cdmf_state.MODEL_STATUS["message"] = "ACE-Step model has not been downloaded yet."
    
    # Create API instance
    api = AceForgeAPI()
    
    # Determine HTML file path
    is_frozen = getattr(sys, 'frozen', False)
    if is_frozen:
        # In frozen app, static files are in Resources (PyInstaller standard)
        # Try multiple possible locations
        exe_path = Path(sys.executable)
        possible_paths = [
            exe_path.parent.parent / 'Resources' / 'static',  # Standard PyInstaller location
            exe_path.parent.parent / 'static',  # Alternative location
            Path(sys._MEIPASS) / 'static',  # PyInstaller temp directory
        ]
        base_path = None
        for path in possible_paths:
            if path.exists():
                base_path = path
                break
        if base_path is None:
            # Fallback: use _MEIPASS if available
            base_path = Path(sys._MEIPASS) / 'static' if hasattr(sys, '_MEIPASS') else exe_path.parent.parent / 'static'
    else:
        # In development, use project root
        base_path = Path(__file__).parent / 'static'
    
    # -----------------------------------------------------------------------
    # UI entrypoint
    #
    # `static/loading.html` is a legacy splash that polls the old Flask server
    # at http://127.0.0.1:5056/; in the new serverless pywebview app it will
    # never transition into the real UI.
    #
    # Instead, render the full UI from `cdmf_template.py` at runtime and open
    # it directly via file:// in pywebview.
    # -----------------------------------------------------------------------

    def _file_url(p: Path) -> str:
        return "file://" + urllib.parse.quote(str(p))

    def _render_ui_html(static_base: Path, api_obj: "AceForgeAPI") -> Path:
        try:
            from jinja2 import Template
        except Exception as e:
            raise RuntimeError("Jinja2 is required to render the UI template") from e

        try:
            import cdmf_template
        except Exception as e:
            raise RuntimeError("Failed to import cdmf_template for UI rendering") from e

        # Initial UI state
        try:
            tracks_payload = api_obj.getTracks()
            track_names = tracks_payload.get("tracks", []) if isinstance(tracks_payload, dict) else []
        except Exception:
            track_names = []

        try:
            presets_payload = api_obj.listPresets()
            presets = presets_payload.get("presets", {"instrumental": [], "vocal": []}) if isinstance(presets_payload, dict) else {"instrumental": [], "vocal": []}
        except Exception:
            presets = {"instrumental": [], "vocal": []}

        try:
            model_payload = api_obj.getModelStatus()
            model_state = model_payload.get("state", "unknown") if isinstance(model_payload, dict) else "unknown"
            model_message = model_payload.get("message", "") if isinstance(model_payload, dict) else ""
            models_ready = model_state == "ready"
        except Exception:
            model_state, model_message, models_ready = "unknown", "", False

        # Output directory and track file URLs
        try:
            out_dir = Path(cdmf_paths.get_default_out_dir())
        except Exception:
            out_dir = Path.cwd() / "generated"

        def url_for(endpoint: str, **kwargs) -> str:
            # Static assets referenced by template.
            # The rendered HTML lives in ~/Library/Application Support/AceForge/ui,
            # so we must use absolute file:// URLs back into the .app bundle.
            if endpoint == "static":
                filename = kwargs.get("filename", "")
                return _file_url(static_base / filename)

            # Fake endpoints for legacy JS (we shim fetch() in pywebview_bridge.js)
            if endpoint == "cdmf_generation.generate":
                return "/generate"
            if endpoint == "cdmf_tracks.serve_music":
                name = kwargs.get("filename") or kwargs.get("name") or ""
                return _file_url(out_dir / name)
            if endpoint == "cdmf_training.train_lora_status":
                return "/train_lora/status"
            if endpoint == "cdmf_mufun.mufun_status":
                return "/mufun/status"
            if endpoint == "cdmf_mufun.mufun_ensure":
                return "/mufun/ensure"
            if endpoint == "cdmf_mufun.mufun_analyze_dataset":
                return "/mufun/analyze_dataset"

            return "/"

        # Inject pywebview bridge before the main UI scripts
        template_html = cdmf_template.HTML
        injection = '\n  <script src="scripts/pywebview_bridge.js"></script>\n'
        if "cdmf_presets_ui.js" in template_html and "pywebview_bridge.js" not in template_html:
            template_html = template_html.replace(
                '<script src="{{ url_for(\'static\', filename=\'scripts/cdmf_presets_ui.js\') }}"></script>',
                injection + '  <script src="{{ url_for(\'static\', filename=\'scripts/cdmf_presets_ui.js\') }}"></script>',
                1,
            )

        rendered = Template(template_html).render(
            url_for=url_for,
            presets=presets,
            models_ready=models_ready,
            model_state=model_state,
            model_message=model_message,
            autoplay_url="",
            default_out_dir=str(out_dir),
            tracks=track_names,
            current_track=None,
            basename=None,
            error=None,
            details=None,
        )

        ui_dir = Path.home() / "Library" / "Application Support" / "AceForge" / "ui"
        ui_dir.mkdir(parents=True, exist_ok=True)
        out_html = ui_dir / "index.html"
        out_html.write_text(rendered, encoding="utf-8")
        return out_html

    html_path = _render_ui_html(base_path, api)
    
    print(f"[AceForge] Starting native window...", flush=True)
    print(f"[AceForge] HTML path: {html_path}", flush=True)
    print(f"[AceForge] HTML exists: {html_path.exists()}", flush=True)
    
    if not html_path.exists():
        error_msg = f"[AceForge] ERROR: HTML file not found at {html_path}"
        print(error_msg, flush=True)
        # Try to log to file
        try:
            log_dir = Path.home() / 'Library' / 'Logs' / 'AceForge'
            log_dir.mkdir(parents=True, exist_ok=True)
            with open(log_dir / 'error.log', 'w') as f:
                f.write(f"{error_msg}\n")
                f.write(f"Base path: {base_path}\n")
                f.write(f"Base path exists: {base_path.exists()}\n")
                if base_path.exists():
                    f.write(f"Files in base_path: {list(base_path.glob('*'))}\n")
        except:
            pass
        raise FileNotFoundError(error_msg)
    
    # Create window with pywebview
    window = webview.create_window(
        title="AceForge - AI Music Generation",
        url=str(html_path),
        js_api=api,
        width=1400,
        height=900,
        min_size=(1000, 700),
        resizable=True,
        fullscreen=False,
        on_top=False,
        shadow=True,
    )
    
    # Set window reference in API
    api.set_window(window)
    
    # Start the GUI event loop
    # When window is closed, the event loop exits and we can clean up
    webview.start(debug=False)
    
    # Cleanup after window closes
    print("[AceForge] Window closed, exiting...", flush=True)
    sys.exit(0)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        import traceback
        error_msg = (
            "[AceForge] FATAL ERROR during startup:\n"
            f"{traceback.format_exc()}\n"
            "\n"
            "The application will now exit.\n"
        )
        # Write to a log file so we can debug even with console=False
        try:
            import os
            from pathlib import Path
            log_dir = Path.home() / 'Library' / 'Logs' / 'AceForge'
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / 'error.log'
            with open(log_file, 'w') as f:
                f.write(error_msg)
            print(f"[AceForge] Error logged to: {log_file}", flush=True)
        except:
            pass
        print(error_msg, flush=True)
        sys.exit(1)
