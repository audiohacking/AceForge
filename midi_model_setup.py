# midi_model_setup.py
# Model setup for basic-pitch MIDI generation

from __future__ import annotations

from pathlib import Path
import sys
import os
import logging
from typing import Optional, Callable

import cdmf_paths

logger = logging.getLogger(__name__)

# Hugging Face repo for basic-pitch models
BASIC_PITCH_REPO_ID = "spotify/basic-pitch"

ProgressCallback = Callable[[float], None]


def _get_bundled_model_path() -> Optional[Path]:
    """
    Get the path to basic-pitch models in a frozen app bundle.
    Returns None if not running in a frozen app or if models not found.
    """
    if not getattr(sys, "frozen", False):
        return None
    
    # In frozen apps, models are in Resources/basic_pitch/saved_models/icassp_2022/
    try:
        # PyInstaller sets sys._MEIPASS to the temp directory where bundled files are extracted
        if hasattr(sys, "_MEIPASS"):
            bundle_root = Path(sys._MEIPASS)
        else:
            # Fallback: try to find the bundle location from executable path
            if sys.executable:
                exe_path = Path(sys.executable)
                # In .app bundle: executable is in Contents/MacOS/, Resources is in Contents/Resources/
                if exe_path.parent.name == "MacOS":
                    bundle_root = exe_path.parent.parent / "Resources"
                else:
                    bundle_root = Path(sys.executable).parent
            else:
                return None
        
        bundled_models = bundle_root / "basic_pitch" / "saved_models" / "icassp_2022"
        if bundled_models.exists():
            logger.debug(f"Found bundled basic-pitch models at: {bundled_models}")
            return bundled_models
    except Exception as e:
        logger.debug(f"Could not locate bundled models: {e}")
    
    return None


def get_basic_pitch_model_root() -> Path:
    """
    Get the root folder for basic-pitch models based on user configuration.
    Models will be stored at:
      <models_folder>/basic_pitch/saved_models/icassp_2022/
    """
    models_folder = cdmf_paths.get_models_folder()
    model_root = models_folder / "basic_pitch" / "saved_models" / "icassp_2022"
    model_root.mkdir(parents=True, exist_ok=True)
    return model_root


def basic_pitch_models_present() -> bool:
    """
    Check if basic-pitch models are present (either in bundled app or user models folder).
    Looks for model files with extensions: .mlpackage (CoreML), .tflite, .onnx, or nmp (TensorFlow)
    """
    # First check bundled models (for frozen apps)
    bundled_path = _get_bundled_model_path()
    if bundled_path and bundled_path.exists():
        logger.debug(f"Checking bundled models at: {bundled_path}")
        # Check for any model file in bundled location
        model_extensions = [".mlpackage", ".tflite", ".onnx", ""]
        for ext in model_extensions:
            if ext == "":
                nmp_dir = bundled_path / "nmp"
                if nmp_dir.is_dir() and any(nmp_dir.iterdir()):
                    logger.info(f"Found bundled TensorFlow model at: {nmp_dir}")
                    return True
            else:
                model_file = bundled_path / f"nmp{ext}"
                if model_file.exists():
                    logger.info(f"Found bundled basic-pitch model at: {model_file}")
                    return True
        logger.debug(f"No model files found in bundled path: {bundled_path}")
    elif bundled_path:
        logger.debug(f"Bundled model path does not exist: {bundled_path}")
    
    # Check user models folder
    model_root = get_basic_pitch_model_root()
    logger.debug(f"Checking user models folder at: {model_root}")
    if not model_root.exists():
        logger.debug(f"User models folder does not exist: {model_root}")
        return False
    
    # Check for any model file
    model_extensions = [".mlpackage", ".tflite", ".onnx", ""]  # "" for TensorFlow "nmp" directory
    for ext in model_extensions:
        if ext == "":
            # TensorFlow model is a directory named "nmp"
            nmp_dir = model_root / "nmp"
            if nmp_dir.is_dir() and any(nmp_dir.iterdir()):
                logger.info(f"Found TensorFlow model at: {nmp_dir}")
                return True
        else:
            model_file = model_root / f"nmp{ext}"
            if model_file.exists():
                logger.info(f"Found basic-pitch model at: {model_file}")
                return True
    
    logger.debug(f"No basic-pitch models found in user folder: {model_root}")
    return False


def get_basic_pitch_model_path() -> Optional[Path]:
    """
    Get the path to the basic-pitch model, selecting the best available format.
    Priority: CoreML (macOS) > TensorFlowLite > ONNX > TensorFlow
    
    Checks bundled models first (for frozen apps), then user models folder.
    
    Returns None if no model is found.
    """
    # First check bundled models (for frozen apps)
    bundled_path = _get_bundled_model_path()
    if bundled_path and bundled_path.exists():
        # Check for CoreML (preferred on macOS)
        coreml_path = bundled_path / "nmp.mlpackage"
        if coreml_path.exists():
            return coreml_path
        
        # Check for TensorFlowLite
        tflite_path = bundled_path / "nmp.tflite"
        if tflite_path.exists():
            return tflite_path
        
        # Check for ONNX
        onnx_path = bundled_path / "nmp.onnx"
        if onnx_path.exists():
            return onnx_path
        
        # Check for TensorFlow (directory)
        tf_path = bundled_path / "nmp"
        if tf_path.is_dir() and any(tf_path.iterdir()):
            return tf_path
    
    # Check user models folder
    model_root = get_basic_pitch_model_root()
    
    # Check for CoreML (preferred on macOS)
    coreml_path = model_root / "nmp.mlpackage"
    if coreml_path.exists():
        return coreml_path
    
    # Check for TensorFlowLite
    tflite_path = model_root / "nmp.tflite"
    if tflite_path.exists():
        return tflite_path
    
    # Check for ONNX
    onnx_path = model_root / "nmp.onnx"
    if onnx_path.exists():
        return onnx_path
    
    # Check for TensorFlow (directory)
    tf_path = model_root / "nmp"
    if tf_path.is_dir() and any(tf_path.iterdir()):
        return tf_path
    
    return None


