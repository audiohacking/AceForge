# C:\AceForge\cdmf_tracks.py

from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List

from flask import Blueprint, request, jsonify, send_from_directory

import cdmf_state
from cdmf_paths import (
    DEFAULT_OUT_DIR,
    PRESETS_PATH,
    TRACK_META_PATH,
    USER_PRESETS_PATH,
    CUSTOM_LORA_ROOT,
)

# ---------------------------------------------------------------------------
# Helper functions for presets, metadata, tracks, LoRA adapters
# ---------------------------------------------------------------------------


def load_presets() -> Dict[str, Any]:
    """
    Load preset definitions from presets.json (if present).
    Returns a dict with "instrumental" and "vocal" arrays.
    """
    try:
        with PRESETS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("presets.json must contain an object at the top level.")
        data.setdefault("instrumental", [])
        data.setdefault("vocal", [])
        return data
    except Exception as e:
        print(f"[AceForge] Failed to load presets.json: {e}", flush=True)
        return {"instrumental": [], "vocal": []}


def load_track_meta() -> Dict[str, Any]:
    """
    Load per-track metadata (favorites, categories, etc.) from disk.
    """
    try:
        with TRACK_META_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        return {}


def save_track_meta(meta: Dict[str, Any]) -> None:
    """
    Persist per-track metadata back to disk.
    """
    try:
        with TRACK_META_PATH.open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, sort_keys=True)
    except Exception as e:
        print(f"[AceForge] Failed to save tracks_meta.json: {e}", flush=True)


def load_user_presets() -> Dict[str, Any]:
    """
    Load user-defined generation presets from disk.

    Returns a dict with a single key "presets" containing a list of objects:
      { "id", "label", ...settings... }
    """
    try:
        with USER_PRESETS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("presets"), list):
            return data
        if isinstance(data, list):
            # Legacy / simple form
            return {"presets": data}
        return {"presets": []}
    except Exception:
        return {"presets": []}


def save_user_presets(data: Dict[str, Any]) -> None:
    """
    Persist user-defined presets back to disk.
    """
    try:
        if not isinstance(data, dict):
            data = {"presets": []}
        if "presets" not in data or not isinstance(data["presets"], list):
            data["presets"] = []
        with USER_PRESETS_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
    except Exception as e:
        print(f"[AceForge] Failed to save user_presets.json: {e}", flush=True)


def get_audio_duration(path: Path) -> float:
    """Return duration in seconds. Uses pydub for .wav and .mp3. Returns 0.0 on error.
    Re-raises with an install hint if the error is ffprobe/ffmpeg not found."""
    try:
        from cdmf_ffmpeg import FFMPEG_INSTALL_HINT, ensure_ffmpeg_in_path, is_ffmpeg_not_found_error

        ensure_ffmpeg_in_path()

        from pydub import AudioSegment

        seg = AudioSegment.from_file(str(path))
        return len(seg) / 1000.0
    except Exception as e:
        if is_ffmpeg_not_found_error(e):
            raise RuntimeError(FFMPEG_INSTALL_HINT) from e
        return 0.0


def list_music_files() -> List[str]:
    """Return a sorted list of .wav, .mp3, and .mid files in the default music directory."""
    music_dir = Path(DEFAULT_OUT_DIR)
    if not music_dir.exists():
        return []
    names = [
        p.name for p in music_dir.iterdir()
        if p.is_file() and p.suffix.lower() in (".wav", ".mp3", ".mid")
    ]
    return sorted(names, key=lambda n: n.lower())


def list_lora_adapters() -> List[Dict[str, Any]]:
    """
    Return a list of discovered LoRA adapters under CUSTOM_LORA_ROOT.

    Each entry is a dict:
      { "name": "<folder_name>", "path": "<full_path>", "size_bytes": int|None }
    """
    adapters: List[Dict[str, Any]] = []
    root = CUSTOM_LORA_ROOT

    try:
        if not root.exists():
            return adapters

        for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if not entry.is_dir():
                continue

            safes = sorted(entry.glob("*.safetensors"))
            if not safes:
                continue

            size_bytes = None
            try:
                size_bytes = safes[0].stat().st_size
            except OSError:
                size_bytes = None

            adapters.append(
                {
                    "name": entry.name,
                    "path": str(entry),
                    "size_bytes": size_bytes,
                }
            )
    except Exception as exc:
        print(f"[AceForge] Failed to list LoRA adapters: {exc}", flush=True)

    return adapters


# ---------------------------------------------------------------------------
# Blueprint and routes
# ---------------------------------------------------------------------------

