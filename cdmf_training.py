# C:\AceForge\cdmf_training.py

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, Dict, Any

import subprocess
import shutil
import time
import signal
import psutil

from flask import Blueprint, jsonify, request

from ace_model_setup import ace_models_present
from cdmf_paths import (
    APP_DIR,
    TRAINING_DATA_ROOT,
    ACE_TRAINER_MODEL_ROOT,
    TRAINING_CONFIG_ROOT,
    DEFAULT_LORA_CONFIG,
    CUSTOM_LORA_ROOT,
)
import cdmf_state


def _ensure_hf_text2music_dataset(raw_dir: Path) -> Path:
    """
    Given a raw CDMF training folder containing .wav/.mp3 plus *_prompt.txt and
    *_lyrics.txt sidecars, build (or reuse) a HuggingFace `datasets` directory
    that ACE-Step's Text2MusicDataset(load_from_disk=...) can consume.

    We save the HF dataset under:
        raw_dir / "_hf_text2music"

    The raw audio + .txt files are left untouched.
    """
    try:
        # Imported lazily so we don't explode at module import time
        from datasets import Dataset  # type: ignore[import]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "The 'datasets' Python package is required to build ACE-Step training "
            "datasets, but it could not be imported. Make sure it is installed "
            "into the same environment that runs music_forge_ui.py / CDMF."
        ) from exc

    hf_root = raw_dir / "_hf_text2music"
    info_json = hf_root / "dataset_info.json"

    # If we've already built a dataset here, just reuse it.
    if info_json.exists():
        print(f"[CDMF] Using existing ACE-Step HF dataset at {hf_root}", flush=True)
        return hf_root

    import re  # local import to avoid top-level clutter

    audio_files = sorted(
        [
            p
            for p in raw_dir.iterdir()
            if p.is_file() and p.suffix.lower() in (".wav", ".mp3")
        ],
        key=lambda p: p.name.lower(),
    )

    if not audio_files:
        raise RuntimeError(
            f"No .wav or .mp3 files found in dataset folder: {raw_dir}"
        )

    records: list[Dict[str, Any]] = []
    skipped = 0

    for audio_path in audio_files:
        stem = audio_path.stem
        prompt_path = raw_dir / f"{stem}_prompt.txt"
        lyrics_path = raw_dir / f"{stem}_lyrics.txt"

        if not prompt_path.exists() or not lyrics_path.exists():
            print(
                f"[CDMF] Skipping {audio_path.name}: missing "
                f"{'prompt' if not prompt_path.exists() else 'lyrics'} file.",
                flush=True,
            )
            skipped += 1
            continue

        try:
            prompt_text = prompt_path.read_text(
                encoding="utf-8", errors="ignore"
            ).strip()
        except Exception:  # noqa: BLE001
            prompt_text = ""

        try:
            lyrics_text = lyrics_path.read_text(
                encoding="utf-8", errors="ignore"
            )
        except Exception:  # noqa: BLE001
            lyrics_text = ""

        # Normalize line endings
        lyrics_text = lyrics_text.replace("\r\n", "\n").replace("\r", "\n").strip()

        # Safety: never feed completely empty lyrics.
        if not lyrics_text:
            lyrics_text = "[inst]"

        # Convert prompt into a tag list.
        tag_pieces = re.split(r"[,\n;]+", prompt_text)
        tags = [t.strip() for t in tag_pieces if t.strip()]
        if not tags:
            tags = ["music"]

        records.append(
            {
                "keys": stem,
                "filename": str(audio_path.resolve()),
                "norm_lyrics": lyrics_text,
                "tags": tags,
            }
        )

    if not records:
        raise RuntimeError(
            "No usable training examples found; all audio files were missing "
            "_prompt.txt and/or _lyrics.txt."
        )

    hf_root.mkdir(parents=True, exist_ok=True)
    ds = Dataset.from_list(records)
    ds.save_to_disk(str(hf_root))

    print(
        f"[CDMF] Built ACE-Step text2music dataset at {hf_root} "
        f"from {len(records)} tracks (skipped {skipped}).",
        flush=True,
    )
    return hf_root


