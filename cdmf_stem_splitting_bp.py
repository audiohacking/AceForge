# cdmf_stem_splitting_bp.py
# Flask blueprint for stem splitting UI

from __future__ import annotations

import time
import traceback
import logging
from pathlib import Path
from typing import Any, Dict

from flask import Blueprint, request, render_template_string, jsonify
from werkzeug.utils import secure_filename

import cdmf_tracks
import cdmf_state
from cdmf_paths import DEFAULT_OUT_DIR, APP_VERSION
from cdmf_stem_splitting import get_stem_splitter

logger = logging.getLogger(__name__)


def create_stem_splitting_blueprint(html_template: str) -> Blueprint:
    """
    Create a blueprint for stem splitting routes.
    
    Routes:
      * "/stem_split" -> Stem splitting endpoint
    """
    bp = Blueprint("cdmf_stem_splitting", __name__)
    
    # Default parameters
    DEFAULT_STEM_COUNT = 4
    DEFAULT_DEVICE_PREFERENCE = "auto"
    DEFAULT_EXPORT_FORMAT = "wav"
    DEFAULT_MODE = None  # None, "vocals_only", or "instrumental"
    
    @bp.route("/stem_split", methods=["POST"])
    def stem_split():
        """Handle stem splitting request."""
        try:
            # Get input audio file
            if "input_file" not in request.files:
                return jsonify({
                    "error": True,
                    "message": "Input audio file is required."
                }), 400
            
            input_file = request.files["input_file"]
            if input_file.filename == "":
                return jsonify({
                    "error": True,
                    "message": "No file selected."
                }), 400
            
            # Validate file extension
            filename = secure_filename(input_file.filename)
            if not filename.lower().endswith(('.mp3', '.wav', '.m4a', '.flac', '.ogg')):
                return jsonify({
                    "error": True,
                    "message": "Invalid file format. Please use MP3, WAV, M4A, FLAC, or OGG."
                }), 400
            
            # Get parameters from form
            stem_count = int(request.form.get("stem_count", DEFAULT_STEM_COUNT))
            if stem_count not in [2, 4, 6]:
                return jsonify({
                    "error": True,
                    "message": "stem_count must be 2, 4, or 6."
                }), 400
            
            device_preference = request.form.get("device_preference", DEFAULT_DEVICE_PREFERENCE)
            mode = request.form.get("mode", DEFAULT_MODE) or None  # "vocals_only", "instrumental", or None
            export_format = request.form.get("export_format", DEFAULT_EXPORT_FORMAT).lower()
            if export_format not in ["wav", "mp3"]:
                export_format = "wav"
            
            # Get output directory (same as music generation)
            out_dir = request.form.get("out_dir", DEFAULT_OUT_DIR)
            out_dir_path = Path(out_dir)
            out_dir_path.mkdir(parents=True, exist_ok=True)
            
            # Extract input basename (without extension) for final file naming
            input_basename = Path(filename).stem
            # Sanitize basename
            input_basename = input_basename.replace("/", "_").replace("\\", "_").replace(":", "_")
            
            # Save uploaded input file temporarily
            # Use a temp directory to avoid cluttering the output directory
            import tempfile
            temp_dir = Path(tempfile.mkdtemp(prefix="aceforge_stem_temp_"))
            temp_input_path = temp_dir / filename
            input_file.save(str(temp_input_path))
            
            try:
                # Reset progress
                cdmf_state.reset_progress()
                with cdmf_state.PROGRESS_LOCK:
                    cdmf_state.GENERATION_PROGRESS["current"] = 0.0
                    cdmf_state.GENERATION_PROGRESS["total"] = 1.0
                    cdmf_state.GENERATION_PROGRESS["stage"] = "stem_split"
                    cdmf_state.GENERATION_PROGRESS["done"] = False
                    cdmf_state.GENERATION_PROGRESS["error"] = False
                
                # Create temporary subdirectory for Demucs output (will be cleaned up)
                # Format: stem_split_YYYYMMDD_HHMMSS
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                temp_demucs_dir = temp_dir / f"stem_split_{timestamp}"
                temp_demucs_dir.mkdir(parents=True, exist_ok=True)
                
                # Perform stem splitting
                # Files will be moved to final_output_dir with proper naming
                logger.info(f"[Stem Splitting] Starting: input={filename}, stems={stem_count}, mode={mode}, final_output={out_dir_path}")
                
                splitter = get_stem_splitter()
                stem_files = splitter.split_audio(
                    input_file=str(temp_input_path),
                    output_dir=str(temp_demucs_dir),  # Temporary Demucs output
                    stem_count=stem_count,
                    device_preference=device_preference,
                    mode=mode,
                    export_format=export_format,
                    final_output_dir=str(out_dir_path),  # Final location (DEFAULT_OUT_DIR)
                    input_basename=input_basename,  # For naming: input_basename_stems_stemname.wav
                )
                
                # Clean up temporary files and directory
                try:
                    import shutil
                    if temp_dir.exists():
                        shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception as e:
                    logger.warning(f"Failed to clean up temp directory: {e}")
                
                # Save track metadata for Music Player
                # Each stem gets its own metadata entry
                try:
                    from cdmf_ffmpeg import ensure_ffmpeg_in_path
                    ensure_ffmpeg_in_path()
                    
                    from pydub import AudioSegment
                    
                    track_meta = cdmf_tracks.load_track_meta()
                    
                    for stem_name, stem_path in stem_files.items():
                        stem_filename = Path(stem_path).name
                        dur = len(AudioSegment.from_file(str(stem_path))) / 1000.0
                        
                        entry = track_meta.get(stem_filename, {})
                        if "favorite" not in entry:
                            entry["favorite"] = False
                        entry["seconds"] = dur
                        entry["created"] = time.time()
                        entry["generator"] = "stem_split"
                        entry["basename"] = Path(stem_filename).stem
                        entry["stem_name"] = stem_name
                        entry["stem_count"] = stem_count
                        entry["mode"] = mode or ""
                        entry["export_format"] = export_format
                        entry["device_preference"] = device_preference
                        entry["out_dir"] = str(out_dir_path)
                        entry["original_file"] = filename
                        track_meta[stem_filename] = entry
                    
                    cdmf_tracks.save_track_meta(track_meta)
                except Exception as e:
                    from cdmf_ffmpeg import FFMPEG_INSTALL_HINT, is_ffmpeg_not_found_error
                    
                    if is_ffmpeg_not_found_error(e):
                        logger.warning("[Stem Splitting] Failed to save track metadata: %s", FFMPEG_INSTALL_HINT)
                    else:
                        logger.warning("[Stem Splitting] Failed to save track metadata: %s", e)
                
                # Mark progress as done
                with cdmf_state.PROGRESS_LOCK:
                    cdmf_state.GENERATION_PROGRESS["current"] = 1.0
                    cdmf_state.GENERATION_PROGRESS["total"] = 1.0
                    cdmf_state.GENERATION_PROGRESS["stage"] = "stem_split_done"
                    cdmf_state.GENERATION_PROGRESS["done"] = True
                    cdmf_state.GENERATION_PROGRESS["error"] = False
                
                # Get updated track list
                tracks = cdmf_tracks.list_music_files()
                
                logger.info(f"[Stem Splitting] Success: {len(stem_files)} stems created")
                
                return jsonify({
                    "error": False,
                    "message": f"Stem splitting completed: {len(stem_files)} stems created",
                    "stem_files": stem_files,
                    "output_dir": str(out_dir_path),
                    "tracks": tracks,
                })
                
            except Exception as e:
                # Clean up temporary directory on error
                try:
                    import shutil
                    if temp_dir.exists():
                        shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception:
                    pass
                # Mark progress as error
                with cdmf_state.PROGRESS_LOCK:
                    cdmf_state.GENERATION_PROGRESS["error"] = True
                    cdmf_state.GENERATION_PROGRESS["done"] = True
                    cdmf_state.GENERATION_PROGRESS["stage"] = "stem_split_error"
                raise
                
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"[Stem Splitting] Error: {e}\n{tb}")
            # Mark progress as error
            with cdmf_state.PROGRESS_LOCK:
                cdmf_state.GENERATION_PROGRESS["error"] = True
                cdmf_state.GENERATION_PROGRESS["done"] = True
                cdmf_state.GENERATION_PROGRESS["stage"] = "stem_split_error"
            return jsonify({
                "error": True,
                "message": f"Stem splitting failed: {str(e)}",
                "details": tb,
            }), 500
    
    return bp
