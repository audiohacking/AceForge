#!/usr/bin/env python3
"""
Standalone test for Demucs stem splitting functionality.
Tests Demucs directly without Flask/AceForge integration.
"""

import sys
import os
from pathlib import Path

def test_demucs_import():
    """Test that Demucs can be imported."""
    print("=" * 60)
    print("Test 1: Demucs Import")
    print("=" * 60)
    try:
        import demucs
        print("✓ Demucs imported successfully")
        try:
            import demucs.separate
            print("✓ demucs.separate module imported")
        except ImportError as e:
            print(f"✗ Failed to import demucs.separate: {e}")
            return False
        return True
    except ImportError as e:
        print(f"✗ Demucs not installed: {e}")
        print("\nInstall with: pip install demucs")
        return False

def test_demucs_model_check():
    """Test checking if Demucs models are present."""
    print("\n" + "=" * 60)
    print("Test 2: Demucs Model Check")
    print("=" * 60)
    try:
        import torch
        hub_dir = Path(torch.hub.get_dir())
        print(f"Torch hub directory: {hub_dir}")
        
        if not hub_dir.exists():
            print("⚠ Torch hub directory does not exist yet (will be created on first model download)")
            return True  # Not a failure - directory will be created when needed
        
        demucs_found = False
        for name in hub_dir.iterdir():
            if name.is_dir() and "demucs" in name.name.lower():
                print(f"✓ Found Demucs cache: {name.name}")
                if any(name.iterdir()):
                    print(f"  Directory has content")
                    demucs_found = True
                else:
                    print(f"  Directory is empty")
        
        if not demucs_found:
            print("⚠ No Demucs models found in torch.hub cache")
            print("  Models will be downloaded on first use")
        return True
    except Exception as e:
        print(f"✗ Error checking models: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_demucs_separation(input_file: str):
    """Test actual stem separation with Demucs."""
    print("\n" + "=" * 60)
    print("Test 3: Demucs Stem Separation")
    print("=" * 60)
    
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"✗ Input file not found: {input_file}")
        return False
    
    print(f"Input file: {input_path.name} ({input_path.stat().st_size:,} bytes)")
    
    # Create temporary output directory
    import tempfile
    temp_dir = Path(tempfile.mkdtemp(prefix="demucs_test_"))
    print(f"Output directory: {temp_dir}")
    
    try:
        import demucs.separate
        
        # Test 2-stem separation (simplest)
        print("\nRunning 2-stem separation (vocals/instrumental)...")
        print("This will download the model on first run (may take a few minutes)...")
        
        import sys
        old_argv = sys.argv[:]
        try:
            sys.argv = ["demucs", "-n", "htdemucs", "--two-stems=vocals", "-o", str(temp_dir), str(input_path)]
            demucs.separate.main()
        except SystemExit:
            pass
        finally:
            sys.argv = old_argv
        
        # Check for output files
        model_dir = temp_dir / "htdemucs" / input_path.stem
        if not model_dir.exists():
            print(f"✗ Output directory not found: {model_dir}")
            return False
        
        print(f"✓ Output directory found: {model_dir}")
        
        # Check for stem files
        vocals_file = model_dir / "vocals.wav"
        no_vocals_file = model_dir / "no_vocals.wav"
        
        found_files = []
        if vocals_file.exists():
            size = vocals_file.stat().st_size
            print(f"✓ vocals.wav found ({size:,} bytes)")
            found_files.append("vocals")
        else:
            print("✗ vocals.wav not found")
        
        if no_vocals_file.exists():
            size = no_vocals_file.stat().st_size
            print(f"✓ no_vocals.wav found ({size:,} bytes)")
            found_files.append("instrumental")
        else:
            print("✗ no_vocals.wav not found")
        
        if len(found_files) == 2:
            print("\n✓ 2-stem separation successful!")
            return True
        else:
            print(f"\n✗ Only found {len(found_files)}/{2} expected stems")
            return False
            
    except Exception as e:
        print(f"\n✗ Separation failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up
        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"\nCleaned up temporary directory: {temp_dir}")
        except Exception:
            pass

def test_device_selection():
    """Test device selection (MPS/CPU)."""
    print("\n" + "=" * 60)
    print("Test 4: Device Selection")
    print("=" * 60)
    try:
        import torch
        print(f"PyTorch version: {torch.__version__}")
        
        if torch.cuda.is_available():
            print(f"✓ CUDA available: {torch.cuda.device_count()} device(s)")
        else:
            print("  CUDA not available")
        
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            print("✓ MPS (Metal) available on Apple Silicon")
            device = torch.device("mps")
            print(f"  Selected device: {device}")
        else:
            print("  MPS not available")
            device = torch.device("cpu")
            print(f"  Selected device: {device}")
        
        return True
    except Exception as e:
        print(f"✗ Error checking devices: {e}")
        return False

def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("Demucs Standalone Test")
    print("=" * 60)
    
    # Check for input file
    input_file = "audiotest.mp3"
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    
    if not Path(input_file).exists():
        print(f"\n✗ Input file not found: {input_file}")
        print("\nUsage: python3 test_stem_splitting_standalone.py [audio_file]")
        print("Default: audiotest.mp3")
        sys.exit(1)
    
    results = []
    
    # Test 1: Import
    results.append(("Import", test_demucs_import()))
    if not results[-1][1]:
        print("\n✗ Cannot continue without Demucs. Install with: pip install demucs")
        sys.exit(1)
    
    # Test 2: Device selection
    results.append(("Device Selection", test_device_selection()))
    
    # Test 3: Model check
    results.append(("Model Check", test_demucs_model_check()))
    
    # Test 4: Actual separation
    results.append(("Stem Separation", test_demucs_separation(input_file)))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(r[1] for r in results)
    if all_passed:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
