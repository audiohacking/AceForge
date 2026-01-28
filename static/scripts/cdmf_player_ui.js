// C:\CandyDungeonMusicForge\static\scripts\cdmf_player_ui.js
(function () {
  "use strict";

  const CDMF = (window.CDMF = window.CDMF || {});
  
  // MIDI playback state (module-scoped so it can be accessed from outside)
  let currentMidiUrl = null;
  let isMidiPlaying = false;
  let isMidiTrack = false;
  let btnPlay = null;
  let btnStop = null;

  function isMidiFile(url) {
    if (!url) return false;
    return url.toLowerCase().endsWith('.mid') || url.toLowerCase().endsWith('.midi');
  }
  
  function setPlayButtonState() {
    if (!btnPlay) return;
    const iconSpan = btnPlay.querySelector(".icon");
    const labelSpan = btnPlay.querySelector(".label");
    
    let isPlaying;
    if (isMidiTrack) {
      isPlaying = isMidiPlaying;
    } else {
      const audio = document.getElementById("audioPlayer");
      isPlaying = audio && !audio.paused && !audio.ended;
    }

    if (iconSpan) iconSpan.textContent = isPlaying ? "⏸" : "▶";
    if (labelSpan) labelSpan.textContent = isPlaying ? "Pause" : "Play";
  }

  function initPlayerUI() {
    const audio = document.getElementById("audioPlayer");
    const list = document.getElementById("trackList");
    const progress = document.getElementById("progressSlider");
    const currentTimeLabel = document.getElementById("currentTimeLabel");
    const durationLabel = document.getElementById("durationLabel");

    if (!audio || !list || !progress) {
      console.warn(
        "[Ace Forge] Audio player elements missing; initPlayer aborted."
      );
      return;
    }

    window.candyAudioPlayer = audio;
    window.candyTrackList = list;

    // Default: just load the currently selected track, but do NOT auto-play.
    let initialUrl = list.value;
    if (initialUrl) {
      isMidiTrack = isMidiFile(initialUrl);
      if (!isMidiTrack) {
        audio.src = initialUrl;
      }
    }

    btnPlay = document.getElementById("btnPlay");
    btnStop = document.getElementById("btnStop");
    const btnRewind = document.getElementById("btnRewind");
    const btnLoop = document.getElementById("btnLoop");
    const btnMute = document.getElementById("btnMute");
    const volumeSlider = document.getElementById("volumeSlider");

    function formatTime(sec) {
      if (!isFinite(sec)) return "0:00";
      const s = Math.floor(sec % 60);
      const m = Math.floor(sec / 60);
      return m + ":" + (s < 10 ? "0" + s : s);
    }

    function setMuteButtonState() {
      if (!btnMute) return;
      // MIDIjs doesn't support mute, so only show mute state for audio files
      if (isMidiTrack) {
        btnMute.classList.remove("mute-active");
        return;
      }
      const isMuted = audio.muted || audio.volume === 0;
      if (isMuted) {
        btnMute.classList.add("mute-active");
      } else {
        btnMute.classList.remove("mute-active");
      }
    }

    function updateMidiUI() {
      // For MIDI files, disable progress slider and time display
      // MIDIjs doesn't provide time tracking
      if (isMidiTrack) {
        if (progress) {
          progress.disabled = true;
          progress.value = 0;
        }
        if (currentTimeLabel) {
          currentTimeLabel.textContent = "--:--";
        }
        if (durationLabel) {
          durationLabel.textContent = "--:--";
        }
        if (btnRewind) {
          btnRewind.disabled = true;
        }
        if (btnLoop) {
          btnLoop.disabled = true;
        }
      } else {
        if (progress) {
          progress.disabled = false;
        }
        if (btnRewind) {
          btnRewind.disabled = false;
        }
        if (btnLoop) {
          btnLoop.disabled = false;
        }
      }
    }

    // Audio event listeners (only for non-MIDI files)
    audio.addEventListener("loadedmetadata", function () {
      if (isMidiTrack) return;
      progress.max = audio.duration || 0;
      progress.value = 0;
      if (durationLabel) {
        durationLabel.textContent = formatTime(audio.duration || 0);
      }
      if (currentTimeLabel) {
        currentTimeLabel.textContent = "0:00";
      }
      setPlayButtonState();
    });

    audio.addEventListener("timeupdate", function () {
      if (isMidiTrack || !audio.duration) return;
      progress.value = audio.currentTime;
      if (currentTimeLabel) {
        currentTimeLabel.textContent = formatTime(audio.currentTime);
      }
    });

    audio.addEventListener("play", setPlayButtonState);
    audio.addEventListener("playing", setPlayButtonState);
    audio.addEventListener("pause", setPlayButtonState);
    audio.addEventListener("ended", function () {
      setPlayButtonState();
    });

    progress.addEventListener("input", function () {
      if (isMidiTrack || !audio.duration) return;
      audio.currentTime = parseFloat(progress.value || "0");
    });

    if (volumeSlider) {
      audio.volume = parseFloat(volumeSlider.value || "0.9");
      volumeSlider.addEventListener("input", function () {
        if (isMidiTrack) return; // MIDIjs doesn't support volume control
        audio.volume = parseFloat(volumeSlider.value || "0.9");
        if (audio.volume > 0 && audio.muted) {
          audio.muted = false;
        }
        setMuteButtonState();
      });
    }

    // Play button handler (works for both audio and MIDI)
    if (btnPlay) {
      btnPlay.addEventListener("click", function () {
        // Do not allow manual playback while a generation is running.
        if (window.candyIsGenerating) {
          return;
        }

        if (isMidiTrack) {
          // MIDI playback
          if (isMidiPlaying) {
            // Stop MIDI playback (MIDIjs doesn't support pause)
            if (window.MIDIjs && typeof window.MIDIjs.stop === 'function') {
              window.MIDIjs.stop();
            }
            isMidiPlaying = false;
            currentMidiUrl = null;
          } else {
            // Start MIDI playback
            const midiUrl = list.value;
            if (midiUrl && window.MIDIjs && typeof window.MIDIjs.play === 'function') {
              window.MIDIjs.play(midiUrl);
              isMidiPlaying = true;
              currentMidiUrl = midiUrl;
            }
          }
          setPlayButtonState();
        } else {
          // Audio playback
          if (!audio.src && list.value) {
            audio.src = list.value;
          }
          if (
            audio.paused ||
            audio.ended ||
            audio.currentTime === 0
          ) {
            audio.play().catch(function () {});
          } else {
            audio.pause();
          }
          setPlayButtonState();
        }
      });
    }

    // Stop button handler (works for both audio and MIDI)
    if (btnStop) {
      btnStop.addEventListener("click", function () {
        if (isMidiTrack) {
          // Stop MIDI playback
          if (window.MIDIjs && typeof window.MIDIjs.stop === 'function') {
            window.MIDIjs.stop();
          }
          isMidiPlaying = false;
          currentMidiUrl = null;
          setPlayButtonState();
        } else {
          // Stop audio playback
          audio.pause();
          audio.currentTime = 0;
          if (progress) progress.value = 0;
          if (currentTimeLabel) currentTimeLabel.textContent = "0:00";
          setPlayButtonState();
        }
      });
    }

    // Rewind button handler (only for audio files)
    if (btnRewind) {
      btnRewind.addEventListener("click", function () {
        if (isMidiTrack) return; // MIDIjs doesn't support seeking
        
        const wasPaused = audio.paused;
        audio.currentTime = 0;
        if (progress) progress.value = 0;
        if (currentTimeLabel) currentTimeLabel.textContent = "0:00";
        if (!wasPaused) {
          audio.play().catch(function () {});
        }
      });
    }

    // Mute button handler (only for audio files)
    if (btnMute) {
      btnMute.addEventListener("click", function () {
        if (isMidiTrack) return; // MIDIjs doesn't support mute
        audio.muted = !audio.muted;
        setMuteButtonState();
      });
    }

    // Loop button handler (only for audio files)
    if (btnLoop) {
      btnLoop.addEventListener("click", function () {
        if (isMidiTrack) return; // MIDIjs doesn't support loop
        audio.loop = !audio.loop;
        if (audio.loop) {
          btnLoop.classList.add("loop-active");
        } else {
          btnLoop.classList.remove("loop-active");
        }
      });
    }

    // Track list change handler
    if (list) {
      list.addEventListener("change", function () {
        if (!list.value) return;
        
        // Stop current playback
        if (isMidiTrack && isMidiPlaying) {
          CDMF.stopMidiPlayback();
        } else if (!isMidiTrack) {
          audio.pause();
          audio.currentTime = 0;
        }
        
        // Check if new track is MIDI
        const newIsMidi = isMidiFile(list.value);
        isMidiTrack = newIsMidi;
        
        if (isMidiTrack) {
          // For MIDI files, update UI state but don't auto-play
          updateMidiUI();
          setPlayButtonState();
        } else {
          // For audio files, load and play
          audio.src = list.value;
          audio.play().catch(function () {});
          setPlayButtonState();
        }
      });
    }

    // Initialize UI state
    updateMidiUI();
    setPlayButtonState();
    setMuteButtonState();
  }

  CDMF.initPlayerUI = initPlayerUI;
  
  // Helper function to check if MIDI is currently playing
  CDMF.isMidiPlaying = function() {
    return isMidiPlaying;
  };
  
  // Helper function to stop MIDI playback (called from other modules if needed)
  CDMF.stopMidiPlayback = function() {
    if (isMidiPlaying && window.MIDIjs && typeof window.MIDIjs.stop === 'function') {
      window.MIDIjs.stop();
      isMidiPlaying = false;
      currentMidiUrl = null;
      setPlayButtonState();
    }
  };
  
  // Helper function to start MIDI playback (called from other modules)
  CDMF.startMidiPlayback = function(url) {
    if (!url) return;
    
    // Stop any current playback
    if (isMidiPlaying && currentMidiUrl !== url) {
      CDMF.stopMidiPlayback();
    }
    
    // Update track state
    isMidiTrack = isMidiFile(url);
    currentMidiUrl = url;
    
    if (isMidiTrack && window.MIDIjs && typeof window.MIDIjs.play === 'function') {
      window.MIDIjs.play(url);
      isMidiPlaying = true;
      setPlayButtonState();
    }
  };
  
  // Expose setPlayButtonState so it can be called from outside
  CDMF.setPlayButtonState = setPlayButtonState;
})();
