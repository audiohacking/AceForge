# cdmf_stem_splitting.py
# Stem splitting module using Demucs
#
# Mac Environment Setup Requirements:
# 1. Install Demucs:
#    pip install demucs
# 2. Demucs uses PyTorch which supports MPS (Metal) on macOS
#
# Performance Notes:
# - Demucs supports MPS (Metal) acceleration on Apple Silicon
# - Falls back to CPU if MPS is not available
# - First run downloads model weights (can be several GB)

from __future__ import annotations

import os
import platform
import tempfile
import logging
import traceback
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Callable

import torch
import inspect

logger = logging.getLogger(__name__)

# CRITICAL for Apple Silicon: This allows the M-series GPU to hand off 
# unsupported operations to the CPU instead of crashing.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

# Progress callback for stem splitting
_stem_split_progress_callback: Optional[Callable[[float, str], None]] = None


def register_stem_split_progress_callback(cb: Optional[Callable[[float, str], None]]) -> None:
    """Register a progress callback for stem splitting."""
    global _stem_split_progress_callback
    _stem_split_progress_callback = cb


def _report_stem_split_progress(fraction: float, stage: str = "stem_split") -> None:
    """Internal helper to report progress to the UI."""
    global _stem_split_progress_callback
    if _stem_split_progress_callback is None:
        return
    try:
        frac = max(0.0, min(1.0, float(fraction)))
        _stem_split_progress_callback(frac, stage)
    except Exception:
        # Do not let UI progress errors kill stem splitting
        pass


