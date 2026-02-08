export interface Song {
  id: string;
  title: string;
  lyrics: string;
  style: string;
  coverUrl: string;
  duration: string;
  createdAt: Date;
  isGenerating?: boolean;
  queuePosition?: number; // Position in queue (undefined = actively generating, number = waiting in queue)
  generationPercent?: number;
  generationSteps?: string;
  generationEtaSeconds?: number;
  /** When status is pending_model: job is waiting for the required model to be installed. */
  generationStatus?: 'queued' | 'running' | 'succeeded' | 'failed' | 'pending_model' | 'cancelled';
  generationPendingReason?: string | null;
  tags: string[];
  audioUrl?: string;
  isPublic?: boolean;
  likeCount?: number;
  viewCount?: number;
  userId?: string;
  creator?: string;
  creator_avatar?: string;
}

export interface Playlist {
  id: string;
  name: string;
  description?: string;
  coverUrl?: string;
  cover_url?: string;
  songIds?: string[];
  isPublic?: boolean;
  is_public?: boolean;
  user_id?: string;
  creator?: string;
  created_at?: string;
  song_count?: number;
  songs?: any[];
}

export interface Comment {
  id: string;
  songId: string;
  userId: string;
  username: string;
  content: string;
  createdAt: Date;
}

export interface GenerationParams {
  // Mode
  customMode: boolean;

  // Simple Mode
  songDescription?: string;

  // Custom Mode
  prompt: string;
  lyrics: string;
  style: string;
  title: string;

  // Common
  instrumental: boolean;
  vocalLanguage: string;

  // Music Parameters
  bpm: number;
  keyScale: string;
  timeSignature: string;
  duration: number;

  // Generation Settings
  inferenceSteps: number;
  guidanceScale: number;
  batchSize: number;
  negativePrompt?: string; // Exclude styles / what to avoid (Suno-like)
  randomSeed: boolean;
  seed: number;
  thinking: boolean;
  audioFormat: 'mp3' | 'flac';
  inferMethod: 'ode' | 'sde';
  shift: number;

  // LM Parameters
  lmTemperature: number;
  lmCfgScale: number;
  lmTopK: number;
  lmTopP: number;
  lmNegativePrompt: string;

  // Expert Parameters
  referenceAudioUrl?: string;
  sourceAudioUrl?: string;
  audioCodes?: string;
  repaintingStart?: number;
  repaintingEnd?: number;
  instruction?: string;
  audioCoverStrength?: number;
  /** When cover uses a second (style) audio, 0 = more source, 1 = more style. */
  coverBlendFactor?: number;
  taskType?: string;
  useAdg?: boolean;
  cfgIntervalStart?: number;
  cfgIntervalEnd?: number;
  customTimesteps?: string;
  useCotMetas?: boolean;
  useCotCaption?: boolean;
  useCotLanguage?: boolean;
  autogen?: boolean;
  constrainedDecodingDebug?: boolean;
  allowLmBatch?: boolean;
  getScores?: boolean;
  getLrc?: boolean;
  scoreScale?: number;
  lmBatchChunkSize?: number;
  isFormatCaption?: boolean;
  loraNameOrPath?: string;
  loraWeight?: number;
  /** Override DiT model for this job (e.g. from Generation tab selector). Only installed models. */
  aceStepDitModel?: string;
}

export interface PlayerState {
  currentSong: Song | null;
  isPlaying: boolean;
  progress: number;
  volume: number;
}

export interface User {
  id: string;
  username: string;
  createdAt: Date;
  followerCount?: number;
  followingCount?: number;
  isFollowing?: boolean;
  isAdmin?: boolean;
  avatar_url?: string;
  banner_url?: string;
}

export interface UserProfile {
  user: User;
  publicSongs: Song[];
  publicPlaylists: Playlist[];
  stats: {
    totalSongs: number;
    totalLikes: number;
  };
}

// Simplified views for ACE-Step UI
export type View =
  | 'create'
  | 'library'
  | 'profile'
  | 'song'
  | 'playlist'
  | 'search'
  | 'training'
  | 'stem-splitting'
  | 'voice-cloning'
  | 'midi';
