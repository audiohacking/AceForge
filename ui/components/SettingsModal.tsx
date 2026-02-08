import React, { useState, useEffect, useRef } from 'react';
import { X, User as UserIcon, Palette, Info, Edit3, ExternalLink, Github, FolderOpen, HardDrive, ZoomIn, Box } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { EditProfileModal } from './EditProfileModal';
import { preferencesApi, aceStepModelsApi } from '../services/api';
import type { AceStepDownloadStatus } from '../services/api';

interface SettingsModalProps {
    isOpen: boolean;
    onClose: () => void;
    theme: 'light' | 'dark';
    onToggleTheme: () => void;
    onNavigateToProfile?: (username: string) => void;
    /** Called when an ACE-Step model download finishes (so pending generation jobs can be retried). */
    onDownloadComplete?: () => void;
}

const ZOOM_OPTIONS = [80, 90, 100, 110, 125] as const;

/** ACE-Step DiT executor variants (Tutorial). */
const ACE_STEP_DIT_OPTIONS = [
  { value: 'turbo', label: 'Turbo (default)', desc: 'Best balance, 8 steps' },
  { value: 'turbo-shift1', label: 'Turbo shift=1', desc: 'Richer details' },
  { value: 'turbo-shift3', label: 'Turbo shift=3', desc: 'Clearer timbre' },
  { value: 'turbo-continuous', label: 'Turbo continuous', desc: 'Flexible shift 1–5' },
  { value: 'sft', label: 'SFT', desc: '50 steps, CFG' },
  { value: 'base', label: 'Base', desc: '50 steps, CFG' },
] as const;

