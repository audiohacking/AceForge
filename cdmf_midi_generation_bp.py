# cdmf_midi_generation_bp.py
# Flask blueprint for MIDI generation UI

from __future__ import annotations

import time
import traceback
import logging
from pathlib import Path
from typing import Any, Dict

from flask import Blueprint, request, render_template_string, jsonify
from werkzeug.utils import secure_filename

import cdmf_tracks
from cdmf_paths import DEFAULT_OUT_DIR, APP_VERSION
from cdmf_midi_generation import get_midi_generator

logger = logging.getLogger(__name__)


def create_midi_generation_blueprint(html_template: str) -> Blueprint:
    """
    Create a blueprint for MIDI generation routes.
    
    Routes:
      * "/midi_generate" -> MIDI generation endpoint
    """
    bp = Blueprint("cdmf_midi_generation", __name__)
    
    # Default parameters (matching basic-pitch defaults)
    DEFAULT_ONSET_THRESHOLD = 0.5
    DEFAULT_FRAME_THRESHOLD = 0.3
    DEFAULT_MINIMUM_NOTE_LENGTH_MS = 127.7
    DEFAULT_MIDI_TEMPO = 120.0
    DEFAULT_MULTIPLE_PITCH_BENDS = False
    DEFAULT_MELODIA_TRICK = True
    
    @bp.route("/midi_generate", methods=["POST"])
    def midi_generate():
        """Handle MIDI generation request."""
        try:
            # Check if model is available
            try:
                from midi_model_setup import basic_pitch_models_present
                if not basic_pitch_models_present():
                    return jsonify({
                        "error": True,
                        "message": "basic-pitch model is not downloaded yet. Please download it using the 'Download Models' button."
                    }), 400
            except ImportError:
                return jsonify({
                    "error": True,
                    "message": "MIDI generation module not available."
                }), 500
            
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
            onset_threshold = float(request.form.get("onset_threshold", DEFAULT_ONSET_THRESHOLD))
            frame_threshold = float(request.form.get("frame_threshold", DEFAULT_FRAME_THRESHOLD))
            minimum_note_length_ms = float(request.form.get("minimum_note_length_ms", DEFAULT_MINIMUM_NOTE_LENGTH_MS))
            minimum_frequency = request.form.get("minimum_frequency", "").strip()
            minimum_frequency = float(minimum_frequency) if minimum_frequency else None
            maximum_frequency = request.form.get("maximum_frequency", "").strip()
            maximum_frequency = float(maximum_frequency) if maximum_frequency else None
            multiple_pitch_bends = request.form.get("multiple_pitch_bends", "false").lower() == "true"
            melodia_trick = request.form.get("melodia_trick", "true").lower() == "true"
            midi_tempo = float(request.form.get("midi_tempo", DEFAULT_MIDI_TEMPO))
            
            # Get output filename
            output_filename = request.form.get("output_filename", "").strip()
            if not output_filename:
                # Generate default filename from input
                input_basename = Path(filename).stem
                output_filename = f"{input_basename}_midi"
            
            # Ensure .mid extension
            if not output_filename.lower().endswith('.mid'):
                output_filename = f"{output_filename}.mid"
            
            # Get output directory (same as music generation)
            out_dir = request.form.get("out_dir", DEFAULT_OUT_DIR)
            out_dir_path = Path(out_dir)
            out_dir_path.mkdir(parents=True, exist_ok=True)
            
            # Save uploaded input file temporarily
            import tempfile
            temp_dir = Path(tempfile.mkdtemp(prefix="aceforge_midi_temp_"))
            temp_input_path = temp_dir / filename
            input_file.save(str(temp_input_path))
            
            try:
                # Generate output path
                output_path = out_dir_path / output_filename
                
                # Perform MIDI generation
                logger.info(f"[MIDI Generation] Starting: input={filename}, output={output_path}")
                
                generator = get_midi_generator()
                result_path = generator.generate_midi(
                    audio_path=str(temp_input_path),
                    output_path=str(output_path),
                    onset_threshold=onset_threshold,
                    frame_threshold=frame_threshold,
                    minimum_note_length_ms=minimum_note_length_ms,
                    minimum_frequency=minimum_frequency,
                    maximum_frequency=maximum_frequency,
                    multiple_pitch_bends=multiple_pitch_bends,
                    melodia_trick=melodia_trick,
                    midi_tempo=midi_tempo,
                )
                
                # Clean up temporary input file
                try:
                    import shutil
                    if temp_dir.exists():
                        shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception as e:
                    logger.warning(f"Failed to clean up temp directory: {e}")
                
                # Save track metadata for Music Player
                try:
                    from cdmf_ffmpeg import ensure_ffmpeg_in_path
                    ensure_ffmpeg_in_path()
                    
                    # For MIDI files, we can't easily get duration without converting
                    # Just save basic metadata
                    track_meta = cdmf_tracks.load_track_meta()
                    midi_filename = Path(result_path).name
                    
                    entry = track_meta.get(midi_filename, {})
                    if "favorite" not in entry:
                        entry["favorite"] = False
                    entry["created"] = time.time()
                    entry["generator"] = "midi_generation"
                    entry["basename"] = Path(midi_filename).stem
                    entry["onset_threshold"] = onset_threshold
                    entry["frame_threshold"] = frame_threshold
                    entry["minimum_note_length_ms"] = minimum_note_length_ms
                    entry["minimum_frequency"] = minimum_frequency
                    entry["maximum_frequency"] = maximum_frequency
                    entry["multiple_pitch_bends"] = multiple_pitch_bends
                    entry["melodia_trick"] = melodia_trick
                    entry["midi_tempo"] = midi_tempo
                    entry["out_dir"] = str(out_dir_path)
                    entry["original_file"] = filename
                    track_meta[midi_filename] = entry
                    
                    cdmf_tracks.save_track_meta(track_meta)
                except Exception as e:
                    from cdmf_ffmpeg import FFMPEG_INSTALL_HINT, is_ffmpeg_not_found_error
                    
                    if is_ffmpeg_not_found_error(e):
                        logger.warning("[MIDI Generation] Failed to save track metadata: %s", FFMPEG_INSTALL_HINT)
                    else:
                        logger.warning("[MIDI Generation] Failed to save track metadata: %s", e)
                
                # Get updated track list
                tracks = cdmf_tracks.list_music_files()
                
                logger.info(f"[MIDI Generation] Success: {result_path}")
                
                return jsonify({
                    "error": False,
                    "message": f"MIDI generation completed: {output_filename}",
                    "output_file": result_path,
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
                raise
                
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"[MIDI Generation] Error: {e}\n{tb}")
            return jsonify({
                "error": True,
                "message": f"MIDI generation failed: {str(e)}",
                "details": tb,
            }), 500
    
    return bp