def ensure_basic_pitch_models(progress_cb: Optional[ProgressCallback] = None) -> Path:
    """
    Ensure basic-pitch models are present in the AceForge models folder.
    In frozen apps, models are bundled and don't need copying.
    In development, copies models from the installed basic-pitch package.
    
    Returns the path to the model directory.
    
    If `progress_cb` is provided, it will be called with a float in [0, 1]
    reflecting approximate copy progress.
    """
    # Check if models are already present (bundled or user folder)
    if basic_pitch_models_present():
        if progress_cb is not None:
            try:
                progress_cb(1.0)
            except Exception:
                pass
        # Return the path where models are found
        bundled_path = _get_bundled_model_path()
        if bundled_path and bundled_path.exists():
            return bundled_path
        return get_basic_pitch_model_root()
    
    # In frozen apps, if bundled models aren't found, that's an error
    if getattr(sys, "frozen", False):
        raise FileNotFoundError(
            "basic-pitch models not found in bundled app. "
            "This should not happen - models should be included during build."
        )
    
    model_root = get_basic_pitch_model_root()
    
    logger.info("basic-pitch models not found at:")
    logger.info(f"  {model_root}")
    logger.info("Copying models from installed basic-pitch package...")
    
    try:
        # Get the model path from the installed basic-pitch package
        try:
            from basic_pitch import ICASSP_2022_MODEL_PATH
            source_model_path = Path(ICASSP_2022_MODEL_PATH)
        except ImportError:
            raise ImportError("basic-pitch package not installed")
        except Exception as e:
            # Try to find the package location manually
            import basic_pitch
            import os
            package_dir = Path(basic_pitch.__file__).parent
            source_model_path = package_dir / "saved_models" / "icassp_2022"
            if not source_model_path.exists():
                raise FileNotFoundError(f"Could not find basic-pitch models in package: {e}")
        
        if progress_cb is not None:
            try:
                progress_cb(0.1)  # Start
            except Exception:
                pass
        
        # Check if source exists
        if not source_model_path.exists():
            raise FileNotFoundError(
                f"basic-pitch model not found at: {source_model_path}. "
                "Make sure basic-pitch is properly installed."
            )
        
        import shutil
        
        # If source is a file (e.g., .mlpackage, .tflite, .onnx), copy it
        if source_model_path.is_file():
            dest_file = model_root / source_model_path.name
            logger.info(f"Copying model file: {source_model_path.name}")
            shutil.copy2(source_model_path, dest_file)
            if progress_cb is not None:
                try:
                    progress_cb(1.0)
                except Exception:
                    pass
        elif source_model_path.is_dir():
            # Source is a directory (TensorFlow model "nmp" directory)
            # Copy all contents
            logger.info(f"Copying model directory: {source_model_path}")
            dest_dir = model_root / source_model_path.name
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            shutil.copytree(source_model_path, dest_dir)
            if progress_cb is not None:
                try:
                    progress_cb(1.0)
                except Exception:
                    pass
        else:
            # Check if parent directory contains model files
            parent_dir = source_model_path.parent
            if parent_dir.exists():
                # Copy all model files from parent directory
                model_files = []
                for ext in [".mlpackage", ".tflite", ".onnx"]:
                    model_file = parent_dir / f"nmp{ext}"
                    if model_file.exists():
                        model_files.append(model_file)
                
                # Also check for "nmp" directory (TensorFlow)
                nmp_dir = parent_dir / "nmp"
                if nmp_dir.is_dir():
                    model_files.append(nmp_dir)
                
                if not model_files:
                    raise FileNotFoundError(
                        f"No model files found in: {parent_dir}. "
                        "Make sure basic-pitch is properly installed."
                    )
                
                total_files = len(model_files)
                for idx, model_item in enumerate(model_files):
                    dest = model_root / model_item.name
                    logger.info(f"Copying model: {model_item.name}")
                    if model_item.is_dir():
                        if dest.exists():
                            shutil.rmtree(dest)
                        shutil.copytree(model_item, dest)
                    else:
                        shutil.copy2(model_item, dest)
                    
                    if progress_cb is not None:
                        try:
                            # Progress: 0.1 (start) + 0.9 * (files copied / total)
                            progress = 0.1 + 0.9 * ((idx + 1) / total_files)
                            progress_cb(progress)
                        except Exception:
                            pass
            else:
                raise FileNotFoundError(
                    f"Model directory not found: {source_model_path}. "
                    "Make sure basic-pitch is properly installed."
                )
        
        logger.info("basic-pitch models copied successfully")
        return model_root
        
    except Exception as exc:
        logger.error(f"Failed to copy basic-pitch models: {exc}")
        logger.error("Make sure basic-pitch is installed: pip install basic-pitch")
        logger.error("If models are already present, place them here:")
        logger.error(f"  {model_root}")
        raise


if __name__ == "__main__":
    # Allow manual execution for testing
    try:
        path = ensure_basic_pitch_models()
        model_path = get_basic_pitch_model_path()
        if model_path:
            print(f"[basic-pitch] Model ready at: {model_path}")
        else:
            print(f"[basic-pitch] Models directory ready at: {path}")
            print("[basic-pitch] But no model file found. Check the directory.")
    except Exception as e:
        print(f"[basic-pitch] Error: {e}")
        sys.exit(1)