/** ACE-Step LM planner sizes (Tutorial). */
const ACE_STEP_LM_OPTIONS = [
  { value: 'none', label: 'No LM' },
  { value: '0.6B', label: '0.6B' },
  { value: '1.7B', label: '1.7B (default)' },
  { value: '4B', label: '4B' },
] as const;

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose, theme, onToggleTheme, onNavigateToProfile, onDownloadComplete }) => {
    const { user } = useAuth();
    const [isEditProfileOpen, setIsEditProfileOpen] = useState(false);
    const [modelsFolder, setModelsFolder] = useState('');
    const [modelsFolderSaved, setModelsFolderSaved] = useState(false);
    const [outputDir, setOutputDir] = useState('');
    const [outputDirSaved, setOutputDirSaved] = useState(false);
    const [uiZoom, setUiZoom] = useState(80);
    const [uiZoomSaved, setUiZoomSaved] = useState(false);
    const [aceStepDitModel, setAceStepDitModel] = useState<string>('turbo');
    const [aceStepLm, setAceStepLm] = useState<string>('1.7B');
    const [modelsSaved, setModelsSaved] = useState(false);
    const [aceStepList, setAceStepList] = useState<{ dit_models: Array<{ id: string; label: string; description?: string; installed: boolean; size_gb?: number }>; lm_models: Array<{ id: string; label: string; installed: boolean; size_gb?: number }>; discovered_models?: Array<{ id: string; label: string; path: string; custom: boolean }>; acestep_download_available: boolean } | null>(null);
    const [downloadingModel, setDownloadingModel] = useState<string | null>(null);
    const [downloadError, setDownloadError] = useState<string | null>(null);
    const [downloadStatus, setDownloadStatus] = useState<AceStepDownloadStatus | null>(null);
    const [pendingDownload, setPendingDownload] = useState<{ id: string; label: string; sizeGb: number } | null>(null);
    const [diskSpace, setDiskSpace] = useState<{ free_gb: number; total_gb: number } | null>(null);
    const wasDownloadingRef = useRef(false);

    useEffect(() => {
        if (isOpen) {
            preferencesApi.get()
                .then((prefs) => {
                    setOutputDir(prefs.output_dir ?? '');
                    setModelsFolder(prefs.models_folder ?? '');
                    const z = prefs.ui_zoom ?? 80;
                    setUiZoom(ZOOM_OPTIONS.includes(z as typeof ZOOM_OPTIONS[number]) ? (z as number) : 80);
                    const ditVal = prefs.ace_step_dit_model ?? 'turbo';
                    setAceStepDitModel(ACE_STEP_DIT_OPTIONS.some((o) => o.value === ditVal) ? ditVal : 'turbo');
                    const lmVal = prefs.ace_step_lm ?? '1.7B';
                    setAceStepLm(ACE_STEP_LM_OPTIONS.some((o) => o.value === lmVal) ? lmVal : '1.7B');
                })
                .catch(() => {});
            aceStepModelsApi.list().then(setAceStepList).catch(() => setAceStepList(null));
            aceStepModelsApi.downloadStatus().then(setDownloadStatus).catch(() => setDownloadStatus(null));
        }
    }, [isOpen]);

    // Poll download status while a download is running (so we show progress and know when it finishes)
    useEffect(() => {
        if (!isOpen || !downloadStatus?.running) return;
        wasDownloadingRef.current = true;
        const interval = setInterval(() => {
            aceStepModelsApi.downloadStatus()
                .then((s) => {
                    setDownloadStatus(s);
                    if (!s.running) {
                        setDownloadingModel(null);
                        if (s.error && !s.cancelled) setDownloadError(s.error);
                        aceStepModelsApi.list().then(setAceStepList).catch(() => {});
                        if (wasDownloadingRef.current && !s.error) onDownloadComplete?.();
                        wasDownloadingRef.current = false;
                    }
                })
                .catch(() => {});
        }, 1500);
        return () => clearInterval(interval);
    }, [isOpen, downloadStatus?.running, onDownloadComplete]);

    // Restrict selection to installed or discovered models: if current choice not in list, switch to first available
    useEffect(() => {
        if (!aceStepList) return;
        const installedDit = aceStepList.dit_models.filter((m) => m.installed);
        const discovered = aceStepList.discovered_models ?? [];
        const allDitIds = new Set([...installedDit.map((m) => m.id), ...discovered.map((d) => d.id)]);
        const installedLm = aceStepList.lm_models.filter((m) => m.installed);
        const ditOk = allDitIds.has(aceStepDitModel);
        const lmOk = installedLm.some((m) => m.id === aceStepLm);
        if (!ditOk && (installedDit.length > 0 || discovered.length > 0)) {
            const fallback = installedDit[0]?.id ?? discovered[0]?.id ?? 'turbo';
            setAceStepDitModel(fallback);
            preferencesApi.update({ ace_step_dit_model: fallback }).catch(() => {});
        }
        if (!lmOk && installedLm.length > 0) {
            const fallback = installedLm[0].id;
            setAceStepLm(fallback);
            preferencesApi.update({ ace_step_lm: fallback }).catch(() => {});
        }
    }, [aceStepList]); // eslint-disable-line react-hooks/exhaustive-deps -- only run when list changes, sync selection once

    const saveOutputDir = () => {
        preferencesApi.update({ output_dir: outputDir.trim() || undefined })
            .then(() => { setOutputDirSaved(true); setTimeout(() => setOutputDirSaved(false), 2000); })
            .catch(() => {});
    };

    const saveModelsFolder = () => {
        preferencesApi.update({ models_folder: modelsFolder.trim() || undefined })
            .then(() => { setModelsFolderSaved(true); setTimeout(() => setModelsFolderSaved(false), 2000); })
            .catch(() => {});
    };

    const saveAceStepModels = (dit?: string, lm?: string) => {
        const nextDit = dit ?? aceStepDitModel;
        const nextLm = lm ?? aceStepLm;
        if (dit != null) setAceStepDitModel(nextDit);
        if (lm != null) setAceStepLm(nextLm);
        preferencesApi.update({
            ace_step_dit_model: nextDit || 'turbo',
            ace_step_lm: nextLm || '1.7B',
        })
            .then(() => { setModelsSaved(true); setTimeout(() => setModelsSaved(false), 2000); })
            .catch(() => {});
    };

    if (!isOpen || !user) {
        if (isEditProfileOpen && user) {
            return (
                <EditProfileModal
                    isOpen={isEditProfileOpen}
                    onClose={() => setIsEditProfileOpen(false)}
                    onSaved={() => setIsEditProfileOpen(false)}
                />
            );
        }
        return null;
    }

    return (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
            <div
                className="bg-white dark:bg-zinc-900 rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-center justify-between p-6 border-b border-zinc-200 dark:border-white/5">
                    <h2 className="text-2xl font-bold text-zinc-900 dark:text-white">Settings</h2>
                    <button
                        onClick={onClose}
                        className="p-2 hover:bg-zinc-100 dark:hover:bg-white/5 rounded-full transition-colors"
                    >
                        <X size={20} className="text-zinc-500" />
                    </button>
                </div>

                <div className="p-6 space-y-8">
                    {/* AceForge paths (models, output) */}
                    <div className="space-y-4">
                        <div className="flex items-center gap-2 text-zinc-900 dark:text-white">
                            <HardDrive size={20} />
                            <h3 className="font-semibold">Paths</h3>
                        </div>
                        <div className="pl-7 space-y-4">
                            <div>
                                <label className="text-sm text-zinc-500 dark:text-zinc-400 block mb-1">Models folder</label>
                                <p className="text-xs text-zinc-400 dark:text-zinc-500 mb-2">Where ACE-Step and other models are stored. Leave blank for app default. Change takes effect immediately.</p>
                                <div className="flex gap-2">
                                    <input
                                        type="text"
                                        value={modelsFolder}
                                        onChange={(e) => setModelsFolder(e.target.value)}
                                        onBlur={saveModelsFolder}
                                        placeholder="Default (app data folder)"
                                        className="flex-1 rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-900 dark:text-white"
                                    />
                                    <button
                                        type="button"
                                        onClick={saveModelsFolder}
                                        className="px-3 py-2 rounded-lg bg-pink-500 text-white text-sm font-medium hover:bg-pink-600"
                                    >
                                        {modelsFolderSaved ? 'Saved' : 'Save'}
                                    </button>
                                </div>
                            </div>
                            <div>
                                <label className="text-sm text-zinc-500 dark:text-zinc-400 block mb-1">Output directory</label>
                                <p className="text-xs text-zinc-400 dark:text-zinc-500 mb-2">Where generated tracks, stems, voice clones, and MIDI are saved. Leave blank for app default.</p>
                                <div className="flex gap-2">
                                    <input
                                        type="text"
                                        value={outputDir}
                                        onChange={(e) => setOutputDir(e.target.value)}
                                        onBlur={saveOutputDir}
                                        placeholder="Default (app data folder)"
                                        className="flex-1 rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-900 dark:text-white"
                                    />
                                    <button
                                        type="button"
                                        onClick={saveOutputDir}
                                        className="px-3 py-2 rounded-lg bg-pink-500 text-white text-sm font-medium hover:bg-pink-600"
                                    >
                                        {outputDirSaved ? 'Saved' : 'Save'}
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* ACE-Step Models */}
                    <div className="space-y-4">
                        <div className="flex items-center gap-2 text-zinc-900 dark:text-white">
                            <Box size={20} />
                            <h3 className="font-semibold">Models</h3>
                        </div>
                        <div className="pl-7 space-y-4">
                            <p className="text-xs text-zinc-400 dark:text-zinc-500 mb-2">
                                ACE-Step executor (DiT) and planner (LM). See Tutorial for VRAM and quality trade-offs.
                            </p>
                            <div>
                                <label className="text-sm text-zinc-500 dark:text-zinc-400 block mb-1">Current ACE-Step model</label>
                                <p className="text-sm text-zinc-900 dark:text-white font-medium">
                                    {(() => {
                                        const discovered = aceStepList?.discovered_models ?? [];
                                        const effDit = aceStepDitModel;
                                        const effLm = aceStepLm;
                                        const ditLabel = ACE_STEP_DIT_OPTIONS.find((o) => o.value === effDit)?.label ?? discovered.find((d) => d.id === effDit)?.label ?? effDit;
                                        const lmLabel = ACE_STEP_LM_OPTIONS.find((o) => o.value === effLm)?.label ?? effLm;
                                        return `${ditLabel} · LM: ${lmLabel}`;
                                    })()}
                                </p>
                            </div>
                            <div>
                                <label className="text-sm text-zinc-500 dark:text-zinc-400 block mb-1">ACE-Step (DiT) model</label>
                                <p className="text-xs text-zinc-400 dark:text-zinc-500 mb-1">Installed and discovered models in the checkpoints folder. Custom models appear when placed there.</p>
                                <select
                                    value={aceStepList?.dit_models.some((m) => m.id === aceStepDitModel && m.installed) || (aceStepList?.discovered_models ?? []).some((d) => d.id === aceStepDitModel) ? aceStepDitModel : (aceStepList?.dit_models.find((m) => m.installed)?.id ?? aceStepList?.discovered_models?.[0]?.id ?? 'turbo')}
                                    onChange={(e) => saveAceStepModels(e.target.value, undefined)}
                                    className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-900 dark:text-white"
                                >
                                    {aceStepList
                                        ? (() => {
                                            const installed = aceStepList.dit_models.filter((m) => m.installed);
                                            const discovered = aceStepList.discovered_models ?? [];
                                            const seen = new Set(installed.map((m) => m.id));
                                            const options: Array<{ id: string; label: string }> = installed.map((m) => {
                                                const o = ACE_STEP_DIT_OPTIONS.find((opt) => opt.value === m.id);
                                                return { id: m.id, label: o ? `${o.label} — ${o.desc}` : m.label };
                                            });
                                            discovered.forEach((d) => {
                                                if (!seen.has(d.id)) {
                                                    seen.add(d.id);
                                                    options.push({ id: d.id, label: d.custom ? `Custom: ${d.label}` : d.label });
                                                }
                                            });
                                            return options.map((opt) => <option key={opt.id} value={opt.id}>{opt.label}</option>);
                                        })()
                                        : <option value="turbo">Loading…</option>}
                                </select>
                            </div>
                            <div>
                                <label className="text-sm text-zinc-500 dark:text-zinc-400 block mb-1">LM planner</label>
                                <p className="text-xs text-zinc-400 dark:text-zinc-500 mb-1">Bundled ACE-Step 5Hz LM (no external LLM). Used when &quot;Thinking&quot; is on in Create. Download the model below if needed; only installed options appear here.</p>
                                <select
                                    value={aceStepList?.lm_models.some((m) => m.id === aceStepLm && m.installed) ? aceStepLm : (aceStepList?.lm_models.find((m) => m.installed)?.id ?? 'none')}
                                    onChange={(e) => saveAceStepModels(undefined, e.target.value)}
                                    className="w-full rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-900 dark:text-white"
                                >
                                    {aceStepList
                                        ? aceStepList.lm_models.filter((m) => m.installed).map((m) => {
                                            const o = ACE_STEP_LM_OPTIONS.find((opt) => opt.value === m.id);
                                            return <option key={m.id} value={m.id}>{o ? o.label : m.label}</option>;
                                        })
                                        : <option value="none">Loading…</option>}
                                </select>
                            </div>
                            {modelsSaved && <span className="text-xs text-green-600 dark:text-green-400">Saved</span>}
                            {/* Download models */}
                            {aceStepList && (
                                <div className="mt-4 pt-4 border-t border-zinc-200 dark:border-white/5">
                                    <label className="text-sm text-zinc-500 dark:text-zinc-400 block mb-2">Download models</label>
                                    <p className="text-xs text-zinc-400 dark:text-zinc-500 mb-2">
                                        {aceStepList.acestep_download_available
                                            ? 'Download DiT or LM models into the checkpoints folder. (Bundled in app.)'
                                            : 'Downloader not available in this build. Default (Turbo) uses the app download.'}
                                    </p>
                                    {downloadError && <p className="text-xs text-red-600 dark:text-red-400 mb-2">{downloadError}</p>}
                                    {downloadStatus?.running && (
                                        <div className="mb-3 p-3 rounded-lg bg-zinc-100 dark:bg-zinc-800/80 border border-zinc-200 dark:border-white/10">
                                            <div className="flex items-center justify-between gap-2 mb-1">
                                                <span className="text-sm font-medium text-zinc-900 dark:text-white">
                                                    Downloading {downloadStatus.model ?? '…'}
                                                </span>
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        aceStepModelsApi.downloadCancel()
                                                            .then(() => { aceStepModelsApi.downloadStatus().then(setDownloadStatus); });
                                                    }}
                                                    className="text-xs px-2 py-1 rounded bg-red-500/90 text-white hover:bg-red-600"
                                                >
                                                    Cancel
                                                </button>
                                            </div>
                                            <div className="h-2 rounded-full bg-zinc-200 dark:bg-zinc-700 overflow-hidden">
                                                <div
                                                    className="h-full bg-pink-500 transition-all duration-300"
                                                    style={{ width: `${Math.round((downloadStatus.progress ?? 0) * 100)}%` }}
                                                />
                                            </div>
                                            <div className="flex justify-between mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                                                <span>
                                                    {downloadStatus.file_index != null && downloadStatus.total_files != null
                                                        ? `File ${downloadStatus.file_index}/${downloadStatus.total_files}`
                                                        : `${Math.round((downloadStatus.progress ?? 0) * 100)}%`}
                                                    {downloadStatus.current_file ? ` · ${downloadStatus.current_file}` : ''}
                                                </span>
                                                {downloadStatus.eta_seconds != null && downloadStatus.eta_seconds > 0 && (
                                                    <span>~{Math.ceil(downloadStatus.eta_seconds)}s left</span>
                                                )}
                                            </div>
                                        </div>
                                    )}
                                    <div className="space-y-2 max-h-48 overflow-y-auto">
                                        <div className="text-xs font-medium text-zinc-500 dark:text-zinc-400">DiT</div>
                                        {aceStepList.dit_models.map((m) => (
                                            <div key={m.id} className="flex items-center justify-between gap-2 text-sm">
                                                <span className="text-zinc-900 dark:text-white">{m.label}</span>
                                                {m.installed ? (
                                                    <span className="text-xs text-green-600 dark:text-green-400">Installed</span>
                                                ) : !aceStepList.acestep_download_available && m.id !== 'turbo' ? (
                                                    <span className="text-xs text-zinc-500 dark:text-zinc-400">Requires ACE-Step 1.5 CLI</span>
                                                ) : (
                                                    <button
                                                        type="button"
                                                        disabled={downloadStatus?.running === true}
                                                        onClick={() => {
                                                            setDownloadError(null);
                                                            const sizeGb = (m as { size_gb?: number }).size_gb ?? 8;
                                                            setPendingDownload({ id: m.id, label: m.label, sizeGb });
                                                            aceStepModelsApi.diskSpace().then((d) => setDiskSpace(d)).catch(() => setDiskSpace(null));
                                                        }}
                                                        className="text-xs px-2 py-1 rounded bg-pink-500 text-white hover:bg-pink-600 disabled:opacity-50"
                                                    >
                                                        {downloadingModel === m.id || (downloadStatus?.running && downloadStatus?.model === m.id) ? '…' : 'Download'}
                                                    </button>
                                                )}
                                            </div>
                                        ))}
                                        <div className="text-xs font-medium text-zinc-500 dark:text-zinc-400 pt-1">LM</div>
                                        {aceStepList.lm_models.map((m) => (
                                            <div key={m.id} className="flex items-center justify-between gap-2 text-sm">
                                                <span className="text-zinc-900 dark:text-white">{m.label}</span>
                                                {m.installed ? (
                                                    <span className="text-xs text-green-600 dark:text-green-400">Installed</span>
                                                ) : !aceStepList.acestep_download_available ? (
                                                    <span className="text-xs text-zinc-500 dark:text-zinc-400">Requires ACE-Step 1.5 CLI</span>
                                                ) : (
                                                    <button
                                                        type="button"
                                                        disabled={downloadStatus?.running === true}
                                                        onClick={() => {
                                                            setDownloadError(null);
                                                            const sizeGb = (m as { size_gb?: number }).size_gb ?? 4;
                                                            setPendingDownload({ id: m.id, label: m.label, sizeGb });
                                                            aceStepModelsApi.diskSpace().then((d) => setDiskSpace(d)).catch(() => setDiskSpace(null));
                                                        }}
                                                        className="text-xs px-2 py-1 rounded bg-pink-500 text-white hover:bg-pink-600 disabled:opacity-50"
                                                    >
                                                        {downloadingModel === m.id || (downloadStatus?.running && downloadStatus?.model === m.id) ? '…' : 'Download'}
                                                    </button>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Display / Zoom */}
                    <div className="space-y-4">
                        <div className="flex items-center gap-2 text-zinc-900 dark:text-white">
                            <ZoomIn size={20} />
                            <h3 className="font-semibold">Display</h3>
                        </div>
                        <div className="pl-7 space-y-3">
                            <div>
                                <label className="text-sm text-zinc-500 dark:text-zinc-400 block mb-1">UI zoom</label>
                                <p className="text-xs text-zinc-400 dark:text-zinc-500 mb-2">Window zoom level. Takes effect on next app launch.</p>
                                <div className="flex flex-wrap gap-2 items-center">
                                    {ZOOM_OPTIONS.map((pct) => (
                                        <button
                                            key={pct}
                                            type="button"
                                            onClick={() => {
                                                setUiZoom(pct);
                                                preferencesApi.update({ ui_zoom: pct })
                                                    .then(() => { setUiZoomSaved(true); setTimeout(() => setUiZoomSaved(false), 2000); })
                                                    .catch(() => {});
                                            }}
                                            className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${uiZoom === pct
                                                ? 'bg-pink-500 text-white'
                                                : 'bg-zinc-200 dark:bg-zinc-700 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-300 dark:hover:bg-zinc-600'
                                            }`}
                                        >
                                            {pct}%
                                        </button>
                                    ))}
                                    {uiZoomSaved && <span className="text-xs text-green-600 dark:text-green-400">Saved</span>}
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* User Profile Section */}
                    <div className="bg-zinc-50 dark:bg-zinc-800/50 rounded-xl p-6">
                        <div className="flex items-center gap-4">
                            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-2xl font-bold text-white shadow-lg overflow-hidden">
                                {user.avatar_url ? (
                                    <img src={user.avatar_url} alt={user.username} className="w-full h-full object-cover" />
                                ) : (
                                    user.username[0].toUpperCase()
                                )}
                            </div>
                            <div className="flex-1">
                                <h3 className="text-xl font-bold text-zinc-900 dark:text-white">@{user.username}</h3>
                                <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-1">
                                    Member since {new Date(user.createdAt).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
                                </p>
                            </div>
                            <div className="flex gap-2">
                                <button
                                    onClick={() => {
                                        onClose();
                                        setIsEditProfileOpen(true);
                                    }}
                                    className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors"
                                >
                                    <Edit3 size={16} />
                                    Edit Profile
                                </button>
                                <button
                                    onClick={() => {
                                        onClose();
                                        onNavigateToProfile?.(user.username);
                                    }}
                                    className="flex items-center gap-2 px-4 py-2 bg-zinc-200 dark:bg-zinc-700 text-zinc-900 dark:text-white rounded-lg text-sm font-medium hover:bg-zinc-300 dark:hover:bg-zinc-600 transition-colors"
                                >
                                    <ExternalLink size={16} />
                                    View Profile
                                </button>
                            </div>
                        </div>
                    </div>

                    {/* Account Section */}
                    <div className="space-y-4">
                        <div className="flex items-center gap-2 text-zinc-900 dark:text-white">
                            <UserIcon size={20} />
                            <h3 className="font-semibold">Account</h3>
                        </div>
                        <div className="pl-7 space-y-3">
                            <div>
                                <label className="text-sm text-zinc-500 dark:text-zinc-400">Username</label>
                                <p className="text-zinc-900 dark:text-white font-medium">@{user.username}</p>
                            </div>
                        </div>
                    </div>

                    {/* Output directory (global for generation, stems, voice clone, MIDI) */}
                    <div className="space-y-4">
                        <div className="flex items-center gap-2 text-zinc-900 dark:text-white">
                            <FolderOpen size={20} />
                            <h3 className="font-semibold">Output</h3>
                        </div>
                        <div className="pl-7 space-y-3">
                            <div>
                                <label className="text-sm text-zinc-500 dark:text-zinc-400 block mb-1">Output directory</label>
                                <p className="text-xs text-zinc-400 dark:text-zinc-500 mb-2">Where generated tracks, stems, voice clones, and MIDI are saved. Leave blank for app default.</p>
                                <div className="flex gap-2">
                                    <input
                                        type="text"
                                        value={outputDir}
                                        onChange={(e) => setOutputDir(e.target.value)}
                                        onBlur={saveOutputDir}
                                        placeholder="Default (app data folder)"
                                        className="flex-1 rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-900 dark:text-white"
                                    />
                                    <button
                                        type="button"
                                        onClick={saveOutputDir}
                                        className="px-3 py-2 rounded-lg bg-pink-500 text-white text-sm font-medium hover:bg-pink-600"
                                    >
                                        {outputDirSaved ? 'Saved' : 'Save'}
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Theme Section */}
                    <div className="space-y-4">
                        <div className="flex items-center gap-2 text-zinc-900 dark:text-white">
                            <Palette size={20} />
                            <h3 className="font-semibold">Appearance</h3>
                        </div>
                        <div className="pl-7 space-y-3">
                            <div className="flex gap-3">
                                <button
                                    onClick={theme === 'dark' ? onToggleTheme : undefined}
                                    className={`flex-1 py-3 px-4 rounded-lg border-2 font-medium transition-colors ${theme === 'light'
                                            ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
                                            : 'border-zinc-300 dark:border-zinc-700 hover:border-zinc-400 dark:hover:border-zinc-600'
                                        }`}
                                >
                                    Light
                                </button>
                                <button
                                    onClick={theme === 'light' ? onToggleTheme : undefined}
                                    className={`flex-1 py-3 px-4 rounded-lg border-2 font-medium transition-colors ${theme === 'dark'
                                            ? 'border-indigo-500 bg-indigo-950 text-indigo-300'
                                            : 'border-zinc-300 dark:border-zinc-700 hover:border-zinc-400 dark:hover:border-zinc-600'
                                        }`}
                                >
                                    Dark
                                </button>
                            </div>
                        </div>
                    </div>

                    {/* About Section */}
                    <div className="space-y-4">
                        <div className="flex items-center gap-2 text-zinc-900 dark:text-white">
                            <Info size={20} />
                            <h3 className="font-semibold">About</h3>
                        </div>
                        <div className="pl-7 space-y-3 text-sm text-zinc-600 dark:text-zinc-400">
                            <p>Version 1.0.0</p>
                            <p>AceForge</p>
                            <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-2">
                                Powered by ACE-Step 1.5. Open source and free to use.
                            </p>
                            <div className="pt-3 border-t border-zinc-200 dark:border-zinc-700/50 mt-4">
                                <p className="text-zinc-900 dark:text-white font-medium mb-3">AceForge</p>
                                <div className="flex flex-wrap gap-2">
                                    <a
                                        href="https://github.com/audiohacking/AceForge"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center gap-2 px-4 py-2 bg-zinc-800 dark:bg-zinc-700 text-white rounded-lg text-sm font-medium hover:bg-zinc-700 dark:hover:bg-zinc-600 transition-colors"
                                    >
                                        <Github size={16} />
                                        GitHub Repo
                                    </a>
                                </div>
                                <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-3">
                                    Report issues or request features on GitHub
                                </p>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Footer */}
                <div className="border-t border-zinc-200 dark:border-white/5 p-6 flex justify-end">
                    <button
                        onClick={onClose}
                        className="px-6 py-2 bg-zinc-900 dark:bg-white text-white dark:text-black font-semibold rounded-lg hover:bg-zinc-800 dark:hover:bg-zinc-200 transition-colors"
                    >
                        Done
                    </button>
                </div>
            </div>

            {/* Confirm model download: ensure user intends to download and has space */}
            {pendingDownload && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/60 z-10 rounded-2xl" onClick={() => setPendingDownload(null)}>
                    <div className="bg-white dark:bg-zinc-800 rounded-xl shadow-xl p-6 max-w-sm w-full mx-4 border border-zinc-200 dark:border-white/10" onClick={(e) => e.stopPropagation()}>
                        <h4 className="font-semibold text-zinc-900 dark:text-white mb-2">Download model?</h4>
                        <p className="text-sm text-zinc-600 dark:text-zinc-300 mb-2">
                            <strong>{pendingDownload.label}</strong> will use approximately <strong>{pendingDownload.sizeGb} GB</strong>.
                        </p>
                        {diskSpace != null && (
                            <p className="text-sm text-zinc-600 dark:text-zinc-300 mb-4">
                                You have <strong>{diskSpace.free_gb} GB</strong> free. Ensure you have enough space before continuing.
                            </p>
                        )}
                        {diskSpace != null && pendingDownload.sizeGb > 0 && diskSpace.free_gb < pendingDownload.sizeGb && (
                            <p className="text-sm text-amber-600 dark:text-amber-400 mb-4">Low disk space. Free at least {pendingDownload.sizeGb - diskSpace.free_gb} GB more.</p>
                        )}
                        <div className="flex gap-3 justify-end">
                            <button type="button" onClick={() => { setPendingDownload(null); setDiskSpace(null); }} className="px-4 py-2 rounded-lg bg-zinc-200 dark:bg-zinc-600 text-zinc-900 dark:text-white font-medium hover:bg-zinc-300 dark:hover:bg-zinc-500">
                                Cancel
                            </button>
                            <button
                                type="button"
                                onClick={() => {
                                    const { id, label } = pendingDownload;
                                    setPendingDownload(null);
                                    setDiskSpace(null);
                                    setDownloadError(null);
                                    setDownloadingModel(id);
                                    aceStepModelsApi.download(id)
                                        .then((r) => {
                                            if (r.error) {
                                                setDownloadError(r.hint ? `${r.error} ${r.hint}` : r.error);
                                                setDownloadingModel(null);
                                            } else {
                                                aceStepModelsApi.downloadStatus().then(setDownloadStatus);
                                            }
                                        })
                                        .catch((err) => {
                                            setDownloadError(err?.message || 'Download failed');
                                            setDownloadingModel(null);
                                        });
                                }}
                                className="px-4 py-2 rounded-lg bg-pink-500 text-white font-medium hover:bg-pink-600"
                            >
                                Download
                            </button>
                        </div>
                    </div>
                </div>
            )}

            <EditProfileModal
                isOpen={isEditProfileOpen}
                onClose={() => setIsEditProfileOpen(false)}
                onSaved={() => setIsEditProfileOpen(false)}
            />
        </div>
    );
};
