// C:\CandyDungeonMusicForge\static\scripts\cdmf_player_ui.js
(function () {
  "use strict";

  const CDMF = (window.CDMF = window.CDMF || {});

  function initPlayerUI() {
    const audio = document.getElementById("audioPlayer");
    const list = document.getElementById("trackList");
    const progress = document.getElementById("progressSlider");
    const currentTimeLabel = document.getElementById("currentTimeLabel");
    const durationLabel = document.getElementById("durationLabel");

    if (!audio || !list || !progress) {
      console.warn(
        "[Candy Dungeon Music Forge] Audio player elements missing; initPlayer aborted."
      );
      return;
    }

    window.candyAudioPlayer = audio;
    window.candyTrackList = list;

    // Default: just load the currently selected track, but do NOT auto-play.
    let initialUrl = list.value;
    if (initialUrl) {
      audio.src = initialUrl;
    }

    const btnPlay = document.getElementById("btnPlay");
    const btnStop = document.getElementById("btnStop");
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

    function setPlayButtonState() {
      if (!btnPlay) return;
      const iconSpan = btnPlay.querySelector(".icon");
      const labelSpan = btnPlay.querySelector(".label");
      const isPlaying = !audio.paused && !audio.ended;

      if (iconSpan) iconSpan.textContent = isPlaying ? "⏸" : "▶";
      if (labelSpan) labelSpan.textContent = isPlaying ? "Pause" : "Play";
    }

    function setMuteButtonState() {
      if (!btnMute) return;
      const isMuted = audio.muted || audio.volume === 0;
      if (isMuted) {
        btnMute.classList.add("mute-active");
      } else {
        btnMute.classList.remove("mute-active");
      }
    }

    audio.addEventListener("loadedmetadata", function () {
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
      if (!audio.duration) return;
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
      if (!audio.duration) return;
      audio.currentTime = parseFloat(progress.value || "0");
    });

    if (volumeSlider) {
      audio.volume = parseFloat(volumeSlider.value || "0.9");
      volumeSlider.addEventListener("input", function () {
        audio.volume = parseFloat(volumeSlider.value || "0.9");
        if (audio.volume > 0 && audio.muted) {
          audio.muted = false;
        }
        setMuteButtonState();
      });
    }

    if (btnPlay) {
      btnPlay.addEventListener("click", function () {
        // Do not allow manual playback while a generation is running.
        if (window.candyIsGenerating) {
          return;
        }

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
      });
    }

    if (btnStop) {
      btnStop.addEventListener("click", function () {
        audio.pause();
        audio.currentTime = 0;
        if (progress) progress.value = 0;
        if (currentTimeLabel) currentTimeLabel.textContent = "0:00";
        setPlayButtonState();
      });
    }

    if (btnRewind) {
      btnRewind.addEventListener("click", function () {
        const wasPaused = audio.paused;
        audio.currentTime = 0;
        if (progress) progress.value = 0;
        if (currentTimeLabel) currentTimeLabel.textContent = "0:00";
        if (!wasPaused) {
          audio.play().catch(function () {});
        }
      });
    }

    if (btnMute) {
      btnMute.addEventListener("click", function () {
        audio.muted = !audio.muted;
        setMuteButtonState();
      });
    }

    if (btnLoop) {
      btnLoop.addEventListener("click", function () {
        audio.loop = !audio.loop;
        if (audio.loop) {
          btnLoop.classList.add("loop-active");
        } else {
          btnLoop.classList.remove("loop-active");
        }
      });
    }

    if (list) {
      list.addEventListener("change", function () {
        if (!list.value) return;
        audio.pause();
        audio.currentTime = 0;
        audio.src = list.value;
        audio.play().catch(function () {});
        setPlayButtonState();
      });
    }

    setPlayButtonState();
    setMuteButtonState();
  }

  CDMF.initPlayerUI = initPlayerUI;
})();