def _start_lora_training(
    dataset_path: str,
    exp_name: str,
    lora_config_path: Optional[str],
    max_steps: int,
    learning_rate: float,
    devices: int,
    max_epochs: int,
    ssl_coeff: float,
    instrumental_only: bool,
    max_audio_seconds: float,
    lora_save_every: int,
    precision: str,
    accumulate_grad_batches: int,
    gradient_clip_val: float,
    gradient_clip_algorithm: str,
    reload_dataloaders_every_n_epochs: int,
    val_check_interval: Optional[int],
) -> Tuple[bool, str]:
    """
    Fire-and-forget spawn of ACE-Step's trainer.py (custom cdmf_trainer.py is used) as a subprocess.

    Returns (ok, message). On success, TRAIN_STATE is updated and the process
    runs independently; we just stream its stdout/stderr into a log file.

    NOTE: dataset_path is interpreted as a folder name / relative path
    under TRAINING_DATA_ROOT (APP_DIR / "training_datasets"), not as an
    arbitrary absolute path on the host filesystem. The raw folder is
    auto-converted into a HuggingFace `datasets` directory under
      <raw_folder> / "_hf_text2music"
    which is what trainer.py actually consumes.

    The extra knobs ssl_coeff, instrumental_only, max_audio_seconds and
    lora_save_every are forwarded directly to trainer.py as:
      --ssl_coeff
      --instrumental_only
      --max_audio_seconds
      --every_n_train_steps

    The advanced knobs are forwarded as:
      --precision
      --accumulate_grad_batches
      --gradient_clip_val
      --gradient_clip_algorithm
      --reload_dataloaders_every_n_epochs
      --val_check_interval   (only when not None)
    """
    import sys
    import threading

    dataset_path = dataset_path.strip()
    exp_name = exp_name.strip()

    if not dataset_path:
        return False, "Dataset folder name is required."
    if not exp_name:
        return False, "Experiment / adapter name is required."

    ds_rel = Path(dataset_path)

    if ds_rel.is_absolute():
        return False, (
            "Dataset folder must be inside the training_datasets directory "
            "(relative path only)."
        )

    ds_path = (TRAINING_DATA_ROOT / ds_rel).resolve()

    try:
        training_root_real = TRAINING_DATA_ROOT.resolve()
    except Exception:  # noqa: BLE001
        training_root_real = TRAINING_DATA_ROOT

    if not str(ds_path).startswith(str(training_root_real)):
        return False, "Dataset folder must live under the training_datasets directory."

    if not ds_path.exists():
        return False, f"Dataset folder does not exist on disk: {ds_path}"

    # Build or reuse an on-disk HuggingFace dataset that matches
    # acestep.text2music_dataset.Text2MusicDataset expectations.
    try:
        hf_ds_path = _ensure_hf_text2music_dataset(ds_path)
    except Exception as exc:  # noqa: BLE001
        return False, (
            "Failed to build ACE-Step training dataset under "
            f"{ds_path}: {exc}"
        )

    trainer_script = APP_DIR / "cdmf_trainer.py"
    if not trainer_script.exists():
        return False, f"trainer.py not found at {trainer_script}"

    # Training logs live under APP_DIR / ace_training / <exp_name>, but the
    # heavy ACE-Step base model weights are cached in a shared root folder.
    train_root = APP_DIR / "ace_training"
    exp_root = train_root / exp_name
    exp_root.mkdir(parents=True, exist_ok=True)
    log_path = exp_root / "trainer.log"

    ckpt_dir = ACE_TRAINER_MODEL_ROOT
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    # Per-experiment logs / Lightning state live under ace_training/<exp_name>/logs
    logger_dir = exp_root / "logs"
    logger_dir.mkdir(parents=True, exist_ok=True)

    # Resolve LoRA config path
    cfg_path: Optional[Path]

    if lora_config_path:
        raw_cfg = Path(lora_config_path.strip())
        if raw_cfg.is_absolute():
            cfg_path = raw_cfg.expanduser()
        else:
            cand1 = (APP_DIR / raw_cfg).resolve()
            cand2 = (TRAINING_CONFIG_ROOT / raw_cfg).resolve()
            cfg_path = cand1 if cand1.exists() else cand2
    else:
        cfg_path = DEFAULT_LORA_CONFIG

    if cfg_path is None or not cfg_path.exists():
        return False, f"LoRA config file does not exist: {cfg_path}"

    cfg_path_str = str(cfg_path)

    # Base command
    cmd: list[str] = [
        sys.executable,
        str(trainer_script),
        "--dataset_path",
        str(hf_ds_path),
        "--exp_name",
        exp_name,
        "--max_steps",
        str(max_steps),
        "--learning_rate",
        str(learning_rate),
        "--devices",
        str(devices),
        "--epochs",
        str(max_epochs),
        "--num_workers",
        "8",
        "--ssl_coeff",
        str(ssl_coeff),
        "--max_audio_seconds",
        str(max_audio_seconds),
        "--every_n_train_steps",
        str(lora_save_every),
        "--precision",
        precision,
        "--accumulate_grad_batches",
        str(accumulate_grad_batches),
        "--gradient_clip_val",
        str(gradient_clip_val),
        "--gradient_clip_algorithm",
        gradient_clip_algorithm,
        "--reload_dataloaders_every_n_epochs",
        str(reload_dataloaders_every_n_epochs),
    ]

    if instrumental_only:
        cmd.append("--instrumental_only")

    if val_check_interval is not None:
        cmd.extend(
            [
                "--val_check_interval",
                str(val_check_interval),
            ]
        )

    cmd.extend(
        [
            "--lora_config_path",
            cfg_path_str,
            "--checkpoint_dir",
            str(ckpt_dir),
            "--logger_dir",
            str(logger_dir),
        ]
    )

    print("[CDMF] Starting ACE-Step LoRA training:")
    print("       Raw dataset folder :", ds_path, flush=True)
    print("       HF dataset path    :", hf_ds_path, flush=True)
    print("       ssl_coeff          :", ssl_coeff, flush=True)
    print("       instrumental_only  :", instrumental_only, flush=True)
    print("       max_audio_seconds  :", max_audio_seconds, flush=True)
    print("       lora_save_every    :", lora_save_every, flush=True)
    print("       precision          :", precision, flush=True)
    print("       accumulate_grad_batches      :", accumulate_grad_batches, flush=True)
    print("       gradient_clip_val            :", gradient_clip_val, flush=True)
    print("       gradient_clip_algorithm      :", gradient_clip_algorithm, flush=True)
    print("       reload_dataloaders_every_n_epochs :", reload_dataloaders_every_n_epochs, flush=True)
    print("       val_check_interval           :", val_check_interval, flush=True)
    print("       ", " ".join(cmd), flush=True)

    try:
        log_f = open(log_path, "w", encoding="utf-8", errors="replace")
    except OSError as exc:  # noqa: BLE001
        return False, f"Could not open log file {log_path}: {exc}"

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(APP_DIR),
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )
    except Exception as exc:  # noqa: BLE001
        log_f.close()
        return False, f"Failed to start trainer subprocess: {exc}"

    start_ts = time.time()
    start_msg = (
        f"LoRA training '{exp_name}' is running (PID {proc.pid}). "
        f"Logs: {log_path}"
    )

    with cdmf_state.TRAIN_LOCK:
        cdmf_state.TRAIN_STATE.update(
            {
                "running": True,
                "exp_name": exp_name,
                "dataset_path": str(ds_path),
                "lora_config_path": cfg_path_str,
                "pid": proc.pid,
                "started_at": start_ts,
                "finished_at": None,
                "returncode": None,
                "log_path": str(log_path),
                "error": None,
                "last_update": start_ts,
                "last_message": start_msg,
                "max_steps": int(max_steps) if max_steps else None,
                "max_epochs": int(max_epochs) if max_epochs else None,
                "current_epoch": 0,
                "current_step": 0,
                "progress": 0.0,
                "paused": False,
                "ssl_coeff": float(ssl_coeff),
                "instrumental_only": bool(instrumental_only),
                "max_audio_seconds": float(max_audio_seconds),
                "lora_save_every": int(lora_save_every),
                "_proc": proc,
            }
        )

    print(
        f"[CDMF] LoRA training '{exp_name}' started (PID {proc.pid}). "
        f"Logging to {log_path}",
        flush=True,
    )

    # ------------------------------------------------------------------    
    #  Background helpers: monitor process + tail trainer.log for progress
    # ------------------------------------------------------------------
    def _tail_log_for_progress(
        log_file: Path,
        exp: str,
        max_epochs_local: Optional[int],
        max_steps_local: Optional[int],
    ) -> None:
        import re
        import time as _time

        epoch_re = re.compile(r"Epoch\s+(\d+):")
        step_re = re.compile(r"(\d+)\s*/\s*(\d+)")
        global_step_re = re.compile(r"global_step\s*=\s*(\d+)")

        last_pos = 0
        while True:
            with cdmf_state.TRAIN_LOCK:
                if not cdmf_state.TRAIN_STATE.get("running"):
                    break

            try:
                with log_file.open("r", encoding="utf-8", errors="ignore") as f:
                    f.seek(last_pos)
                    chunk = f.read()
                    last_pos = f.tell()
            except OSError:
                _time.sleep(1.0)
                continue

            if not chunk:
                _time.sleep(1.0)
                continue

            lines = chunk.splitlines()
            current_epoch = None
            current_step = None
            steps_in_epoch = None
            global_step = None

            for line in lines:
                m_epoch = epoch_re.search(line)
                if m_epoch:
                    try:
                        current_epoch = int(m_epoch.group(1))
                    except Exception:
                        pass

                m_step = step_re.search(line)
                if m_step:
                    try:
                        current_step = int(m_step.group(1))
                        steps_in_epoch = int(m_step.group(2))
                    except Exception:
                        pass

                m_gs = global_step_re.search(line)
                if m_gs:
                    try:
                        global_step = int(m_gs.group(1))
                    except Exception:
                        pass

            if (
                current_epoch is None
                and current_step is None
                and global_step is None
            ):
                _time.sleep(1.0)
                continue

            with cdmf_state.TRAIN_LOCK:
                prev_progress = float(cdmf_state.TRAIN_STATE.get("progress", 0.0) or 0.0)
                max_epochs_val = max_epochs_local or cdmf_state.TRAIN_STATE.get("max_epochs") or 0
                max_steps_val = max_steps_local or cdmf_state.TRAIN_STATE.get("max_steps") or 0

                progress_step = None
                progress_epoch = None

                # Step-based progress
                if global_step is not None and max_steps_val:
                    try:
                        progress_step = float(global_step) / float(max_steps_val)
                    except Exception:
                        progress_step = None
                    cdmf_state.TRAIN_STATE["current_step"] = global_step

                # Epoch-based progress
                if (
                    current_epoch is not None
                    and steps_in_epoch
                    and max_epochs_val
                ):
                    cdmf_state.TRAIN_STATE["current_epoch"] = current_epoch
                    try:
                        epoch_idx = max(current_epoch - 1, 0)
                        inner = float(current_step or 0) / float(steps_in_epoch)
                        raw = (epoch_idx + inner) / float(max_epochs_val)
                        progress_epoch = raw
                    except Exception:
                        progress_epoch = None

                    if global_step is None and current_step is not None:
                        cdmf_state.TRAIN_STATE["current_step"] = current_step

                candidates = [prev_progress]
                for v in (progress_step, progress_epoch):
                    if v is not None:
                        candidates.append(v)

                progress = max(0.0, min(1.0, max(candidates)))

                cdmf_state.TRAIN_STATE["progress"] = progress
                cdmf_state.TRAIN_STATE["last_update"] = time.time()
                cdmf_state.TRAIN_STATE["last_message"] = (
                    f"Training '{exp}': epoch={cdmf_state.TRAIN_STATE.get('current_epoch')}, "
                    f"step={cdmf_state.TRAIN_STATE.get('current_step')}, "
                    f"progress={progress * 100.0:.1f}%"
                )

            _time.sleep(1.0)

    def _monitor_proc(p: subprocess.Popen, exp: str) -> None:
        rc = p.wait()
        finished_ts = time.time()
        if rc == 0:
            msg = f"LoRA training '{exp}' finished successfully."
        else:
            msg = (
                f"LoRA training '{exp}' finished with errors "
                f"(return code {rc}). See trainer.log for details."
            )

            try:
                if log_path.is_file():
                    with log_path.open("r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                    tail = lines[-40:] if len(lines) > 40 else lines
                    print("[CDMF] ---- trainer.log (tail) ----", flush=True)
                    for line in tail:
                        print(line.rstrip("\n"), flush=True)
                    print("[CDMF] ---- end trainer.log tail ----", flush=True)
            except Exception as log_exc:  # noqa: BLE001
                print(
                    f"[CDMF] Warning: could not read trainer.log tail: {log_exc}",
                    flush=True,
                )

        with cdmf_state.TRAIN_LOCK:
            cdmf_state.TRAIN_STATE["running"] = False
            cdmf_state.TRAIN_STATE["finished_at"] = finished_ts
            cdmf_state.TRAIN_STATE["returncode"] = rc
            cdmf_state.TRAIN_STATE["last_update"] = finished_ts
            cdmf_state.TRAIN_STATE["last_message"] = msg
            cdmf_state.TRAIN_STATE["error"] = None if rc == 0 else msg
            if rc == 0:
                cdmf_state.TRAIN_STATE["progress"] = 1.0
            cdmf_state.TRAIN_STATE.pop("_proc", None)
        print(f"[CDMF] {msg}", flush=True)

        if rc == 0:
            try:
                train_root_local = APP_DIR / "ace_training"
                exp_root_local = train_root_local / exp
                cleanup_dirs = [
                    exp_root_local / "checkpoints",
                    exp_root_local / "logs",
                    exp_root_local / "lightning_logs",
                    exp_root_local / "tb_logs",
                ]
                for d in cleanup_dirs:
                    if d.exists():
                        shutil.rmtree(d, ignore_errors=True)
            except Exception as cleanup_exc:  # noqa: BLE001
                print(
                    f"[CDMF] Warning: Failed to clean up training artifacts for "
                    f"'{exp}': {cleanup_exc}",
                    flush=True,
                )

            try:
                stray = CUSTOM_LORA_ROOT / f"{exp}.safetensors"
                canonical = CUSTOM_LORA_ROOT / exp / "pytorch_lora_weights.safetensors"
                if stray.exists() and canonical.exists():
                    try:
                        stray.unlink()
                        print(
                            "[CDMF] Removed stray root-level LoRA weights "
                            f"{stray} (kept {canonical}).",
                            flush=True,
                        )
                    except Exception as unlink_exc:
                        print(
                            f"[CDMF] Warning: could not remove stray LoRA file {stray}: "
                            f"{unlink_exc}",
                            flush=True,
                        )
            except Exception as stray_exc:
                print(
                    f"[CDMF] Warning: error while cleaning stray LoRA copies for "
                    f"'{exp}': {stray_exc}",
                    flush=True,
                )

    t_tail = threading.Thread(
        target=_tail_log_for_progress,
        args=(log_path, exp_name, max_epochs, max_steps),
        daemon=True,
    )
    t_tail.start()

    t_mon = threading.Thread(
        target=_monitor_proc,
        args=(proc, exp_name),
        daemon=True,
    )
    t_mon.start()

    return True, start_msg


def create_training_blueprint() -> Blueprint:
    bp = Blueprint("cdmf_training", __name__)

    @bp.route("/train_lora/status", methods=["GET"])
    def train_lora_status():
        """
        JSON status endpoint so the frontend can poll training state later.
        """
        with cdmf_state.TRAIN_LOCK:
            state = {
                k: v for k, v in cdmf_state.TRAIN_STATE.items()
                if k != "_proc"
            }
        return jsonify(state)

    @bp.route("/train_lora/configs", methods=["GET"])
    def train_lora_configs():
        """
        List available LoRA config JSON files under TRAINING_CONFIG_ROOT.

        Returns JSON:
          {
            "ok": true,
            "configs": [
              {"file": "default_config.json", "label": "..."},
              ...
            ],
            "default": "default_config.json"
          }
        """
        try:
            configs = []
            for path in sorted(TRAINING_CONFIG_ROOT.glob("*.json")):
                fname = path.name
                label = fname
                # Mark the default and explain the relationship to light_base_layers
                if fname == DEFAULT_LORA_CONFIG.name:
                    label += " (default; same as light_base_layers.json)"
                configs.append({"file": fname, "label": label})

            return jsonify(
                {
                    "ok": True,
                    "configs": configs,
                    "default": DEFAULT_LORA_CONFIG.name,
                }
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[CDMF] /train_lora/configs error: {exc}", flush=True)
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                ),
                500,
            )

    @bp.route("/train_lora", methods=["POST"])
    def train_lora():
        """
        Hidden-iframe POST target from the Training tab.

        It validates the inputs, starts trainer.py as a subprocess, and writes a
        very small HTML snippet into the iframe so the browser is happy.
        """

        # --- Block training if the ACE-Step model hasn't been downloaded yet ----
        training_model_ready = ace_models_present()
        with cdmf_state.MODEL_LOCK:
            model_state = cdmf_state.MODEL_STATUS.get("state", "unknown")

            if training_model_ready and model_state != "ready":
                cdmf_state.MODEL_STATUS["state"] = "ready"
                if not cdmf_state.MODEL_STATUS.get("message"):
                    cdmf_state.MODEL_STATUS["message"] = "ACE-Step model is present."
                model_state = "ready"
            elif not training_model_ready and model_state not in ("downloading", "error"):
                cdmf_state.MODEL_STATUS["state"] = "absent"
                cdmf_state.MODEL_STATUS["message"] = (
                    "ACE-Step training model has not been downloaded yet."
                )
                model_state = "absent"

        if (
            not training_model_ready
            or model_state in ("absent", "unknown", "downloading")
        ):
            msg = (
                "ACE-Step training model is not available yet.\n\n"
                "Use the 'Download Training Model' button in the Training tab "
                "to download the ACE-Step weights first. Once the download "
                "finishes, the 'Start Training' button will be enabled."
            )
            print(
                "[CDMF] /train_lora blocked: ACE-Step training model missing or downloading.",
                flush=True,
            )
            html = (
                "<pre style='color:#f97373;'>"
                "ACE-Step training model is not available yet.\n\n"
                f"{msg}\n"
                "</pre>"
            )
            return html

        # --- DEBUG: log that we actually hit this endpoint -------------------
        print("[CDMF] /train_lora called", flush=True)

        dataset_path = request.form.get("dataset_path", "").strip()
        exp_name = request.form.get("exp_name", "").strip()
        max_steps_raw = request.form.get("max_steps", "").strip()
        max_epochs_raw = request.form.get("max_epochs", "").strip()
        lr_raw = request.form.get("learning_rate", "").strip()
        devices_raw = request.form.get("devices", "").strip()
        ssl_coeff_raw = request.form.get("ssl_coeff", "").strip()
        instrumental_only_raw = request.form.get("instrumental_only")
        instrumental_only = bool(instrumental_only_raw)
        max_audio_seconds_raw = request.form.get("max_audio_seconds", "").strip()
        lora_save_every_raw = request.form.get("lora_save_every", "").strip()

        # Advanced trainer knobs
        precision_raw = request.form.get("precision", "").strip()
        accumulate_raw = request.form.get("accumulate_grad_batches", "").strip()
        clip_val_raw = request.form.get("gradient_clip_val", "").strip()
        clip_alg_raw = request.form.get("gradient_clip_algorithm", "").strip()
        reload_raw = request.form.get("reload_dataloaders_every_n_epochs", "").strip()
        val_interval_raw = request.form.get("val_check_interval", "").strip()

        print(
            "[CDMF] /train_lora form data:\n"
            f"  dataset_path        = {dataset_path!r}\n"
            f"  exp_name            = {exp_name!r}\n"
            f"  max_steps_raw       = {max_steps_raw!r}\n"
            f"  max_epochs_raw      = {max_epochs_raw!r}\n"
            f"  lr_raw              = {lr_raw!r}\n"
            f"  devices_raw         = {devices_raw!r}\n"
            f"  ssl_coeff_raw       = {ssl_coeff_raw!r}\n"
            f"  instrumental_only   = {instrumental_only_raw!r}\n"
            f"  max_audio_seconds   = {max_audio_seconds_raw!r}\n"
            f"  lora_save_every_raw = {lora_save_every_raw!r}\n"
            f"  precision_raw       = {precision_raw!r}\n"
            f"  accumulate_raw      = {accumulate_raw!r}\n"
            f"  clip_val_raw        = {clip_val_raw!r}\n"
            f"  clip_alg_raw        = {clip_alg_raw!r}\n"
            f"  reload_raw          = {reload_raw!r}\n"
            f"  val_interval_raw    = {val_interval_raw!r}",
            flush=True,
        )

        # LoRA config selection:
        # If the user picks a simple file name from the dropdown
        # (e.g. "light_full_stack.json"), resolve it relative to
        # TRAINING_CONFIG_ROOT. If they pass an absolute or explicit path,
        # keep it as-is for advanced workflows.
        lora_config_raw = request.form.get("lora_config_path", "").strip()
        if lora_config_raw:
            cfg_name = lora_config_raw
            cfg_path = Path(cfg_name)
            if not cfg_path.is_absolute() and not any(sep in cfg_name for sep in ("/", "\\")):
                lora_config_path = str(TRAINING_CONFIG_ROOT / cfg_name)
            else:
                lora_config_path = cfg_name
        else:
            lora_config_path = str(DEFAULT_LORA_CONFIG)

        print(f"[CDMF] /train_lora lora_config_path = {lora_config_path!r}", flush=True)

        try:
            max_steps = int(max_steps_raw) if max_steps_raw else 2000
        except ValueError:
            max_steps = 2000

        try:
            max_epochs = int(max_epochs_raw) if max_epochs_raw else 20
        except ValueError:
            max_epochs = 20

        try:
            learning_rate = float(lr_raw) if lr_raw else 1e-4
        except ValueError:
            learning_rate = 1e-4

        try:
            devices = int(devices_raw) if devices_raw else 1
        except ValueError:
            devices = 1

        try:
            ssl_coeff = float(ssl_coeff_raw) if ssl_coeff_raw else 1.0
        except ValueError:
            ssl_coeff = 1.0

        try:
            max_audio_seconds = float(max_audio_seconds_raw) if max_audio_seconds_raw else 20.0
        except ValueError:
            max_audio_seconds = 20.0

        try:
            lora_save_every = int(lora_save_every_raw) if lora_save_every_raw else 50
        except ValueError:
            lora_save_every = 50

        # Precision with whitelist
        precision = precision_raw or "32"
        if precision not in ("32", "16-mixed", "bf16-mixed"):
            precision = "32"

        # Grad accumulation
        try:
            accumulate_grad_batches = int(accumulate_raw) if accumulate_raw else 1
        except ValueError:
            accumulate_grad_batches = 1
        if accumulate_grad_batches < 1:
            accumulate_grad_batches = 1

        # Gradient clip
        try:
            gradient_clip_val = float(clip_val_raw) if clip_val_raw else 0.5
        except ValueError:
            gradient_clip_val = 0.5
        if gradient_clip_val < 0.0:
            gradient_clip_val = 0.0

        gradient_clip_algorithm = clip_alg_raw or "norm"
        if gradient_clip_algorithm not in ("norm", "value"):
            gradient_clip_algorithm = "norm"

        # Reload dataloaders
        try:
            reload_dataloaders_every_n_epochs = int(reload_raw) if reload_raw else 1
        except ValueError:
            reload_dataloaders_every_n_epochs = 1
        if reload_dataloaders_every_n_epochs < 0:
            reload_dataloaders_every_n_epochs = 0

        # Optional validation interval
        if not val_interval_raw:
            val_check_interval: Optional[int] = None
        else:
            try:
                tmp_val = int(val_interval_raw)
            except ValueError:
                tmp_val = 0
            if tmp_val <= 0:
                val_check_interval = None
            else:
                val_check_interval = tmp_val

        print(
            "[CDMF] /train_lora parsed params:\n"
            f"  max_steps        = {max_steps}\n"
            f"  max_epochs       = {max_epochs}\n"
            f"  learning_rate    = {learning_rate}\n"
            f"  devices          = {devices}\n"
            f"  ssl_coeff        = {ssl_coeff}\n"
            f"  instrumental_only= {instrumental_only}\n"
            f"  max_audio_seconds= {max_audio_seconds}\n"
            f"  lora_save_every  = {lora_save_every}\n"
            f"  precision        = {precision}\n"
            f"  accumulate_grad_batches = {accumulate_grad_batches}\n"
            f"  gradient_clip_val       = {gradient_clip_val}\n"
            f"  gradient_clip_algorithm = {gradient_clip_algorithm}\n"
            f"  reload_dataloaders_every_n_epochs = {reload_dataloaders_every_n_epochs}\n"
            f"  val_check_interval      = {val_check_interval}",
            flush=True,
        )

        with cdmf_state.TRAIN_LOCK:
            if cdmf_state.TRAIN_STATE.get("running"):
                ...
        ok, message = _start_lora_training(
            dataset_path=dataset_path,
            exp_name=exp_name or "cdmf_lora",
            lora_config_path=lora_config_path,
            max_steps=max_steps,
            learning_rate=learning_rate,
            devices=devices,
            max_epochs=max_epochs,
            ssl_coeff=ssl_coeff,
            instrumental_only=instrumental_only,
            max_audio_seconds=max_audio_seconds,
            lora_save_every=lora_save_every,
            precision=precision,
            accumulate_grad_batches=accumulate_grad_batches,
            gradient_clip_val=gradient_clip_val,
            gradient_clip_algorithm=gradient_clip_algorithm,
            reload_dataloaders_every_n_epochs=reload_dataloaders_every_n_epochs,
            val_check_interval=val_check_interval,
        )

        if not ok:
            print("[CDMF] Failed to start LoRA training:", message, flush=True)
            html = (
                "<pre style='color:#f97373;'>"
                "ERROR starting LoRA training:\n\n"
                f"{message}\n"
                "</pre>"
            )
            return html

        print("[CDMF] LoRA training successfully started.", flush=True)

        html = (
            "<pre>"
            "LoRA training started.\n\n"
            f"{message}\n\n"
            "Tip: keep the server console window open to watch detailed training logs.\n"
            "</pre>"
        )
        return html

    @bp.route("/dataset_mass_tag", methods=["POST"])
    def dataset_mass_tag():
        """
        Mass-create _prompt.txt and/or _lyrics.txt files for all .mp3 / .wav
        files in a dataset folder under TRAINING_DATA_ROOT.

        Expected JSON body:
          {
            "dataset_path": "my_dataset",          # relative folder name
            "base_prompt": "SNES, 16-bit, ...",   # required if mode includes "prompt"
            "mode": "prompt" | "lyrics_inst" | "both",
            "overwrite": false                    # optional
          }
        """
        payload = request.get_json(silent=True) or {}
        dataset_path = (payload.get("dataset_path") or "").strip()
        base_prompt = (payload.get("base_prompt") or "").strip()
        mode = (payload.get("mode") or "prompt").strip().lower()
        overwrite = bool(payload.get("overwrite"))

        if not dataset_path:
            return (
                jsonify({"ok": False, "error": "dataset_path is required"}),
                400,
            )

        if mode not in {"prompt", "lyrics_inst", "both"}:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": f"Invalid mode '{mode}'. Use 'prompt', 'lyrics_inst', or 'both'.",
                    }
                ),
                400,
            )

        if mode in {"prompt", "both"} and not base_prompt:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "base_prompt is required when creating prompt files.",
                    }
                ),
                400,
            )

        ds_rel = Path(dataset_path)

        if ds_rel.is_absolute():
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": (
                            "dataset_path must be a folder name / relative path under "
                            "the training_datasets directory, not an absolute path."
                        ),
                    }
                ),
                400,
            )

        # Mirror the safety checks from _start_lora_training
        try:
            training_root_real = TRAINING_DATA_ROOT.resolve()
        except Exception:  # noqa: BLE001
            training_root_real = TRAINING_DATA_ROOT

        ds_path = (TRAINING_DATA_ROOT / ds_rel).resolve()

        if not str(ds_path).startswith(str(training_root_real)):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "Dataset folder must live under the training_datasets directory.",
                    }
                ),
                400,
            )

        if not ds_path.exists() or not ds_path.is_dir():
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": f"Dataset folder does not exist on disk: {ds_path}",
                    }
                ),
                400,
            )

        audio_exts = {".wav", ".mp3"}

        prompt_created = 0
        prompt_skipped = 0
        lyrics_created = 0
        lyrics_skipped = 0

        try:
            for entry in sorted(ds_path.iterdir(), key=lambda p: p.name.lower()):
                if not entry.is_file():
                    continue
                if entry.suffix.lower() not in audio_exts:
                    continue

                stem = entry.with_suffix("")
                prompt_path = stem.with_name(stem.name + "_prompt.txt")
                lyrics_path = stem.with_name(stem.name + "_lyrics.txt")

                if mode in {"prompt", "both"}:
                    if prompt_path.exists() and not overwrite:
                        prompt_skipped += 1
                    else:
                        prompt_path.write_text(base_prompt + "\n", encoding="utf-8")
                        prompt_created += 1

                if mode in {"lyrics_inst", "both"}:
                    if lyrics_path.exists() and not overwrite:
                        lyrics_skipped += 1
                    else:
                        lyrics_path.write_text("[inst]\n", encoding="utf-8")
                        lyrics_created += 1
        except Exception as exc:  # noqa: BLE001
            print(
                f"[CDMF] /dataset_mass_tag failed for {ds_path}: {exc}",
                flush=True,
            )
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                ),
                500,
            )

        return jsonify(
            {
                "ok": True,
                "dataset": str(ds_rel),
                "mode": mode,
                "prompt_files_created": prompt_created,
                "prompt_files_skipped": prompt_skipped,
                "lyrics_files_created": lyrics_created,
                "lyrics_files_skipped": lyrics_skipped,
            }
        )

    # ----------------------------------------------------------------------
    # Pause / Resume / Cancel endpoints
    # ----------------------------------------------------------------------

    def _get_proc():
        """
        Return a psutil.Process handle for the current training process, if any.
        We prefer psutil so that suspend()/resume()/terminate() work uniformly
        on Windows and POSIX.
        """
        pid = None

        # If we still have a live Popen object, prefer its PID.
        p = cdmf_state.TRAIN_STATE.get("_proc")
        if p is not None and hasattr(p, "pid"):
            pid = p.pid
        else:
            pid = cdmf_state.TRAIN_STATE.get("pid")

        if not pid:
            return None

        try:
            return psutil.Process(pid)
        except Exception:
            return None

    @bp.route("/train_lora/pause", methods=["POST"])
    def pause_lora():
        with cdmf_state.TRAIN_LOCK:
            p = _get_proc()
            if not p or not cdmf_state.TRAIN_STATE.get("running"):
                return jsonify({"ok": False, "error": "No training process running."}), 400
            try:
                # psutil.Process.suspend() works on Windows and POSIX
                p.suspend()
                cdmf_state.TRAIN_STATE["paused"] = True
                cdmf_state.TRAIN_STATE["last_message"] = "Training paused."
                return jsonify({"ok": True, "message": "Training paused."})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500

    @bp.route("/train_lora/resume", methods=["POST"])
    def resume_lora():
        with cdmf_state.TRAIN_LOCK:
            p = _get_proc()
            if not p or not cdmf_state.TRAIN_STATE.get("paused"):
                return jsonify({"ok": False, "error": "No paused training found."}), 400
            try:
                p.resume()
                cdmf_state.TRAIN_STATE["paused"] = False
                cdmf_state.TRAIN_STATE["last_message"] = "Training resumed."
                return jsonify({"ok": True, "message": "Training resumed."})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500

    @bp.route("/train_lora/cancel", methods=["POST"])
    def cancel_lora():
        with cdmf_state.TRAIN_LOCK:
            p = _get_proc()
            if not p or not cdmf_state.TRAIN_STATE.get("running"):
                return jsonify({"ok": False, "error": "No active training to cancel."}), 400
            try:
                p.terminate()
                cdmf_state.TRAIN_STATE["running"] = False
                cdmf_state.TRAIN_STATE["paused"] = False
                cdmf_state.TRAIN_STATE["last_message"] = "Training cancelled by user."
                return jsonify({"ok": True, "message": "Training cancelled."})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500

    return bp

