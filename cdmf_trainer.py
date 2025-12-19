# C:\AceForge\cdmf_trainer.py
# Customized version of the ACE-Step trainer.py script.

from pytorch_lightning.callbacks import ModelCheckpoint
from pytorch_lightning.loggers import TensorBoardLogger
from pytorch_lightning import Trainer
from datetime import datetime
from pathlib import Path
import argparse
import torch
import json
import matplotlib
import torch.nn.functional as F
import torch.utils.data
from pytorch_lightning.core import LightningModule
from torch.utils.data import DataLoader
from acestep.schedulers.scheduling_flow_match_euler_discrete import (
    FlowMatchEulerDiscreteScheduler,
)
from cdmf_text2music_dataset import Text2MusicDataset
from loguru import logger
from transformers import AutoModel, Wav2Vec2FeatureExtractor
import torchaudio

from diffusers.pipelines.stable_diffusion_3.pipeline_stable_diffusion_3 import (
    retrieve_timesteps,
)
from diffusers.utils.torch_utils import randn_tensor
from acestep.apg_guidance import apg_forward, MomentumBuffer
from tqdm import tqdm
import random
import os
from cdmf_pipeline_ace_step import ACEStepPipeline

matplotlib.use("Agg")
# Configure CUDA backends if available
if torch.cuda.is_available():
    torch.backends.cudnn.benchmark = False
torch.set_float32_matmul_precision("high")


