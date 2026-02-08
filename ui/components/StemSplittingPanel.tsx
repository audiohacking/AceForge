import React, { useState, useEffect, useRef } from 'react';
import { Layers, Download, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toolsApi, preferencesApi } from '../services/api';

const POLL_INTERVAL_MS = 500;
const MODEL_POLL_MS = 800;

interface StemSplittingPanelProps {
  onTracksUpdated?: () => void | Promise<void>;
}

export const StemSplittingPanel: React.FC<StemSplittingPanelProps> = ({ onTracksUpdated }) => {
  const { t } = useTranslation();
  const [inputFile, setInputFile] = useState<File | null>(null);
  const [baseFilename, setBaseFilename] = useState('');
  const [stemCount, setStemCount] = useState('4');
  const [mode, setMode] = useState('');
  const [device, setDevice] = useState('auto');
  const [exportFormat, setExportFormat] = useState('wav');
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [modelReady, setModelReady] = useState<boolean | null>(null);
  const [modelState, setModelState] = useState('');
  const [modelMessage, setModelMessage] = useState('');
  const [modelDownloadProgress, setModelDownloadProgress] = useState<number | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const modelPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    toolsApi.stemSplitModelStatus()
      .then((r) => {
        setModelReady(r.ready);
        setModelState(r.state || '');
        setModelMessage(r.message || '');
      })
      .catch(() => setModelReady(false));
  }, []);

  useEffect(() => {
    preferencesApi.get()
      .then((prefs) => {
        const s = prefs.stem_split;
        if (s?.stem_count != null) setStemCount(String(s.stem_count));
        if (s?.mode != null) setMode(s.mode);
        if (s?.device_preference != null) setDevice(s.device_preference);
        if (s?.export_format != null) setExportFormat(s.export_format);
      })
      .catch(() => { });
  }, []);

  useEffect(() => {
    if (modelState !== 'downloading') {
      setModelDownloadProgress(null);
      if (modelPollRef.current) {
        clearInterval(modelPollRef.current);
        modelPollRef.current = null;
      }
      return;
    }
    const poll = () => {
      toolsApi.stemSplitModelStatus()
        .then((r) => {
          setModelReady(r.ready);
          setModelState(r.state || '');
          setModelMessage(r.message || '');
        })
        .catch(() => { });
      toolsApi.getProgress()
        .then((p) => {
          if (p.stage === 'stem_split_model_download') {
            setModelDownloadProgress(p.fraction);
          }
        })
        .catch(() => { });
    };
    poll();
    modelPollRef.current = setInterval(poll, MODEL_POLL_MS);
    return () => {
      if (modelPollRef.current) clearInterval(modelPollRef.current);
    };
  }, [modelState]);

  useEffect(() => {
    if (!loading) return;
    const poll = () => {
      toolsApi.getProgress()
        .then((p) => {
          setProgress(p.fraction);
          if (p.done || p.error) {
            setLoading(false);
            if (pollRef.current) {
              clearInterval(pollRef.current);
              pollRef.current = null;
            }
          }
        })
        .catch(() => { });
    };
    poll();
    pollRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [loading]);

  const handleDownloadModels = () => {
    setError(null);
    toolsApi.stemSplitModelEnsure().then(() => {
      setModelState('downloading');
      setModelMessage(t('stem_splitting.downloading_demucs'));
    }).catch((e) => setError(e.message));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    if (!inputFile) {
      setError(t('stem_splitting.error_select_file'));
      return;
    }
    if (modelReady !== true || modelState === 'downloading') {
      setError(modelState === 'downloading' ? t('stem_splitting.error_wait_download') : t('stem_splitting.error_model_not_ready'));
      return;
    }
    const formData = new FormData();
    formData.append('input_file', inputFile);
    if (baseFilename.trim()) formData.set('base_filename', baseFilename.trim());
    formData.set('stem_count', stemCount);
    formData.set('mode', mode);
    formData.set('device_preference', device);
    formData.set('export_format', exportFormat);
    setLoading(true);
    setProgress(0);
    try {
      const prefs = await preferencesApi.get();
      if (prefs.output_dir) formData.set('out_dir', prefs.output_dir);
      const res = await toolsApi.stemSplit(formData);
      if (res?.error) {
        setError(res.message || t('stem_splitting.error_failed'));
        setLoading(false);
        return;
      }
      await preferencesApi.update({ stem_split: { stem_count: stemCount, mode, device_preference: device, export_format: exportFormat } });
      setSuccess(res?.message || t('stem_splitting.success_message'));
      setLoading(false);
      onTracksUpdated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('stem_splitting.error_failed'));
      setLoading(false);
    }
  };

  return (
    <div className="h-full flex flex-col overflow-y-auto p-4 text-zinc-800 dark:text-zinc-200">
      <div className="flex items-center gap-2 mb-4">
        <Layers className="w-6 h-6 text-pink-500" />
        <h2 className="text-lg font-semibold">{t('stem_splitting.title')}</h2>
      </div>
      <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-4">
        {t('stem_splitting.description')}
      </p>

      {modelReady === false && modelState !== 'downloading' && (
        <div className="mb-4 p-3 rounded-lg bg-amber-500/10 text-amber-700 dark:text-amber-400 text-sm">
          <p className="font-medium mb-1">{t('stem_splitting.model_not_downloaded')}</p>
          <p className="mb-2">{t('stem_splitting.model_download_hint')}</p>
          <button
            type="button"
            onClick={handleDownloadModels}
            className="inline-flex items-center gap-1 rounded-lg bg-amber-500 text-white px-3 py-1.5 text-sm font-medium hover:bg-amber-600"
          >
            <Download size={14} /> {t('stem_splitting.download_demucs')}
          </button>
        </div>
      )}
      {modelState === 'downloading' && (
        <div className="mb-4 p-3 rounded-lg bg-blue-500/10 text-blue-700 dark:text-blue-400 text-sm">
          <p className="font-medium mb-2 flex items-center gap-2">
            <Loader2 size={16} className="animate-spin" /> {t('stem_splitting.downloading_demucs')}
          </p>
          <div className="w-full h-2 rounded-full bg-zinc-200 dark:bg-zinc-700 overflow-hidden">
            <div
              className="h-full bg-pink-500 transition-all duration-300"
              style={{ width: modelDownloadProgress != null ? `${modelDownloadProgress * 100}%` : '30%' }}
            />
          </div>
        </div>
      )}
      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-500/10 text-red-600 dark:text-red-400 text-sm">{error}</div>
      )}
      {success && (
        <div className="mb-4 p-3 rounded-lg bg-green-500/10 text-green-700 dark:text-green-400 text-sm">{success}</div>
      )}

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div>
          <label className="block text-sm font-medium mb-1">{t('stem_splitting.input_audio')}</label>
          <input
            type="file"
            accept="audio/*,.mp3,.wav,.m4a,.flac,.ogg"
            onChange={(e) => setInputFile(e.target.files?.[0] || null)}
            className="w-full text-sm file:mr-2 file:rounded-lg file:border-0 file:bg-pink-500 file:px-3 file:py-2 file:text-white file:text-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">{t('stem_splitting.base_filename')}</label>
          <input
            type="text"
            value={baseFilename}
            onChange={(e) => setBaseFilename(e.target.value)}
            placeholder={t('stem_splitting.base_filename_placeholder')}
            className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">{t('stem_splitting.stem_count')}</label>
          <select
            value={stemCount}
            onChange={(e) => setStemCount(e.target.value)}
            className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
          >
            <option value="2">{t('stem_splitting.stem_2')}</option>
            <option value="4">{t('stem_splitting.stem_4')}</option>
            <option value="6">{t('stem_splitting.stem_6')}</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">{t('stem_splitting.mode')}</label>
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value)}
            className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
          >
            <option value="">{t('stem_splitting.mode_standard')}</option>
            <option value="vocals_only">{t('stem_splitting.mode_vocals')}</option>
            <option value="instrumental">{t('stem_splitting.mode_instrumental')}</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">{t('stem_splitting.device')}</label>
          <select
            value={device}
            onChange={(e) => setDevice(e.target.value)}
            className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
          >
            <option value="auto">{t('stem_splitting.device_auto')}</option>
            <option value="mps">{t('stem_splitting.device_mps')}</option>
            <option value="cpu">{t('stem_splitting.device_cpu')}</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">{t('stem_splitting.export_format')}</label>
          <select
            value={exportFormat}
            onChange={(e) => setExportFormat(e.target.value)}
            className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
          >
            <option value="wav">{t('stem_splitting.format_wav')}</option>
            <option value="mp3">{t('stem_splitting.format_mp3')}</option>
          </select>
        </div>

        {loading && (
          <div className="w-full h-2 rounded-full bg-zinc-200 dark:bg-zinc-700 overflow-hidden">
            <div
              className="h-full bg-pink-500 transition-all duration-300"
              style={{ width: `${Math.min(100, progress * 100)}%` }}
            />
          </div>
        )}

        <button
          type="submit"
          disabled={loading || modelReady !== true || modelState === 'downloading'}
          className="rounded-lg bg-pink-500 text-white px-4 py-2 text-sm font-medium hover:bg-pink-600 disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center justify-center gap-2"
        >
          {modelState === 'downloading' ? (
            <><Loader2 size={16} className="animate-spin" /> {t('stem_splitting.downloading_demucs')}</>
          ) : loading ? (
            <><Loader2 size={16} className="animate-spin" /> {t('stem_splitting.splitting')}</>
          ) : (
            t('stem_splitting.split_stems')
          )}
        </button>
      </form>
    </div>
  );
};
