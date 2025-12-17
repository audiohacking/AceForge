// C:\CandyDungeonMusicForge\static\scripts\cdmf_mode_ui.js

(function () {
  "use strict";

  window.CDMF = window.CDMF || {};
  var CDMF = window.CDMF;

  CDMF.switchMode = function (mode) {
    try {
      var cards = document.querySelectorAll(".card-mode");
      cards.forEach(function (card) {
        if (!card.dataset) return;
        var cardMode = card.dataset.mode;
        card.style.display = cardMode === mode ? "" : "none";
      });

      var buttons = document.querySelectorAll(".mode-tab-btn");
      buttons.forEach(function (btn) {
        if (!btn.dataset) return;
        var btnMode = btn.dataset.mode;
        if (btnMode === mode) {
          btn.classList.add("tab-btn-active");
        } else {
          btn.classList.remove("tab-btn-active");
        }
      });
    } catch (e) {
      if (window.console && console.error) {
        console.error("[CDMF] switchMode error", e);
      }
    }
  };
})();