class StemSplitter:
    """
    Stem splitting using Demucs.
    Supports 2-stem (vocals/instrumental), 4-stem (vocals/drums/bass/other),
    and 6-stem (vocals/drums/bass/guitar/piano/other) modes.
    On macOS: Uses MPS (Metal) if available, else CPU.
    """
    
    def __init__(self):
        """Initialize the stem splitter."""
        self.model = None
        self.device = None
        self._initialized = False
        self._device_preference = None
        
    def _patch_demucs_tqdm(self):
        """Patch Demucs's tqdm to report progress."""
        try:
            import demucs.separate as demucs_mod
            from tqdm import tqdm as orig_tqdm
            
            # Avoid double-patching
            if getattr(demucs_mod, "_aceforge_tqdm_patched", False):
                return
            
            def patched_tqdm(iterable=None, *args, **kwargs):
                """Wrapper around tqdm that reports progress."""
                # If tqdm is used in "manual" mode (no iterable), just delegate
                if iterable is None:
                    return orig_tqdm(*args, **kwargs)
                
                # Get total if not provided
                total = kwargs.get("total")
                if total is None:
                    try:
                        total = len(iterable)
                    except Exception:
                        total = None
                
                # Create original tqdm
                inner = orig_tqdm(iterable, *args, **kwargs)
                
                # Progress range: 0.10 to 0.90 (leave room for start/end)
                start_progress = 0.10
                end_progress = 0.90
                span = end_progress - start_progress
                
                def generator():
                    idx = 0
                    denom = float(total) if total else None
                    
                    for item in inner:
                        idx += 1
                        if denom:
                            frac_local = idx / denom  # 0..1 within this stage
                            frac_global = start_progress + span * frac_local
                            _report_stem_split_progress(frac_global, "stem_split")
                        yield item
                
                return generator()
            
            # Patch tqdm in demucs.separate module
            demucs_mod.tqdm = patched_tqdm
            demucs_mod._aceforge_tqdm_patched = True
            logger.debug("Patched Demucs tqdm for progress reporting")
            
        except Exception as e:
            logger.warning(f"Could not patch Demucs tqdm for progress: {e}")
    
    def _initialize(self, device_preference: str = "auto"):
        """
        Lazy initialization of the Demucs model.
        
        Args:
            device_preference: Device to use ("mps", "cpu", or "auto")
                - "mps": Force Apple Silicon GPU (MPS)
                - "cpu": Force CPU
                - "auto": Auto-detect (MPS if available, else CPU)
        """
        if self._initialized and self._device_preference == device_preference:
            return
            
        try:
            import demucs.separate
        except ImportError as e:
            raise ImportError(
                "Demucs library not installed. Install with: pip install demucs. (Original: %s)" % e
            ) from e
        
        # Determine device
        if platform.system() == "Darwin":
            if device_preference == "cpu":
                self.device = torch.device("cpu")
                logger.info("Using CPU for stem splitting (user selected).")
            elif device_preference == "mps" and torch.backends.mps.is_available():
                self.device = torch.device("mps")
                logger.info("Using MPS (Metal) for stem splitting.")
            elif device_preference == "auto":
                if torch.backends.mps.is_available():
                    self.device = torch.device("mps")
                    logger.info("Using MPS (Metal) for stem splitting (auto-detected).")
                else:
                    self.device = torch.device("cpu")
                    logger.info("Using CPU for stem splitting (MPS not available).")
            else:
                self.device = torch.device("cpu")
                logger.info("Using CPU for stem splitting (MPS requested but not available).")
        else:
            # Non-Mac: use CUDA if available, else CPU
            if device_preference == "cpu":
                self.device = torch.device("cpu")
                logger.info("Using CPU for stem splitting (user selected).")
            elif device_preference == "mps":
                self.device = torch.device("cpu")
                logger.warning("MPS not available on this platform. Using CPU.")
            else:
                self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
                logger.info("Using %s for stem splitting.", self.device)
        
        self._initialized = True
        self._device_preference = device_preference
        logger.info("Stem splitter initialized successfully.")
    
    def split_audio(
        self,
        input_file: str,
        output_dir: str,
        stem_count: int = 4,
        model: Optional[str] = None,
        device_preference: str = "auto",
        mode: Optional[str] = None,
        export_format: str = "wav",
        final_output_dir: Optional[str] = None,
        input_basename: Optional[str] = None,
        **kwargs
    ) -> Dict[str, str]:
        """
        Split audio into stems.
        
        Args:
            input_file: Path to input audio file
            output_dir: Temporary directory for Demucs output (will be cleaned up)
            stem_count: Number of stems (2, 4, or 6)
            model: Model name (auto-selected if None)
            device_preference: Device to use ("mps", "cpu", or "auto")
            mode: Optional mode ("vocals_only", "instrumental")
            export_format: Output format ("wav" or "mp3")
            final_output_dir: Final output directory (defaults to output_dir if None)
            input_basename: Base name for output files (defaults to input file stem if None)
            
        Returns:
            Dictionary mapping stem names to final output file paths
        """
        # Initialize with device preference
        self._initialize(device_preference)
        
        # Validate input file
        input_path = Path(input_file)
        if not input_path.exists():
            raise FileNotFoundError(f"Input audio file not found: {input_file}")
        
        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Select model based on stem count
        if model is None:
            if stem_count == 2:
                model = "htdemucs"
            elif stem_count == 4:
                model = "htdemucs_ft"  # Fine-tuned 4-stem model
            elif stem_count == 6:
                model = "htdemucs_6s"  # 6-stem specialized model
            else:
                raise ValueError(f"Unsupported stem_count: {stem_count}. Must be 2, 4, or 6.")
        
        logger.info(f"Splitting audio: {input_path.name} -> {stem_count} stems using {model}")
        
        # Prepare arguments for demucs.separate.main
        # Demucs CLI: demucs.separate.main(["-n", model, "-o", output_dir, input_file])
        args = ["-n", model, "-o", str(output_path), str(input_path)]
        
        # Add two-stems option for 2-stem mode
        if stem_count == 2:
            args.append("--two-stems=vocals")
        
        # Set device preference via environment (Demucs respects CUDA_VISIBLE_DEVICES, etc.)
        # For MPS, we'll let PyTorch handle it automatically
        
        try:
            import demucs.separate
            
            # Patch Demucs's tqdm to report progress
            self._patch_demucs_tqdm()
            
            # Demucs will use the device based on PyTorch's default
            # We can't directly pass device to demucs.separate.main, but
            # we can set torch's default device before calling
            original_device = None
            try:
                if self.device.type == "mps":
                    # MPS is already set as default via torch.device("mps")
                    # Demucs should pick it up automatically
                    pass
                elif self.device.type == "cuda":
                    # Set CUDA device
                    torch.cuda.set_device(self.device)
            except Exception as e:
                logger.warning(f"Could not set device preference: {e}")
            
            # Report start
            _report_stem_split_progress(0.05, "stem_split_load")
            
            # Demucs.separate.main() uses argparse and expects sys.argv to be set
            # Save original argv and restore it after
            import sys
            old_argv = sys.argv[:]
            try:
                sys.argv = ["demucs"] + args
                logger.debug(f"Calling demucs.separate.main() with sys.argv: {sys.argv}")
                # Run separation
                demucs.separate.main()
            except SystemExit as se:
                # argparse may call sys.exit(), which raises SystemExit
                # Check exit code - 0 means success, non-zero means error
                if se.code != 0:
                    logger.error(f"Demucs exited with code {se.code}")
                    raise RuntimeError(f"Demucs separation failed with exit code {se.code}") from se
                logger.debug("Demucs completed (SystemExit with code 0)")
            finally:
                sys.argv = old_argv
            
            # Report near completion (before file operations)
            _report_stem_split_progress(0.95, "stem_split_finalize")
            
            # Find output files
            # Demucs creates: output_dir/model_name/track_name/stem_name.wav
            model_output_dir = output_path / model / input_path.stem
            
            if not model_output_dir.exists():
                raise RuntimeError(f"Demucs output directory not found: {model_output_dir}")
            
            # Map stem names to files
            stem_files = {}
            
            if stem_count == 2:
                # Vocals and instrumental
                vocals_file = model_output_dir / "vocals.wav"
                instrumental_file = model_output_dir / "no_vocals.wav"
                
                if vocals_file.exists():
                    stem_files["vocals"] = str(vocals_file)
                if instrumental_file.exists():
                    stem_files["instrumental"] = str(instrumental_file)
                    
            elif stem_count == 4:
                # Vocals, drums, bass, other
                for stem_name in ["vocals", "drums", "bass", "other"]:
                    stem_file = model_output_dir / f"{stem_name}.wav"
                    if stem_file.exists():
                        stem_files[stem_name] = str(stem_file)
                        
            elif stem_count == 6:
                # Vocals, drums, bass, guitar, piano, other
                for stem_name in ["vocals", "drums", "bass", "guitar", "piano", "other"]:
                    stem_file = model_output_dir / f"{stem_name}.wav"
                    if stem_file.exists():
                        stem_files[stem_name] = str(stem_file)
            
            # Handle mode-specific processing
            if mode == "vocals_only":
                # For acapella extraction, return only vocals
                if "vocals" in stem_files:
                    # Optionally apply de-reverb or other post-processing here
                    stem_files = {"vocals": stem_files["vocals"]}
            elif mode == "instrumental":
                # For karaoke/instrumental, return only instrumental
                if "instrumental" in stem_files:
                    stem_files = {"instrumental": stem_files["instrumental"]}
                elif "no_vocals" in stem_files:
                    stem_files = {"instrumental": stem_files["no_vocals"]}
            
            # Determine final output directory and basename
            final_out_dir = Path(final_output_dir) if final_output_dir else output_path
            final_out_dir.mkdir(parents=True, exist_ok=True)
            
            base_name = input_basename if input_basename else input_path.stem
            # Sanitize basename (remove path separators, etc.)
            base_name = base_name.replace("/", "_").replace("\\", "_").replace(":", "_")
            
            # Move files to final location with proper naming
            # Format: input_basename_stems_stemname.wav
            final_stem_files = {}
            ext = f".{export_format.lower()}" if export_format.lower() in ["wav", "mp3"] else ".wav"
            
            def _next_available_path(base_dir: Path, base_stem: str, stem_name: str, ext: str) -> Path:
                """Find next available filename, avoiding collisions."""
                candidate = base_dir / f"{base_stem}_stems_{stem_name}{ext}"
                if not candidate.exists():
                    return candidate
                idx = 2
                while True:
                    candidate = base_dir / f"{base_stem}_stems_{stem_name}_{idx}{ext}"
                    if not candidate.exists():
                        return candidate
                    idx += 1
            
            import shutil
            
            for stem_name, temp_stem_path in stem_files.items():
                temp_path = Path(temp_stem_path)
                
                # Convert to MP3 if requested (before moving)
                if export_format.lower() == "mp3" and temp_path.suffix.lower() == ".wav":
                    from cdmf_ffmpeg import ensure_ffmpeg_in_path
                    ensure_ffmpeg_in_path()
                    from pydub import AudioSegment
                    
                    mp3_temp = temp_path.with_suffix(".mp3")
                    try:
                        audio = AudioSegment.from_wav(str(temp_path))
                        audio.export(str(mp3_temp), format="mp3", bitrate="256k")
                        temp_path = mp3_temp
                        # Remove original WAV
                        Path(temp_stem_path).unlink()
                    except Exception as e:
                        logger.warning(f"Failed to convert {stem_name} to MP3: {e}")
                        # Keep WAV as fallback
                
                # Determine final filename
                final_path = _next_available_path(final_out_dir, base_name, stem_name, ext)
                
                # Move file to final location
                try:
                    shutil.move(str(temp_path), str(final_path))
                    final_stem_files[stem_name] = str(final_path)
                    logger.debug(f"Moved {stem_name} stem: {temp_path.name} -> {final_path.name}")
                except Exception as e:
                    logger.error(f"Failed to move {stem_name} stem: {e}")
                    # Fallback: use original path if move fails
                    final_stem_files[stem_name] = str(temp_path)
            
            # Clean up temporary Demucs structure
            try:
                if output_path != final_out_dir:
                    # Only clean up if we used a different temp directory
                    if output_path.exists():
                        shutil.rmtree(output_path, ignore_errors=True)
                        logger.debug(f"Cleaned up temporary Demucs output: {output_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary directory: {e}")
            
            # Report completion
            _report_stem_split_progress(1.0, "stem_split_done")
            
            logger.info(f"Stem splitting completed: {len(final_stem_files)} stems created in {final_out_dir}")
            return final_stem_files
            
        except Exception as e:
            # Report error
            _report_stem_split_progress(0.0, "stem_split_error")
            logger.error(f"Stem splitting failed: {e}")
            raise