def create_tracks_blueprint() -> Blueprint:
    bp = Blueprint("cdmf_tracks", __name__)

    @bp.route("/music/<path:filename>")
    def serve_music(filename: str):
        """Serve audio files from the AceForge music directory."""
        return send_from_directory(DEFAULT_OUT_DIR, filename)

    @bp.route("/progress", methods=["GET"])
    def get_progress():
        """Return current generation progress as JSON for the front-end progress bar."""
        with cdmf_state.PROGRESS_LOCK:
            current = cdmf_state.GENERATION_PROGRESS["current"]
            total = cdmf_state.GENERATION_PROGRESS["total"] or 0.0
            done = cdmf_state.GENERATION_PROGRESS["done"]
            error = cdmf_state.GENERATION_PROGRESS["error"]
            stage = cdmf_state.GENERATION_PROGRESS["stage"]

        if error:
            fraction = 0.0
        elif done:
            fraction = 1.0
        elif total > 0:
            try:
                if total == 1 and 0.0 <= float(current) <= 1.0:
                    fraction = float(current)
                else:
                    fraction = float(current) / float(total)
            except Exception:
                fraction = 0.35
        else:
            fraction = 0.0

        return jsonify(
            {
                "current": current,
                "total": total,
                "fraction": fraction,
                "done": done,
                "error": error,
                "stage": stage,
            }
        )

    @bp.route("/tracks.json", methods=["GET"])
    def tracks_json():
        """
        JSON list of available .wav and .mp3 tracks plus the most recently generated one
        (if known). Used by the front-end after a generation finishes.
        """
        tracks = list_music_files()
        meta = load_track_meta()

        music_dir = Path(DEFAULT_OUT_DIR)

        # Prefer the last generated track, if it's in the list
        with cdmf_state.PROGRESS_LOCK:
            last = cdmf_state.LAST_GENERATED_TRACK

        current = None
        latest_name = None
        latest_mtime = None
        mtimes: Dict[str, float] = {}

        if tracks:
            for name in tracks:
                p = music_dir / name
                try:
                    mtime = p.stat().st_mtime
                except OSError:
                    continue
                mtimes[name] = mtime
                if latest_mtime is None or mtime > latest_mtime:
                    latest_mtime = mtime
                    latest_name = name

            if last and last in tracks:
                current = last
            else:
                current = latest_name or tracks[-1]

        track_items = []
        for name in tracks:
            info = meta.get(name, {})
            seconds_val = float(info.get("seconds") or 0.0)
            if seconds_val <= 0:
                seconds_val = get_audio_duration(music_dir / name)
            track_items.append(
                {
                    "name": name,
                    "favorite": bool(info.get("favorite", False)),
                    "category": info.get("category") or "",
                    "seconds": seconds_val,
                    "bpm": float(info.get("bpm")) if info.get("bpm") is not None else None,
                    # Created timestamp: stored in meta if present, otherwise file mtime
                    "created": float(info.get("created") or mtimes.get(name) or 0.0),
                }
            )

        # Newest first (by created time)
        track_items.sort(key=lambda x: float(x.get("created") or 0), reverse=True)

        return jsonify({"tracks": track_items, "current": current})

    @bp.route("/tracks/meta", methods=["GET", "POST"])
    def tracks_meta():
        """
        GET: Return full metadata (including generation settings) for a track.
        POST: Update metadata (favorite, category, etc.) for a given track.
        """
        if request.method == "GET":
            name = (request.args.get("name") or "").strip()
            if not name:
                return jsonify({"error": "Missing track name"}), 400

            track_path = Path(DEFAULT_OUT_DIR) / name
            if not track_path.is_file():
                return jsonify({"error": "Track not found"}), 404

            meta = load_track_meta()
            entry = meta.get(name)
            if not entry:
                return jsonify({"error": "No metadata for this track"}), 404

            return jsonify({"ok": True, "meta": entry})

        # POST: update favorite/category (existing behavior)
        payload = request.get_json(silent=True) or {}
        name = (payload.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Missing track name"}), 400

        track_path = Path(DEFAULT_OUT_DIR) / name
        if not track_path.is_file():
            return jsonify({"error": "Track not found"}), 404

        meta = load_track_meta()
        entry = meta.get(name, {})

        if "favorite" in payload:
            entry["favorite"] = bool(payload["favorite"])
        if "category" in payload:
            entry["category"] = str(payload["category"] or "").strip()

        meta[name] = entry
        save_track_meta(meta)

        return jsonify({"ok": True, "meta": entry})

    @bp.route("/user_presets", methods=["GET", "POST"])
    def user_presets():
        """
        GET: Return all user-defined presets.
        POST: Save or delete a preset.

        POST JSON:
          { "mode": "save",
            "id": optional existing id to overwrite,
            "label": "My preset name",
            "settings": { ...generation knobs... }
          }

          or

          { "mode": "delete", "id": "preset_id_here" }
        """
        if request.method == "GET":
            data = load_user_presets()
            return jsonify({"ok": True, "presets": data.get("presets", [])})

        payload = request.get_json(silent=True) or {}
        mode = (payload.get("mode") or "save").strip().lower()

        data = load_user_presets()
        presets = data.get("presets", [])

        if mode == "delete":
            pid = (payload.get("id") or "").strip()
            if not pid:
                return jsonify({"error": "Missing preset id"}), 400
            presets = [p for p in presets if str(p.get("id")) != pid]
            data["presets"] = presets
            save_user_presets(data)
            return jsonify({"ok": True})

        # Default: save / upsert
        label = (payload.get("label") or "").strip()
        settings = payload.get("settings") or {}
        if not label:
            return jsonify({"error": "Preset label is required"}), 400

        pid = (payload.get("id") or "").strip()
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
            preset = {"id": pid, "label": label}
            preset.update(settings or {})
            presets.append(preset)

        data["presets"] = presets
        save_user_presets(data)
        return jsonify({"ok": True, "preset": {"id": pid, "label": label}})

    @bp.route("/tracks/rename", methods=["POST"])
    def rename_track():
        """
        Rename a track file on disk and move its metadata entry.
        """
        payload = request.get_json(silent=True) or {}
        old_name = (payload.get("old_name") or "").strip()
        new_name = (payload.get("new_name") or "").strip()

        if not old_name or not new_name:
            return jsonify({"error": "Missing old_name or new_name"}), 400

        # Prevent directory traversal / path injection
        if "/" in old_name or "\\" in old_name or "/" in new_name or "\\" in new_name:
            return jsonify({"error": "Track names cannot contain path separators."}), 400

        # Always treat tracks as .wav files on disk
        old_base, _old_ext = os.path.splitext(old_name)
        if not old_base:
            return jsonify({"error": "Invalid original track name."}), 400

        new_base, _ = os.path.splitext(new_name)
        if not new_base:
            return jsonify({"error": "New track name cannot be empty."}), 400
        final_name = new_base + ".wav"

        old_path = Path(DEFAULT_OUT_DIR) / (old_base + ".wav")
        new_path = Path(DEFAULT_OUT_DIR) / final_name

        if not old_path.is_file():
            return jsonify({"error": "Original track not found."}), 404

        if new_path.exists():
            return jsonify({"error": "A track with that name already exists."}), 409

        try:
            old_path.rename(new_path)
        except OSError as e:
            return jsonify({"error": f"Failed to rename track: {e}"}), 500

        meta = load_track_meta()
        if old_path.name in meta:
            entry = meta.pop(old_path.name)
            # Keep basename aligned with the new file's base name
            if isinstance(entry, dict):
                entry["basename"] = new_base
            meta[final_name] = entry
            save_track_meta(meta)

        with cdmf_state.PROGRESS_LOCK:
            if cdmf_state.LAST_GENERATED_TRACK == old_path.name:
                cdmf_state.LAST_GENERATED_TRACK = final_name

        return jsonify({"ok": True, "name": final_name})

    @bp.route("/tracks/delete", methods=["POST"])
    def delete_track():
        """
        Delete a track file from disk and remove its metadata entry.
        """
        payload = request.get_json(silent=True) or {}
        name = (payload.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Missing track name"}), 400

        track_path = Path(DEFAULT_OUT_DIR) / name
        if not track_path.is_file():
            return jsonify({"error": "Track not found"}), 404

        try:
            track_path.unlink()
        except OSError as e:
            return jsonify({"error": f"Failed to delete track: {e}"}), 500

        meta = load_track_meta()
        if name in meta:
            meta.pop(name, None)
            save_track_meta(meta)

        with cdmf_state.PROGRESS_LOCK:
            if cdmf_state.LAST_GENERATED_TRACK == name:
                cdmf_state.LAST_GENERATED_TRACK = None

        return jsonify({"ok": True})

    @bp.route("/tracks/reveal-in-finder", methods=["POST"])
    def reveal_in_finder():
        """
        Open the track's parent folder in the system file manager and reveal/select the file.
        Supported on macOS (open -R). Other platforms may return an error.
        """
        payload = request.get_json(silent=True) or {}
        name = (payload.get("name") or "").strip()
        if not name:
            return jsonify({"ok": False, "error": "Missing track name"}), 400

        if "/" in name or "\\" in name or ".." in name:
            return jsonify({"ok": False, "error": "Invalid track name"}), 400

        track_path = Path(DEFAULT_OUT_DIR) / name
        if not track_path.is_file():
            return jsonify({"ok": False, "error": "Track not found"}), 404

        if platform.system() == "Darwin":
            try:
                subprocess.run(
                    ["open", "-R", str(track_path.resolve())],
                    check=True,
                    capture_output=True,
                    timeout=5,
                )
                return jsonify({"ok": True})
            except subprocess.CalledProcessError as e:
                err = (e.stderr.decode(errors="replace") if e.stderr else str(e)) or "open failed"
                return jsonify({"ok": False, "error": err}), 500
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500
        # Windows: explorer /select,"path" ; Linux: xdg-open parent. For now only macOS.
        return jsonify({"ok": False, "error": "Reveal in Finder is only supported on macOS"}), 501

    return bp
