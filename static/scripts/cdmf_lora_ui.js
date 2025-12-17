// C:\CandyDungeonMusicForge\static\scripts\cdmf_lora_ui.js

(function () {
  "use strict";

  window.CDMF = window.CDMF || {};

  (function initLoraUI() {
    try {
      var select = document.getElementById("lora_select");
      var input   = document.getElementById("lora_name_or_path");
      var btnApply = document.getElementById("btnApplyLora");
      var btnClear = document.getElementById("btnClearLora");

      // Folder browse controls
      var btnBrowse = document.getElementById("btnLoraBrowse");
      var folderPicker = document.getElementById("lora_folder_picker");

      if (!input) return;

      //
      // INSTALLED LORAS DROPDOWN
      //
      if (select && btnApply) {
        btnApply.addEventListener("click", function () {
          // The dropdown must contain folder paths already.
          input.value = select.value || "";
        });
      }

      if (btnClear) {
        btnClear.addEventListener("click", function () {
          if (select) select.value = "";
          input.value = "";
        });
      }

      //
      // FOLDER BROWSE (webkitdirectory)
      //
      if (btnBrowse && folderPicker) {
        btnBrowse.addEventListener("click", function () {
          folderPicker.click();
        });

        folderPicker.addEventListener("change", function () {
          if (!folderPicker.files || folderPicker.files.length === 0) return;

          // With webkitdirectory, each file includes its relative path under the folder.
          // Extract the folder root path from the first file.
          var first = folderPicker.files[0];
          var fullPath = first.webkitRelativePath || first.relativePath;

          if (fullPath) {
            // Strip off everything after the first folder name
            // Example fullPath: "chiptunes_v1/pytorch_lora_weights.safetensors"
            var topFolder = fullPath.split("/")[0];
            input.value = topFolder;
          }
        });
      }

    } catch (e) {
      if (window.console && console.error) {
        console.error("[CDMF] initLoraUI error", e);
      }
    }
  })();
})();
