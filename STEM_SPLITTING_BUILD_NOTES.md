# Stem Splitting Feature - Build & Test Notes

## Summary
Stem splitting feature has been implemented and tested standalone. Ready for AceForge build integration.

## Files Added/Modified

### New Files:
- `cdmf_stem_splitting.py` - Core stem splitting logic using Demucs
- `cdmf_stem_splitting_bp.py` - Flask blueprint for stem splitting routes
- `static/scripts/cdmf_stem_splitting_ui.js` - Frontend UI logic
- `test_stem_splitting_simple.sh` - Integration test script
- `test_stem_splitting_standalone.py` - Standalone Demucs test
- `audiotest.mp3` - Test audio file (460KB)
- `.github/workflows/test-stem-splitting.yml` - CI workflow

### Modified Files:
- `cdmf_template.py` - Added Stem Splitting tab and form
- `music_forge_ui.py` - Registered stem splitting blueprint
- `cdmf_state.py` - Added STEM_SPLIT_STATUS
- `cdmf_models.py` - Added `/models/stem_split/status` and `/ensure` routes
- `cdmf_presets_ui.js` - Added "copy settings" support for stem split tracks
- `requirements_ace_macos.txt` - Added `demucs==4.0.1`
- `CDMF.spec` - Added Demucs to hiddenimports and data collection
- `build_local.sh` - Added Demucs installation step

## Standalone Test Results ✓
- ✓ Demucs imports successfully
- ✓ Device selection works (MPS/CPU)
- ✓ Model check works
- ✓ 2-stem separation successful (vocals/instrumental)
- ✓ Files created with proper naming: `audiotest_stems_vocals.wav`, `audiotest_stems_instrumental.wav`
- ✓ Files saved to DEFAULT_OUT_DIR: `~/Library/Application Support/AceForge/generated/`
- ✓ Metadata saved correctly
- ✓ Files appear in Music Player

## Build Instructions

1. **Build the app:**
   ```bash
   ./build_local.sh
   ```

2. **Verify Demucs is included:**
   The build script will install Demucs and verify it imports correctly.

3. **Test the built app:**
   ```bash
   ./test_stem_splitting_simple.sh audiotest.mp3
   ```

## Manual Testing Checklist

1. **Launch AceForge.app**
2. **Navigate to Stem Splitting tab**
3. **Check model status:**
   - Should show "Demucs model is not downloaded yet" notice
   - "Download Demucs models" button should be visible
4. **Download models:**
   - Click "Download Demucs models"
   - Wait for download to complete (progress bar should show)
   - Notice should disappear, "Split Stems" button should be enabled
5. **Test stem splitting:**
   - Upload `audiotest.mp3` (or any audio file)
   - Select 2-stem mode
   - Click "Split Stems"
   - Wait for processing (progress bar should update)
   - Verify files appear in Music Player:
     - `audiotest_stems_vocals.wav`
     - `audiotest_stems_instrumental.wav`
6. **Verify file locations:**
   - Files should be in: `~/Library/Application Support/AceForge/generated/`
   - Not in subdirectories (directly in generated/)
7. **Test "Copy Settings" button:**
   - Click ⧉ button on a stem track in Music Player
   - Should switch to Stem Splitting tab
   - Form should be populated with settings

## Expected Behavior

- **First use:** User sees "Download Demucs models" notice and button
- **After download:** Notice disappears, "Split Stems" enabled
- **During split:** Progress bar shows real-time progress
- **After split:** Files appear in Music Player with `_stems_` naming
- **File location:** All stems in DEFAULT_OUT_DIR (not subdirectories)
- **Naming:** `{input_basename}_stems_{stem_name}.wav`

## Known Issues / Notes

- Demucs models download on first use (~80MB for htdemucs)
- Processing time depends on file length and device (MPS faster than CPU)
- Temporary Demucs structure is cleaned up automatically
- Model check may show "absent" until first successful download
