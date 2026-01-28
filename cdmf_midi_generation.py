# cdmf_midi_generation.py
# MIDI generation module using basic-pitch
#
# Requirements:
#   pip install basic-pitch
#
# Notes:
# - basic-pitch supports Python 3.7-3.11 (Mac M1 only supports 3.10)
# - Default runtime: CoreML on macOS, TensorFlowLite on Linux, ONNX on Windows
# - Audio is automatically downmixed to mono and resampled to 22050 Hz
# - Supports: .mp3, .ogg, .wav, .flac, .m4a

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class MIDIGenerator:
    """
    MIDI generation using basic-pitch (Spotify's audio-to-MIDI converter).
    """
    
    def __init__(self):
        """Initialize the MIDI generator."""
        self._initialized = False
        self._model = None
        self._model_path = None
        
    def _get_model_path(self):
        """
        Get the path to the basic-pitch model in AceForge models folder.
        Overrides the default ICASSP_2022_MODEL_PATH.
        """
        try:
            from midi_model_setup import get_basic_pitch_model_path
            model_path = get_basic_pitch_model_path()
            if model_path and model_path.exists():
                return model_path
        except Exception as e:
            logger.debug(f"Could not get custom model path: {e}")
        
        # Fallback: try to use basic-pitch's default, but it may not work in frozen apps
        try:
            from basic_pitch import ICASSP_2022_MODEL_PATH
            if ICASSP_2022_MODEL_PATH.exists():
                return ICASSP_2022_MODEL_PATH
        except Exception:
            pass
        
        return None
        
    def _initialize(self):
        """Lazy initialization of the basic-pitch model."""
        if self._initialized:
            return
        
        try:
            from basic_pitch.inference import Model
            
            # Get model path from AceForge models folder
            model_path = self._get_model_path()
            if not model_path:
                raise FileNotFoundError(
                    "basic-pitch model not found. Please download it using the 'Download Models' button."
                )
            
            if not model_path.exists():
                raise FileNotFoundError(
                    f"basic-pitch model file not found at: {model_path}. "
                    "Please download it using the 'Download Models' button."
                )
            
            logger.info(f"Loading basic-pitch model from: {model_path}")
            self._model = Model(str(model_path))
            self._model_path = model_path
            self._initialized = True
            logger.info("basic-pitch model loaded successfully.")
        except ImportError as e:
            raise ImportError(
                "basic-pitch library not installed. Install with: pip install basic-pitch. (Original: %s)" % e
            ) from e
        except Exception as e:
            logger.error(f"Failed to load basic-pitch model: {e}")
            raise
    
    def generate_midi(
        self,
        audio_path: str,
        output_path: str,
        onset_threshold: float = 0.5,
        frame_threshold: float = 0.3,
        minimum_note_length_ms: float = 127.7,
        minimum_frequency: Optional[float] = None,
        maximum_frequency: Optional[float] = None,
        multiple_pitch_bends: bool = False,
        melodia_trick: bool = True,
        midi_tempo: float = 120.0,
    ) -> str:
        """
        Generate MIDI from audio file using basic-pitch.
        
        Args:
            audio_path: Path to input audio file (mp3, wav, flac, m4a, ogg)
            output_path: Path to output MIDI file (.mid)
            onset_threshold: Minimum energy required for an onset (0.0-1.0, default 0.5)
            frame_threshold: Minimum energy requirement for a frame (0.0-1.0, default 0.3)
            minimum_note_length_ms: Minimum allowed note length in milliseconds (default 127.7)
            minimum_frequency: Minimum allowed output frequency in Hz (None = no limit)
            maximum_frequency: Maximum allowed output frequency in Hz (None = no limit)
            multiple_pitch_bends: Allow overlapping notes to have pitch bends (default False)
            melodia_trick: Use melodia post-processing step (default True)
            midi_tempo: MIDI tempo in BPM (default 120.0)
            
        Returns:
            Path to generated MIDI file
        """
        # Initialize model if needed
        self._initialize()
        
        # Validate input file exists
        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        # Validate output path
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Ensure output has .mid extension
        if output_file.suffix.lower() != ".mid":
            output_file = output_file.with_suffix(".mid")
        
        logger.info(f"Generating MIDI from {audio_file.name}...")
        
        try:
            from basic_pitch.inference import predict
            
            # Run prediction
            model_output, midi_data, note_events = predict(
                audio_path=str(audio_file),
                model_or_model_path=self._model,
                onset_threshold=onset_threshold,
                frame_threshold=frame_threshold,
                minimum_note_length=minimum_note_length_ms,
                minimum_frequency=minimum_frequency,
                maximum_frequency=maximum_frequency,
                multiple_pitch_bends=multiple_pitch_bends,
                melodia_trick=melodia_trick,
                midi_tempo=midi_tempo,
            )
            
            # Save MIDI file
            midi_data.write(str(output_file))
            
            logger.info(f"MIDI generation completed: {output_file}")
            return str(output_file)
            
        except Exception as e:
            logger.error(f"MIDI generation failed: {e}")
            raise


# Global singleton instance
_midi_generator: Optional[MIDIGenerator] = None


def get_midi_generator() -> MIDIGenerator:
    """Get or create the global MIDI generator instance."""
    global _midi_generator
    if _midi_generator is None:
        _midi_generator = MIDIGenerator()
    return _midi_generator
