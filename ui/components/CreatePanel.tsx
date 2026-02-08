import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Sparkles, ChevronDown, Settings2, Trash2, Music2, Sliders, Dices, Hash, RefreshCw, Plus, Upload, Play, Pause, Info, Loader2, Wrench } from 'lucide-react';
import { GenerationParams, Song } from '../types';
import { useAuth } from '../context/AuthContext';
import { generateApi, preferencesApi, aceStepModelsApi, type LoraAdapter } from '../services/api';

/** Tasks that require ACE-Step Base model only (see docs/ACE-Step-Tutorial.md). */
const TASKS_REQUIRING_BASE = ['cover', 'lego', 'extract', 'complete'] as const;
function taskRequiresBase(taskType: string): boolean {
  return TASKS_REQUIRING_BASE.includes(taskType as typeof TASKS_REQUIRING_BASE[number]);
}

interface ReferenceTrack {
  id: string;
  filename: string;
  storage_key: string;
  duration: number | null;
  file_size_bytes: number | null;
  tags: string[] | null;
  created_at?: string;
  audio_url: string;
  /** Display name (title or filename stem) */
  label?: string;
  /** 'uploaded' = ref uploads (deletable); 'library' = generated/player library */
  source?: 'uploaded' | 'library';
}

interface CreatePanelProps {
  onGenerate: (params: GenerationParams) => void;
  isGenerating: boolean;
  initialData?: { song: Song, timestamp: number } | null;
  /** Open Settings modal (e.g. to download required model). */
  onOpenSettings?: () => void;
  /** Open Console logs panel (e.g. when model is downloading in background). */
  onOpenConsoleLogs?: () => void;
}

/** Visible tooltip on hover (native title has delay and is unreliable). */
function InfoTooltip({ text }: { text: string }) {
  return (
    <span className="relative inline-flex group/tt">
      <Info size={12} className="shrink-0 text-zinc-400 dark:text-zinc-500 cursor-help" aria-label={text} />
      <span className="absolute left-0 bottom-full mb-1 hidden group-hover/tt:block z-[100] w-64 p-2 rounded-lg bg-zinc-800 dark:bg-zinc-700 text-white text-xs shadow-xl whitespace-normal pointer-events-none">
        {text}
      </span>
    </span>
  );
}

const KEY_SIGNATURES = [
  '',
  'C major', 'C minor',
  'C# major', 'C# minor',
  'Db major', 'Db minor',
  'D major', 'D minor',
  'D# major', 'D# minor',
  'Eb major', 'Eb minor',
  'E major', 'E minor',
  'F major', 'F minor',
  'F# major', 'F# minor',
  'Gb major', 'Gb minor',
  'G major', 'G minor',
  'G# major', 'G# minor',
  'Ab major', 'Ab minor',
  'A major', 'A minor',
  'A# major', 'A# minor',
  'Bb major', 'Bb minor',
  'B major', 'B minor'
];

const TIME_SIGNATURES = ['', '2/4', '3/4', '4/4', '6/8'];

/** Genre presets for Simple mode (ACE-Step-style tags; from ACE-Step-MCP reference). */
const GENRE_PRESETS: Record<string, string> = {
  'Modern Pop': 'pop, synth, drums, guitar, 120 bpm, upbeat, catchy, vibrant, female vocals, polished vocals',
  'Rock': 'rock, electric guitar, drums, bass, 130 bpm, energetic, rebellious, gritty, male vocals, raw vocals',
  'Hip Hop': 'hip hop, 808 bass, hi-hats, synth, 90 bpm, bold, urban, intense, male vocals, rhythmic vocals',
  'Country': 'country, acoustic guitar, steel guitar, fiddle, 100 bpm, heartfelt, rustic, warm, male vocals, twangy vocals',
  'EDM': 'edm, synth, bass, kick drum, 128 bpm, euphoric, pulsating, energetic, instrumental',
  'Reggae': 'reggae, guitar, bass, drums, 80 bpm, chill, soulful, positive, male vocals, smooth vocals',
  'Classical': 'classical, orchestral, strings, piano, 60 bpm, elegant, emotive, timeless, instrumental',
  'Jazz': 'jazz, saxophone, piano, double bass, 110 bpm, smooth, improvisational, soulful, male vocals, crooning vocals',
  'Metal': 'metal, electric guitar, double kick drum, bass, 160 bpm, aggressive, intense, heavy, male vocals, screamed vocals',
  'R&B': 'r&b, synth, bass, drums, 85 bpm, sultry, groovy, romantic, female vocals, silky vocals',
};

// Lego / Extract / Complete: available track names (ACE-Step 1.5 Base model)
const LEGO_TRACKS = [
  { value: 'vocals', label: 'Vocals' },
  { value: 'backing_vocals', label: 'Backing vocals' },
  { value: 'drums', label: 'Drums' },
  { value: 'bass', label: 'Bass' },
  { value: 'guitar', label: 'Guitar' },
  { value: 'keyboard', label: 'Keyboard' },
  { value: 'percussion', label: 'Percussion' },
  { value: 'strings', label: 'Strings' },
  { value: 'synth', label: 'Synth' },
  { value: 'fx', label: 'FX' },
  { value: 'brass', label: 'Brass' },
  { value: 'woodwinds', label: 'Woodwinds' },
];

const VOCAL_LANGUAGES = [
  { value: 'unknown', label: 'Auto / Instrumental' },
  { value: 'ar', label: 'Arabic' },
  { value: 'az', label: 'Azerbaijani' },
  { value: 'bg', label: 'Bulgarian' },
  { value: 'bn', label: 'Bengali' },
  { value: 'ca', label: 'Catalan' },
  { value: 'cs', label: 'Czech' },
  { value: 'da', label: 'Danish' },
  { value: 'de', label: 'German' },
  { value: 'el', label: 'Greek' },
  { value: 'en', label: 'English' },
  { value: 'es', label: 'Spanish' },
  { value: 'fa', label: 'Persian' },
  { value: 'fi', label: 'Finnish' },
  { value: 'fr', label: 'French' },
  { value: 'he', label: 'Hebrew' },
  { value: 'hi', label: 'Hindi' },
  { value: 'hr', label: 'Croatian' },
  { value: 'ht', label: 'Haitian Creole' },
  { value: 'hu', label: 'Hungarian' },
  { value: 'id', label: 'Indonesian' },
  { value: 'is', label: 'Icelandic' },
  { value: 'it', label: 'Italian' },
  { value: 'ja', label: 'Japanese' },
  { value: 'ko', label: 'Korean' },
  { value: 'la', label: 'Latin' },
  { value: 'lt', label: 'Lithuanian' },
  { value: 'ms', label: 'Malay' },
  { value: 'ne', label: 'Nepali' },
  { value: 'nl', label: 'Dutch' },
  { value: 'no', label: 'Norwegian' },
  { value: 'pa', label: 'Punjabi' },
  { value: 'pl', label: 'Polish' },
  { value: 'pt', label: 'Portuguese' },
  { value: 'ro', label: 'Romanian' },
  { value: 'ru', label: 'Russian' },
  { value: 'sa', label: 'Sanskrit' },
  { value: 'sk', label: 'Slovak' },
  { value: 'sr', label: 'Serbian' },
  { value: 'sv', label: 'Swedish' },
  { value: 'sw', label: 'Swahili' },
  { value: 'ta', label: 'Tamil' },
  { value: 'te', label: 'Telugu' },
  { value: 'th', label: 'Thai' },
  { value: 'tl', label: 'Tagalog' },
  { value: 'tr', label: 'Turkish' },
  { value: 'uk', label: 'Ukrainian' },
  { value: 'ur', label: 'Urdu' },
  { value: 'vi', label: 'Vietnamese' },
  { value: 'yue', label: 'Cantonese' },
  { value: 'zh', label: 'Chinese (Mandarin)' },
];

// Create panel mode: Simple (description), Custom (full controls), Cover (pure cover: source + caption), Lego (add-instrument tracks)
type CreateMode = 'simple' | 'custom' | 'cover' | 'lego';