class Pipeline(LightningModule):
    def __init__(
        self,
        learning_rate: float = 1e-4,
        num_workers: int = 4,
        train: bool = True,
        T: int = 1000,
        weight_decay: float = 1e-2,
        every_plot_step: int = 2000,
        shift: float = 3.0,
        logit_mean: float = 0.0,
        logit_std: float = 1.0,
        timestep_densities_type: str = "logit_normal",
        ssl_coeff: float = 1.0,
        instrumental_only: bool = False,
        checkpoint_dir=None,
        max_steps: int = 200000,
        warmup_steps: int = 10,
        dataset_path: str = "./data/your_dataset_path",
        lora_config_path: str = None,
        adapter_name: str = "lora_adapter",
        max_audio_seconds: float = 60.0,
        lora_save_every: int = 0,
    ):
        super().__init__()

        self.save_hyperparameters()
        self.is_train = train
        self.T = T

        # Initialize scheduler
        self.scheduler = self.get_scheduler()

        # step 1: load model
        acestep_pipeline = ACEStepPipeline(checkpoint_dir)
        acestep_pipeline.load_checkpoint(acestep_pipeline.checkpoint_dir)

        transformers = acestep_pipeline.ace_step_transformer.float().cpu()
        transformers.enable_gradient_checkpointing()

        assert lora_config_path is not None, "Please provide a LoRA config path"
        if lora_config_path is not None:
            try:
                from peft import LoraConfig
            except ImportError:
                raise ImportError("Please install peft library to use LoRA training")
            with open(lora_config_path, encoding="utf-8") as f:
                import json
                lora_config = json.load(f)
            lora_config = LoraConfig(**lora_config)
            transformers.add_adapter(adapter_config=lora_config, adapter_name=adapter_name)
            self.adapter_name = adapter_name

        self.transformers = transformers

        # Explicitly freeze base weights and unfreeze only LoRA parameters.
        # If instrumental_only is enabled, we also freeze LoRA weights
        # attached to lyric / speaker / vocal-specific submodules so they
        # are not trained on instrumental-only datasets.
        trainable_params = 0
        frozen_params = 0

        def _is_vocalish_param(param_name: str) -> bool:
            lower = param_name.lower()
            # Lyric encoder stack + projection
            if "lyric_encoder" in lower or "lyric_proj" in lower:
                return True
            # Explicit speaker embeddings
            if "speaker_embedder" in lower:
                return True
            # Future-proof catch-all: anything explicitly marked vocal/speech
            if "vocal" in lower or "speech" in lower:
                return True
            return False

        instrumental_only_flag = getattr(self.hparams, "instrumental_only", False)

        for name, p in self.transformers.named_parameters():
            is_lora_param = "lora" in name.lower()

            # Base weights are always frozen; we only ever train LoRA params.
            if not is_lora_param:
                p.requires_grad_(False)
                frozen_params += p.numel()
                continue

            # LoRA params on vocal/lyric-related modules: freeze when in instrumental mode.
            if instrumental_only_flag and _is_vocalish_param(name):
                p.requires_grad_(False)
                frozen_params += p.numel()
            else:
                p.requires_grad_(True)
                trainable_params += p.numel()

        logger.info(
            f"[Pipeline.__init__] LoRA setup (instrumental_only={instrumental_only_flag}): "
            f"trainable_params={trainable_params}, frozen_params={frozen_params}"
        )

        # DEBUG: how many transformer params are actually marked trainable?
        trainable = 0
        frozen = 0
        for name, p in self.transformers.named_parameters():
            if p.requires_grad:
                trainable += p.numel()
            else:
                frozen += p.numel()
        logger.info(
            f"[Pipeline.__init__] transformers params: trainable={trainable}, "
            f"frozen={frozen}"
        )

        self.dcae = acestep_pipeline.music_dcae.float().cpu()
        self.dcae.requires_grad_(False)

        self.text_encoder_model = acestep_pipeline.text_encoder_model.float().cpu()
        self.text_encoder_model.requires_grad_(False)
        self.text_tokenizer = acestep_pipeline.text_tokenizer

        if self.is_train:
            self.transformers.train()

            # download first
            try:
                self.mert_model = AutoModel.from_pretrained(
                    "m-a-p/MERT-v1-330M", trust_remote_code=True, cache_dir=checkpoint_dir
                ).eval()
            except:
                import json
                import os

                mert_config_path = os.path.join(
                    os.path.expanduser("~"),
                    ".cache",
                    "huggingface",
                    "hub",
                    "models--m-a-p--MERT-v1-330M",
                    "blobs",
                    "14f770758c7fe5c5e8ead4fe0f8e5fa727eb6942"
                )

                with open(mert_config_path) as f:
                    mert_config = json.load(f)
                mert_config["conv_pos_batch_norm"] = False
                with open(mert_config_path, mode="w") as f:
                    json.dump(mert_config, f)
                self.mert_model = AutoModel.from_pretrained(
                    "m-a-p/MERT-v1-330M", trust_remote_code=True, cache_dir=checkpoint_dir
                ).eval()
            self.mert_model.requires_grad_(False)
            self.resampler_mert = torchaudio.transforms.Resample(
                orig_freq=48000, new_freq=24000
            )
            self.processor_mert = Wav2Vec2FeatureExtractor.from_pretrained(
                "m-a-p/MERT-v1-330M", trust_remote_code=True
            )

            self.hubert_model = AutoModel.from_pretrained("utter-project/mHuBERT-147").eval()
            self.hubert_model.requires_grad_(False)
            self.resampler_mhubert = torchaudio.transforms.Resample(
                orig_freq=48000, new_freq=16000
            )
            self.processor_mhubert = Wav2Vec2FeatureExtractor.from_pretrained(
                "utter-project/mHuBERT-147",
                cache_dir=checkpoint_dir,
            )

            self.ssl_coeff = ssl_coeff

    def _prune_lightning_checkpoints(self, keep: int = 1) -> None:
        """
        Keep at most `keep` .ckpt files in this run's Lightning checkpoints
        folder, deleting older ones by modification time.

        This prevents disk usage from exploding while still leaving a recent
        checkpoint available for manual resume/debugging.
        """
        try:
            log_dir = getattr(self.logger, "log_dir", None)
        except Exception:
            log_dir = None

        if not log_dir:
            return

        ckpt_dir = Path(log_dir) / "checkpoints"
        if not ckpt_dir.is_dir():
            return

        try:
            ckpts = sorted(
                ckpt_dir.glob("*.ckpt"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return

        for old in ckpts[keep:]:
            try:
                old.unlink()
            except OSError:
                # If a delete fails (e.g. in use), just skip it.
                pass

    def infer_mert_ssl(self, target_wavs, wav_lengths):
        # Input is N x 2 x T (48kHz), convert to N x T (24kHz), mono
        mert_input_wavs_mono_24k = self.resampler_mert(target_wavs.mean(dim=1))
        bsz = target_wavs.shape[0]
        actual_lengths_24k = wav_lengths // 2  # 48kHz -> 24kHz

        # Normalize the actual audio part
        means = torch.stack(
            [
                mert_input_wavs_mono_24k[i, : actual_lengths_24k[i]].mean()
                for i in range(bsz)
            ]
        )
        vars = torch.stack(
            [
                mert_input_wavs_mono_24k[i, : actual_lengths_24k[i]].var()
                for i in range(bsz)
            ]
        )
        mert_input_wavs_mono_24k = (
            mert_input_wavs_mono_24k - means.view(-1, 1)
        ) / torch.sqrt(vars.view(-1, 1) + 1e-7)

        # MERT SSL constraint
        # Define the length of each chunk (5 seconds of samples)
        chunk_size = 24000 * 5  # 5 seconds, 24000 samples per second
        total_length = mert_input_wavs_mono_24k.shape[1]

        num_chunks_per_audio = (actual_lengths_24k + chunk_size - 1) // chunk_size

        # Process chunks
        all_chunks = []
        chunk_actual_lengths = []
        for i in range(bsz):
            audio = mert_input_wavs_mono_24k[i]
            actual_length = actual_lengths_24k[i]
            for start in range(0, actual_length, chunk_size):
                end = min(start + chunk_size, actual_length)
                chunk = audio[start:end]
                if len(chunk) < chunk_size:
                    chunk = F.pad(
                        chunk, (0, chunk_size - len(chunk))
                    )  # Pad insufficient parts with zeros
                all_chunks.append(chunk)
                chunk_actual_lengths.append(end - start)

        # Stack all chunks to (total_chunks, chunk_size)
        all_chunks = torch.stack(all_chunks, dim=0)

        # Batch inference
        with torch.no_grad():
            # Output shape: (total_chunks, seq_len, hidden_size)
            mert_ssl_hidden_states = self.mert_model(all_chunks).last_hidden_state

        # Calculate the number of features for each chunk
        chunk_num_features = [(length + 319) // 320 for length in chunk_actual_lengths]

        # Trim the hidden states of each chunk
        chunk_hidden_states = [
            mert_ssl_hidden_states[i, : chunk_num_features[i], :]
            for i in range(len(all_chunks))
        ]

        # Organize hidden states by audio
        mert_ssl_hidden_states_list = []
        chunk_idx = 0
        for i in range(bsz):
            audio_chunks = chunk_hidden_states[
                chunk_idx : chunk_idx + num_chunks_per_audio[i]
            ]
            audio_hidden = torch.cat(
                audio_chunks, dim=0
            )  # Concatenate chunks of the same audio
            mert_ssl_hidden_states_list.append(audio_hidden)
            chunk_idx += num_chunks_per_audio[i]

        return mert_ssl_hidden_states_list

    def infer_mhubert_ssl(self, target_wavs, wav_lengths):
        # Step 1: Preprocess audio
        # Input: N x 2 x T (48kHz, stereo) -> N x T (16kHz, mono)
        mhubert_input_wavs_mono_16k = self.resampler_mhubert(target_wavs.mean(dim=1))
        bsz = target_wavs.shape[0]
        actual_lengths_16k = wav_lengths // 3  # Convert lengths from 48kHz to 16kHz

        # Step 2: Zero-mean unit-variance normalization (only on actual audio)
        means = torch.stack(
            [
                mhubert_input_wavs_mono_16k[i, : actual_lengths_16k[i]].mean()
                for i in range(bsz)
            ]
        )
        vars = torch.stack(
            [
                mhubert_input_wavs_mono_16k[i, : actual_lengths_16k[i]].var()
                for i in range(bsz)
            ]
        )
        mhubert_input_wavs_mono_16k = (
            mhubert_input_wavs_mono_16k - means.view(-1, 1)
        ) / torch.sqrt(vars.view(-1, 1) + 1e-7)

        # Step 3: Define chunk size for MHubert (30 seconds at 16kHz)
        chunk_size = 16000 * 30  # 30 seconds = 480,000 samples

        # Step 4: Split audio into chunks
        num_chunks_per_audio = (
            actual_lengths_16k + chunk_size - 1
        ) // chunk_size  # Ceiling division
        all_chunks = []
        chunk_actual_lengths = []

        for i in range(bsz):
            audio = mhubert_input_wavs_mono_16k[i]
            actual_length = actual_lengths_16k[i]
            for start in range(0, actual_length, chunk_size):
                end = min(start + chunk_size, actual_length)
                chunk = audio[start:end]
                if len(chunk) < chunk_size:
                    chunk = F.pad(chunk, (0, chunk_size - len(chunk)))  # Pad with zeros
                all_chunks.append(chunk)
                chunk_actual_lengths.append(end - start)

        # Step 5: Stack all chunks for batch inference
        all_chunks = torch.stack(all_chunks, dim=0)  # Shape: (total_chunks, chunk_size)

        # Step 6: Batch inference with MHubert model
        with torch.no_grad():
            mhubert_ssl_hidden_states = self.hubert_model(all_chunks).last_hidden_state
            # Shape: (total_chunks, seq_len, hidden_size)

        # Step 7: Compute number of features per chunk (assuming model stride of 320)
        chunk_num_features = [(length + 319) // 320 for length in chunk_actual_lengths]

        # Step 8: Trim hidden states to remove padding effects
        chunk_hidden_states = [
            mhubert_ssl_hidden_states[i, : chunk_num_features[i], :]
            for i in range(len(all_chunks))
        ]

        # Step 9: Reorganize hidden states by original audio
        mhubert_ssl_hidden_states_list = []
        chunk_idx = 0
        for i in range(bsz):
            audio_chunks = chunk_hidden_states[
                chunk_idx : chunk_idx + num_chunks_per_audio[i]
            ]
            audio_hidden = torch.cat(
                audio_chunks, dim=0
            )  # Concatenate chunks for this audio
            mhubert_ssl_hidden_states_list.append(audio_hidden)
            chunk_idx += num_chunks_per_audio[i]
        return mhubert_ssl_hidden_states_list

    def get_text_embeddings(self, texts, device, text_max_length=256):
        from loguru import logger

        logger.info("[get_text_embeddings] start (real encoder)")

        # Tokenize on CPU
        inputs = self.text_tokenizer(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=text_max_length,
        )

        # Move token ids + masks to the target device (GPU)
        inputs = {key: value.to(device) for key, value in inputs.items()}

        # Make sure the encoder itself is on the same device
        if self.text_encoder_model.device != device:
            logger.info(
                f"[get_text_embeddings] moving text_encoder_model to device={device}"
            )
            self.text_encoder_model.to(device)

        with torch.no_grad():
            outputs = self.text_encoder_model(**inputs)
            last_hidden_states = outputs.last_hidden_state

        attention_mask = inputs["attention_mask"]

        logger.info(
            f"[get_text_embeddings] done, hidden_states.shape={tuple(last_hidden_states.shape)}"
        )

        return last_hidden_states, attention_mask

    def preprocess(self, batch, train=True):
        logger.info("[preprocess] start")

        target_wavs = batch["target_wavs"]
        wav_lengths = batch["wav_lengths"]

        dtype = target_wavs.dtype
        bs = target_wavs.shape[0]
        device = target_wavs.device

        # ------------------------------------------------------------------
        # 1) Optional cropping: avoid feeding entire multi-minute songs
        # ------------------------------------------------------------------
        max_audio_seconds = getattr(self.hparams, "max_audio_seconds", 60.0)
        if max_audio_seconds is not None and max_audio_seconds > 0:
            max_samples_48k = int(max_audio_seconds * 48000)

            if target_wavs.shape[-1] > max_samples_48k:
                old_samples = target_wavs.shape[-1]
                logger.info(
                    f"[preprocess] cropping audio from {old_samples} to "
                    f"{max_samples_48k} samples "
                    f"({old_samples / 48000.0:.1f}s -> {max_audio_seconds:.1f}s)"
                )
                # Trim time dimension
                target_wavs = target_wavs[..., :max_samples_48k]
                # Clamp reported lengths
                wav_lengths = torch.clamp(wav_lengths, max=max_samples_48k)

        # ------------------------------------------------------------------
        # 2) SSL features (MERT + mHuBERT), controlled by ssl_coeff
        # ------------------------------------------------------------------
        mert_ssl_hidden_states = None
        mhubert_ssl_hidden_states = None

        if train and self.ssl_coeff > 0:
            logger.info(
                f"[preprocess] SSL ENABLED (ssl_coeff={self.ssl_coeff}); "
                "running MERT/mHuBERT"
            )
            # Use device-agnostic autocast - get device type from tensor device
            device_type = device.type if device.type in ["cuda", "cpu", "mps"] else "cpu"
            with torch.amp.autocast(device_type=device_type, dtype=dtype):
                mert_ssl_hidden_states = self.infer_mert_ssl(
                    target_wavs, wav_lengths
                )
                mhubert_ssl_hidden_states = self.infer_mhubert_ssl(
                    target_wavs, wav_lengths
                )
        else:
            logger.info(
                f"[preprocess] SSL DISABLED (train={train}, ssl_coeff={self.ssl_coeff}); "
                "skipping MERT/mHuBERT"
            )

        # ------------------------------------------------------------------
        # 3) Text embeddings (real encoder now)
        # ------------------------------------------------------------------
        texts = batch["prompts"]
        logger.info(
            f"[preprocess] before text encoder; batch_size={bs}, "
            f"num_chars_first_prompt={len(texts[0]) if len(texts) > 0 else 0}"
        )

        encoder_text_hidden_states, text_attention_mask = self.get_text_embeddings(
            texts, device
        )
        encoder_text_hidden_states = encoder_text_hidden_states.to(dtype)

        logger.info(
            "[preprocess] after text encoder; "
            f"encoder_text_hidden_states.shape={tuple(encoder_text_hidden_states.shape)}"
        )

        # ------------------------------------------------------------------
        # 4) DCAE encode to latents (real, not fake)
        # ------------------------------------------------------------------
        logger.info(
            "[preprocess] before DCAE.encode; "
            f"target_wavs.shape={tuple(target_wavs.shape)}, "
            f"wav_lengths[0]={int(wav_lengths[0].item()) if wav_lengths.numel() > 0 else -1}"
        )

        target_latents, _ = self.dcae.encode(target_wavs, wav_lengths)

        logger.info(
            "[preprocess] after DCAE.encode; "
            f"target_latents.shape={tuple(target_latents.shape)}"
        )

        attention_mask = torch.ones(
            bs, target_latents.shape[-1], device=device, dtype=dtype
        )

        speaker_embds = batch["speaker_embs"].to(dtype)
        keys = batch["keys"]
        lyric_token_ids = batch["lyric_token_ids"]
        lyric_mask = batch["lyric_masks"]

        # ------------------------------------------------------------------
        # 5) Classifier-free guidance masks
        # ------------------------------------------------------------------
        if train:
            full_cfg_condition_mask = torch.where(
                (torch.rand(size=(bs,), device=device) < 0.15),
                torch.zeros(size=(bs,), device=device),
                torch.ones(size=(bs,), device=device),
            ).long()
            # N x T x 768
            encoder_text_hidden_states = torch.where(
                full_cfg_condition_mask.unsqueeze(1).unsqueeze(1).bool(),
                encoder_text_hidden_states,
                torch.zeros_like(encoder_text_hidden_states),
            )

            full_cfg_condition_mask = torch.where(
                (torch.rand(size=(bs,), device=device) < 0.50),
                torch.zeros(size=(bs,), device=device),
                torch.ones(size=(bs,), device=device),
            ).long()
            # N x 512
            speaker_embds = torch.where(
                full_cfg_condition_mask.unsqueeze(1).bool(),
                speaker_embds,
                torch.zeros_like(speaker_embds),
            )

            # Lyrics
            full_cfg_condition_mask = torch.where(
                (torch.rand(size=(bs,), device=device) < 0.15),
                torch.zeros(size=(bs,), device=device),
                torch.ones(size=(bs,), device=device),
            ).long()
            lyric_token_ids = torch.where(
                full_cfg_condition_mask.unsqueeze(1).bool(),
                lyric_token_ids,
                torch.zeros_like(lyric_token_ids),
            )
            lyric_mask = torch.where(
                full_cfg_condition_mask.unsqueeze(1).bool(),
                lyric_mask,
                torch.zeros_like(lyric_mask),
            )

        logger.info("[preprocess] done")

        return (
            keys,
            target_latents,
            attention_mask,
            encoder_text_hidden_states,
            text_attention_mask,
            speaker_embds,
            lyric_token_ids,
            lyric_mask,
            mert_ssl_hidden_states,
            mhubert_ssl_hidden_states,
        )

    def get_scheduler(self):
        return FlowMatchEulerDiscreteScheduler(
            num_train_timesteps=self.T,
            shift=self.hparams.shift,
        )

    def configure_optimizers(self):
        trainable_params = [
            p for name, p in self.transformers.named_parameters() if p.requires_grad
        ]

        if not trainable_params:
            raise RuntimeError(
                "[Pipeline.configure_optimizers] No trainable parameters found in "
                "self.transformers; LoRA adapter is not active / all params frozen."
            )

        optimizer = torch.optim.AdamW(
            params=[
                {"params": trainable_params},
            ],
            lr=self.hparams.learning_rate,
            weight_decay=self.hparams.weight_decay,
            betas=(0.8, 0.9),
        )
        max_steps = self.hparams.max_steps
        warmup_steps = self.hparams.warmup_steps  # New hyperparameter for warmup steps

        # Create a scheduler that first warms up linearly, then (optionally) decays linearly.
        # If max_steps <= 0, treat it as "no step limit" and keep LR constant after warmup.
        def lr_lambda(current_step):
            if current_step < warmup_steps:
                # Linear warmup from 0 to learning_rate
                return float(current_step) / float(max(1, warmup_steps))

            # No decay if max_steps is unset / negative (epoch-based runs only)
            if max_steps is None or max_steps <= 0:
                return 1.0

            # Linear decay from learning_rate to 0 over [warmup_steps, max_steps]
            progress = float(current_step - warmup_steps) / float(
                max(1, max_steps - warmup_steps)
            )
            return max(0.0, 1.0 - progress)

        lr_scheduler = torch.optim.lr_scheduler.LambdaLR(
            optimizer, lr_lambda, last_epoch=-1
        )
        return [optimizer], [{"scheduler": lr_scheduler, "interval": "step"}]

    def train_dataloader(self):
        self.train_dataset = Text2MusicDataset(
            train=True,
            train_dataset_path=self.hparams.dataset_path,
        )
        return DataLoader(
            self.train_dataset,
            shuffle=True,
            num_workers=self.hparams.num_workers,
            pin_memory=False,
            persistent_workers=self.hparams.num_workers > 0,
            collate_fn=self.train_dataset.collate_fn,
        )

    def get_sd3_sigmas(self, timesteps, device, n_dim=4, dtype=torch.float32):
        sigmas = self.scheduler.sigmas.to(device=device, dtype=dtype)
        schedule_timesteps = self.scheduler.timesteps.to(device)
        timesteps = timesteps.to(device)
        step_indices = [(schedule_timesteps == t).nonzero().item() for t in timesteps]
        sigma = sigmas[step_indices].flatten()
        while len(sigma.shape) < n_dim:
            sigma = sigma.unsqueeze(-1)
        return sigma

    def get_timestep(self, bsz, device):
        if self.hparams.timestep_densities_type == "logit_normal":
            # See 3.1 in the SD3 paper ($rf/lognorm(0.00,1.00)$).
            # In practice, we sample the random variable u from a normal distribution u ∼ N (u; m, s)
            # and map it through the standard logistic function
            u = torch.normal(
                mean=self.hparams.logit_mean,
                std=self.hparams.logit_std,
                size=(bsz,),
                device="cpu",
            )
            u = torch.nn.functional.sigmoid(u)
            indices = (u * self.scheduler.config.num_train_timesteps).long()
            indices = torch.clamp(
                indices, 0, self.scheduler.config.num_train_timesteps - 1
            )
            timesteps = self.scheduler.timesteps[indices].to(device)

        return timesteps

    def run_step(self, batch, batch_idx):
        # NOTE:
        # Mid-training diffusion previews (plot_step/predict_step/diffusion_process)
        # are temporarily disabled because they were interfering with Lightning's
        # autograd/precision contexts. If you want to re-enable them later for
        # qualitative monitoring, restore the call to self.plot_step(...) below.
        #
        # self.plot_step(batch, batch_idx)

        (
            keys,
            target_latents,
            attention_mask,
            encoder_text_hidden_states,
            text_attention_mask,
            speaker_embds,
            lyric_token_ids,
            lyric_mask,
            mert_ssl_hidden_states,
            mhubert_ssl_hidden_states,
        ) = self.preprocess(batch, train=True)

        target_image = target_latents
        device = target_image.device
        dtype = target_image.dtype

        # Step 1: Generate random noise, initialize settings
        noise = torch.randn_like(target_image, device=device)
        bsz = target_image.shape[0]
        timesteps = self.get_timestep(bsz, device)

        # Add noise according to flow matching.
        sigmas = self.get_sd3_sigmas(
            timesteps=timesteps,
            device=device,
            n_dim=target_image.ndim,
            dtype=dtype,
        )
        noisy_image = sigmas * noise + (1.0 - sigmas) * target_image

        # This is the flow-matching target for vanilla SD3.
        target = target_image

        # SSL constraints for CLAP and vocal_latent_channel2
        all_ssl_hiden_states = None
        if mert_ssl_hidden_states is not None or mhubert_ssl_hidden_states is not None:
            all_ssl_hiden_states = []
            if mert_ssl_hidden_states is not None:
                all_ssl_hiden_states.append(mert_ssl_hidden_states)
            if mhubert_ssl_hidden_states is not None:
                all_ssl_hiden_states.append(mhubert_ssl_hidden_states)

        # N x H -> N x c x W x H
        x = noisy_image

        # Step 5: Predict noise
        transformer_output = self.transformers(
            hidden_states=x,
            attention_mask=attention_mask,
            encoder_text_hidden_states=encoder_text_hidden_states,
            text_attention_mask=text_attention_mask,
            speaker_embeds=speaker_embds,
            lyric_token_idx=lyric_token_ids,
            lyric_mask=lyric_mask,
            timestep=timesteps.to(device).to(dtype),
            ssl_hidden_states=all_ssl_hiden_states,
        )
        model_pred = transformer_output.sample
        proj_losses = transformer_output.proj_losses

        # Follow: Section 5 of https://arxiv.org/abs/2206.00364.
        # Preconditioning of the model outputs.
        model_pred = model_pred * (-sigmas) + noisy_image

        # Compute loss. Only calculate loss where chunk_mask is 1 and there is no padding
        # N x T x 64
        # N x T -> N x c x W x T
        mask = (
            attention_mask.unsqueeze(1)
            .unsqueeze(1)
            .expand(-1, target_image.shape[1], target_image.shape[2], -1)
        )

        selected_model_pred = (model_pred * mask).reshape(bsz, -1).contiguous()
        selected_target = (target * mask).reshape(bsz, -1).contiguous()

        loss = F.mse_loss(selected_model_pred, selected_target, reduction="none")
        loss = loss.mean(1)
        loss = loss * mask.reshape(bsz, -1).mean(1)
        loss = loss.mean()

        # Extra safety: if something ever nukes the grad graph again, fail loudly.
        if not loss.requires_grad:
            logger.error(
                f"[run_step] loss has no grad at global_step={self.global_step}, "
                f"batch_idx={batch_idx}; something disabled grad tracking "
                "around the training step."
            )
            raise RuntimeError(
                "Loss tensor does not require grad in run_step; likely an interaction "
                "with a no_grad/autocast context."
            )

        prefix = "train"

        self.log(
            f"{prefix}/denoising_loss",
            loss,
            on_step=True,
            on_epoch=False,
            prog_bar=True,
        )

        total_proj_loss = 0.0
        for k, v in proj_losses:
            self.log(
                f"{prefix}/{k}_loss",
                v,
                on_step=True,
                on_epoch=False,
                prog_bar=True,
            )
            total_proj_loss += v

        if len(proj_losses) > 0:
            total_proj_loss = total_proj_loss / len(proj_losses)

        loss = loss + total_proj_loss * self.ssl_coeff
        self.log(
            f"{prefix}/loss",
            loss,
            on_step=True,
            on_epoch=False,
            prog_bar=True,
        )

        # Log learning rate if scheduler exists
        if self.lr_schedulers() is not None:
            learning_rate = self.lr_schedulers().get_last_lr()[0]
            self.log(
                f"{prefix}/learning_rate",
                learning_rate,
                on_step=True,
                on_epoch=False,
                prog_bar=True,
            )

        return loss

    # The below version of run_step includes diffusion_previews. They were nuked due to causing errors as soon as plot_step was invoked.
    # def run_step(self, batch, batch_idx):
        # # ------------------------------------------------------------------
        # # 1) Optional eval preview under no_grad
        # # ------------------------------------------------------------------
        # try:
            # every_plot = getattr(self.hparams, "every_plot_step", 0)

            # if (
                # every_plot
                # and self.global_step > 0
                # and (self.global_step % every_plot) == 0
            # ):
                # # Run plotting / diffusion fully under no_grad so it cannot
                # # interfere with the actual training graph.
                # with torch.no_grad():
                    # self.plot_step(batch, batch_idx)
        # except Exception as e:
            # logger.warning(
                # f"[run_step] plot_step failed at global_step={self.global_step}, "
                # f"batch_idx={batch_idx}: {e}"
            # )

        # # ------------------------------------------------------------------
        # # 2) Actual training step, with gradients forced ON
        # # ------------------------------------------------------------------
        # with torch.set_grad_enabled(True):
            # (
                # keys,
                # target_latents,
                # attention_mask,
                # encoder_text_hidden_states,
                # text_attention_mask,
                # speaker_embds,
                # lyric_token_ids,
                # lyric_mask,
                # mert_ssl_hidden_states,
                # mhubert_ssl_hidden_states,
            # ) = self.preprocess(batch, train=True)

            # target_image = target_latents
            # device = target_image.device
            # dtype = target_image.dtype
            # # Step 1: Generate random noise, initialize settings
            # noise = torch.randn_like(target_image, device=device)
            # bsz = target_image.shape[0]
            # timesteps = self.get_timestep(bsz, device)

            # # Add noise according to flow matching.
            # sigmas = self.get_sd3_sigmas(
                # timesteps=timesteps,
                # device=device,
                # n_dim=target_image.ndim,
                # dtype=dtype,
            # )
            # noisy_image = sigmas * noise + (1.0 - sigmas) * target_image

            # # This is the flow-matching target for vanilla SD3.
            # target = target_image

            # # SSL constraints for CLAP and vocal_latent_channel2
            # all_ssl_hiden_states = None
            # if mert_ssl_hidden_states is not None or mhubert_ssl_hidden_states is not None:
                # all_ssl_hiden_states = []
                # if mert_ssl_hidden_states is not None:
                    # all_ssl_hiden_states.append(mert_ssl_hidden_states)
                # if mhubert_ssl_hidden_states is not None:
                    # all_ssl_hiden_states.append(mhubert_ssl_hidden_states)

            # # N x H -> N x c x W x H
            # x = noisy_image
            # # Step 5: Predict noise
            # transformer_output = self.transformers(
                # hidden_states=x,
                # attention_mask=attention_mask,
                # encoder_text_hidden_states=encoder_text_hidden_states,
                # text_attention_mask=text_attention_mask,
                # speaker_embeds=speaker_embds,
                # lyric_token_idx=lyric_token_ids,
                # lyric_mask=lyric_mask,
                # timestep=timesteps.to(device).to(dtype),
                # ssl_hidden_states=all_ssl_hiden_states,
            # )
            # model_pred = transformer_output.sample
            # proj_losses = transformer_output.proj_losses

            # # Follow: Section 5 of https://arxiv.org/abs/2206.00364.
            # # Preconditioning of the model outputs.
            # model_pred = model_pred * (-sigmas) + noisy_image

            # # Compute loss. Only calculate loss where chunk_mask is 1 and there is no padding
            # # N x T x 64
            # # N x T -> N x c x W x T
            # mask = (
                # attention_mask.unsqueeze(1)
                # .unsqueeze(1)
                # .expand(-1, target_image.shape[1], target_image.shape[2], -1)
            # )

            # selected_model_pred = (model_pred * mask).reshape(bsz, -1).contiguous()
            # selected_target = (target * mask).reshape(bsz, -1).contiguous()

            # loss = F.mse_loss(selected_model_pred, selected_target, reduction="none")
            # loss = loss.mean(1)
            # loss = loss * mask.reshape(bsz, -1).mean(1)
            # loss = loss.mean()

            # prefix = "train"

            # self.log(
                # f"{prefix}/denoising_loss",
                # loss,
                # on_step=True,
                # on_epoch=False,
                # prog_bar=True,
            # )

            # total_proj_loss = 0.0
            # for k, v in proj_losses:
                # self.log(
                    # f"{prefix}/{k}_loss",
                    # v,
                    # on_step=True,
                    # on_epoch=False,
                    # prog_bar=True,
                # )
                # total_proj_loss += v

            # if len(proj_losses) > 0:
                # total_proj_loss = total_proj_loss / len(proj_losses)

            # loss = loss + total_proj_loss * self.ssl_coeff
            # self.log(
                # f"{prefix}/loss",
                # loss,
                # on_step=True,
                # on_epoch=False,
                # prog_bar=True,
            # )

            # # Sanity check: if this ever trips again, we *know* gradients are off.
            # if not loss.requires_grad:
                # logger.error(
                    # f"[run_step] loss has no grad at global_step={self.global_step}, "
                    # f"batch_idx={batch_idx}; torch.is_grad_enabled()={torch.is_grad_enabled()}"
                # )
                # raise RuntimeError(
                    # "Loss tensor does not require grad in run_step; likely an "
                    # "interaction with a no_grad/autocast context."
                # )

            # # Log learning rate if scheduler exists
            # if self.lr_schedulers() is not None:
                # learning_rate = self.lr_schedulers().get_last_lr()[0]
                # self.log(
                    # f"{prefix}/learning_rate",
                    # learning_rate,
                    # on_step=True,
                    # on_epoch=False,
                    # prog_bar=True,
                # )

            # # with torch.autograd.detect_anomaly():
            # #     self.manual_backward(loss)
            # return loss

    def _save_lora_adapter(self, tag: str) -> None:
        """
        Save the current LoRA adapter both into the run's checkpoint folder
        and into a stable <APP_DIR>/custom_lora/<adapter_name> folder.

        This is a small, custom save that avoids Lightning's huge .ckpt blobs.
        """
        log_dir = getattr(self.logger, "log_dir", None)
        if not log_dir:
            return

        # Per-run checkpoint-style folder under the logger dir
        run_ckpt_name = f"{tag}_lora"
        run_ckpt_dir = os.path.join(log_dir, "checkpoints", run_ckpt_name)
        os.makedirs(run_ckpt_dir, exist_ok=True)
        self.transformers.save_lora_adapter(
            run_ckpt_dir, adapter_name=self.adapter_name
        )

        # Stable copy under <APP_DIR>/custom_lora/<adapter_name>
        app_dir = Path(__file__).resolve().parent
        custom_root = app_dir / "custom_lora" / self.adapter_name
        os.makedirs(custom_root, exist_ok=True)
        self.transformers.save_lora_adapter(
            str(custom_root), adapter_name=self.adapter_name
        )

        logger.info(
            f"[save_lora_adapter] saved LoRA adapter '{self.adapter_name}' "
            f"to run_ckpt_dir={run_ckpt_dir} and custom_root={custom_root}"
        )

    def training_step(self, batch, batch_idx):
        logger.info(
            f"[training_step] enter batch_idx={batch_idx}, "
            f"global_step={self.global_step}"
        )
        out = self.run_step(batch, batch_idx)
        logger.info(
            f"[training_step] done batch_idx={batch_idx}, "
            f"global_step={self.global_step}"
        )

        # Optionally save LoRA adapters every N global steps, without invoking
        # Lightning's full checkpoint machinery.
        save_every = getattr(self.hparams, "lora_save_every", 0)
        if save_every and self.global_step > 0 and (self.global_step % save_every) == 0:
            tag = f"epoch={self.current_epoch}-step={self.global_step}"
            self._save_lora_adapter(tag)

        return out

    def on_train_end(self):
        """
        Always save a final LoRA adapter when training finishes.
        This does not rely on Lightning checkpoints.
        """
        logger.info(
            f"[on_train_end] training finished at "
            f"epoch={self.current_epoch}, step={self.global_step}; "
            f"saving final LoRA adapter '{self.adapter_name}'"
        )

        tag = f"final-epoch={self.current_epoch}-step={self.global_step}"
        self._save_lora_adapter(tag)

        logger.info(
            f"[on_train_end] saved final LoRA adapter '{self.adapter_name}'"
        )

    @torch.no_grad()
    def diffusion_process(
        self,
        duration,
        encoder_text_hidden_states,
        text_attention_mask,
        speaker_embds,
        lyric_token_ids,
        lyric_mask,
        random_generators=None,
        infer_steps=60,
        guidance_scale=15.0,
        omega_scale=10.0,
    ):

        do_classifier_free_guidance = True
        if guidance_scale == 0.0 or guidance_scale == 1.0:
            do_classifier_free_guidance = False

        device = encoder_text_hidden_states.device
        dtype = encoder_text_hidden_states.dtype
        bsz = encoder_text_hidden_states.shape[0]

        scheduler = FlowMatchEulerDiscreteScheduler(
            num_train_timesteps=1000,
            shift=3.0,
        )

        frame_length = int(duration * 44100 / 512 / 8)
        timesteps, num_inference_steps = retrieve_timesteps(
            scheduler, num_inference_steps=infer_steps, device=device, timesteps=None
        )

        target_latents = randn_tensor(
            shape=(bsz, 8, 16, frame_length),
            generator=random_generators,
            device=device,
            dtype=dtype,
        )
        attention_mask = torch.ones(bsz, frame_length, device=device, dtype=dtype)
        if do_classifier_free_guidance:
            attention_mask = torch.cat([attention_mask] * 2, dim=0)
            encoder_text_hidden_states = torch.cat(
                [
                    encoder_text_hidden_states,
                    torch.zeros_like(encoder_text_hidden_states),
                ],
                0,
            )
            text_attention_mask = torch.cat([text_attention_mask] * 2, dim=0)

            speaker_embds = torch.cat(
                [speaker_embds, torch.zeros_like(speaker_embds)], 0
            )

            lyric_token_ids = torch.cat(
                [lyric_token_ids, torch.zeros_like(lyric_token_ids)], 0
            )
            lyric_mask = torch.cat([lyric_mask, torch.zeros_like(lyric_mask)], 0)

        momentum_buffer = MomentumBuffer()

        for i, t in tqdm(enumerate(timesteps), total=num_inference_steps):
            # expand the latents if we are doing classifier free guidance
            latents = target_latents
            latent_model_input = (
                torch.cat([latents] * 2) if do_classifier_free_guidance else latents
            )
            timestep = t.expand(latent_model_input.shape[0])
            noise_pred = self.transformers(
                hidden_states=latent_model_input,
                attention_mask=attention_mask,
                encoder_text_hidden_states=encoder_text_hidden_states,
                text_attention_mask=text_attention_mask,
                speaker_embeds=speaker_embds,
                lyric_token_idx=lyric_token_ids,
                lyric_mask=lyric_mask,
                timestep=timestep,
            ).sample

            if do_classifier_free_guidance:
                noise_pred_with_cond, noise_pred_uncond = noise_pred.chunk(2)
                noise_pred = apg_forward(
                    pred_cond=noise_pred_with_cond,
                    pred_uncond=noise_pred_uncond,
                    guidance_scale=guidance_scale,
                    momentum_buffer=momentum_buffer,
                )

            target_latents = scheduler.step(
                model_output=noise_pred,
                timestep=t,
                sample=target_latents,
                return_dict=False,
                omega=omega_scale,
            )[0]

        return target_latents

    def predict_step(self, batch):
        (
            keys,
            target_latents,
            attention_mask,
            encoder_text_hidden_states,
            text_attention_mask,
            speaker_embds,
            lyric_token_ids,
            lyric_mask,
            mert_ssl_hidden_states,
            mhubert_ssl_hidden_states,
        ) = self.preprocess(batch, train=False)

        infer_steps = 60
        guidance_scale = 15.0
        omega_scale = 10.0
        seed_num = 1234
        random.seed(seed_num)
        bsz = target_latents.shape[0]
        random_generators = [torch.Generator(device=self.device) for _ in range(bsz)]
        seeds = []
        for i in range(bsz):
            seed = random.randint(0, 2**32 - 1)
            random_generators[i].manual_seed(seed)
            seeds.append(seed)
        duration = 240  # Fixed duration (24 * 10)
        pred_latents = self.diffusion_process(
            duration=duration,
            encoder_text_hidden_states=encoder_text_hidden_states,
            text_attention_mask=text_attention_mask,
            speaker_embds=speaker_embds,
            lyric_token_ids=lyric_token_ids,
            lyric_mask=lyric_mask,
            random_generators=random_generators,
            infer_steps=infer_steps,
            guidance_scale=guidance_scale,
            omega_scale=omega_scale,
        )

        audio_lengths = batch["wav_lengths"]
        sr, pred_wavs = self.dcae.decode(
            pred_latents, audio_lengths=audio_lengths, sr=48000
        )
        return {
            "target_wavs": batch["target_wavs"],
            "pred_wavs": pred_wavs,
            "keys": keys,
            "prompts": batch["prompts"],
            "candidate_lyric_chunks": batch["candidate_lyric_chunks"],
            "sr": sr,
            "seeds": seeds,
        }

    def construct_lyrics(self, candidate_lyric_chunk):
        lyrics = []
        for chunk in candidate_lyric_chunk:
            lyrics.append(chunk["lyric"])

        lyrics = "\n".join(lyrics)
        return lyrics

    def plot_step(self, batch, batch_idx):
        global_step = self.global_step

        # Only run plotting:
        #  - after we've done at least one optimizer step
        #  - every `every_plot_step` steps
        #  - on GPU 0 (if we even have a device index)
        if global_step == 0:
            return

        if global_step % self.hparams.every_plot_step != 0:
            return

        # In single-GPU / non-DDP runs, just check our own device index.
        device_index = getattr(self.device, "index", None)
        if device_index is not None and device_index != 0:
            return

        results = self.predict_step(batch)

        target_wavs = results["target_wavs"]
        pred_wavs = results["pred_wavs"]
        keys = results["keys"]
        prompts = results["prompts"]
        candidate_lyric_chunks = results["candidate_lyric_chunks"]
        sr = results["sr"]
        seeds = results["seeds"]
        i = 0
        for key, target_wav, pred_wav, prompt, candidate_lyric_chunk, seed in zip(
            keys, target_wavs, pred_wavs, prompts, candidate_lyric_chunks, seeds
        ):
            key = key
            prompt = prompt
            lyric = self.construct_lyrics(candidate_lyric_chunk)
            key_prompt_lyric = f"# KEY\n\n{key}\n\n\n# PROMPT\n\n{prompt}\n\n\n# LYRIC\n\n{lyric}\n\n# SEED\n\n{seed}\n\n"
            log_dir = self.logger.log_dir
            save_dir = f"{log_dir}/eval_results/step_{self.global_step}"
            if not os.path.exists(save_dir):
                os.makedirs(save_dir, exist_ok=True)
            torchaudio.save(
                f"{save_dir}/target_wav_{key}_{i}.wav", target_wav.float().cpu(), sr
            )
            torchaudio.save(
                f"{save_dir}/pred_wav_{key}_{i}.wav", pred_wav.float().cpu(), sr
            )
            with open(
                f"{save_dir}/key_prompt_lyric_{key}_{i}.txt", "w", encoding="utf-8"
            ) as f:
                f.write(key_prompt_lyric)
            i += 1


def main(args):
    model = Pipeline(
        learning_rate=args.learning_rate,
        num_workers=args.num_workers,
        shift=args.shift,
        max_steps=args.max_steps,
        every_plot_step=args.every_plot_step,
        dataset_path=args.dataset_path,
        checkpoint_dir=args.checkpoint_dir,
        adapter_name=args.exp_name,
        lora_config_path=args.lora_config_path,
        ssl_coeff=args.ssl_coeff,
        instrumental_only=args.instrumental_only,
        max_audio_seconds=args.max_audio_seconds,
        # Save LoRA adapters every N training steps, instead of relying on
        # Lightning's full checkpointing.
        lora_save_every=args.every_n_train_steps,
    )

    checkpoint_callback = ModelCheckpoint(
        dirpath="./ace_training/checkpoints",
        filename="latest",
        save_top_k=1,
        every_n_train_steps=args.every_n_train_steps,
        save_last=True,
        monitor=None,
    )

    # add datetime str to version
    logger_callback = TensorBoardLogger(
        version=datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + args.exp_name,
        save_dir=args.logger_dir,
    )

    # On Windows / single-GPU we don't want DDP+NCCL.
    # For devices == 1 and a single node, use Lightning's "auto" strategy
    # so it runs as a single-process trainer without distributed.
    if args.devices <= 1 and args.num_nodes == 1:
        pl_strategy = "auto"
    else:
        pl_strategy = "ddp_find_unused_parameters_true"

    trainer = Trainer(
        accelerator="gpu",
        devices=args.devices,
        num_nodes=args.num_nodes,
        precision=args.precision,
        accumulate_grad_batches=args.accumulate_grad_batches,
        strategy=pl_strategy,
        max_epochs=args.epochs,
        max_steps=args.max_steps,
        log_every_n_steps=1,
        logger=logger_callback,
        callbacks=[checkpoint_callback],
        enable_checkpointing=True,
        gradient_clip_val=args.gradient_clip_val,
        gradient_clip_algorithm=args.gradient_clip_algorithm,
        reload_dataloaders_every_n_epochs=args.reload_dataloaders_every_n_epochs,
        val_check_interval=args.val_check_interval,
    )

    trainer.fit(
        model,
        ckpt_path=args.ckpt_path,
    )


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument("--num_nodes", type=int, default=1)
    args.add_argument("--shift", type=float, default=3.0)
    args.add_argument("--learning_rate", type=float, default=1e-4)
    args.add_argument("--num_workers", type=int, default=8)

    # Stop training by epochs by default; this is what we’ll expose in the UI
    args.add_argument("--epochs", type=int, default=20)

    # By default, do NOT stop by max_steps (Lightning treats -1 as "no step limit")
    args.add_argument("--max_steps", type=int, default=-1)

    args.add_argument("--every_n_train_steps", type=int, default=50)
    args.add_argument("--dataset_path", type=str, default="./zh_lora_dataset")
    args.add_argument("--exp_name", type=str, default="chinese_rap_lora")
    args.add_argument("--precision", type=str, default="32")
    args.add_argument("--accumulate_grad_batches", type=int, default=1)
    args.add_argument("--devices", type=int, default=1)
    args.add_argument("--logger_dir", type=str, default="./exps/logs/")
    args.add_argument("--ckpt_path", type=str, default=None)
    args.add_argument("--checkpoint_dir", type=str, default=None)
    args.add_argument("--gradient_clip_val", type=float, default=0.5)
    args.add_argument("--gradient_clip_algorithm", type=str, default="norm")
    args.add_argument("--reload_dataloaders_every_n_epochs", type=int, default=1)
    args.add_argument("--every_plot_step", type=int, default=2000)
    args.add_argument("--val_check_interval", type=int, default=None)
    args.add_argument("--lora_config_path", type=str, default="config/zh_rap_lora_config.json")

    # New knobs
    args.add_argument("--ssl_coeff", type=float, default=1.0)
    args.add_argument("--max_audio_seconds", type=float, default=60.0)
    args.add_argument(
        "--instrumental_only",
        action="store_true",
        help=(
            "Treat dataset as instrumental / no vocals. "
            "LoRA layers attached to lyric and speaker-specific blocks will be frozen."
        ),
    )

    args = args.parse_args()
    main(args)