# Global singleton instance
_stem_splitter: Optional[StemSplitter] = None


def get_stem_splitter() -> StemSplitter:
    """Get or create the global stem splitter instance."""
    global _stem_splitter
    if _stem_splitter is None:
        _stem_splitter = StemSplitter()
    return _stem_splitter


def stem_split_models_present() -> bool:
    """
    Check if the default Demucs model (htdemucs) is already in torch.hub cache.
    Models are stored in the AceForge models directory (configured via TORCH_HOME).
    Used to show "Download Demucs models" only when needed (first use).
    
    Demucs stores models in torch.hub/checkpoints/ as .th files (PyTorch model files).
    """
    try:
        # Ensure TORCH_HOME points to AceForge models directory
        # Use assignment (not setdefault) to force update in case it was set elsewhere
        import cdmf_paths
        models_folder = cdmf_paths.get_models_folder()
        os.environ["TORCH_HOME"] = str(models_folder)
        
        # Force torch.hub to re-read TORCH_HOME by ensuring it's set before calling get_dir()
        hub_dir = Path(torch.hub.get_dir())
        logger.debug(f"Checking for Demucs models in: {hub_dir}")
        logger.debug(f"TORCH_HOME environment variable: {os.environ.get('TORCH_HOME')}")
        
        if not hub_dir.exists():
            logger.debug(f"Torch hub directory does not exist: {hub_dir}")
            return False
        
        # Demucs 4.x stores models in hub/checkpoints/ as .th files
        checkpoints_dir = hub_dir / "checkpoints"
        if checkpoints_dir.exists() and checkpoints_dir.is_dir():
            # Check for .th files (PyTorch model files) - Demucs models are typically large (>50MB)
            for model_file in checkpoints_dir.iterdir():
                if model_file.is_file() and model_file.suffix == ".th":
                    # Check if file is substantial (at least 10MB to avoid false positives)
                    if model_file.stat().st_size > 10 * 1024 * 1024:
                        logger.info(f"Found Demucs model file at: {model_file} ({model_file.stat().st_size / (1024*1024):.1f} MB)")
                        return True
        
        # Also check for legacy directory-based storage (older Demucs versions)
        # Look for directories with "demucs" or "htdemucs" in the name
        for name in hub_dir.iterdir():
            if name.is_dir() and ("demucs" in name.name.lower() or "htdemucs" in name.name.lower()):
                # Has content (model files)
                if any(name.iterdir()):
                    logger.debug(f"Found Demucs models at: {name}")
                    return True
        
        logger.debug(f"No Demucs models found in: {hub_dir}")
        return False
    except Exception as e:
        logger.debug(f"Error checking for Demucs models: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return False


def ensure_stem_split_models(progress_cb: Optional[Callable[[float], None]] = None) -> None:
    """
    Pre-download the default Demucs model (htdemucs) so first stem-split run doesn't block.
    Uses CPU to avoid MPS/GPU memory during download. Progress: 0.0 at start, 1.0 when done.
    Models are downloaded to the AceForge models directory (configured via TORCH_HOME).
    """
    # Ensure TORCH_HOME is set to AceForge models directory
    # This should already be set early in music_forge_ui.py, but verify it here
    import cdmf_paths
    models_folder = cdmf_paths.get_models_folder()
    models_folder.mkdir(parents=True, exist_ok=True)
    
    # Set TORCH_HOME to ensure torch.hub uses AceForge models directory
    os.environ["TORCH_HOME"] = str(models_folder)
    logger.info(f"Ensuring Demucs models download to: {models_folder}")
    logger.info(f"TORCH_HOME set to: {os.environ.get('TORCH_HOME')}")
    logger.info(f"torch.hub.get_dir() returns: {torch.hub.get_dir()}")
    
    if progress_cb:
        try:
            progress_cb(0.0)
        except Exception:
            pass
    
    try:
        # Demucs downloads on first use. Trigger load by running a minimal separation:
        # Match the local test exactly - use same approach as test_stem_splitting_standalone.py
        import tempfile
        import wave
        import traceback
        import sys
        
        tmp_dir = Path(tempfile.mkdtemp(prefix="aceforge_stem_dl_"))
        try:
            # Create a minimal WAV file (1 second silence, 44.1kHz mono) - same as local test approach
            wav_path = tmp_dir / "silence.wav"
            logger.info(f"Creating temporary test WAV file: {wav_path}")
            with wave.open(str(wav_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(44100)
                wf.writeframes(b"\x00\x00" * 44100)
            
            if not wav_path.exists():
                raise FileNotFoundError(f"Failed to create test WAV file: {wav_path}")
            
            # Ensure paths are absolute (critical for frozen apps)
            wav_path = wav_path.resolve()
            if not wav_path.exists():
                raise FileNotFoundError(f"WAV file does not exist after resolve: {wav_path}")
            
            out_dir = tmp_dir / "out"
            out_dir.mkdir(exist_ok=True)
            out_dir = out_dir.resolve()
            
            logger.info("Importing Demucs modules...")
            from demucs.pretrained import get_model
            from demucs.separate import load_track, apply_model, save_audio
            from demucs.audio import convert_audio
            
            logger.info(f"Triggering Demucs model download...")
            logger.info(f"  Model: htdemucs")
            logger.info(f"  Torch hub cache: {torch.hub.get_dir()}")
            
            # Instead of using argparse (which causes AssertionError in frozen app),
            # call get_model directly to trigger model download
            # This avoids argparse issues while still downloading the model
            try:
                logger.info("Loading Demucs model (this will download if not present)...")
                model = get_model("htdemucs", repo=None)
                model.cpu()
                model.eval()
                logger.info("Demucs model loaded successfully (download completed if needed)")
                
                # Verify model was downloaded by checking torch.hub cache
                hub_dir = Path(torch.hub.get_dir())
                logger.info(f"Model cache location: {hub_dir}")
                if hub_dir.exists():
                    demucs_found = False
                    # Check for .th files in checkpoints directory
                    checkpoints_dir = hub_dir / "checkpoints"
                    if checkpoints_dir.exists():
                        for model_file in checkpoints_dir.iterdir():
                            if model_file.is_file() and model_file.suffix == ".th":
                                if model_file.stat().st_size > 10 * 1024 * 1024:
                                    logger.info(f"✓ Found Demucs model file: {model_file} ({model_file.stat().st_size / (1024*1024):.1f} MB)")
                                    demucs_found = True
                                    break
                    # Also check for legacy directory-based storage
                    if not demucs_found:
                        for name in hub_dir.iterdir():
                            if name.is_dir() and "demucs" in name.name.lower():
                                if any(name.iterdir()):
                                    logger.info(f"✓ Found Demucs cache: {name}")
                                    demucs_found = True
                                    break
                    if not demucs_found:
                        logger.warning("Demucs cache directory not found, but model loaded - may be in memory only")
                
            except Exception as e:
                import sys as sys_module
                exc_type, exc_value, exc_tb = sys_module.exc_info()
                tb_str = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
                logger.error(f"Error loading Demucs model: {type(e).__name__}: {e}")
                logger.error(f"Full traceback:\n{tb_str}")
                raise RuntimeError(f"Failed to load Demucs model: {e}\nTraceback:\n{tb_str}") from e
        finally:
            try:
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)
                logger.debug(f"Cleaned up temporary directory: {tmp_dir}")
            except Exception as cleanup_err:
                logger.warning(f"Failed to clean up temporary directory: {cleanup_err}")
        
        if progress_cb:
            try:
                progress_cb(1.0)
            except Exception:
                pass
    except Exception as e:
        error_msg = f"Stem split model ensure failed: {type(e).__name__}: {e}"
        logger.error(error_msg)
        logger.error("Full traceback:\n%s", traceback.format_exc())
        # Re-raise with more context
        raise RuntimeError(error_msg) from e