export const CreatePanel: React.FC<CreatePanelProps> = ({ onGenerate, isGenerating, initialData, onOpenSettings, onOpenConsoleLogs }) => {
  const { isAuthenticated, token } = useAuth();

  // Mode: simple | custom | cover | lego
  const [createMode, setCreateMode] = useState<CreateMode>('custom');
  const customMode = createMode === 'custom';

  // ACE-Step model for this generation (only installed models). Updated by workflow (e.g. base for cover) or user override.
  const [generationDitModel, setGenerationDitModel] = useState<string>('turbo');
  const [installedDitModels, setInstalledDitModels] = useState<Array<{ id: string; label: string; description?: string }>>([]);
  const [modelDownloadInProgress, setModelDownloadInProgress] = useState(false);

  // Cover tab: pure cover (source + caption) or blend (source + style audio)
  const [coverCaption, setCoverCaption] = useState('');
  const [coverStrength, setCoverStrength] = useState(0.8);
  const [coverStyleAudioUrl, setCoverStyleAudioUrl] = useState('');
  const [coverBlendFactor, setCoverBlendFactor] = useState(0.5);
  const [coverValidationError, setCoverValidationError] = useState('');

  // Lego tab only
  const [legoTrackName, setLegoTrackName] = useState('guitar');
  const [legoCaption, setLegoCaption] = useState('');
  const [legoBackingInfluence, setLegoBackingInfluence] = useState(0.25);
  const [legoValidationError, setLegoValidationError] = useState('');

  // Shared between Simple and Custom: description/style (genre, mood, etc.) and title
  const [style, setStyle] = useState('');
  const [title, setTitle] = useState('');

  // Custom Mode (lyrics only in Custom; title/style shared)
  const [lyrics, setLyrics] = useState('');

  // Common
  const [instrumental, setInstrumental] = useState(false);
  const [vocalLanguage, setVocalLanguage] = useState('en');

  // Music Parameters
  const [bpm, setBpm] = useState(0);
  const [keyScale, setKeyScale] = useState('');
  const [timeSignature, setTimeSignature] = useState('');

  // Quality preset: Basic / Great / Best (ACE-Step docs). Visible in both Simple and Advanced.
  type QualityPreset = 'basic' | 'great' | 'best' | 'custom';
  const [qualityPreset, setQualityPreset] = useState<QualityPreset>('great');

  // Negative prompt / Exclude styles (Suno-like; shown above sliders in Simple)
  const [negativePrompt, setNegativePrompt] = useState('');

  // SUNO-like influence sliders (Simple mode): drive effective guidance/audio/creativity
  const [weirdness, setWeirdness] = useState(50);       // 0–100: more creative/experimental
  const [styleInfluence, setStyleInfluence] = useState(50); // 0–100: how much caption is followed
  const [audioInfluence, setAudioInfluence] = useState(50); // 0–100: reference audio strength (when ref loaded)

  // Advanced Settings
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [duration, setDuration] = useState(-1);
  const [batchSize, setBatchSize] = useState(1);
  const [bulkCount, setBulkCount] = useState(1); // Number of independent generation jobs to queue
  const [guidanceScale, setGuidanceScale] = useState(5.5);
  const [randomSeed, setRandomSeed] = useState(true);
  const [seed, setSeed] = useState(-1);
  const [thinking, setThinking] = useState(true);
  const [audioFormat, setAudioFormat] = useState<'mp3' | 'flac'>('mp3');
  const [inferenceSteps, setInferenceSteps] = useState(40);
  const [inferMethod, setInferMethod] = useState<'ode' | 'sde'>('ode');
  const [shift, setShift] = useState(3.0);

  // Presets tuned from ACE-Step INFERENCE.md: Turbo 8–20 steps; Base 32–64; guidance 5–9; thinking/CoT for quality
  const applyPreset = (preset: QualityPreset) => {
    setQualityPreset(preset);
    if (preset === 'basic') {
      setInferenceSteps(12);
      setGuidanceScale(4.0);
      setThinking(false);
      setUseCotMetas(false);
      setUseCotCaption(false);
      setUseCotLanguage(false);
    } else if (preset === 'great') {
      setInferenceSteps(40);
      setGuidanceScale(5.5);
      setThinking(true);
      setUseCotMetas(true);
      setUseCotCaption(true);
      setUseCotLanguage(true);
    } else if (preset === 'best') {
      setInferenceSteps(75);
      setGuidanceScale(8.0);
      setThinking(true);
      setUseCotMetas(true);
      setUseCotCaption(true);
      setUseCotLanguage(true);
    }
    // 'custom' = don't change anything
  };

  // LM Parameters (under Expert)
  const [showLmParams, setShowLmParams] = useState(false);
  const [lmTemperature, setLmTemperature] = useState(0.85);
  const [lmCfgScale, setLmCfgScale] = useState(2.0);
  const [lmTopK, setLmTopK] = useState(0);
  const [lmTopP, setLmTopP] = useState(0.9);
  const [lmNegativePrompt, setLmNegativePrompt] = useState('NO USER INPUT');

  // Expert Parameters (now in Advanced section)
  const [referenceAudioUrl, setReferenceAudioUrl] = useState('');
  const [sourceAudioUrl, setSourceAudioUrl] = useState('');
  const [audioCodes, setAudioCodes] = useState('');
  const [repaintingStart, setRepaintingStart] = useState(0);
  const [repaintingEnd, setRepaintingEnd] = useState(-1);
  const [audioCoverStrength, setAudioCoverStrength] = useState(1.0);
  const [taskType, setTaskType] = useState('text2music');
  const [useAdg, setUseAdg] = useState(false);
  const [cfgIntervalStart, setCfgIntervalStart] = useState(0.0);
  const [cfgIntervalEnd, setCfgIntervalEnd] = useState(1.0);
  const [customTimesteps, setCustomTimesteps] = useState('');
  const [loraAdapters, setLoraAdapters] = useState<LoraAdapter[]>([]);
  const [loraLoading, setLoraLoading] = useState(false);
  const [loraNameOrPath, setLoraNameOrPath] = useState('');
  const [loraWeight, setLoraWeight] = useState(0.75);
  const [useCotMetas, setUseCotMetas] = useState(true);
  const [useCotCaption, setUseCotCaption] = useState(true);
  const [useCotLanguage, setUseCotLanguage] = useState(true);
  const [autogen, setAutogen] = useState(false);
  const [constrainedDecodingDebug, setConstrainedDecodingDebug] = useState(false);
  const [allowLmBatch, setAllowLmBatch] = useState(true);
  const [getScores, setGetScores] = useState(false);
  const [getLrc, setGetLrc] = useState(false);
  const [scoreScale, setScoreScale] = useState(0.5);
  const [lmBatchChunkSize, setLmBatchChunkSize] = useState(8);
  const [trackName, setTrackName] = useState('');           // Lego/Extract: single track (e.g. guitar)
  const [completeTrackClasses, setCompleteTrackClasses] = useState(''); // Complete: comma-separated (e.g. drums, bass, guitar)
  const [isFormatCaption, setIsFormatCaption] = useState(false);

  const [isUploadingReference, setIsUploadingReference] = useState(false);
  const [isUploadingSource, setIsUploadingSource] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isFormatting, setIsFormatting] = useState(false);
  const [showAudioModal, setShowAudioModal] = useState(false);
  const [audioModalTarget, setAudioModalTarget] = useState<'reference' | 'source' | 'cover_style'>('reference');
  const [tempAudioUrl, setTempAudioUrl] = useState('');
  const [audioTab, setAudioTab] = useState<'reference' | 'source'>('reference');
  const referenceAudioRef = useRef<HTMLAudioElement>(null);
  const sourceAudioRef = useRef<HTMLAudioElement>(null);
  const [referencePlaying, setReferencePlaying] = useState(false);
  const [sourcePlaying, setSourcePlaying] = useState(false);
  const [referenceTime, setReferenceTime] = useState(0);
  const [sourceTime, setSourceTime] = useState(0);
  const [referenceDuration, setReferenceDuration] = useState(0);
  const [sourceDuration, setSourceDuration] = useState(0);

  // Reference tracks modal state
  const [referenceTracks, setReferenceTracks] = useState<ReferenceTrack[]>([]);
  const [libraryTagFilter, setLibraryTagFilter] = useState<string>('all');
  const [isLoadingTracks, setIsLoadingTracks] = useState(false);
  const [playingTrackId, setPlayingTrackId] = useState<string | null>(null);
  const modalAudioRef = useRef<HTMLAudioElement>(null);
  const [modalTrackTime, setModalTrackTime] = useState(0);
  const [modalTrackDuration, setModalTrackDuration] = useState(0);

  const getAudioLabel = (url: string) => {
    try {
      const parsed = new URL(url);
      return decodeURIComponent(parsed.pathname.split('/').pop() || parsed.hostname);
    } catch {
      const parts = url.split('/');
      return decodeURIComponent(parts[parts.length - 1] || url);
    }
  };

  // Resize Logic
  const [lyricsHeight, setLyricsHeight] = useState(() => {
    const saved = localStorage.getItem('acestep_lyrics_height');
    return saved ? parseInt(saved, 10) : 144; // Default h-36 is 144px (9rem * 16)
  });
  const [isResizing, setIsResizing] = useState(false);
  const lyricsRef = useRef<HTMLDivElement>(null);

  // Reuse Effect - must be after all state declarations
  useEffect(() => {
    if (initialData) {
      setCreateMode('custom');
      setLyrics(initialData.song.lyrics);
      setStyle(initialData.song.style);
      setTitle(initialData.song.title);
      setInstrumental(initialData.song.lyrics.length === 0);
    }
  }, [initialData]);

  // When both reference and source audio are removed, restore Text → Music mode
  useEffect(() => {
    if (!referenceAudioUrl.trim() && !sourceAudioUrl.trim()) {
      setTaskType('text2music');
    }
  }, [referenceAudioUrl, sourceAudioUrl]);

  const fetchLoraAdapters = useCallback(() => {
    setLoraLoading(true);
    generateApi.getLoraAdapters()
      .then((res) => setLoraAdapters(res.adapters || []))
      .catch(() => setLoraAdapters([]))
      .finally(() => setLoraLoading(false));
  }, []);

  // Fetch LoRA adapters on mount (Training output + custom_lora)
  useEffect(() => { fetchLoraAdapters(); }, [fetchLoraAdapters]);

  // Load installed ACE-Step DiT models and sync generation model from preferences (or default base for cover/lego).
  useEffect(() => {
    aceStepModelsApi.list().then((list) => {
      const installed = (list.dit_models || []).filter((m) => m.installed).map((m) => ({ id: m.id, label: m.label, description: m.description }));
      setInstalledDitModels(installed);
      preferencesApi.get().then((prefs) => {
        const prefDit = (prefs.ace_step_dit_model || 'turbo').trim();
        const valid = installed.some((m) => m.id === prefDit);
        setGenerationDitModel(valid ? prefDit : (installed[0]?.id || 'turbo'));
      }).catch(() => {
        if (installed.length) setGenerationDitModel(installed[0].id);
      });
    }).catch(() => setInstalledDitModels([]));
  }, []);

  // When switching to Cover or Lego, default model to base (user can override via selector).
  useEffect(() => {
    if ((createMode === 'cover' || createMode === 'lego') && installedDitModels.some((m) => m.id === 'base')) {
      setGenerationDitModel((prev) => (prev === 'turbo' ? 'base' : prev));
    }
  }, [createMode, installedDitModels]);

  // Poll model-download status when generating so we can show banner + link to console.
  useEffect(() => {
    if (!isGenerating) {
      setModelDownloadInProgress(false);
      return;
    }
    const poll = () => {
      generateApi.modelDownloadStatus().then((st) => setModelDownloadInProgress(st.in_progress)).catch(() => setModelDownloadInProgress(false));
    };
    poll();
    const t = setInterval(poll, 2000);
    return () => clearInterval(t);
  }, [isGenerating]);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return;

      // Calculate new height based on mouse position relative to the lyrics container top
      // We can't easily get the container top here without a ref to it, 
      // but we can use dy (delta y) from the previous position if we tracked it,
      // OR simpler: just update based on movement if we track the start.
      //
      // Better approach for absolute sizing: 
      // 1. Get the bounding rect of the textarea wrapper on mount/resize start? 
      //    We can just rely on the fact that we are dragging the bottom.
      //    So new height = currentMouseY - topOfElement.

      if (lyricsRef.current) {
        const rect = lyricsRef.current.getBoundingClientRect();
        const newHeight = e.clientY - rect.top;
        // detailed limits: min 96px (h-24), max 600px
        if (newHeight > 96 && newHeight < 600) {
          setLyricsHeight(newHeight);
        }
      }
    };

    const handleMouseUp = () => {
      setIsResizing(false);
      document.body.style.cursor = 'default';
      document.body.style.userSelect = 'auto';
      // Save height to localStorage
      localStorage.setItem('acestep_lyrics_height', String(lyricsHeight));
    };

    if (isResizing) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'ns-resize';
      document.body.style.userSelect = 'none'; // Prevent text selection while dragging
    }

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'default';
      document.body.style.userSelect = 'auto';
    };
  }, [isResizing]);

  const startResizing = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  };

  const uploadAudio = async (file: File, target: 'reference' | 'source' | 'cover_style') => {
    setUploadError(null);
    const setUploading = target === 'reference' ? setIsUploadingReference : target === 'cover_style' ? setIsUploadingReference : setIsUploadingSource;
    setUploading(true);
    try {
      const result = await generateApi.uploadAudio(file, token || '');
      if (target === 'reference') {
        setReferenceAudioUrl(result.url);
        setTaskType('audio2audio');
        setAudioTab('reference');
      } else if (target === 'cover_style') {
        setCoverStyleAudioUrl(result.url);
      } else {
        setSourceAudioUrl(result.url);
        setTaskType('cover');
        setAudioTab('source');
      }
      setShowAudioModal(false);
      setTempAudioUrl('');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Upload failed';
      setUploadError(message);
    } finally {
      setUploading(false);
    }
  };

  // Format handler - uses LLM to enhance style and auto-fill parameters
  const handleFormat = async () => {
    if (!token || !style.trim()) return;
    setIsFormatting(true);
    try {
      const result = await generateApi.formatInput({
        caption: style,
        lyrics: lyrics,
        bpm: bpm > 0 ? bpm : undefined,
        duration: duration > 0 ? duration : undefined,
        keyScale: keyScale || undefined,
        timeSignature: timeSignature || undefined,
        temperature: lmTemperature,
        topK: lmTopK > 0 ? lmTopK : undefined,
        topP: lmTopP,
      }, token);

      if (result.success) {
        // Update fields with LLM-generated values
        if (result.caption) setStyle(result.caption);
        if (result.lyrics) setLyrics(result.lyrics);
        if (result.bpm && result.bpm > 0) setBpm(result.bpm);
        if (result.duration && result.duration > 0) setDuration(result.duration);
        if (result.key_scale) setKeyScale(result.key_scale);
        if (result.time_signature) setTimeSignature(result.time_signature);
        if (result.language) setVocalLanguage(result.language);
        setIsFormatCaption(true);
      } else {
        console.error('Format failed:', result.error || result.status_message);
        alert(result.error || result.status_message || 'Format failed. Make sure the LLM is initialized.');
      }
    } catch (err) {
      console.error('Format error:', err);
      alert('Format failed. The LLM may not be available.');
    } finally {
      setIsFormatting(false);
    }
  };

  const openAudioModal = (target: 'reference' | 'source' | 'cover_style') => {
    setAudioModalTarget(target);
    setTempAudioUrl('');
    setShowAudioModal(true);
    void fetchReferenceTracks();
  };

  const fetchReferenceTracks = useCallback(async () => {
    setIsLoadingTracks(true);
    try {
      const [refRes, songsRes] = await Promise.all([
        fetch('/api/reference-tracks', { headers: token ? { Authorization: `Bearer ${token}` } : {} }),
        fetch('/api/songs', { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      ]);
      const refData = refRes.ok ? await refRes.json() : { tracks: [] };
      const songsData = songsRes.ok ? await songsRes.json() : { songs: [] };
      const refTracks: ReferenceTrack[] = (refData.tracks || []).map((r: { id: string; filename?: string; storage_key?: string; audio_url: string; duration?: number | null; tags?: string[] | null; file_size_bytes?: number | null }) => ({
        id: r.id,
        filename: r.filename || r.storage_key || r.id,
        storage_key: r.storage_key || r.filename || r.id,
        audio_url: r.audio_url,
        duration: r.duration ?? null,
        tags: r.tags ?? null,
        file_size_bytes: r.file_size_bytes ?? null,
        label: (r.filename || r.storage_key || r.id).replace(/\.[^/.]+$/, ''),
        source: 'uploaded' as const,
      }));
      const songs = songsData.songs || [];
      const libraryTracks: ReferenceTrack[] = songs.map((s: { id: string; title?: string; audio_url: string; duration?: number | null; tags?: string[] }) => ({
        id: s.id,
        filename: s.title || s.id,
        storage_key: s.id,
        audio_url: s.audio_url,
        duration: s.duration ?? null,
        tags: Array.isArray(s.tags) ? s.tags : null,
        file_size_bytes: null,
        label: s.title || s.id.replace(/\.[^/.]+$/, '') || s.id,
        source: (s.id.startsWith('ref:') ? 'uploaded' : 'library') as 'uploaded' | 'library',
      }));
      const merged = [...refTracks];
      const seenIds = new Set(refTracks.map(t => t.id));
      for (const t of libraryTracks) {
        if (t.source === 'library' && !seenIds.has(t.id)) {
          merged.push(t);
          seenIds.add(t.id);
        }
      }
      merged.sort((a, b) => (b.label || b.filename).localeCompare(a.label || a.filename, undefined, { sensitivity: 'base' }));
      setReferenceTracks(merged);
      setLibraryTagFilter('all');
    } catch (err) {
      console.error('Failed to fetch library/reference tracks:', err);
    } finally {
      setIsLoadingTracks(false);
    }
  }, [token]);

  // Refresh library list periodically so API-completed generations show up in "From library"
  useEffect(() => {
    void fetchReferenceTracks();
    const REFRESH_MS = 20_000;
    const id = setInterval(() => fetchReferenceTracks(), REFRESH_MS);
    return () => clearInterval(id);
  }, [fetchReferenceTracks]);

  const uploadReferenceTrack = async (file: File) => {
    setUploadError(null);
    setIsUploadingReference(true);
    try {
      const formData = new FormData();
      formData.append('audio', file);

      const headers: Record<string, string> = {};
      if (token) headers.Authorization = `Bearer ${token}`;

      const response = await fetch('/api/reference-tracks', {
        method: 'POST',
        headers,
        body: formData
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.error || 'Upload failed');
      }

      const data = await response.json();
      const r = data.track || {};
      const normalized: ReferenceTrack = {
        id: r.id,
        filename: r.filename || r.storage_key || r.id,
        storage_key: r.storage_key || r.filename || r.id,
        audio_url: r.audio_url,
        duration: r.duration ?? null,
        tags: r.tags ?? ['uploaded'],
        file_size_bytes: r.file_size_bytes ?? null,
        label: (r.filename || r.storage_key || r.id || '').replace(/\.[^/.]+$/, ''),
        source: 'uploaded',
      };
      setReferenceTracks(prev => [normalized, ...prev]);

      const audioUrl = data.track?.audio_url;
      if (audioUrl) {
        if (audioModalTarget === 'reference') {
          setReferenceAudioUrl(audioUrl);
          setTaskType('audio2audio');
          setAudioTab('reference');
        } else if (audioModalTarget === 'cover_style') {
          setCoverStyleAudioUrl(audioUrl);
        } else {
          setSourceAudioUrl(audioUrl);
          setTaskType('cover');
          setAudioTab('source');
        }
      }
      setShowAudioModal(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Upload failed';
      setUploadError(message);
    } finally {
      setIsUploadingReference(false);
    }
  };

  const deleteReferenceTrack = async (trackId: string) => {
    if (!token) return;
    try {
      const response = await fetch(`/api/reference-tracks/${trackId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (response.ok) {
        setReferenceTracks(prev => prev.filter(t => t.id !== trackId));
        if (playingTrackId === trackId) {
          setPlayingTrackId(null);
          if (modalAudioRef.current) {
            modalAudioRef.current.pause();
          }
        }
      }
    } catch (err) {
      console.error('Failed to delete track:', err);
    }
  };

  const useReferenceTrack = (track: ReferenceTrack) => {
    if (audioModalTarget === 'reference') {
      setReferenceAudioUrl(track.audio_url);
      setTaskType('audio2audio');
      setAudioTab('reference');
    } else if (audioModalTarget === 'cover_style') {
      setCoverStyleAudioUrl(track.audio_url);
    } else {
      setSourceAudioUrl(track.audio_url);
      setTaskType('cover');
      setAudioTab('source');
    }
    setShowAudioModal(false);
    setPlayingTrackId(null);
  };

  const toggleModalTrack = (track: ReferenceTrack) => {
    if (playingTrackId === track.id) {
      if (modalAudioRef.current) {
        modalAudioRef.current.pause();
      }
      setPlayingTrackId(null);
    } else {
      setPlayingTrackId(track.id);
      if (modalAudioRef.current) {
        modalAudioRef.current.src = track.audio_url;
        modalAudioRef.current.play().catch(() => undefined);
      }
    }
  };

  const applyAudioUrl = () => {
    if (!tempAudioUrl.trim()) return;
    if (audioModalTarget === 'reference') {
      setReferenceAudioUrl(tempAudioUrl.trim());
      setReferenceTime(0);
      setReferenceDuration(0);
      setTaskType('audio2audio');
    } else if (audioModalTarget === 'cover_style') {
      setCoverStyleAudioUrl(tempAudioUrl.trim());
    } else {
      setSourceAudioUrl(tempAudioUrl.trim());
      setSourceTime(0);
      setSourceDuration(0);
      setTaskType('cover');
    }
    setShowAudioModal(false);
    setTempAudioUrl('');
  };

  const formatTime = (time: number) => {
    if (!Number.isFinite(time) || time <= 0) return '0:00';
    const minutes = Math.floor(time / 60);
    const seconds = Math.floor(time % 60);
    return `${minutes}:${String(seconds).padStart(2, '0')}`;
  };

  const toggleAudio = (target: 'reference' | 'source') => {
    const audio = target === 'reference' ? referenceAudioRef.current : sourceAudioRef.current;
    if (!audio) return;
    if (audio.paused) {
      audio.play().catch(() => undefined);
    } else {
      audio.pause();
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>, target: 'reference' | 'source') => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) {
      void uploadAudio(file, target);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  const handleGenerate = async () => {
    console.log('[CreatePanel] Create button clicked', { bulkCount, customMode, createMode, isAuthenticated });

    const effectiveTaskType = createMode === 'lego' ? 'lego' : createMode === 'cover' ? 'cover' : (customMode ? taskType : (sourceAudioUrl?.trim() ? 'cover' : 'text2music'));
    if (taskRequiresBase(effectiveTaskType)) {
      setLegoValidationError('');
      setCoverValidationError('');
      try {
        const list = await aceStepModelsApi.list();
        const baseInstalled = list.dit_models.some((m) => m.id === 'base' && m.installed);
        if (!baseInstalled) {
          const msg = effectiveTaskType === 'cover'
            ? 'Cover requires the Base model. Open Settings to download it, then try again.'
            : 'Lego (and Extract/Complete) require the Base model. Open Settings to download it, then try again.';
          if (effectiveTaskType === 'cover') setCoverValidationError(msg);
          else setLegoValidationError(msg);
          onOpenSettings?.();
          return;
        }
      } catch (e) {
        const msg = 'Could not check models. Open Settings to ensure the Base model is installed.';
        if (effectiveTaskType === 'cover') setCoverValidationError(msg);
        else setLegoValidationError(msg);
        onOpenSettings?.();
        return;
      }
    }

    // Cover mode: pure cover — source audio + caption (like ComfyUI audio_ace_step_1_5_cover)
    if (createMode === 'cover') {
      setCoverValidationError('');
      if (!sourceAudioUrl?.trim()) {
        setCoverValidationError('Please select source audio (required for Cover).');
        return;
      }
      const coverPrompt = (coverCaption || '').trim();
      if (!coverPrompt) {
        setCoverValidationError('Describe the cover style (e.g. jazz piano cover with swing rhythm).');
        return;
      }
      onGenerate({
        customMode: false,
        songDescription: undefined,
        prompt: coverPrompt,
        lyrics: instrumental ? '[Instrumental]' : (lyrics.trim() || ''),
        style: coverPrompt,
        title: title.trim() || 'Cover',
        instrumental,
        vocalLanguage: 'en',
        bpm: 0,
        keyScale: '',
        timeSignature: '',
        duration: -1,
        inferenceSteps,
        guidanceScale: guidanceScale,
        batchSize: 1,
        randomSeed: randomSeed,
        seed: randomSeed ? -1 : seed,
        thinking,
        audioFormat,
        inferMethod,
        shift,
        lmTemperature: lmTemperature,
        lmCfgScale,
        lmTopK,
        lmTopP,
        lmNegativePrompt,
        referenceAudioUrl: coverStyleAudioUrl?.trim() || undefined,
        sourceAudioUrl: sourceAudioUrl.trim(),
        audioCodes: undefined,
        repaintingStart: 0,
        repaintingEnd: -1,
        audioCoverStrength: coverStrength,
        coverBlendFactor: coverStyleAudioUrl ? coverBlendFactor : undefined,
        taskType: 'cover',
        useAdg,
        cfgIntervalStart,
        cfgIntervalEnd,
        customTimesteps: customTimesteps.trim() || undefined,
        loraNameOrPath: loraNameOrPath.trim() || undefined,
        loraWeight,
        useCotMetas,
        useCotCaption,
        useCotLanguage,
        autogen,
        constrainedDecodingDebug,
        allowLmBatch,
        getScores,
        getLrc,
        scoreScale,
        lmBatchChunkSize,
        negativePrompt: negativePrompt.trim() || undefined,
        isFormatCaption,
        aceStepDitModel: generationDitModel,
      });
      return;
    }

    // Lego mode: require backing audio and send a single lego job
    if (createMode === 'lego') {
      setLegoValidationError('');
      if (!sourceAudioUrl?.trim()) {
        setLegoValidationError('Please select backing audio (required for Lego).');
        return;
      }
      const instruction = `Generate the ${legoTrackName} track based on the audio context:`;
      const effGuidance = guidanceScale;
      const effAudioCover = legoBackingInfluence;
      const effLmTemp = lmTemperature;
      onGenerate({
        customMode: false,
        songDescription: undefined,
        prompt: instruction + (legoCaption.trim() ? ', ' + legoCaption.trim() : ''),
        lyrics: '',
        style: legoCaption.trim() || instruction,
        title: title.trim() || `Lego ${legoTrackName}`,
        instrumental: true,
        vocalLanguage: 'en',
        bpm: 0,
        keyScale: '',
        timeSignature: '',
        duration: -1,
        inferenceSteps,
        guidanceScale: effGuidance,
        batchSize: 1,
        randomSeed: randomSeed,
        seed: randomSeed ? -1 : seed,
        thinking,
        audioFormat,
        inferMethod,
        shift,
        lmTemperature: effLmTemp,
        lmCfgScale,
        lmTopK,
        lmTopP,
        lmNegativePrompt,
        referenceAudioUrl: undefined,
        sourceAudioUrl: sourceAudioUrl.trim(),
        audioCodes: undefined,
        repaintingStart: 0,
        repaintingEnd: -1,
        audioCoverStrength: effAudioCover,
        taskType: 'lego',
        instruction,
        useAdg,
        cfgIntervalStart,
        cfgIntervalEnd,
        customTimesteps: customTimesteps.trim() || undefined,
        loraNameOrPath: loraNameOrPath.trim() || undefined,
        loraWeight,
        useCotMetas,
        useCotCaption,
        useCotLanguage,
        autogen,
        constrainedDecodingDebug,
        allowLmBatch,
        getScores,
        getLrc,
        scoreScale,
        lmBatchChunkSize,
        negativePrompt: negativePrompt.trim() || undefined,
        isFormatCaption,
        aceStepDitModel: generationDitModel,
      });
      return;
    }

    // Bulk generation: loop bulkCount times
    for (let i = 0; i < bulkCount; i++) {
      // Seed handling: first job uses user's seed, rest get random seeds
      let jobSeed = -1;
      if (!randomSeed && i === 0) {
        jobSeed = seed;
      } else if (!randomSeed && i > 0) {
        // Subsequent jobs get random seeds for variety
        jobSeed = Math.floor(Math.random() * 4294967295);
      }

      // In Simple mode, apply SUNO-like sliders to effective params (preset base + influence)
        const hasRef = !!(referenceAudioUrl?.trim() || sourceAudioUrl?.trim());
        const effGuidance = customMode
          ? guidanceScale
          : Math.max(2, Math.min(10, guidanceScale * (0.5 + styleInfluence / 100) * (1 - 0.35 * weirdness / 100)));
        const effAudioCover = customMode || !hasRef ? audioCoverStrength : audioInfluence / 100;
        const effLmTemp = customMode ? lmTemperature : (thinking ? 0.7 + 0.5 * (weirdness / 100) : lmTemperature);

        onGenerate({
        customMode,
        songDescription: customMode ? undefined : style,
        prompt: style,
        lyrics,
        style,
        title: bulkCount > 1 ? `${title} (${i + 1})` : title,
        instrumental,
        vocalLanguage,
        bpm,
        keyScale,
        timeSignature,
        duration,
        inferenceSteps,
        guidanceScale: effGuidance,
        batchSize,
        randomSeed: randomSeed || i > 0, // Force random for subsequent bulk jobs
        seed: jobSeed,
        thinking,
        audioFormat,
        inferMethod,
        shift,
        lmTemperature: effLmTemp,
        lmCfgScale,
        lmTopK,
        lmTopP,
        lmNegativePrompt,
        referenceAudioUrl: referenceAudioUrl.trim() || undefined,
        sourceAudioUrl: sourceAudioUrl.trim() || undefined,
        audioCodes: audioCodes.trim() || undefined,
        repaintingStart,
        repaintingEnd,
        audioCoverStrength: effAudioCover,
        taskType: customMode ? taskType : (sourceAudioUrl?.trim() ? 'cover' : 'text2music'),
        useAdg,
        cfgIntervalStart,
        cfgIntervalEnd,
        customTimesteps: customTimesteps.trim() || undefined,
        loraNameOrPath: loraNameOrPath.trim() || undefined,
        loraWeight,
        useCotMetas,
        useCotCaption,
        useCotLanguage,
        autogen,
        constrainedDecodingDebug,
        allowLmBatch,
        getScores,
        getLrc,
        scoreScale,
        lmBatchChunkSize,
        negativePrompt: negativePrompt.trim() || undefined,
        isFormatCaption,
        aceStepDitModel: generationDitModel,
      });
    }

    // Reset bulk count after generation
    if (bulkCount > 1) {
      setBulkCount(1);
    }
  };

  return (
    <div className="flex flex-col h-full bg-zinc-50 dark:bg-suno-panel w-full overflow-y-auto custom-scrollbar transition-colors duration-300">
      <div className="p-4 pt-14 md:pt-4 space-y-5">
        <audio
          ref={referenceAudioRef}
          src={referenceAudioUrl || undefined}
          onPlay={() => setReferencePlaying(true)}
          onPause={() => setReferencePlaying(false)}
          onEnded={() => setReferencePlaying(false)}
          onTimeUpdate={(e) => setReferenceTime(e.currentTarget.currentTime)}
          onLoadedMetadata={(e) => setReferenceDuration(e.currentTarget.duration || 0)}
        />
        <audio
          ref={sourceAudioRef}
          src={sourceAudioUrl || undefined}
          onPlay={() => setSourcePlaying(true)}
          onPause={() => setSourcePlaying(false)}
          onEnded={() => setSourcePlaying(false)}
          onTimeUpdate={(e) => setSourceTime(e.currentTarget.currentTime)}
          onLoadedMetadata={(e) => setSourceDuration(e.currentTarget.duration || 0)}
        />

        {/* Model selector: only installed models; workflow (e.g. Cover→base) updates this; user can override. */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400 shrink-0">ACE-Step model</label>
            {installedDitModels.length > 0 ? (
              <select
                value={installedDitModels.some((m) => m.id === generationDitModel) ? generationDitModel : (installedDitModels[0]?.id || 'turbo')}
                onChange={(e) => setGenerationDitModel(e.target.value)}
                className="bg-zinc-100 dark:bg-black/30 text-zinc-900 dark:text-white text-xs rounded-lg px-2.5 py-1.5 border border-zinc-200 dark:border-white/10 focus:ring-2 focus:ring-pink-500/50 focus:outline-none"
              >
                {installedDitModels.map((m) => (
                  <option key={m.id} value={m.id}>{m.label}</option>
                ))}
              </select>
            ) : (
              <span className="text-xs text-zinc-500">No models installed</span>
            )}
            {(createMode === 'cover' || createMode === 'lego') && generationDitModel === 'base' && (
              <span className="text-[10px] text-zinc-500 italic">(recommended for this mode)</span>
            )}
          </div>
          {installedDitModels.length === 0 && (
            <button type="button" onClick={() => onOpenSettings?.()} className="text-xs font-medium text-pink-600 dark:text-pink-400 hover:underline">
              Open Settings to download
            </button>
          )}
        </div>

        {/* Notify when pipeline is loading (may be downloading model files in background). */}
        {modelDownloadInProgress && (
          <div className="flex items-center justify-between gap-3 rounded-lg bg-amber-500/15 dark:bg-amber-500/10 border border-amber-500/30 px-3 py-2 text-sm text-amber-800 dark:text-amber-200">
            <span>Model files are being downloaded or prepared. This may take a while. Do not close the app.</span>
            {onOpenConsoleLogs && (
              <button type="button" onClick={onOpenConsoleLogs} className="shrink-0 font-medium text-amber-700 dark:text-amber-300 hover:underline">
                View console logs
              </button>
            )}
          </div>
        )}

        {/* Header - Mode Toggle */}
        <div className="flex items-center justify-end">
          <div className="flex items-center bg-zinc-200 dark:bg-black/40 rounded-lg p-1 border border-zinc-300 dark:border-white/5">
            <button
              onClick={() => { setCreateMode('simple'); setLegoValidationError(''); setCoverValidationError(''); }}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${createMode === 'simple' ? 'bg-white dark:bg-zinc-800 text-black dark:text-white shadow-sm' : 'text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-300'}`}
            >
              Simple
            </button>
            <button
              onClick={() => { setCreateMode('custom'); setLegoValidationError(''); setCoverValidationError(''); }}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${createMode === 'custom' ? 'bg-white dark:bg-zinc-800 text-black dark:text-white shadow-sm' : 'text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-300'}`}
            >
              Custom
            </button>
            <button
              onClick={() => {
                setCreateMode('cover');
                setLegoValidationError('');
                setCoverValidationError('');
                if (installedDitModels.some((m) => m.id === 'base')) setGenerationDitModel('base');
              }}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${createMode === 'cover' ? 'bg-white dark:bg-zinc-800 text-black dark:text-white shadow-sm' : 'text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-300'}`}
            >
              Cover
            </button>
            <button
              onClick={() => {
                setCreateMode('lego');
                setLegoValidationError('');
                setCoverValidationError('');
                if (installedDitModels.some((m) => m.id === 'base')) setGenerationDitModel('base');
                preferencesApi.update({ ace_step_dit_model: 'base' }).catch(() => {});
              }}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${createMode === 'lego' ? 'bg-white dark:bg-zinc-800 text-black dark:text-white shadow-sm' : 'text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-300'}`}
            >
              Lego
            </button>
          </div>
        </div>

        {/* SIMPLE MODE */}
        {createMode === 'simple' && (
          <div className="space-y-5">
            {/* Title (same as Custom mode) */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5">
                Title
              </div>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Name your song"
                className="w-full bg-transparent p-3 text-sm text-zinc-900 dark:text-white placeholder-zinc-400 dark:placeholder-zinc-600 focus:outline-none"
              />
            </div>

            {/* Genre preset + Song Description */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5 flex items-center gap-1.5">
                Describe Your Song
                <InfoTooltip text="Use a genre preset to fill tags (style, instruments, BPM), or type your own description. Presets use ACE-Step-style comma-separated tags." />
              </div>
              <div className="p-3 space-y-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <label className="text-[11px] font-medium text-zinc-600 dark:text-zinc-400 shrink-0">Genre preset:</label>
                  <select
                    value={Object.keys(GENRE_PRESETS).find(k => GENRE_PRESETS[k] === style) || 'Custom'}
                    onChange={(e) => {
                      const key = e.target.value;
                      if (key === 'Custom') return;
                      const text = GENRE_PRESETS[key];
                      if (text) {
                        setStyle(text);
                        const bpmMatch = text.match(/(\d+)\s*bpm/i);
                        if (bpmMatch) setBpm(parseInt(bpmMatch[1], 10));
                      }
                    }}
                    className="bg-zinc-100 dark:bg-black/30 text-zinc-900 dark:text-white text-xs rounded-lg px-2.5 py-1.5 border-0 focus:ring-2 focus:ring-pink-500/50 focus:outline-none"
                  >
                    <option value="Custom">Custom (type below)</option>
                    {Object.keys(GENRE_PRESETS).map((name) => (
                      <option key={name} value={name}>{name}</option>
                    ))}
                  </select>
                </div>
                <textarea
                  value={style}
                  onChange={(e) => setStyle(e.target.value)}
                  placeholder="e.g. A happy pop song about summer... or use a genre preset above"
                  className="w-full h-28 bg-transparent text-sm text-zinc-900 dark:text-white placeholder-zinc-400 dark:placeholder-zinc-600 focus:outline-none resize-none border-0 p-0"
                />
              </div>
            </div>

            {/* Vocal Language (Simple) */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5">
                Vocal Language
              </div>
              <select
                value={vocalLanguage}
                onChange={(e) => setVocalLanguage(e.target.value)}
                className="w-full bg-transparent p-3 text-sm text-zinc-900 dark:text-white focus:outline-none"
              >
                {VOCAL_LANGUAGES.map(lang => (
                  <option key={lang.value} value={lang.value}>{lang.label}</option>
                ))}
              </select>
            </div>

            {/* Quality preset (Simple + Advanced) — Basic / Great / Best from ACE-Step docs */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5 flex items-center gap-1.5">
                Quality
                <InfoTooltip text="Basic: fast, fewer steps. Great: balanced. Best: maximum quality (more steps, higher guidance, LM thinking)." />
              </div>
              <div className="p-3 flex gap-2">
                {(['basic', 'great', 'best'] as const).map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => applyPreset(p)}
                    className={`flex-1 py-2 rounded-lg text-xs font-semibold transition-colors ${
                      qualityPreset === p
                        ? 'bg-pink-600 text-white'
                        : 'bg-zinc-100 dark:bg-black/30 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-white/10'
                    }`}
                  >
                    {p === 'basic' ? 'Basic' : p === 'great' ? 'Great' : 'Best'}
                  </button>
                ))}
              </div>
            </div>

            {/* Exclude styles (Suno-like negative prompt) — right above sliders */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 flex items-center gap-2">
                <Wrench size={14} className="text-zinc-500 dark:text-zinc-400 shrink-0" />
                <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Exclude styles</label>
                <InfoTooltip text="Things to avoid in the output (e.g. genres, instruments, mood). Added as negative guidance." />
              </div>
              <input
                type="text"
                value={negativePrompt}
                onChange={(e) => setNegativePrompt(e.target.value)}
                placeholder="e.g. heavy distortion, screaming"
                className="w-full bg-transparent px-3 pb-3 pt-0 text-sm text-zinc-900 dark:text-white placeholder-zinc-400 dark:placeholder-zinc-600 focus:outline-none border-0"
              />
            </div>

            {/* SUNO-like influence sliders (Simple): Weirdness, Style Influence, Audio Influence */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 p-4 space-y-4">
              <h3 className="text-xs font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide flex items-center gap-2">
                <Sliders size={14} />
                Generation influence
              </h3>
              <p className="text-[11px] text-zinc-500 dark:text-zinc-400">Fine-tune how the model follows your description and reference (if any).</p>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="inline-flex items-center gap-1.5">
                    <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Weirdness</label>
                    <InfoTooltip text="Higher = more creative/experimental; lower = more predictable and on-prompt." />
                  </span>
                  <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">{weirdness}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="5"
                  value={weirdness}
                  onChange={(e) => setWeirdness(Number(e.target.value))}
                  className="w-full h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
                />
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="inline-flex items-center gap-1.5">
                    <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Style influence</label>
                    <InfoTooltip text="How strongly the style/caption is followed. Higher = closer to your description." />
                  </span>
                  <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">{styleInfluence}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="5"
                  value={styleInfluence}
                  onChange={(e) => setStyleInfluence(Number(e.target.value))}
                  className="w-full h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
                />
              </div>

              {(referenceAudioUrl?.trim() || sourceAudioUrl?.trim()) && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-1.5">
                      <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Audio influence</label>
                      <InfoTooltip text="How much the reference/cover audio influences the result. Higher = stronger reference style." />
                    </span>
                    <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">{audioInfluence}%</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    step="5"
                    value={audioInfluence}
                    onChange={(e) => setAudioInfluence(Number(e.target.value))}
                    className="w-full h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
                  />
                </div>
              )}
            </div>

            {/* Reference & cover (optional) — same as Custom but compact; no hidden features */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 p-4 space-y-3">
              <h3 className="text-xs font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">Reference & cover (optional)</h3>
              <p className="text-[11px] text-zinc-500 dark:text-zinc-400">Use a style reference or a song to cover. Leave empty to generate from your description only.</p>
              <div className="space-y-3">
                <div>
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Reference style</span>
                    <div className="flex gap-1.5">
                      <button type="button" onClick={() => openAudioModal('reference')} className="flex items-center justify-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-medium bg-zinc-100 dark:bg-white/5 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-white/10 transition-colors">
                        Choose from library
                      </button>
                    </div>
                  </div>
                  {referenceAudioUrl ? <p className="text-[11px] text-pink-600 dark:text-pink-400 truncate" title={referenceAudioUrl}>Reference: {getAudioLabel(referenceAudioUrl)}</p> : <p className="text-[11px] text-zinc-400 italic">None</p>}
                </div>
                <div>
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Song to cover</span>
                    <div className="flex gap-1.5">
                      <button type="button" onClick={() => openAudioModal('source')} className="flex items-center justify-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-medium bg-zinc-100 dark:bg-white/5 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-white/10 transition-colors">
                        Choose from library
                      </button>
                    </div>
                  </div>
                  {sourceAudioUrl ? <p className="text-[11px] text-emerald-600 dark:text-emerald-400 truncate" title={sourceAudioUrl}>Cover: {getAudioLabel(sourceAudioUrl)}</p> : <p className="text-[11px] text-zinc-400 italic">None</p>}
                </div>
              </div>
            </div>

            {/* Quick Settings (Simple Mode) */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 p-4 space-y-4">
              <h3 className="text-xs font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide flex items-center gap-2">
                <Sliders size={14} />
                Quick Settings
              </h3>

              {/* Duration */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Duration</label>
                  <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">
                    {duration === -1 ? 'Auto' : `${duration}s`}
                  </span>
                </div>
                <input
                  type="range"
                  min="-1"
                  max="600"
                  step="5"
                  value={duration}
                  onChange={(e) => setDuration(Number(e.target.value))}
                  className="w-full h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
                />
              </div>

              {/* BPM */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">BPM</label>
                  <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">
                    {bpm === 0 ? 'Auto' : bpm}
                  </span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="300"
                  step="5"
                  value={bpm}
                  onChange={(e) => setBpm(Number(e.target.value))}
                  className="w-full h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
                />
              </div>

              {/* Key & Time Signature */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Key</label>
                  <select
                    value={keyScale}
                    onChange={(e) => setKeyScale(e.target.value)}
                    className="w-full bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg px-2 py-1.5 text-xs text-zinc-900 dark:text-white focus:outline-none"
                  >
                    <option value="">Auto</option>
                    {KEY_SIGNATURES.filter(k => k).map(key => (
                      <option key={key} value={key}>{key}</option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Time</label>
                  <select
                    value={timeSignature}
                    onChange={(e) => setTimeSignature(e.target.value)}
                    className="w-full bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg px-2 py-1.5 text-xs text-zinc-900 dark:text-white focus:outline-none"
                  >
                    <option value="">Auto</option>
                    {TIME_SIGNATURES.filter(t => t).map(time => (
                      <option key={time} value={time}>{time}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Variations */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Variations</label>
                  <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">{batchSize}</span>
                </div>
                <input
                  type="range"
                  min="1"
                  max="4"
                  step="1"
                  value={batchSize}
                  onChange={(e) => setBatchSize(Number(e.target.value))}
                  className="w-full h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
                />
                <p className="text-[10px] text-zinc-500">Number of song variations to generate</p>
              </div>
            </div>
          </div>
        )}

        {/* COVER MODE — pure cover: source audio + caption (like ComfyUI audio_ace_step_1_5_cover) */}
        {createMode === 'cover' && (
          <div className="space-y-5">
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 p-4">
              <p className="text-sm text-zinc-600 dark:text-zinc-400">
                Generate a new version of your source audio in a different style. One source + one style description (e.g. &quot;jazz piano cover with swing rhythm&quot;). No semantic blending — pure cover task.
              </p>
            </div>

            {/* Title (optional) */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5">
                Title (optional)
              </div>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Name the output"
                className="w-full bg-transparent p-3 text-sm text-zinc-900 dark:text-white placeholder-zinc-400 dark:placeholder-zinc-600 focus:outline-none"
              />
            </div>

            {/* Source audio (required) */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5 flex items-center gap-1.5">
                Source audio
                <span className="text-red-500">*</span>
                <InfoTooltip text="The audio to re-style (cover). Required." />
              </div>
              <div className="p-3 space-y-2">
                <div className="flex gap-2">
                  <button type="button" onClick={() => openAudioModal('source')} className="flex-1 flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium bg-zinc-100 dark:bg-white/5 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-white/10 transition-colors">
                    Choose from library
                  </button>
                </div>
                <p className="text-[11px] text-zinc-500 dark:text-zinc-400">Pick a track from your library or upload in the picker (uploads go to the library).</p>
                {sourceAudioUrl ? (
                  <p className="text-xs text-emerald-600 dark:text-emerald-400 truncate" title={sourceAudioUrl}>{getAudioLabel(sourceAudioUrl)}</p>
                ) : (
                  <p className="text-xs text-zinc-400 italic">No source audio selected</p>
                )}
              </div>
            </div>

            {/* Cover style (caption) */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5 flex items-center gap-1.5">
                Cover style
                <span className="text-red-500">*</span>
                <InfoTooltip text="Describe the target style (e.g. jazz piano cover with swing rhythm, orchestral version, lo-fi hip hop)." />
              </div>
              <textarea
                value={coverCaption}
                onChange={(e) => setCoverCaption(e.target.value)}
                placeholder="e.g. jazz piano cover with swing rhythm"
                className="w-full h-24 bg-transparent p-3 text-sm text-zinc-900 dark:text-white placeholder-zinc-400 dark:placeholder-zinc-600 focus:outline-none resize-none"
              />
            </div>

            {/* Cover strength */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5 flex items-center gap-1.5">
                Source influence
                <InfoTooltip text="How much the output follows the source (1 = strong adherence, lower = more influence from your cover style)." />
              </div>
              <div className="p-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={coverStrength}
                    onChange={(e) => setCoverStrength(Number(e.target.value))}
                    className="flex-1 h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
                  />
                  <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-1 rounded shrink-0 w-12 text-right">
                    {coverStrength.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between text-[10px] text-zinc-500">
                  <span>0 — style only</span>
                  <span>1 — strong source</span>
                </div>
              </div>
            </div>

            {/* Instrumental / Lyrics override for cover */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5 flex items-center gap-1.5">
                Vocals
                <InfoTooltip text="Instrumental: no vocals. Vocal: override the cover with your own lyrics (e.g. [Verse], [Chorus])." />
              </div>
              <div className="p-3 space-y-3">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setInstrumental(!instrumental)}
                    className={`w-11 h-6 rounded-full flex items-center transition-colors duration-200 px-1 border border-zinc-200 dark:border-white/5 ${instrumental ? 'bg-pink-600' : 'bg-zinc-300 dark:bg-black/40'}`}
                  >
                    <div className={`w-4 h-4 rounded-full bg-white transform transition-transform duration-200 shadow-sm ${instrumental ? 'translate-x-5' : 'translate-x-0'}`} />
                  </button>
                  <span className="text-xs text-zinc-600 dark:text-zinc-400">{instrumental ? 'Instrumental' : 'Vocal (custom lyrics)'}</span>
                </div>
                {!instrumental && (
                  <textarea
                    value={lyrics}
                    onChange={(e) => setLyrics(e.target.value)}
                    placeholder="[Verse]\nYour lyrics for the cover...\n\n[Chorus]\n..."
                    className="w-full h-28 bg-transparent p-3 text-sm text-zinc-900 dark:text-white placeholder-zinc-400 dark:placeholder-zinc-600 focus:outline-none resize-none font-mono leading-relaxed border border-zinc-200 dark:border-white/10 rounded-lg"
                  />
                )}
              </div>
            </div>

            {/* Optional: Blend with second audio */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5 flex items-center gap-1.5">
                Optional: Blend with a second audio
                <InfoTooltip text="Add a second track to blend structure (source) with style/timbre from another. Leave empty for a single-source cover." />
              </div>
              <div className="p-3 space-y-3">
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  Combine the source above with another track: structure and length follow the source; style can follow the second audio.
                </p>
                <div className="flex gap-2">
                  <button type="button" onClick={() => openAudioModal('cover_style')} className="flex-1 flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium bg-zinc-100 dark:bg-white/5 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-white/10 transition-colors">
                    Choose from library
                  </button>
                </div>
                <p className="text-[11px] text-zinc-500 dark:text-zinc-400">Pick from library or upload in the picker (uploads go to the library).</p>
                {coverStyleAudioUrl ? (
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-xs text-emerald-600 dark:text-emerald-400 truncate flex-1 min-w-0" title={coverStyleAudioUrl}>{getAudioLabel(coverStyleAudioUrl)}</p>
                    <button type="button" onClick={() => setCoverStyleAudioUrl('')} className="shrink-0 px-2 py-1 text-[11px] font-medium rounded bg-zinc-200 dark:bg-white/10 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-300 dark:hover:bg-white/20">
                      Clear
                    </button>
                  </div>
                ) : (
                  <p className="text-xs text-zinc-400 italic">No style audio — single-source cover</p>
                )}
                {coverStyleAudioUrl && (
                  <div className="pt-2 border-t border-zinc-100 dark:border-white/5 space-y-2">
                    <label className="text-[11px] font-medium text-zinc-600 dark:text-zinc-400">Blend: source vs style</label>
                    <div className="flex items-center justify-between gap-2">
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.05"
                        value={coverBlendFactor}
                        onChange={(e) => setCoverBlendFactor(Number(e.target.value))}
                        className="flex-1 h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
                      />
                      <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-1 rounded shrink-0 w-12 text-right">
                        {coverBlendFactor.toFixed(2)}
                      </span>
                    </div>
                    <div className="flex justify-between text-[10px] text-zinc-500">
                      <span>0 — more source</span>
                      <span>1 — more style</span>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Inference steps (cover): up to 80 for base model (docs) */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5 flex items-center gap-1.5">
                Inference steps
                <InfoTooltip text="Cover uses Base model automatically. Docs recommend 32–80 steps for base; more steps = better quality, slower." />
              </div>
              <div className="p-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <input
                    type="range"
                    min="8"
                    max="80"
                    step="1"
                    value={inferenceSteps}
                    onChange={(e) => { setInferenceSteps(Number(e.target.value)); setQualityPreset('custom'); }}
                    className="flex-1 h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
                  />
                  <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-1 rounded w-10 text-right">{inferenceSteps}</span>
                </div>
                <p className="text-[10px] text-zinc-500">1–80 (Base model used for Cover; 32–64 recommended)</p>
              </div>
            </div>

            {/* Quality preset */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5 flex items-center gap-1.5">
                Quality
                <InfoTooltip text="Basic: fast. Great: balanced. Best: maximum quality." />
              </div>
              <div className="p-3 flex gap-2">
                {(['basic', 'great', 'best'] as const).map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => applyPreset(p)}
                    className={`flex-1 py-2 rounded-lg text-xs font-semibold transition-colors ${
                      qualityPreset === p ? 'bg-pink-500 text-white' : 'bg-zinc-100 dark:bg-white/5 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-white/10'
                    }`}
                  >
                    {p === 'basic' ? 'Basic' : p === 'great' ? 'Great' : 'Best'}
                  </button>
                ))}
              </div>
            </div>

            {coverValidationError && (
              <p className="text-sm text-red-600 dark:text-red-400" role="alert">{coverValidationError}</p>
            )}
          </div>
        )}

        {/* LEGO MODE — generate a single instrument track over existing audio */}
        {createMode === 'lego' && (
          <div className="space-y-5">
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 p-4">
              <p className="text-sm text-zinc-600 dark:text-zinc-400">
                Generate one instrument track to layer over your backing audio. Pick the track type and describe how it should sound.
              </p>
            </div>

            {/* Title (optional) */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5">
                Title (optional)
              </div>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Name the output"
                className="w-full bg-transparent p-3 text-sm text-zinc-900 dark:text-white placeholder-zinc-400 dark:placeholder-zinc-600 focus:outline-none"
              />
            </div>

            {/* Source audio (required for Lego) */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5 flex items-center gap-1.5">
                Backing audio
                <span className="text-red-500">*</span>
                <InfoTooltip text="The existing audio to add an instrument track to. Required for Lego." />
              </div>
              <div className="p-3 space-y-2">
                <div className="flex gap-2">
                  <button type="button" onClick={() => openAudioModal('source')} className="flex-1 flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium bg-zinc-100 dark:bg-white/5 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-white/10 transition-colors">
                    Choose from library
                  </button>
                </div>
                <p className="text-[11px] text-zinc-500 dark:text-zinc-400">Pick a track from your library or upload in the picker (uploads go to the library).</p>
                {sourceAudioUrl ? (
                  <p className="text-xs text-emerald-600 dark:text-emerald-400 truncate" title={sourceAudioUrl}>{getAudioLabel(sourceAudioUrl)}</p>
                ) : (
                  <p className="text-xs text-zinc-400 italic">No backing audio selected</p>
                )}
              </div>
            </div>

            {/* Track to generate */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5">
                Track to generate
              </div>
              <select
                value={legoTrackName}
                onChange={(e) => setLegoTrackName(e.target.value)}
                className="w-full bg-transparent p-3 text-sm text-zinc-900 dark:text-white focus:outline-none"
              >
                {LEGO_TRACKS.map(t => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>

            {/* Describe the track (caption) */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5">
                Describe the track
              </div>
              <textarea
                value={legoCaption}
                onChange={(e) => setLegoCaption(e.target.value)}
                placeholder="e.g. lead guitar melody with bluesy feel, punchy drums, warm bass line..."
                className="w-full h-24 bg-transparent p-3 text-sm text-zinc-900 dark:text-white placeholder-zinc-400 dark:placeholder-zinc-600 focus:outline-none resize-none"
              />
            </div>

            {/* Backing influence (critical for Lego: low = new instrument, high = copy) */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5 flex items-center gap-1.5">
                Backing influence
                <InfoTooltip text="How much the backing audio affects the result. Lower (0.2–0.4) = more new instrument from your description; higher = output closer to the backing (can sound like a copy). Start with 0.25 and increase if timing drifts." />
              </div>
              <div className="p-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={legoBackingInfluence}
                    onChange={(e) => setLegoBackingInfluence(Number(e.target.value))}
                    className="flex-1 h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
                  />
                  <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-1 rounded shrink-0 w-12 text-right">
                    {legoBackingInfluence.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between text-[10px] text-zinc-500">
                  <span>0 — prompt only</span>
                  <span>1 — strong backing</span>
                </div>
              </div>
            </div>

            {/* Quality preset (Lego) */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5 flex items-center gap-1.5">
                Quality
                <InfoTooltip text="Basic: fast. Great: balanced. Best: maximum quality (more steps, LM thinking)." />
              </div>
              <div className="p-3 flex gap-2">
                {(['basic', 'great', 'best'] as const).map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => applyPreset(p)}
                    className={`flex-1 py-2 rounded-lg text-xs font-semibold transition-colors ${
                      qualityPreset === p ? 'bg-pink-500 text-white' : 'bg-zinc-100 dark:bg-white/5 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-white/10'
                    }`}
                  >
                    {p === 'basic' ? 'Basic' : p === 'great' ? 'Great' : 'Best'}
                  </button>
                ))}
              </div>
            </div>

            {/* Lego tuning (optional) — key sliders for experiments; report what works best */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5 flex items-center gap-1.5">
                Lego tuning (optional)
                <InfoTooltip text="Critical parameters for Lego. Tweak and report what works best: backing influence (low = new instrument, high = copy), guidance (higher = follow prompt more), steps (more = quality)." />
              </div>
              <div className="p-3 space-y-4">
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Backing influence</label>
                    <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">{legoBackingInfluence.toFixed(2)}</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={legoBackingInfluence}
                    onChange={(e) => setLegoBackingInfluence(Number(e.target.value))}
                    className="w-full h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
                  />
                  <p className="text-[10px] text-zinc-500">0 = prompt only, 1 = strong backing (risk of copy)</p>
                </div>
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Guidance scale</label>
                    <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">{guidanceScale.toFixed(1)}</span>
                  </div>
                  <input
                    type="range"
                    min="2"
                    max="12"
                    step="0.5"
                    value={guidanceScale}
                    onChange={(e) => { setGuidanceScale(Number(e.target.value)); setQualityPreset('custom'); }}
                    className="w-full h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
                  />
                  <p className="text-[10px] text-zinc-500">Higher = stronger adherence to track description (Base: 5–9 typical)</p>
                </div>
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Inference steps</label>
                    <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">{inferenceSteps}</span>
                  </div>
                  <input
                    type="range"
                    min="8"
                    max="75"
                    step="1"
                    value={inferenceSteps}
                    onChange={(e) => { setInferenceSteps(Number(e.target.value)); setQualityPreset('custom'); }}
                    className="w-full h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
                  />
                  <p className="text-[10px] text-zinc-500">More steps = better quality, slower (Base: 32–65 typical)</p>
                </div>
              </div>
            </div>

          </div>
        )}

        {/* CUSTOM MODE */}
        {createMode === 'custom' && (
          <div className="space-y-5">
            {/* Title */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5">
                Title
              </div>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Name your song"
                className="w-full bg-transparent p-3 text-sm text-zinc-900 dark:text-white placeholder-zinc-400 dark:placeholder-zinc-600 focus:outline-none"
              />
            </div>

            {/* Style of Music (shared with Simple: same style field + genre presets) */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden transition-colors group focus-within:border-zinc-400 dark:focus-within:border-white/20">
              <div className="flex items-center justify-between px-3 py-2.5 bg-zinc-50 dark:bg-white/5 border-b border-zinc-100 dark:border-white/5">
                <div>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="text-xs font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">Style of Music</span>
                    <InfoTooltip text={(taskType === 'cover' || taskType === 'audio2audio') ? 'Target style for the cover (genre, mood, instruments). Lower Cover Strength gives this more influence over the source.' : 'Genre, mood, instruments, vibe. Same as Simple mode — switching tabs keeps this text.'} />
                  </span>
                  <p className="text-[11px] text-zinc-400 dark:text-zinc-500 mt-0.5">Genre, mood, instruments, vibe</p>
                </div>
                <button
                  className={`p-1.5 hover:bg-zinc-200 dark:hover:bg-white/10 rounded transition-colors ${isFormatting ? 'text-pink-500 animate-pulse' : 'text-zinc-500 hover:text-black dark:hover:text-white'}`}
                  title="AI Format - Enhance style & auto-fill parameters"
                  onClick={handleFormat}
                  disabled={isFormatting || !style.trim()}
                >
                  <Sparkles size={14} />
                </button>
              </div>
              <div className="p-3 space-y-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <label className="text-[11px] font-medium text-zinc-600 dark:text-zinc-400 shrink-0">Genre preset:</label>
                  <select
                    value={Object.keys(GENRE_PRESETS).find(k => GENRE_PRESETS[k] === style) || 'Custom'}
                    onChange={(e) => {
                      const key = e.target.value;
                      if (key === 'Custom') return;
                      const text = GENRE_PRESETS[key];
                      if (text) {
                        setStyle(text);
                        const bpmMatch = text.match(/(\d+)\s*bpm/i);
                        if (bpmMatch) setBpm(parseInt(bpmMatch[1], 10));
                      }
                    }}
                    className="bg-zinc-100 dark:bg-black/30 text-zinc-900 dark:text-white text-xs rounded-lg px-2.5 py-1.5 border-0 focus:ring-2 focus:ring-pink-500/50 focus:outline-none"
                  >
                    <option value="Custom">Custom (type below)</option>
                    {Object.keys(GENRE_PRESETS).map((name) => (
                      <option key={name} value={name}>{name}</option>
                    ))}
                  </select>
                </div>
                <textarea
                  value={style}
                  onChange={(e) => setStyle(e.target.value)}
                  placeholder="e.g. upbeat pop rock, emotional ballad, 90s hip hop — or use a genre preset above"
                  className="w-full h-20 bg-transparent text-sm text-zinc-900 dark:text-white placeholder-zinc-400 dark:placeholder-zinc-600 focus:outline-none resize-none border-0 p-0"
                />
              </div>
              <div className="px-3 pb-3 flex flex-wrap gap-2">
                {['Pop', 'Rock', 'Electronic', 'Hip Hop', 'Jazz', 'Classical'].map(tag => (
                  <button
                    key={tag}
                    onClick={() => setStyle(prev => prev ? `${prev}, ${tag}` : tag)}
                    className="text-[10px] font-medium bg-zinc-100 dark:bg-white/5 hover:bg-zinc-200 dark:hover:bg-white/10 text-zinc-600 dark:text-zinc-400 hover:text-black dark:hover:text-white px-2.5 py-1 rounded-full transition-colors border border-zinc-200 dark:border-white/5"
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>

            {/* Lyrics */}
            <div
              ref={lyricsRef}
              className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden transition-colors group focus-within:border-zinc-400 dark:focus-within:border-white/20 relative flex flex-col"
              style={{ height: 'auto' }}
            >
              <div className="flex items-center justify-between px-3 py-2.5 bg-zinc-50 dark:bg-white/5 border-b border-zinc-100 dark:border-white/5 flex-shrink-0">
                <div>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="text-xs font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">Lyrics</span>
                    <InfoTooltip text={(taskType === 'cover' || taskType === 'audio2audio') ? 'Target lyrics for the cover. Uncheck Instrumental to use them. Lower Cover Strength gives your lyrics more influence.' : 'Lyric content and structure. Use [Verse], [Chorus], etc. Leave empty or use Instrumental for no vocals.'} />
                  </span>
                  <p className="text-[11px] text-zinc-400 dark:text-zinc-500 mt-0.5">Leave empty for instrumental or switch to Instrumental below</p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setInstrumental(!instrumental)}
                    className={`px-2.5 py-1 rounded-full text-[10px] font-semibold border transition-colors ${
                      instrumental
                        ? 'bg-pink-600 text-white border-pink-500'
                        : 'bg-white dark:bg-suno-card border-zinc-200 dark:border-white/10 text-zinc-600 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-white/10'
                    }`}
                  >
                    {instrumental ? 'Instrumental' : 'Vocal'}
                  </button>
                  <button
                    className={`p-1.5 hover:bg-zinc-200 dark:hover:bg-white/10 rounded transition-colors ${isFormatting ? 'text-pink-500 animate-pulse' : 'text-zinc-500 hover:text-black dark:hover:text-white'}`}
                    title="AI Format - Enhance style & auto-fill parameters"
                    onClick={handleFormat}
                    disabled={isFormatting || !style.trim()}
                  >
                    <Sparkles size={14} />
                  </button>
                  <button
                    className="p-1.5 hover:bg-zinc-200 dark:hover:bg-white/10 rounded text-zinc-500 hover:text-black dark:hover:text-white transition-colors"
                    onClick={() => setLyrics('')}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              <textarea
                disabled={instrumental}
                value={lyrics}
                onChange={(e) => setLyrics(e.target.value)}
                placeholder={instrumental ? "Instrumental mode - no lyrics needed" : "[Verse]\nYour lyrics here...\n\n[Chorus]\nThe catchy part..."}
                className={`w-full bg-transparent p-3 text-sm text-zinc-900 dark:text-white placeholder-zinc-400 dark:placeholder-zinc-600 focus:outline-none resize-none font-mono leading-relaxed ${instrumental ? 'opacity-30 cursor-not-allowed' : ''}`}
                style={{ height: `${lyricsHeight}px` }}
              />
              <div
                onMouseDown={startResizing}
                className="h-3 w-full cursor-ns-resize flex items-center justify-center hover:bg-zinc-100 dark:hover:bg-white/5 transition-colors absolute bottom-0 left-0 z-10"
              >
                <div className="w-8 h-1 rounded-full bg-zinc-300 dark:bg-zinc-700"></div>
              </div>
            </div>

            {/* Vocal Language (Custom) */}
            <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden">
              <div className="px-3 py-2.5 text-xs font-bold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/5 flex items-center gap-1.5">
                Vocal Language
                <InfoTooltip text="ISO 639-1 language code for vocals. Auto/unknown lets the model detect. Affects vocal characteristics when not in Instrumental mode." />
              </div>
              <select
                value={vocalLanguage}
                onChange={(e) => setVocalLanguage(e.target.value)}
                className="w-full bg-transparent p-3 text-sm text-zinc-900 dark:text-white focus:outline-none"
              >
                {VOCAL_LANGUAGES.map(lang => (
                  <option key={lang.value} value={lang.value}>{lang.label}</option>
                ))}
              </select>
              <p className="text-[11px] text-zinc-400 dark:text-zinc-500 px-3 pb-2">Applies when not in Instrumental mode</p>
            </div>

            {/* Audio */}
            <div
              onDrop={(e) => handleDrop(e, audioTab)}
              onDragOver={handleDragOver}
              className="bg-white dark:bg-[#1a1a1f] rounded-xl border border-zinc-200 dark:border-white/5 overflow-hidden"
            >
              {/* Header with Audio label, selected track names, and tabs */}
              <div className="px-3 py-2.5 border-b border-zinc-100 dark:border-white/5 bg-zinc-50 dark:bg-white/[0.02]">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="min-w-0 flex-1">
                    <span className="text-xs font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">Audio</span>
                    {referenceAudioUrl && (
                      <p className="text-[11px] text-pink-600 dark:text-pink-400 mt-0.5 truncate" title={referenceAudioUrl}>
                        Reference: {getAudioLabel(referenceAudioUrl)}
                      </p>
                    )}
                    {sourceAudioUrl && (
                      <p className="text-[11px] text-emerald-600 dark:text-emerald-400 mt-0.5 truncate" title={sourceAudioUrl}>
                        Cover: {getAudioLabel(sourceAudioUrl)}
                      </p>
                    )}
                    {!referenceAudioUrl && !sourceAudioUrl && (taskType === 'cover' || taskType === 'audio2audio' || taskType === 'repaint' || taskType === 'extend' || taskType === 'lego' || taskType === 'extract' || taskType === 'complete') && (
                      <p className="text-[10px] text-amber-600 dark:text-amber-400 mt-0.5">Source/cover audio required for this mode</p>
                    )}
                  </div>
                  <div className="flex items-center gap-1 bg-zinc-200/50 dark:bg-black/30 rounded-lg p-0.5">
                    <button
                      type="button"
                      onClick={() => setAudioTab('reference')}
                      className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all inline-flex items-center gap-1.5 ${
                        audioTab === 'reference'
                          ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-white shadow-sm'
                          : 'text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200'
                      }`}
                      title="Style reference (used for Text → Music or Audio → Audio)"
                    >
                      Reference
                      {referenceAudioUrl && <span className="w-1.5 h-1.5 rounded-full bg-pink-500" aria-label="Reference selected" />}
                    </button>
                    <button
                      type="button"
                      onClick={() => setAudioTab('source')}
                      className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-all inline-flex items-center gap-1.5 ${
                        audioTab === 'source'
                          ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-white shadow-sm'
                          : 'text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200'
                      }`}
                      title="Source to cover, repaint, or extend (required for Cover/Repaint/Extend)"
                    >
                      Cover
                      {sourceAudioUrl && <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" aria-label="Cover selected" />}
                    </button>
                  </div>
                </div>
              </div>

              {/* Audio Content */}
              <div className="p-3 space-y-2">
                {/* Reference tab: selected state */}
                {audioTab === 'reference' && referenceAudioUrl && (
                  <div className="rounded-lg border-2 border-pink-500/40 dark:border-pink-400/50 bg-pink-500/5 dark:bg-pink-500/10 p-2.5 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-pink-700 dark:text-pink-300">
                        <span className="w-2 h-2 rounded-full bg-pink-500" aria-hidden />
                        Reference selected
                      </span>
                      <button
                        type="button"
                        onClick={() => { setReferenceAudioUrl(''); setReferencePlaying(false); setReferenceTime(0); setReferenceDuration(0); }}
                        className="flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium bg-zinc-200 dark:bg-white/10 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-300 dark:hover:bg-white/20 transition-colors"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/></svg>
                        Deselect
                      </button>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => toggleAudio('reference')}
                        className="relative flex-shrink-0 w-10 h-10 rounded-full bg-gradient-to-br from-pink-500 to-purple-600 text-white flex items-center justify-center shadow-lg shadow-pink-500/20 hover:scale-105 transition-transform"
                      >
                        {referencePlaying ? (
                          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/></svg>
                        ) : (
                          <svg className="w-4 h-4 ml-0.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                        )}
                        <span className="absolute -bottom-1 -right-1 text-[8px] font-bold bg-zinc-900 text-white px-1 py-0.5 rounded">
                          {formatTime(referenceDuration)}
                        </span>
                      </button>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium text-zinc-800 dark:text-zinc-200 truncate mb-1.5">
                          {getAudioLabel(referenceAudioUrl)}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-zinc-400 tabular-nums">{formatTime(referenceTime)}</span>
                          <div
                            className="flex-1 h-1.5 rounded-full bg-zinc-200 dark:bg-white/10 cursor-pointer group/seek"
                            onClick={(e) => {
                              if (referenceAudioRef.current && referenceDuration > 0) {
                                const rect = e.currentTarget.getBoundingClientRect();
                                const percent = (e.clientX - rect.left) / rect.width;
                                referenceAudioRef.current.currentTime = percent * referenceDuration;
                              }
                            }}
                          >
                            <div
                              className="h-full bg-gradient-to-r from-pink-500 to-purple-500 rounded-full transition-all relative"
                              style={{ width: referenceDuration ? `${Math.min(100, (referenceTime / referenceDuration) * 100)}%` : '0%' }}
                            >
                              <div className="absolute right-0 top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-white shadow-md opacity-0 group-hover/seek:opacity-100 transition-opacity" />
                            </div>
                          </div>
                          <span className="text-[10px] text-zinc-400 tabular-nums">{formatTime(referenceDuration)}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
                {/* Reference tab: empty state */}
                {audioTab === 'reference' && !referenceAudioUrl && (
                  <div className="rounded-lg border border-dashed border-zinc-300 dark:border-white/20 bg-zinc-50/50 dark:bg-white/[0.02] p-3 text-center">
                    <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-2">No reference audio selected</p>
                    <p className="text-[11px] text-zinc-400 dark:text-zinc-500 mb-3">Upload a file or choose from your library to use as style reference.</p>
                    <div className="flex gap-2 justify-center">
                      <button type="button" onClick={() => openAudioModal('reference')} className="flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[11px] font-medium bg-zinc-100 dark:bg-white/5 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-white/10 transition-colors">
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"/></svg>
                        Choose from Library
                      </button>
                      <button type="button" onClick={() => openAudioModal('reference')} className="flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[11px] font-medium bg-zinc-100 dark:bg-white/5 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-white/10 transition-colors">
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/></svg>
                        Upload
                      </button>
                    </div>
                  </div>
                )}

                {/* Source/Cover tab: selected state */}
                {audioTab === 'source' && sourceAudioUrl && (
                  <div className="rounded-lg border-2 border-emerald-500/40 dark:border-emerald-400/50 bg-emerald-500/5 dark:bg-emerald-500/10 p-2.5 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                        <span className="w-2 h-2 rounded-full bg-emerald-500" aria-hidden />
                        Cover selected
                      </span>
                      <button
                        type="button"
                        onClick={() => { setSourceAudioUrl(''); setSourcePlaying(false); setSourceTime(0); setSourceDuration(0); }}
                        className="flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium bg-zinc-200 dark:bg-white/10 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-300 dark:hover:bg-white/20 transition-colors"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/></svg>
                        Deselect
                      </button>
                    </div>
                    <div className="flex items-center gap-3">
                      <button type="button" onClick={() => toggleAudio('source')} className="relative flex-shrink-0 w-10 h-10 rounded-full bg-gradient-to-br from-emerald-500 to-teal-600 text-white flex items-center justify-center shadow-lg shadow-emerald-500/20 hover:scale-105 transition-transform">
                        {sourcePlaying ? <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/></svg> : <svg className="w-4 h-4 ml-0.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>}
                        <span className="absolute -bottom-1 -right-1 text-[8px] font-bold bg-zinc-900 text-white px-1 py-0.5 rounded">{formatTime(sourceDuration)}</span>
                      </button>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium text-zinc-800 dark:text-zinc-200 truncate mb-1.5">{getAudioLabel(sourceAudioUrl)}</div>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-zinc-400 tabular-nums">{formatTime(sourceTime)}</span>
                          <div className="flex-1 h-1.5 rounded-full bg-zinc-200 dark:bg-white/10 cursor-pointer group/seek" onClick={(e) => { if (sourceAudioRef.current && sourceDuration > 0) { const rect = e.currentTarget.getBoundingClientRect(); const percent = (e.clientX - rect.left) / rect.width; sourceAudioRef.current.currentTime = percent * sourceDuration; } }}>
                            <div className="h-full bg-gradient-to-r from-emerald-500 to-teal-500 rounded-full transition-all relative" style={{ width: sourceDuration ? `${Math.min(100, (sourceTime / sourceDuration) * 100)}%` : '0%' }}>
                              <div className="absolute right-0 top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-white shadow-md opacity-0 group-hover/seek:opacity-100 transition-opacity" />
                            </div>
                          </div>
                          <span className="text-[10px] text-zinc-400 tabular-nums">{formatTime(sourceDuration)}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
                {/* Source/Cover tab: empty state */}
                {audioTab === 'source' && !sourceAudioUrl && (
                  <div className="rounded-lg border border-dashed border-zinc-300 dark:border-white/20 bg-zinc-50/50 dark:bg-white/[0.02] p-3 text-center">
                    <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-2">No cover audio selected</p>
                    <p className="text-[11px] text-zinc-400 dark:text-zinc-500 mb-3">Pick from library or upload in the picker (uploads go to the library).</p>
                    <div className="flex gap-2 justify-center">
                      <button type="button" onClick={() => openAudioModal('source')} className="flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[11px] font-medium bg-zinc-100 dark:bg-white/5 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-white/10 transition-colors">
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"/></svg>
                        Choose from Library
                      </button>
                    </div>
                  </div>
                )}

                {/* Action buttons: show when selection exists (to replace) */}
                {((audioTab === 'reference' && referenceAudioUrl) || (audioTab === 'source' && sourceAudioUrl)) && (
                  <div className="flex gap-2">
                    <button type="button" onClick={() => openAudioModal(audioTab)} className="flex-1 flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[11px] font-medium bg-zinc-100 dark:bg-white/5 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-white/10 transition-colors">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"/></svg>
                      Choose from Library (replace)
                    </button>
                  </div>
                )}
              </div>
            </div>

          </div>
        )}

        {/* COMMON SETTINGS */}
        <div className="space-y-4">
          {/* Instrumental Toggle (Simple Mode) */}
          {!customMode && (
            <div className="flex items-center justify-between px-1 py-2">
              <div className="flex items-center gap-2">
                <Music2 size={14} className="text-zinc-500" />
                <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Instrumental</span>
              </div>
              <button
                onClick={() => setInstrumental(!instrumental)}
                className={`w-11 h-6 rounded-full flex items-center transition-colors duration-200 px-1 border border-zinc-200 dark:border-white/5 ${instrumental ? 'bg-pink-600' : 'bg-zinc-300 dark:bg-black/40'}`}
              >
                <div className={`w-4 h-4 rounded-full bg-white transform transition-transform duration-200 shadow-sm ${instrumental ? 'translate-x-5' : 'translate-x-0'}`} />
              </button>
            </div>
          )}

        </div>

        {/* MUSIC PARAMETERS — Custom mode only (Simple has these in Quick Settings) */}
        {customMode && (
        <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 p-4 space-y-4">
          <h3 className="text-xs font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide flex items-center gap-2">
            <Sliders size={14} />
            Music Parameters
          </h3>

          {/* BPM */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5">
                <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">BPM</label>
                <InfoTooltip text="Beats per minute (30–300). Auto (0) lets the model infer tempo from context or lyrics." />
              </span>
              <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">
                {bpm === 0 ? 'Auto' : bpm}
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="300"
              step="5"
              value={bpm}
              onChange={(e) => setBpm(Number(e.target.value))}
              className="w-full h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
            />
            <div className="flex justify-between text-[10px] text-zinc-500">
              <span>Auto</span>
              <span>300</span>
            </div>
          </div>

          {/* Key & Time Signature */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <span className="inline-flex items-center gap-1.5">
                <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Key</label>
                <InfoTooltip text="Musical key (e.g. C major, Am). Empty = auto-detect from context." />
              </span>
              <select
                value={keyScale}
                onChange={(e) => setKeyScale(e.target.value)}
                className="w-full bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg px-2 py-1.5 text-xs text-zinc-900 dark:text-white focus:outline-none"
              >
                <option value="">Auto</option>
                {KEY_SIGNATURES.filter(k => k).map(key => (
                  <option key={key} value={key}>{key}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <span className="inline-flex items-center gap-1.5">
                <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Time</label>
                <InfoTooltip text="Time signature (2/4, 3/4, 4/4, 6/8). Empty = auto-detect." />
              </span>
              <select
                value={timeSignature}
                onChange={(e) => setTimeSignature(e.target.value)}
                className="w-full bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg px-2 py-1.5 text-xs text-zinc-900 dark:text-white focus:outline-none"
              >
                <option value="">Auto</option>
                {TIME_SIGNATURES.filter(t => t).map(time => (
                  <option key={time} value={time}>{time}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
        )}

        {/* ADVANCED SETTINGS — Custom mode only; Simple has no advanced section */}
        {customMode && (
        <>
        <button
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="w-full flex items-center justify-between px-4 py-3 bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 text-sm font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-white/5 transition-colors"
        >
          <div className="flex items-center gap-2">
            <Settings2 size={16} className="text-zinc-500" />
            <span>Advanced Settings</span>
          </div>
          <ChevronDown size={16} className={`text-zinc-500 transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
        </button>

        {showAdvanced && (
          <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 p-4 space-y-4">

            <p className="text-[11px] text-zinc-500 dark:text-zinc-400 border-b border-zinc-100 dark:border-white/5 pb-2">Common to all modes: duration, steps, guidance, seed.</p>

            {/* Exclude styles (negative prompt) — same as Simple, for Custom mode */}
            <div className="space-y-1.5">
              <span className="inline-flex items-center gap-1.5">
                <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Exclude styles</label>
                <InfoTooltip text="Things to avoid in the output (e.g. genres, instruments). Added as negative guidance." />
              </span>
              <input
                type="text"
                value={negativePrompt}
                onChange={(e) => setNegativePrompt(e.target.value)}
                placeholder="e.g. heavy distortion, screaming"
                className="w-full bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg px-3 py-2 text-xs text-zinc-900 dark:text-white focus:outline-none"
              />
            </div>

            {/* Duration */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="inline-flex items-center gap-1.5">
                  <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Duration</label>
                  <InfoTooltip text="Target length in seconds (10–600). Set to Auto (or ≤0) to let the model choose based on lyrics." />
                </span>
                <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">
                  {duration === -1 ? 'Auto' : `${duration}s`}
                </span>
              </div>
              <input
                type="range"
                min="-1"
                max="600"
                step="5"
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
                className="w-full h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
              />
              <div className="flex justify-between text-[10px] text-zinc-500">
                <span>Auto</span>
                <span>4 min</span>
              </div>
            </div>

            {/* Batch Size */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="inline-flex items-center gap-1.5">
                  <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Batch Size (Variations)</label>
                  <InfoTooltip text="Number of samples to generate in one run (1–8). Higher values need more GPU memory." />
                </span>
                <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">{batchSize}</span>
              </div>
              <input
                type="range"
                min="1"
                max="4"
                step="1"
                value={batchSize}
                onChange={(e) => setBatchSize(Number(e.target.value))}
                className="w-full h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
              />
              <p className="text-[10px] text-zinc-500">Number of song variations to generate</p>
            </div>

            {/* Bulk Generate */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="inline-flex items-center gap-1.5">
                  <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Bulk Generate</label>
                  <InfoTooltip text="Queue multiple independent jobs with the same settings. Each job gets a different random seed when enabled." />
                </span>
                <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">
                  {bulkCount} {bulkCount === 1 ? 'job' : 'jobs'}
                </span>
              </div>
              <div className="flex items-center gap-1">
                {[1, 2, 3, 5, 10].map((count) => (
                  <button
                    key={count}
                    onClick={() => setBulkCount(count)}
                    className={`flex-1 py-2 rounded-lg text-xs font-bold transition-all ${
                      bulkCount === count
                        ? 'bg-gradient-to-r from-orange-500 to-pink-600 text-white shadow-md'
                        : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-zinc-700'
                    }`}
                  >
                    {count}
                  </button>
                ))}
              </div>
              <p className="text-[10px] text-zinc-500">Queue multiple independent generation jobs with same settings</p>
            </div>

            {/* Quality Preset */}
            <div className="space-y-2">
              <span className="inline-flex gap-1.5">
                <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Quality preset</label>
                <InfoTooltip text="Basic: ~12 steps, no Thinking. Great: ~40 steps + Thinking/CoT. Best: max quality (~75 steps, guidance 8, full CoT). Custom: use sliders below." />
              </span>
              <select
                value={qualityPreset}
                onChange={(e) => applyPreset(e.target.value as QualityPreset)}
                className="w-full bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg px-3 py-2 text-sm text-zinc-900 dark:text-white focus:outline-none"
              >
                <option value="basic">Basic — fast, fewer steps</option>
                <option value="great">Great — balanced quality</option>
                <option value="best">Best — maximum quality</option>
                <option value="custom">Custom — use sliders only</option>
              </select>
              <p className="text-[10px] text-zinc-500">Preset updates steps, guidance, and Thinking/CoT below</p>
            </div>

            {/* Inference Steps */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="inline-flex items-center gap-1.5">
                  <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Inference Steps</label>
                  <InfoTooltip text="Number of denoising steps. 65 recommended for quality (low CFG + high steps). Turbo: 8–20. Base/Cover: 32–80 (docs)." />
                </span>
                <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">{inferenceSteps}</span>
              </div>
              <input
                type="range"
                min="4"
                max="80"
                step="1"
                value={inferenceSteps}
                onChange={(e) => { setInferenceSteps(Number(e.target.value)); setQualityPreset('custom'); }}
                className="w-full h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
              />
              <p className="text-[10px] text-zinc-500">65 recommended for quality; base/cover can use up to 80 steps (INFERENCE.md)</p>
            </div>

            {/* Guidance Scale */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="inline-flex items-center gap-1.5">
                  <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Guidance Scale</label>
                  <InfoTooltip text="Classifier-free guidance (1–15). Higher = stronger adherence to the text prompt. Typical range 5–9." />
                </span>
                <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">{guidanceScale.toFixed(1)}</span>
              </div>
              <input
                type="range"
                min="1"
                max="15"
                step="0.5"
                value={guidanceScale}
                onChange={(e) => { setGuidanceScale(Number(e.target.value)); setQualityPreset('custom'); }}
                className="w-full h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
              />
              <p className="text-[10px] text-zinc-500">How closely to follow the prompt</p>
            </div>

            {/* Audio Format & Inference Method */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <span className="inline-flex items-center gap-1.5">
                  <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Audio Format</label>
                  <InfoTooltip text="Output file format. FLAC is lossless; MP3 is smaller. Default FLAC for fast saving." />
                </span>
                <select
                  value={audioFormat}
                  onChange={(e) => setAudioFormat(e.target.value as 'mp3' | 'flac')}
                  className="w-full bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg px-2 py-1.5 text-xs text-zinc-900 dark:text-white focus:outline-none"
                >
                  <option value="mp3">MP3 (smaller)</option>
                  <option value="flac">FLAC (lossless)</option>
                </select>
              </div>
              <div className="space-y-1.5">
                <span className="inline-flex items-center gap-1.5">
                  <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Inference Method</label>
                  <InfoTooltip text="ODE (Euler): faster, deterministic. SDE: stochastic, can add variance per run." />
                </span>
                <select
                  value={inferMethod}
                  onChange={(e) => setInferMethod(e.target.value as 'ode' | 'sde')}
                  className="w-full bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg px-2 py-1.5 text-xs text-zinc-900 dark:text-white focus:outline-none"
                >
                  <option value="ode">ODE (deterministic)</option>
                  <option value="sde">SDE (stochastic)</option>
                </select>
              </div>
            </div>

            {/* LoRA adapter (Training / custom_lora) */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <span className="inline-flex items-center gap-1.5">
                  <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">LoRA adapter</label>
                  <InfoTooltip text="Use a custom LoRA (e.g. from Training). After training, click Refresh to see new adapters." />
                  <button
                    type="button"
                    onClick={fetchLoraAdapters}
                    disabled={loraLoading}
                    className="p-0.5 rounded hover:bg-zinc-200 dark:hover:bg-zinc-600 disabled:opacity-50"
                    title="Refresh LoRA list"
                  >
                    {loraLoading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                  </button>
                </span>
                <select
                  value={loraNameOrPath}
                  onChange={(e) => setLoraNameOrPath(e.target.value)}
                  className="w-full bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg px-2 py-1.5 text-xs text-zinc-900 dark:text-white focus:outline-none"
                >
                  <option value="">None</option>
                  {loraAdapters.map((a) => (
                    <option key={a.path} value={a.path}>{a.name}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <span className="inline-flex items-center gap-1.5">
                  <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">LoRA weight</label>
                  <InfoTooltip text="Strength of the LoRA (0–2). 0.75 is a good default; lower = subtler, higher = stronger style." />
                </span>
                <input
                  type="number"
                  min={0}
                  max={2}
                  step={0.05}
                  value={loraWeight}
                  onChange={(e) => setLoraWeight(Number(e.target.value))}
                  className="w-full bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg px-2 py-1.5 text-xs text-zinc-900 dark:text-white focus:outline-none"
                />
              </div>
            </div>

            {/* Seed */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Dices size={14} className="text-zinc-500" />
                  <span className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Seed</span>
                  <InfoTooltip text="Random seed for reproducibility. Use -1 or random for different results each time; fixed positive integer for identical runs." />
                </div>
                <button
                  onClick={() => setRandomSeed(!randomSeed)}
                  className={`w-10 h-5 rounded-full flex items-center transition-colors duration-200 px-0.5 border border-zinc-200 dark:border-white/5 ${randomSeed ? 'bg-pink-600' : 'bg-zinc-300 dark:bg-black/40'}`}
                >
                  <div className={`w-4 h-4 rounded-full bg-white transform transition-transform duration-200 shadow-sm ${randomSeed ? 'translate-x-5' : 'translate-x-0'}`} />
                </button>
              </div>
              <div className="flex items-center gap-2">
                <Hash size={14} className="text-zinc-500" />
                <input
                  type="number"
                  value={seed}
                  onChange={(e) => setSeed(Number(e.target.value))}
                  placeholder="Enter fixed seed"
                  disabled={randomSeed}
                  className={`flex-1 bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg px-3 py-1.5 text-xs text-zinc-900 dark:text-white focus:outline-none ${randomSeed ? 'opacity-40 cursor-not-allowed' : ''}`}
                />
              </div>
              <p className="text-[10px] text-zinc-500">{randomSeed ? 'Randomized every run (recommended)' : 'Fixed seed for reproducible results'}</p>
            </div>

            {/* Thinking Toggle */}
            <div className="flex items-center justify-between py-2 border-t border-zinc-100 dark:border-white/5">
              <span className="inline-flex items-center gap-1.5">
                <span className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Thinking (CoT)</span>
                <InfoTooltip text="Enable LM chain-of-thought for metadata and caption refinement when a thinking LM is selected in Settings. Params are sent to the backend; full LM path may require ACE-Step 1.5 integration." />
              </span>
              <button
                onClick={() => { setThinking(!thinking); setQualityPreset('custom'); }}
                className={`w-10 h-5 rounded-full flex items-center transition-colors duration-200 px-0.5 border border-zinc-200 dark:border-white/5 ${thinking ? 'bg-pink-600' : 'bg-zinc-300 dark:bg-black/40'}`}
              >
                <div className={`w-4 h-4 rounded-full bg-white transform transition-transform duration-200 shadow-sm ${thinking ? 'translate-x-5' : 'translate-x-0'}`} />
              </button>
            </div>

            {/* Shift */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="inline-flex items-center gap-1.5">
                  <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Shift</label>
                  <InfoTooltip text="Timestep shift factor (1–5). Applies t = shift·t/(1+(shift-1)·t). Recommended 3.0 for turbo; less effective on base." />
                </span>
                <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">{shift.toFixed(1)}</span>
              </div>
              <input
                type="range"
                min="1"
                max="5"
                step="0.1"
                value={shift}
                onChange={(e) => setShift(Number(e.target.value))}
                className="w-full h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
              />
              <p className="text-[10px] text-zinc-500">Timestep shift for base models (not effective for turbo)</p>
            </div>

            {/* Divider */}
            <div className="border-t border-zinc-200 dark:border-white/10 pt-4">
              <p className="text-[10px] text-zinc-500 uppercase tracking-wide font-bold mb-3">Expert Controls</p>
            </div>

            {uploadError && (
              <div className="text-[11px] text-rose-500">{uploadError}</div>
            )}

            {/* LM Parameters */}
            <button
              onClick={() => setShowLmParams(!showLmParams)}
              className="w-full flex items-center justify-between px-4 py-3 bg-white/60 dark:bg-black/20 rounded-xl border border-zinc-200/70 dark:border-white/10 text-sm font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-white/5 transition-colors"
            >
              <div className="flex items-center gap-2">
                <Music2 size={16} className="text-zinc-500" />
                <div className="flex flex-col items-start">
                  <span>LM Parameters</span>
                  <span className="text-[11px] text-zinc-400 dark:text-zinc-500 font-normal">Control lyric generation + creativity</span>
                </div>
              </div>
              <ChevronDown size={16} className={`text-zinc-500 transition-transform ${showLmParams ? 'rotate-180' : ''}`} />
            </button>

            {showLmParams && (
              <div className="bg-white dark:bg-suno-card rounded-xl border border-zinc-200 dark:border-white/5 p-4 space-y-4">
                {/* LM Temperature */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-1.5">
                      <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">LM Temperature</label>
                      <InfoTooltip text="LM sampling temperature (0–2). Higher = more creative/diverse, lower = more conservative." />
                    </span>
                    <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">{lmTemperature.toFixed(2)}</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="2"
                    step="0.05"
                    value={lmTemperature}
                    onChange={(e) => setLmTemperature(Number(e.target.value))}
                    className="w-full h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
                  />
                  <p className="text-[10px] text-zinc-500">Higher = more random (0-2)</p>
                </div>

                {/* LM CFG Scale */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-1.5">
                      <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">LM CFG Scale</label>
                      <InfoTooltip text="LM classifier-free guidance. Higher = stronger adherence to prompt. Use with LM Negative Prompt when &gt; 1." />
                    </span>
                    <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">{lmCfgScale.toFixed(1)}</span>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="3"
                    step="0.1"
                    value={lmCfgScale}
                    onChange={(e) => setLmCfgScale(Number(e.target.value))}
                    className="w-full h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
                  />
                  <p className="text-[10px] text-zinc-500">1.0 = no CFG (1-3)</p>
                </div>

                {/* LM Top-K & Top-P */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="inline-flex items-center gap-1.5">
                        <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Top-K</label>
                        <InfoTooltip text="LM top-k sampling. 0 = off. Typical 40–100 to limit token choices." />
                      </span>
                      <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">{lmTopK}</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      step="1"
                      value={lmTopK}
                      onChange={(e) => setLmTopK(Number(e.target.value))}
                      className="w-full h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
                    />
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="inline-flex items-center gap-1.5">
                        <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Top-P</label>
                        <InfoTooltip text="LM nucleus sampling (0–1). 1.0 = off. Typical 0.9–0.95." />
                      </span>
                      <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">{lmTopP.toFixed(2)}</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.01"
                      value={lmTopP}
                      onChange={(e) => setLmTopP(Number(e.target.value))}
                      className="w-full h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
                    />
                  </div>
                </div>

                {/* LM Negative Prompt */}
                <div className="space-y-1.5">
                  <span className="inline-flex items-center gap-1.5">
                    <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">LM Negative Prompt</label>
                    <InfoTooltip text="Text to avoid in LM output. Most useful when LM CFG Scale &gt; 1. Default: NO USER INPUT." />
                  </span>
                  <textarea
                    value={lmNegativePrompt}
                    onChange={(e) => setLmNegativePrompt(e.target.value)}
                    placeholder="Things to avoid..."
                    className="w-full h-16 bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg p-2 text-xs text-zinc-900 dark:text-white focus:outline-none resize-none"
                  />
                  <p className="text-[10px] text-zinc-500">Use when LM CFG Scale {">"} 1.0</p>
                </div>
              </div>
            )}

            <div className="space-y-1">
              <h4 className="text-xs font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">Audio codes (advanced)</h4>
              <p className="text-[11px] text-zinc-400 dark:text-zinc-500">Pre-extracted 5Hz codes; leave empty for normal generation.</p>
            </div>
            <div className="space-y-1.5">
              <span className="inline-flex items-center gap-1.5">
                <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Audio Codes</label>
                <InfoTooltip text="Pre-extracted 5Hz audio semantic codes as a string. Advanced use only; leave empty for normal generation." />
              </span>
              <textarea
                value={audioCodes}
                onChange={(e) => setAudioCodes(e.target.value)}
                placeholder="Optional audio codes payload"
                className="w-full h-16 bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg p-2 text-xs text-zinc-900 dark:text-white focus:outline-none resize-none"
              />
            </div>

            {/* Task type & mode-specific controls */}
            <div className="space-y-1">
              <h4 className="text-xs font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">Generation Mode</h4>
              <p className="text-[11px] text-zinc-400 dark:text-zinc-500">
                {taskType === 'text2music' && 'Generate from style and lyrics only. No audio input required.'}
                {(taskType === 'cover' || taskType === 'audio2audio') && 'Transform an existing track: set a source/cover audio and describe the new style. Use Cover Strength to control how much to follow the original.'}
                {taskType === 'repaint' && 'Regenerate only a time segment of the source. Set start/end (seconds; -1 = end of file) and style for that section.'}
                {taskType === 'extend' && 'Extend the source audio. Use source audio and optional style for the continuation.'}
                {(taskType === 'cover' || taskType === 'lego' || taskType === 'extract' || taskType === 'complete') && 'Requires ACE-Step 1.5 Base model. Cover: style transfer. Lego: add new tracks. Extract: separate stems. Complete: add accompaniment.'}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <span className="inline-flex items-center gap-1.5">
                  <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Task Type</label>
                  <InfoTooltip text="Text→Music: from prompt only. Cover/Audio→Audio: transform a track. Repaint: regenerate a segment. Extend: continue source. Lego/Extract/Complete require Base model (Settings → Models)." />
                </span>
                <select
                  value={taskType}
                  onChange={(e) => {
                    const v = e.target.value;
                    setTaskType(v);
                    setLegoValidationError('');
                    if (taskRequiresBase(v)) {
                      preferencesApi.update({ ace_step_dit_model: 'base' }).catch(() => {});
                    }
                  }}
                  className="w-full bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg px-2 py-1.5 text-xs text-zinc-900 dark:text-white focus:outline-none"
                >
                  <option value="text2music">Text → Music</option>
                  <option value="audio2audio">Audio → Audio</option>
                  <option value="cover">Cover</option>
                  <option value="repaint">Repaint</option>
                  <option value="extend">Extend</option>
                  <option value="lego">Lego (add tracks)</option>
                  <option value="extract">Extract (stems)</option>
                  <option value="complete">Complete (accompaniment)</option>
                </select>
              </div>
              {(taskType === 'cover' || taskType === 'audio2audio' || taskType === 'repaint' || taskType === 'extend' || taskType === 'lego' || taskType === 'extract' || taskType === 'complete') && (
                <div className="space-y-2 col-span-2">
                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-1.5">
                      <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                        {taskType === 'repaint' ? 'Segment blend' : 'Source influence'}
                      </label>
                      <InfoTooltip text={taskType === 'repaint' ? 'Blend strength for the repainted segment (0–1).' : 'Key parameter: how much the output follows the source vs your Style/Lyrics. 1.0 = strong adherence to source; lower (e.g. 0.5–0.7) = more influence from your style and lyrics.'} />
                    </span>
                    <span className="text-xs font-mono text-zinc-900 dark:text-white bg-zinc-100 dark:bg-black/20 px-2 py-0.5 rounded">
                      {Number(audioCoverStrength).toFixed(2)}
                    </span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={audioCoverStrength}
                    onChange={(e) => setAudioCoverStrength(Number(e.target.value))}
                    className="w-full h-2 bg-zinc-200 dark:bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-pink-500"
                    title="20 steps from 0.0 to 1.0"
                  />
                  <div className="flex justify-between text-[10px] text-zinc-500">
                    <span>0 — loose</span>
                    <span>1 — strong (20 steps)</span>
                  </div>
                </div>
              )}
            </div>

            {taskType === 'repaint' && (
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <span className="inline-flex items-center gap-1.5">
                    <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Repaint start (s)</label>
                    <InfoTooltip text="Start time in seconds of the segment to regenerate. Rest of the track stays unchanged." />
                  </span>
                  <input
                    type="number"
                    step="0.1"
                    min={0}
                    value={repaintingStart}
                    onChange={(e) => setRepaintingStart(Number(e.target.value))}
                    className="w-full bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg px-3 py-2 text-xs text-zinc-900 dark:text-white focus:outline-none"
                  />
                </div>
                <div className="space-y-1.5">
                  <span className="inline-flex items-center gap-1.5">
                    <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Repaint end (s)</label>
                    <InfoTooltip text="End time in seconds of the segment. Use -1 for end of file." />
                  </span>
                  <input
                    type="number"
                    step="0.1"
                    value={repaintingEnd}
                    onChange={(e) => setRepaintingEnd(Number(e.target.value))}
                    className="w-full bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg px-3 py-2 text-xs text-zinc-900 dark:text-white focus:outline-none"
                    placeholder="-1 = end"
                  />
                  <p className="text-[10px] text-zinc-500">-1 = end of file</p>
                </div>
              </div>
            )}

            <div className="space-y-1">
              <h4 className="text-xs font-bold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">Guidance</h4>
              <p className="text-[11px] text-zinc-400 dark:text-zinc-500">Advanced CFG scheduling controls.</p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <span className="inline-flex items-center gap-1.5">
                  <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">CFG Interval Start</label>
                  <InfoTooltip text="Ratio (0–1) when to start applying classifier-free guidance during diffusion." />
                </span>
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={cfgIntervalStart}
                  onChange={(e) => setCfgIntervalStart(Number(e.target.value))}
                  className="w-full bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg px-3 py-2 text-xs text-zinc-900 dark:text-white focus:outline-none"
                />
              </div>
              <div className="space-y-1.5">
                <span className="inline-flex items-center gap-1.5">
                  <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">CFG Interval End</label>
                  <InfoTooltip text="Ratio (0–1) when to stop applying classifier-free guidance. Use 1.0 to apply until the end." />
                </span>
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={cfgIntervalEnd}
                  onChange={(e) => setCfgIntervalEnd(Number(e.target.value))}
                  className="w-full bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg px-3 py-2 text-xs text-zinc-900 dark:text-white focus:outline-none"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <span className="inline-flex items-center gap-1.5">
                <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Custom Timesteps</label>
                <InfoTooltip text="Override inference steps with a custom list of timesteps (e.g. 0.97,0.76,0.5,0.28,0). Leave empty to use Inference Steps." />
              </span>
              <input
                type="text"
                value={customTimesteps}
                onChange={(e) => setCustomTimesteps(e.target.value)}
                placeholder="e.g. 1,3,5,7"
                className="w-full bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg px-3 py-2 text-xs text-zinc-900 dark:text-white focus:outline-none"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">Score Scale</label>
                <input
                  type="number"
                  step="0.05"
                  value={scoreScale}
                  onChange={(e) => setScoreScale(Number(e.target.value))}
                  className="w-full bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg px-3 py-2 text-xs text-zinc-900 dark:text-white focus:outline-none"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">LM Batch Chunk Size</label>
                <input
                  type="number"
                  min="1"
                  value={lmBatchChunkSize}
                  onChange={(e) => setLmBatchChunkSize(Number(e.target.value))}
                  className="w-full bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 rounded-lg px-3 py-2 text-xs text-zinc-900 dark:text-white focus:outline-none"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <label className="flex items-center gap-2 text-xs font-medium text-zinc-600 dark:text-zinc-400">
                <input type="checkbox" checked={useAdg} onChange={() => setUseAdg(!useAdg)} />
                Use ADG
              </label>
              <label className="flex items-center gap-2 text-xs font-medium text-zinc-600 dark:text-zinc-400">
                <input type="checkbox" checked={allowLmBatch} onChange={() => setAllowLmBatch(!allowLmBatch)} />
                Allow LM Batch
              </label>
              <label className="flex items-center gap-2 text-xs font-medium text-zinc-600 dark:text-zinc-400">
                <input type="checkbox" checked={useCotMetas} onChange={() => setUseCotMetas(!useCotMetas)} />
                Use CoT Metas
              </label>
              <label className="flex items-center gap-2 text-xs font-medium text-zinc-600 dark:text-zinc-400">
                <input type="checkbox" checked={useCotCaption} onChange={() => setUseCotCaption(!useCotCaption)} />
                Use CoT Caption
              </label>
              <label className="flex items-center gap-2 text-xs font-medium text-zinc-600 dark:text-zinc-400">
                <input type="checkbox" checked={useCotLanguage} onChange={() => setUseCotLanguage(!useCotLanguage)} />
                Use CoT Language
              </label>
              <label className="flex items-center gap-2 text-xs font-medium text-zinc-600 dark:text-zinc-400">
                <input type="checkbox" checked={autogen} onChange={() => setAutogen(!autogen)} />
                Autogen
              </label>
              <label className="flex items-center gap-2 text-xs font-medium text-zinc-600 dark:text-zinc-400">
                <input type="checkbox" checked={constrainedDecodingDebug} onChange={() => setConstrainedDecodingDebug(!constrainedDecodingDebug)} />
                Constrained Decoding Debug
              </label>
              <label className="flex items-center gap-2 text-xs font-medium text-zinc-600 dark:text-zinc-400">
                <input type="checkbox" checked={isFormatCaption} onChange={() => setIsFormatCaption(!isFormatCaption)} />
                Format Caption
              </label>
              <label className="flex items-center gap-2 text-xs font-medium text-zinc-600 dark:text-zinc-400">
                <input type="checkbox" checked={getScores} onChange={() => setGetScores(!getScores)} />
                Get Scores
              </label>
              <label className="flex items-center gap-2 text-xs font-medium text-zinc-600 dark:text-zinc-400">
                <input type="checkbox" checked={getLrc} onChange={() => setGetLrc(!getLrc)} />
                Get LRC (Lyrics)
              </label>
            </div>
          </div>
        )}
        </>
        )}
      </div>

      {showAudioModal && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => { setShowAudioModal(false); setPlayingTrackId(null); }}
          />
          <div className="relative w-[92%] max-w-lg rounded-2xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-white/10 shadow-2xl overflow-hidden">
            {/* Header */}
            <div className="p-5 pb-4">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="text-xl font-semibold text-zinc-900 dark:text-white">
                    {audioModalTarget === 'reference' ? 'Reference' : audioModalTarget === 'cover_style' ? 'Style audio (blend)' : 'Cover'}
                  </h3>
                  <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
                    {audioModalTarget === 'reference'
                      ? 'Create songs inspired by a reference track'
                      : audioModalTarget === 'cover_style'
                        ? 'Second audio to blend with the source — style/timbre from this track'
                        : 'Transform an existing track into a new version'}
                  </p>
                </div>
                <button
                  onClick={() => { setShowAudioModal(false); setPlayingTrackId(null); }}
                  className="p-1.5 rounded-lg hover:bg-zinc-100 dark:hover:bg-white/10 text-zinc-400 hover:text-zinc-900 dark:hover:text-white transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/>
                  </svg>
                </button>
              </div>

              {/* Upload Button */}
              <button
                type="button"
                onClick={() => {
                  const input = document.createElement('input');
                  input.type = 'file';
                  input.accept = '.mp3,.wav,.flac,audio/*';
                  input.onchange = (e) => {
                    const file = (e.target as HTMLInputElement).files?.[0];
                    if (file) void uploadReferenceTrack(file);
                  };
                  input.click();
                }}
                disabled={isUploadingReference}
                className="mt-4 w-full flex items-center justify-center gap-2 rounded-xl border border-dashed border-zinc-300 dark:border-white/20 bg-zinc-50 dark:bg-white/5 px-4 py-3 text-sm font-medium text-zinc-700 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-white/10 hover:border-zinc-400 dark:hover:border-white/30 transition-all"
              >
                {isUploadingReference ? (
                  <>
                    <RefreshCw size={16} className="animate-spin" />
                    Uploading...
                  </>
                ) : (
                  <>
                    <Upload size={16} />
                    Upload audio
                    <span className="text-xs text-zinc-400 ml-1">MP3, WAV, FLAC</span>
                  </>
                )}
              </button>

              {uploadError && (
                <div className="mt-2 text-xs text-rose-500">{uploadError}</div>
              )}
            </div>

            {/* Library + Ref uploads: tag filter and track list */}
            <div className="border-t border-zinc-100 dark:border-white/5">
              <div className="px-5 py-3 flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-2">
                  <span className="px-3 py-1 rounded-full bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 text-xs font-semibold">
                    Library & uploads
                  </span>
                  <span className="text-[11px] text-zinc-400">(local)</span>
                  <button
                    type="button"
                    onClick={() => void fetchReferenceTracks()}
                    disabled={isLoadingTracks}
                    className="p-1 rounded text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-white/10 disabled:opacity-50"
                    title="Refresh library (e.g. after API generations)"
                    aria-label="Refresh library"
                  >
                    <RefreshCw size={14} className={isLoadingTracks ? 'animate-spin' : ''} />
                  </button>
                </div>
                {referenceTracks.length > 0 && (() => {
                  const allTags = Array.from(new Set(referenceTracks.flatMap(t => t.tags || []))).filter(Boolean).sort();
                  return (
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-[10px] text-zinc-500 dark:text-zinc-400">Filter:</span>
                      <button
                        type="button"
                        onClick={() => setLibraryTagFilter('all')}
                        className={`px-2 py-1 rounded-md text-[10px] font-medium transition-colors ${libraryTagFilter === 'all' ? 'bg-zinc-900 dark:bg-white text-white dark:text-zinc-900' : 'bg-zinc-100 dark:bg-white/10 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-white/20'}`}
                      >
                        All
                      </button>
                      {allTags.map(tag => (
                        <button
                          key={tag}
                          type="button"
                          onClick={() => setLibraryTagFilter(tag)}
                          className={`px-2 py-1 rounded-md text-[10px] font-medium transition-colors ${libraryTagFilter === tag ? 'bg-zinc-900 dark:bg-white text-white dark:text-zinc-900' : 'bg-zinc-100 dark:bg-white/10 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-white/20'}`}
                        >
                          {tag}
                        </button>
                      ))}
                    </div>
                  );
                })()}
              </div>

              {/* Track List */}
              <div className="max-h-[280px] overflow-y-auto">
                {isLoadingTracks ? (
                  <div className="px-5 py-8 text-center">
                    <RefreshCw size={20} className="animate-spin mx-auto text-zinc-400" />
                    <p className="text-xs text-zinc-400 mt-2">Loading library...</p>
                  </div>
                ) : (() => {
                  const filtered = libraryTagFilter === 'all'
                    ? referenceTracks
                    : referenceTracks.filter(t => (t.tags || []).includes(libraryTagFilter));
                  return filtered.length === 0 ? (
                    <div className="px-5 py-8 text-center">
                      <Music2 size={24} className="mx-auto text-zinc-300 dark:text-zinc-600" />
                      <p className="text-sm text-zinc-400 mt-2">
                        {referenceTracks.length === 0 ? 'No tracks yet' : `No tracks with tag “${libraryTagFilter}”`}
                      </p>
                      <p className="text-xs text-zinc-400 mt-1">
                        {referenceTracks.length === 0 ? 'Upload audio or generate tracks to see them here' : 'Try “All” or another tag'}
                      </p>
                    </div>
                  ) : (
                    <div className="divide-y divide-zinc-100 dark:divide-white/5">
                      {filtered.map((track) => (
                        <div
                          key={track.id}
                          className="px-5 py-3 flex items-center gap-3 hover:bg-zinc-50 dark:hover:bg-white/[0.02] transition-colors group"
                        >
                          <button
                            type="button"
                            onClick={() => toggleModalTrack(track)}
                            className="flex-shrink-0 w-9 h-9 rounded-full bg-zinc-100 dark:bg-white/10 text-zinc-600 dark:text-zinc-300 flex items-center justify-center hover:bg-zinc-200 dark:hover:bg-white/20 transition-colors"
                          >
                            {playingTrackId === track.id ? (
                              <Pause size={14} fill="currentColor" />
                            ) : (
                              <Play size={14} fill="currentColor" className="ml-0.5" />
                            )}
                          </button>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-medium text-zinc-800 dark:text-zinc-200 truncate">
                                {track.label ?? track.filename.replace(/\.[^/.]+$/, '')}
                              </span>
                              {track.source === 'library' && (
                                <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-500/20 text-emerald-600 dark:text-emerald-400">library</span>
                              )}
                              {track.tags && track.tags.length > 0 && (
                                <div className="flex gap-1">
                                  {track.tags.slice(0, 2).map((tag, i) => (
                                    <span key={i} className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-zinc-200 dark:bg-white/10 text-zinc-600 dark:text-zinc-400">
                                      {tag}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                            {playingTrackId === track.id ? (
                              <div className="flex items-center gap-2 mt-1.5">
                                <span className="text-[10px] text-zinc-400 tabular-nums w-8">{formatTime(modalTrackTime)}</span>
                                <div
                                  className="flex-1 h-1.5 rounded-full bg-zinc-200 dark:bg-white/10 cursor-pointer group/seek"
                                  onClick={(e) => {
                                    if (modalAudioRef.current && modalTrackDuration > 0) {
                                      const rect = e.currentTarget.getBoundingClientRect();
                                      const percent = (e.clientX - rect.left) / rect.width;
                                      modalAudioRef.current.currentTime = percent * modalTrackDuration;
                                    }
                                  }}
                                >
                                  <div
                                    className="h-full bg-gradient-to-r from-pink-500 to-purple-500 rounded-full relative"
                                    style={{ width: modalTrackDuration > 0 ? `${(modalTrackTime / modalTrackDuration) * 100}%` : '0%' }}
                                  >
                                    <div className="absolute right-0 top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-white shadow-md opacity-0 group-hover/seek:opacity-100 transition-opacity" />
                                  </div>
                                </div>
                                <span className="text-[10px] text-zinc-400 tabular-nums w-8 text-right">{formatTime(modalTrackDuration)}</span>
                              </div>
                            ) : (
                              <div className="text-xs text-zinc-400 mt-0.5">
                                {track.duration ? formatTime(track.duration) : '--:--'}
                              </div>
                            )}
                          </div>
                          <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                            <button
                              type="button"
                              onClick={() => useReferenceTrack(track)}
                              className="px-3 py-1.5 rounded-lg bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 text-xs font-semibold hover:bg-zinc-800 dark:hover:bg-zinc-100 transition-colors"
                            >
                              Use
                            </button>
                            {track.source === 'uploaded' && (
                              <button
                                type="button"
                                onClick={() => void deleteReferenceTrack(track.id)}
                                className="p-1.5 rounded-lg hover:bg-zinc-200 dark:hover:bg-white/10 text-zinc-400 hover:text-rose-500 transition-colors"
                                title="Remove uploaded track"
                              >
                                <Trash2 size={14} />
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  );
                })()}
              </div>
            </div>

            {/* Hidden audio element for modal playback */}
            <audio
              ref={modalAudioRef}
              onTimeUpdate={() => {
                if (modalAudioRef.current) {
                  setModalTrackTime(modalAudioRef.current.currentTime);
                }
              }}
              onLoadedMetadata={() => {
                if (modalAudioRef.current) {
                  setModalTrackDuration(modalAudioRef.current.duration);
                  const track = referenceTracks.find(t => t.id === playingTrackId);
                  if (track?.source === 'uploaded' && !track.duration && token) {
                    fetch(`/api/reference-tracks/${track.id}`, {
                      method: 'PATCH',
                      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                      body: JSON.stringify({ duration: Math.round(modalAudioRef.current.duration) })
                    }).then(() => {
                      setReferenceTracks(prev => prev.map(t =>
                        t.id === track.id ? { ...t, duration: Math.round(modalAudioRef.current?.duration || 0) } : t
                      ));
                    }).catch(() => undefined);
                  }
                }
              }}
              onEnded={() => setPlayingTrackId(null)}
            />
          </div>
        </div>
      )}

      {/* Footer Create Button */}
      <div className="p-4 mt-auto sticky bottom-0 bg-zinc-50/95 dark:bg-suno-panel/95 backdrop-blur-sm z-10 border-t border-zinc-200 dark:border-white/5 space-y-3">
        {(legoValidationError || coverValidationError) && (
          <p className="text-sm text-red-600 dark:text-red-400" role="alert">{legoValidationError || coverValidationError}</p>
        )}
        <button
          onClick={() => void handleGenerate()}
          className="w-full h-12 rounded-xl font-bold text-base flex items-center justify-center gap-2 transition-all transform active:scale-[0.98] bg-gradient-to-r from-orange-500 to-pink-600 text-white shadow-lg hover:brightness-110"
        >
          <Sparkles size={18} />
          <span>
            {createMode === 'lego'
              ? 'Generate Lego track'
              : createMode === 'cover'
                ? 'Generate cover'
                : bulkCount > 1
                ? `Create ${bulkCount} Jobs (${bulkCount * batchSize} tracks)`
                : `Create${batchSize > 1 ? ` (${batchSize} variations)` : ''}`}
          </span>
        </button>
      </div>
    </div>
  );
};
