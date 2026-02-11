import React, { useState, useEffect, useRef } from 'react';
import { GraduationCap, Play, Pause, Square, RotateCw, Download, HelpCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toolsApi, preferencesApi } from '../services/api';

const POLL_INTERVAL_MS = 2000;
const MODEL_POLL_MS = 1500;

interface TrainingPanelProps {
  onTracksUpdated?: () => void | Promise<void>;
}

export const TrainingPanel: React.FC<TrainingPanelProps> = ({ onTracksUpdated: _onTracksUpdated }) => {
  const { t } = useTranslation();
  const [datasetPath, setDatasetPath] = useState('');
  const [expName, setExpName] = useState('');
  const [loraConfigPath, setLoraConfigPath] = useState('');
  const [configs, setConfigs] = useState<Array<{ file: string; label: string }>>([]);
  const [defaultConfig, setDefaultConfig] = useState('');
  const [maxSteps, setMaxSteps] = useState(50000);
  const [maxEpochs, setMaxEpochs] = useState(20);
  const [learningRate, setLearningRate] = useState(1e-4);
  const [maxAudioSeconds, setMaxAudioSeconds] = useState(60);
  const [sslCoeff, setSslCoeff] = useState(1.0);
  const [instrumentalOnly, setInstrumentalOnly] = useState(false);
  const [loraSaveEvery, setLoraSaveEvery] = useState(50);
  const [devices, setDevices] = useState(1);
  const [precision, setPrecision] = useState('32');
  const [accumulateGradBatches, setAccumulateGradBatches] = useState(1);
  const [gradientClipVal, setGradientClipVal] = useState(0.5);
  const [gradientClipAlgorithm, setGradientClipAlgorithm] = useState('norm');
  const [reloadDataloadersEveryNEpochs, setReloadDataloadersEveryNEpochs] = useState(1);
  const [valCheckInterval, setValCheckInterval] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showLoraHelp, setShowLoraHelp] = useState(false);
  const [datasetFiles, setDatasetFiles] = useState<FileList | null>(null);
  const [statusText, setStatusText] = useState('');
  const [progress, setProgress] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const [paused, setPaused] = useState(false);
  const [loadingConfigs, setLoadingConfigs] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [returncode, setReturncode] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ACE-Step model status for training
  const [aceReady, setAceReady] = useState<boolean | null>(null);
  const [aceState, setAceState] = useState('');
  const [aceMessage, setAceMessage] = useState('');
  const [aceDownloadProgress, setAceDownloadProgress] = useState<number | null>(null);
  const acePollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    toolsApi.trainConfigs()
      .then((res) => {
        if (res.ok && res.configs) {
          setConfigs(res.configs);
          if (res.default) {
            setDefaultConfig(res.default);
            setLoraConfigPath(res.default);
          }
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoadingConfigs(false));
  }, []);

  useEffect(() => {
    preferencesApi.get()
      .then((prefs) => {
        const t = prefs.training as Record<string, unknown> | undefined;
        if (t?.dataset_path != null) setDatasetPath(String(t.dataset_path));
        if (t?.exp_name != null) setExpName(String(t.exp_name));
        if (t?.lora_config_path != null) setLoraConfigPath(String(t.lora_config_path));
        if (t?.max_steps != null) setMaxSteps(Number(t.max_steps));
        if (t?.max_epochs != null) setMaxEpochs(Number(t.max_epochs));
        if (t?.learning_rate != null) setLearningRate(Number(t.learning_rate));
      })
      .catch(() => { });
  }, []);

  useEffect(() => {
    toolsApi.aceModelStatus()
      .then((r) => {
        setAceReady(r.ready);
        setAceState(r.state || '');
        setAceMessage(r.message || '');
      })
      .catch(() => setAceReady(false));
  }, []);

  useEffect(() => {
    if (aceState !== 'downloading') {
      setAceDownloadProgress(null);
      if (acePollRef.current) {
        clearInterval(acePollRef.current);
        acePollRef.current = null;
      }
      return;
    }
    const poll = () => {
      toolsApi.getProgress()
        .then((p) => {
          if (p.stage === 'ace_model_download') {
            setAceDownloadProgress(p.fraction);
          }
        })
        .catch(() => { });
      toolsApi.aceModelStatus()
        .then((r) => {
          setAceReady(r.ready);
          setAceState(r.state || '');
          setAceMessage(r.message || '');
        })
        .catch(() => { });
    };
    poll();
    acePollRef.current = setInterval(poll, MODEL_POLL_MS);
    return () => {
      if (acePollRef.current) clearInterval(acePollRef.current);
    };
  }, [aceState]);

  useEffect(() => {
    if (!running && !paused) return;
    const poll = () => {
      toolsApi.trainStatus()
        .then((s) => {
          setRunning(!!s.running);
          setPaused(!!s.paused);
          if (s.last_message) setStatusText(s.last_message);
          if (typeof (s as { returncode?: number }).returncode === 'number') {
            setReturncode((s as { returncode: number }).returncode);
          }
          if (typeof s.progress === 'number') setProgress(s.progress);
          else if (typeof s.current_step === 'number' && typeof s.max_steps === 'number' && s.max_steps > 0)
            setProgress(s.current_step / s.max_steps);
          else if (typeof s.current_epoch === 'number' && typeof s.max_epochs === 'number' && s.max_epochs > 0)
            setProgress(s.current_epoch / s.max_epochs);
        })
        .catch(() => { });
    };
    poll();
    pollRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [running, paused]);

  const handleStart = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setReturncode(null);
    if (aceState === 'downloading') return;
    if (!aceReady && aceState !== 'ready') {
      toolsApi.aceModelEnsure().then(() => {
        setAceState('downloading');
        setAceMessage(t('training.downloading_model'));
      }).catch((err) => setError(err instanceof Error ? err.message : t('training.error_start_failed')));
      return;
    }
    const hasPath = datasetPath.trim().length > 0;
    const hasFiles = datasetFiles && datasetFiles.length > 0;
    if (!hasPath && !hasFiles) {
      setError(t('training.error_select_dataset'));
      return;
    }
    const formData = new FormData();
    if (datasetPath.trim()) formData.set('dataset_path', datasetPath.trim());
    if (datasetFiles) {
      for (let i = 0; i < datasetFiles.length; i++) {
        formData.append('dataset_files', datasetFiles[i]);
      }
    }
    formData.set('exp_name', expName.trim() || 'lora_exp');
    formData.set('lora_config_path', loraConfigPath || defaultConfig || '');
    formData.set('max_steps', String(maxSteps));
    formData.set('max_epochs', String(maxEpochs));
    formData.set('learning_rate', String(learningRate));
    formData.set('max_audio_seconds', String(maxAudioSeconds));
    formData.set('ssl_coeff', String(sslCoeff));
    formData.set('devices', String(devices));
    formData.set('lora_save_every', String(loraSaveEvery));
    formData.set('precision', precision);
    formData.set('accumulate_grad_batches', String(accumulateGradBatches));
    formData.set('gradient_clip_val', String(gradientClipVal));
    formData.set('gradient_clip_algorithm', gradientClipAlgorithm);
    formData.set('reload_dataloaders_every_n_epochs', String(reloadDataloadersEveryNEpochs));
    if (valCheckInterval.trim()) formData.set('val_check_interval', valCheckInterval.trim());
    if (instrumentalOnly) formData.set('instrumental_only', '1');
    try {
      await toolsApi.trainStart(formData);
      await preferencesApi.update({
        training: {
          dataset_path: datasetPath.trim(),
          exp_name: expName.trim() || 'lora_exp',
          lora_config_path: loraConfigPath || defaultConfig || '',
          max_steps: maxSteps,
          max_epochs: maxEpochs,
          learning_rate: learningRate,
        },
      });
      setRunning(true);
      setPaused(false);
      setStatusText(t('training.training_running'));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('training.error_start_failed'));
    }
  };

  const handlePause = () => {
    toolsApi.trainPause().then((r) => { if (!r.ok) setError(r.error || ''); }).catch((e) => setError(e.message));
  };
  const handleResume = () => {
    toolsApi.trainResume().then((r) => { if (!r.ok) setError(r.error || ''); }).catch((e) => setError(e.message));
  };
  const handleCancel = () => {
    toolsApi.trainCancel().then((r) => {
      if (r.ok) setRunning(false); else setError(r.error || '');
    }).catch((e) => setError(e.message));
  };

  const handleFolderPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    setDatasetFiles(files && files.length ? files : null);
    // Backend expects dataset_path = folder name under training_datasets. Derive from first file's webkitRelativePath.
    if (files && files.length > 0) {
      const first = files[0] as File & { webkitRelativePath?: string };
      const rel = first.webkitRelativePath || (first as unknown as { path?: string }).path || '';
      const folderName = rel.split('/')[0] || '';
      setDatasetPath(folderName);
    } else {
      setDatasetPath('');
    }
  };

  const startModelDownload = () => {
    toolsApi.aceModelEnsure().then(() => {
      setAceState('downloading');
      setAceMessage(t('training.downloading_model'));
    }).catch((e) => setError(e.message));
  };

  const canStartTraining = aceReady === true && !running && aceState !== 'downloading';
  const showDownloadButton = aceReady === false && aceState !== 'downloading';

  const getStatusDisplay = () => {
    if (returncode != null && !running && !paused) {
      return returncode === 0
        ? (statusText || t('training.training_finished'))
        : (statusText || t('training.training_error', { code: returncode }));
    }
    return statusText || t('training.idle');
  };

  return (
    <div className="h-full flex flex-col overflow-y-auto p-4 text-zinc-800 dark:text-zinc-200">
      <div className="flex items-center gap-2 mb-4">
        <GraduationCap className="w-6 h-6 text-pink-500" />
        <h2 className="text-lg font-semibold">{t('training.title')}</h2>
      </div>
      <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-4">
        {t('training.description')}
      </p>

      {aceReady === false && aceState !== 'downloading' && (
        <div className="mb-4 p-3 rounded-lg bg-amber-500/10 text-amber-700 dark:text-amber-400 text-sm">
          <p className="font-medium mb-1">{t('training.model_not_downloaded')}</p>
          <p className="mb-2">{t('training.model_download_hint')}</p>
          <button
            type="button"
            onClick={startModelDownload}
            className="inline-flex items-center gap-2 rounded-lg bg-amber-500 text-white px-3 py-2 text-sm font-medium hover:bg-amber-600"
          >
            <Download size={16} /> {t('training.download_training_model')}
          </button>
        </div>
      )}
      {aceState === 'downloading' && (
        <div className="mb-4 p-3 rounded-lg bg-blue-500/10 text-blue-700 dark:text-blue-400 text-sm">
          <p className="font-medium mb-2">{t('training.downloading_model')}</p>
          <div className="w-full h-2 rounded-full bg-zinc-200 dark:bg-zinc-700 overflow-hidden">
            <div
              className="h-full bg-pink-500 transition-all duration-300"
              style={{ width: aceDownloadProgress != null ? `${aceDownloadProgress * 100}%` : '100%' }}
            />
          </div>
        </div>
      )}

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-500/10 text-red-600 dark:text-red-400 text-sm">
          {error}
        </div>
      )}

      <form onSubmit={handleStart} className="flex flex-col gap-4">
        <div>
          <label className="block text-sm font-medium mb-1">{t('training.dataset')}</label>
          <div className="flex gap-2">
            <input
              type="text"
              value={datasetPath}
              onChange={(e) => { setDatasetPath(e.target.value); setDatasetFiles(null); }}
              placeholder={t('training.dataset_placeholder')}
              className="flex-1 rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
            />
            <input
              ref={fileInputRef}
              type="file"
              webkitdirectory="true"
              directory="true"
              multiple
              onChange={handleFolderPick}
              className="hidden"
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="rounded-lg border border-zinc-300 dark:border-zinc-600 px-3 py-2 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-700"
            >
              {t('training.browse')}
            </button>
          </div>
          {datasetFiles && (
            <p className="text-xs text-zinc-500 mt-1">{t('training.files_selected', { count: datasetFiles.length })}</p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">{t('training.exp_name')}</label>
          <input
            type="text"
            value={expName}
            onChange={(e) => setExpName(e.target.value)}
            placeholder={t('training.exp_name_placeholder')}
            className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
          />
        </div>

        <div>
          <div className="flex items-center gap-2 mb-1">
            <label className="block text-sm font-medium">{t('training.lora_config')}</label>
            <button
              type="button"
              title={t('training.lora_config_help')}
              onClick={() => setShowLoraHelp(!showLoraHelp)}
              className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
            >
              <HelpCircle size={14} />
            </button>
          </div>
          {showLoraHelp && (
            <div className="mb-2 p-3 rounded-lg bg-zinc-100 dark:bg-zinc-800 text-xs text-zinc-600 dark:text-zinc-400 space-y-2">
              <p><strong>{t('training.lora_help_light')}</strong></p>
              <p><strong>{t('training.lora_help_base')}</strong></p>
              <p><strong>{t('training.lora_help_extended')}</strong></p>
              <p><strong>{t('training.lora_help_deep')}</strong></p>
              <p><em>{t('training.lora_help_default')}</em></p>
            </div>
          )}
          <select
            value={loraConfigPath || defaultConfig}
            onChange={(e) => setLoraConfigPath(e.target.value)}
            className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
          >
            {loadingConfigs ? <option>{t('training.loading_configs')}</option> : configs.map((c) => (
              <option key={c.file} value={c.file}>{c.label}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">{t('training.max_steps')}</label>
          <input
            type="number"
            min={100}
            step={100}
            value={maxSteps}
            onChange={(e) => setMaxSteps(Number(e.target.value))}
            className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">{t('training.max_epochs')}</label>
          <input
            type="number"
            min={1}
            value={maxEpochs}
            onChange={(e) => setMaxEpochs(Number(e.target.value))}
            className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">{t('training.learning_rate')}</label>
          <input
            type="number"
            step={1e-6}
            value={learningRate}
            onChange={(e) => setLearningRate(Number(e.target.value))}
            className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">{t('training.max_clip_seconds')}</label>
          <input
            type="number"
            min={4}
            max={120}
            value={maxAudioSeconds}
            onChange={(e) => setMaxAudioSeconds(Number(e.target.value))}
            className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">{t('training.ssl_loss_weight')}</label>
          <input
            type="number"
            min={0}
            max={2}
            step={0.1}
            value={sslCoeff}
            onChange={(e) => setSslCoeff(Number(e.target.value))}
            className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
          />
          <p className="text-xs text-zinc-500 mt-1">{t('training.ssl_note')}</p>
        </div>

        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={instrumentalOnly}
            onChange={(e) => setInstrumentalOnly(e.target.checked)}
          />
          <span className="text-sm">{t('training.instrumental_dataset')}</span>
        </label>

        <div>
          <label className="block text-sm font-medium mb-1">{t('training.save_lora_every')}</label>
          <input
            type="number"
            min={0}
            step={10}
            value={loraSaveEvery}
            onChange={(e) => setLoraSaveEvery(Number(e.target.value))}
            className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
          />
        </div>

        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="text-sm text-pink-500 hover:underline"
        >
          {showAdvanced ? t('training.hide_advanced') : t('training.show_advanced')}
        </button>

        {showAdvanced && (
          <>
            <div>
              <label className="block text-sm font-medium mb-1">{t('training.precision')}</label>
              <select
                value={precision}
                onChange={(e) => setPrecision(e.target.value)}
                className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
              >
                <option value="32">{t('training.precision_32')}</option>
                <option value="16-mixed">{t('training.precision_16')}</option>
                <option value="bf16-mixed">{t('training.precision_bf16')}</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">{t('training.grad_accumulation')}</label>
              <input
                type="number"
                min={1}
                value={accumulateGradBatches}
                onChange={(e) => setAccumulateGradBatches(Number(e.target.value))}
                className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">{t('training.gradient_clip')}</label>
              <input
                type="number"
                min={0}
                step={0.1}
                value={gradientClipVal}
                onChange={(e) => setGradientClipVal(Number(e.target.value))}
                className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">{t('training.clip_algorithm')}</label>
              <select
                value={gradientClipAlgorithm}
                onChange={(e) => setGradientClipAlgorithm(e.target.value)}
                className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
              >
                <option value="norm">{t('training.clip_norm')}</option>
                <option value="value">{t('training.clip_value')}</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">{t('training.reload_dataloader')}</label>
              <input
                type="number"
                min={0}
                value={reloadDataloadersEveryNEpochs}
                onChange={(e) => setReloadDataloadersEveryNEpochs(Number(e.target.value))}
                className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">{t('training.val_check_interval')}</label>
              <input
                type="text"
                value={valCheckInterval}
                onChange={(e) => setValCheckInterval(e.target.value)}
                placeholder={t('training.val_check_placeholder')}
                className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">{t('training.devices')}</label>
              <input
                type="number"
                min={1}
                value={devices}
                onChange={(e) => setDevices(Number(e.target.value))}
                className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
              />
            </div>
          </>
        )}

        <div className="rounded-lg bg-zinc-100 dark:bg-zinc-800 p-3 text-sm">
          <span className="font-medium">{t('training.status')}: </span>
          {getStatusDisplay()}
        </div>
        {(running || paused) && (
          <div className="w-full h-2 rounded-full bg-zinc-200 dark:bg-zinc-700 overflow-hidden">
            <div
              className="h-full bg-pink-500 transition-all duration-300"
              style={{ width: progress != null && progress > 0 ? `${Math.min(100, progress * 100)}%` : '100%' }}
            />
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          {showDownloadButton && (
            <button
              type="button"
              onClick={startModelDownload}
              className="inline-flex items-center gap-2 rounded-lg border border-amber-500 text-amber-600 dark:text-amber-400 px-4 py-2 text-sm font-medium hover:bg-amber-500/10"
            >
              <Download size={16} /> {t('training.download_training_model')}
            </button>
          )}
          <button
            type="submit"
            disabled={!canStartTraining}
            className="inline-flex items-center gap-2 rounded-lg bg-pink-500 text-white px-4 py-2 text-sm font-medium hover:bg-pink-600 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Play size={16} /> {t('training.start_training')}
          </button>
          {running && (
            <>
              {paused ? (
                <button type="button" onClick={handleResume} className="inline-flex items-center gap-2 rounded-lg border border-zinc-300 dark:border-zinc-600 px-4 py-2 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-700">
                  <RotateCw size={16} /> {t('training.resume')}
                </button>
              ) : (
                <button type="button" onClick={handlePause} className="inline-flex items-center gap-2 rounded-lg border border-zinc-300 dark:border-zinc-600 px-4 py-2 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-700">
                  <Pause size={16} /> {t('training.pause')}
                </button>
              )}
              <button type="button" onClick={handleCancel} className="inline-flex items-center gap-2 rounded-lg border border-red-300 dark:border-red-600 text-red-600 dark:text-red-400 px-4 py-2 text-sm hover:bg-red-500/10">
                <Square size={16} /> {t('training.cancel')}
              </button>
            </>
          )}
        </div>
      </form>
    </div>
  );
};
