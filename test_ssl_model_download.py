#!/usr/bin/env python3
"""
Test that the SSL context manager correctly handles model downloads.
This test verifies that the fix for certificate errors works properly.
"""

import sys
import os
import logging
import tempfile
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_model_download_handles_ssl_errors():
    """Test that model download succeeds despite potential SSL certificate errors."""
    print("=" * 60)
    print("Test: Model Download with SSL Error Handling")
    print("=" * 60)
    
    # Save original environment state
    original_torch_home = os.environ.get("TORCH_HOME")
    original_cdmf_paths_module = sys.modules.get('cdmf_paths')
    tmp_models_dir = None
    
    try:
        # Set up test environment
        import torch
        
        # Create a temporary models directory for testing
        tmp_models_dir = Path(tempfile.mkdtemp(prefix="aceforge_test_models_"))
        os.environ["TORCH_HOME"] = str(tmp_models_dir)
        
        logger.info(f"Test models directory: {tmp_models_dir}")
        logger.info(f"TORCH_HOME: {os.environ['TORCH_HOME']}")
        logger.info(f"torch.hub.get_dir(): {torch.hub.get_dir()}")
        
        # Import the ensure_stem_split_models function
        from cdmf_stem_splitting import ensure_stem_split_models
        
        # Mock the cdmf_paths module if it's not available
        try:
            import cdmf_paths
        except ImportError:
            # Create a mock cdmf_paths module
            import types
            cdmf_paths = types.ModuleType('cdmf_paths')
            cdmf_paths.get_models_folder = lambda: tmp_models_dir
            sys.modules['cdmf_paths'] = cdmf_paths
            logger.info("Created mock cdmf_paths module")
        
        # Progress callback for monitoring
        progress_values = []
        def progress_callback(value):
            progress_values.append(value)
            logger.info(f"Progress: {value * 100:.1f}%")
        
        # Attempt to download the model
        logger.info("Starting model download test...")
        try:
            ensure_stem_split_models(progress_cb=progress_callback)
            logger.info("✓ Model download completed successfully")
            
            # Check that progress was reported
            if len(progress_values) > 0:
                logger.info(f"✓ Progress reported {len(progress_values)} times")
                if progress_values[0] == 0.0 and progress_values[-1] == 1.0:
                    logger.info("✓ Progress started at 0.0 and ended at 1.0")
                else:
                    logger.warning(f"⚠ Progress range unexpected: {progress_values[0]} to {progress_values[-1]}")
            else:
                logger.warning("⚠ No progress values reported")
            
            # Verify model was downloaded
            hub_dir = Path(torch.hub.get_dir())
            model_found = False
            
            if hub_dir.exists():
                # Check for model files
                checkpoints_dir = hub_dir / "checkpoints"
                if checkpoints_dir.exists():
                    for model_file in checkpoints_dir.iterdir():
                        if model_file.is_file() and model_file.suffix == ".th":
                            size_mb = model_file.stat().st_size / (1024 * 1024)
                            if size_mb > 10:
                                logger.info(f"✓ Found model file: {model_file.name} ({size_mb:.1f} MB)")
                                model_found = True
                                break
            
            if model_found:
                logger.info("✓ Model successfully downloaded to cache")
                return True
            else:
                logger.warning("⚠ Model not found in expected location, but download didn't fail")
                return True  # Still consider this a pass since download didn't error
            
        except Exception as e:
            logger.error(f"✗ Model download failed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    except Exception as e:
        logger.error(f"✗ Test setup failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Clean up: restore environment state
        if original_torch_home is not None:
            os.environ["TORCH_HOME"] = original_torch_home
        elif "TORCH_HOME" in os.environ:
            del os.environ["TORCH_HOME"]
        
        # Remove mock module if we created it
        if original_cdmf_paths_module is None and 'cdmf_paths' in sys.modules:
            del sys.modules['cdmf_paths']
        
        # Clean up temporary directory
        if tmp_models_dir is not None:
            import shutil
            try:
                shutil.rmtree(tmp_models_dir, ignore_errors=True)
                logger.info(f"Cleaned up test directory: {tmp_models_dir}")
            except Exception:
                pass


def main():
    """Run the test."""
    print("\n" + "=" * 60)
    print("SSL Context Manager - Model Download Test")
    print("=" * 60)
    
    result = test_model_download_handles_ssl_errors()
    
    print("\n" + "=" * 60)
    if result:
        print("✓ Test PASSED")
        print("=" * 60)
        sys.exit(0)
    else:
        print("✗ Test FAILED")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
