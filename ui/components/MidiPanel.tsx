import React, { useState, useEffect, useRef } from 'react';
import { Music2, Download, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toolsApi, preferencesApi } from '../services/api';

const POLL_INTERVAL_MS = 500;
const MODEL_POLL_MS = 800;

interface MidiPanelProps {
  onTracksUpdated?: () => void | Promise<void>;
}

export const MidiPanel: React.FC<MidiPanelProps> = ({ onTracksUpdated }) => {
  const { t } = useTranslation();
  const [inputFile, setInputFile] = useState<File | null>(null);
  const [outputFilename, setOutputFilename] = useState('');
  const [onsetThreshold, setOnsetThreshold] = useState(0.5);
  const [frameThreshold, setFrameThreshold] = useState(0.3);
  const [minimumNoteLengthMs, setMinimumNoteLengthMs] = useState(127.7);
  const [minimumFrequency, setMinimumFrequency] = useState('');
  const [maximumFrequency, setMaximumFrequency] = useState('');
  const [midiTempo, setMidiTempo] = useState(120);
  const [multiplePitchBends, setMultiplePitchBends] = useState(false);
  const [melodiaTrick, setMelodiaTrick] = useState(true);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [modelReady, setModelReady] = useState<boolean | null>(null);
  const [modelState, setModelState] = useState('');
  const [modelMessage, setModelMessage] = useState('');
  const [modelDownloadProgress, setModelDownloadProgress] = useState<number | null>(null);
  const modelPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    toolsApi.midiModelStatus()
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
        const m = prefs.midi_gen as Record<string, unknown> | undefined;
        if (m?.onset_threshold != null) setOnsetThreshold(Number(m.onset_threshold));
        if (m?.frame_threshold != null) setFrameThreshold(Number(m.frame_threshold));
        if (m?.minimum_note_length_ms != null) setMinimumNoteLengthMs(Number(m.minimum_note_length_ms));
        if (m?.midi_tempo != null) setMidiTempo(Number(m.midi_tempo));
        if (m?.melodia_trick != null) setMelodiaTrick(Boolean(m.melodia_trick));
        if (m?.multiple_pitch_bends != null) setMultiplePitchBends(Boolean(m.multiple_pitch_bends));
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
      toolsApi.midiModelStatus()
        .then((r) => {
          setModelReady(r.ready);
          setModelState(r.state || '');
          setModelMessage(r.message || '');
        })
        .catch(() => { });
      toolsApi.getProgress()
        .then((p) => {
          if (p.stage === 'midi_model_download') {
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
    const t = setInterval(() => {
      toolsApi.getProgress().then((p) => {
        setProgress(p.fraction);
        if (p.done || p.error) setLoading(false);
      }).catch(() => { });
    }, POLL_INTERVAL_MS);
    return () => clearInterval(t);
  }, [loading]);

  const handleDownloadModels = () => {
    setError(null);
    toolsApi.midiModelEnsure().then(() => {
      setModelState('downloading');
      setModelMessage(t('midi.downloading_model'));
    }).catch((e) => setError(e.message));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    const out = outputFilename.trim();
    if (!out) {
      setError(t('midi.error_filename_required'));
      return;
    }
    if (!inputFile) {
      setError(t('midi.error_select_file'));
      return;
    }
    if (modelReady !== true || modelState === 'downloading') {
      setError(modelState === 'downloading' ? t('midi.error_wait_download') : t('midi.error_model_not_ready'));
      return;
    }
    const formData = new FormData();
    formData.append('input_file', inputFile);
    formData.set('output_filename', out);
    formData.set('onset_threshold', String(onsetThreshold));
    formData.set('frame_threshold', String(frameThreshold));
    formData.set('minimum_note_length_ms', String(minimumNoteLengthMs));
    if (minimumFrequency.trim()) formData.set('minimum_frequency', minimumFrequency.trim());
    if (maximumFrequency.trim()) formData.set('maximum_frequency', maximumFrequency.trim());
    formData.set('midi_tempo', String(midiTempo));
    formData.set('multiple_pitch_bends', multiplePitchBends ? 'true' : '');
    formData.set('melodia_trick', melodiaTrick ? 'true' : '');
    setLoading(true);
    setProgress(0);
    try {
      const prefs = await preferencesApi.get();
      if (prefs.output_dir) formData.set('out_dir', prefs.output_dir);
      const res = await toolsApi.midiGenerate(formData);
      if (res?.error) {
        setError(res.message || t('midi.error_failed'));
        setLoading(false);
        return;
      }
      await preferencesApi.update({
        midi_gen: {
          onset_threshold: onsetThreshold,
          frame_threshold: frameThreshold,
          minimum_note_length_ms: minimumNoteLengthMs,
          midi_tempo: midiTempo,
          melodia_trick: melodiaTrick,
          multiple_pitch_bends: multiplePitchBends,
        },
      });
      setSuccess(res?.message || t('midi.success_message'));
      setLoading(false);
      onTracksUpdated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('midi.error_failed'));
      setLoading(false);
    }
  };

  return (
    <div className="h-full flex flex-col overflow-y-auto p-4 text-zinc-800 dark:text-zinc-200">
      <div className="flex items-center gap-2 mb-4">
        <Music2 className="w-6 h-6 text-pink-500" />
        <h2 className="text-lg font-semibold">{t('midi.title')}</h2>
      </div>
      <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-4">
        {t('midi.description')}
      </p>

      {modelReady === false && modelState !== 'downloading' && (
        <div className="mb-4 p-3 rounded-lg bg-amber-500/10 text-amber-700 dark:text-amber-400 text-sm">
          <p className="font-medium mb-1">{t('midi.model_not_downloaded')}</p>
          <p className="mb-2">{t('midi.model_download_hint')}</p>
          <button
            type="button"
            onClick={handleDownloadModels}
            className="inline-flex items-center gap-1 rounded-lg bg-amber-500 text-white px-3 py-1.5 text-sm font-medium hover:bg-amber-600"
          >
            <Download size={14} /> {t('midi.download_model')}
          </button>
        </div>
      )}
      {modelState === 'downloading' && (
        <div className="mb-4 p-3 rounded-lg bg-blue-500/10 text-blue-700 dark:text-blue-400 text-sm">
          <p className="font-medium mb-2 flex items-center gap-2">
            <Loader2 size={16} className="animate-spin" /> {t('midi.downloading_model')}
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
          <label className="block text-sm font-medium mb-1">{t('midi.input_audio')}</label>
          <input
            type="file"
            accept="audio/*,.mp3,.wav,.m4a,.flac,.ogg"
            onChange={(e) => setInputFile(e.target.files?.[0] || null)}
            className="w-full text-sm file:mr-2 file:rounded-lg file:border-0 file:bg-pink-500 file:px-3 file:py-2 file:text-white file:text-sm"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">{t('midi.output_filename')}</label>
          <input
            type="text"
            value={outputFilename}
            onChange={(e) => setOutputFilename(e.target.value)}
            placeholder={t('midi.output_placeholder')}
            className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">{t('midi.onset_threshold')}: {onsetThreshold}</label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={onsetThreshold}
            onChange={(e) => setOnsetThreshold(Number(e.target.value))}
            className="w-full"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">{t('midi.frame_threshold')}: {frameThreshold}</label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={frameThreshold}
            onChange={(e) => setFrameThreshold(Number(e.target.value))}
            className="w-full"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">{t('midi.min_note_length')}: {minimumNoteLengthMs}</label>
          <input
            type="range"
            min={0}
            max={500}
            step={1}
            value={minimumNoteLengthMs}
            onChange={(e) => setMinimumNoteLengthMs(Number(e.target.value))}
            className="w-full"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">{t('midi.min_frequency')}</label>
          <input
            type="number"
            min={0}
            value={minimumFrequency}
            onChange={(e) => setMinimumFrequency(e.target.value)}
            placeholder={t('midi.frequency_placeholder')}
            className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">{t('midi.max_frequency')}</label>
          <input
            type="number"
            min={0}
            value={maximumFrequency}
            onChange={(e) => setMaximumFrequency(e.target.value)}
            placeholder={t('midi.frequency_placeholder')}
            className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">{t('midi.midi_tempo')}: {midiTempo}</label>
          <input
            type="range"
            min={60}
            max={200}
            value={midiTempo}
            onChange={(e) => setMidiTempo(Number(e.target.value))}
            className="w-full"
          />
        </div>

        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={multiplePitchBends}
            onChange={(e) => setMultiplePitchBends(e.target.checked)}
          />
          <span className="text-sm">{t('midi.multiple_pitch_bends')}</span>
        </label>

        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={melodiaTrick}
            onChange={(e) => setMelodiaTrick(e.target.checked)}
          />
          <span className="text-sm">{t('midi.melodia_trick')}</span>
        </label>

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
            <><Loader2 size={16} className="animate-spin" /> {t('midi.downloading_model')}</>
          ) : loading ? (
            <><Loader2 size={16} className="animate-spin" /> {t('midi.generating')}</>
          ) : (
            t('midi.generate_midi')
          )}
        </button>
      </form>
    </div>
  );
};
