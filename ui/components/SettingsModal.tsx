import React, { useState, useEffect } from 'react';
import { X, User as UserIcon, Palette, Info, Edit3, ExternalLink, Github, FolderOpen, HardDrive, ZoomIn, Box, Globe } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { EditProfileModal } from './EditProfileModal';
import { preferencesApi, aceStepModelsApi } from '../services/api';
import type { AceStepDownloadStatus } from '../services/api';
import { useTranslation } from 'react-i18next';

interface SettingsModalProps {
    isOpen: boolean;
    onClose: () => void;
    theme: 'light' | 'dark';
    onToggleTheme: () => void;
    onNavigateToProfile?: (username: string) => void;
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

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose, theme, onToggleTheme, onNavigateToProfile }) => {
    const { t, i18n } = useTranslation();
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
    const [aceStepList, setAceStepList] = useState<{ dit_models: Array<{ id: string; label: string; description?: string; installed: boolean }>; lm_models: Array<{ id: string; label: string; installed: boolean }>; discovered_models?: Array<{ id: string; label: string; path: string; custom: boolean }>; acestep_download_available: boolean } | null>(null);
    const [downloadingModel, setDownloadingModel] = useState<string | null>(null);
    const [downloadError, setDownloadError] = useState<string | null>(null);
    const [downloadStatus, setDownloadStatus] = useState<AceStepDownloadStatus | null>(null);

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
        const interval = setInterval(() => {
            aceStepModelsApi.downloadStatus()
                .then((s) => {
                    setDownloadStatus(s);
                    if (!s.running) {
                        setDownloadingModel(null);
                        if (s.error && !s.cancelled) setDownloadError(s.error);
                        aceStepModelsApi.list().then(setAceStepList).catch(() => {});
                    }
                })
                .catch(() => {});
        }, 1500);
        return () => clearInterval(interval);
    }, [isOpen, downloadStatus?.running]);

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

    const toggleLanguage = (lang: string) => {
        i18n.changeLanguage(lang);
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
                    <h2 className="text-2xl font-bold text-zinc-900 dark:text-white">{t('settings.title')}</h2>
                    <button
                        onClick={onClose}
                        className="p-2 hover:bg-zinc-100 dark:hover:bg-white/5 rounded-full transition-colors"
                    >
                        <X size={20} className="text-zinc-500" />
                    </button>
                </div>

                <div className="p-6 space-y-8">

                    {/* Language Section */}
                    <div className="space-y-4">
                        <div className="flex items-center gap-2 text-zinc-900 dark:text-white">
                            <Globe size={20} />
                            <h3 className="font-semibold">{t('settings.language')}</h3>
                        </div>
                        <div className="pl-7 space-y-3">
                            <div className="flex gap-3">
                                <button
                                    onClick={() => toggleLanguage('en')}
                                    className={`flex-1 py-3 px-4 rounded-lg border-2 font-medium transition-colors ${i18n.language.startsWith('en')
                                            ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
                                            : 'border-zinc-300 dark:border-zinc-700 hover:border-zinc-400 dark:hover:border-zinc-600'
                                        }`}
                                >
                                    English
                                </button>
                                <button
                                    onClick={() => toggleLanguage('zh')}
                                    className={`flex-1 py-3 px-4 rounded-lg border-2 font-medium transition-colors ${i18n.language.startsWith('zh')
                                            ? 'border-indigo-500 bg-indigo-950 text-indigo-300'
                                            : 'border-zinc-300 dark:border-zinc-700 hover:border-zinc-400 dark:hover:border-zinc-600'
                                        }`}
                                >
                                    中文
                                </button>
                            </div>
                        </div>
                    </div>

                    {/* AceForge paths (models, output) */}
                    <div className="space-y-4">
                        <div className="flex items-center gap-2 text-zinc-900 dark:text-white">
                            <HardDrive size={20} />
                            <h3 className="font-semibold">{t('settings.paths')}</h3>
                        </div>
                        <div className="pl-7 space-y-4">
                            <div>
                                <label className="text-sm text-zinc-500 dark:text-zinc-400 block mb-1">{t('settings.models_folder')}</label>
                                <p className="text-xs text-zinc-400 dark:text-zinc-500 mb-2">{t('settings.models_folder_desc')}</p>
                                <div className="flex gap-2">
                                    <input
                                        type="text"
                                        value={modelsFolder}
                                        onChange={(e) => setModelsFolder(e.target.value)}
                                        onBlur={saveModelsFolder}
                                        placeholder={t('settings.default_placeholder')}
                                        className="flex-1 rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-900 dark:text-white"
                                    />
                                    <button
                                        type="button"
                                        onClick={saveModelsFolder}
                                        className="px-3 py-2 rounded-lg bg-pink-500 text-white text-sm font-medium hover:bg-pink-600"
                                    >
                                        {modelsFolderSaved ? t('settings.saved') : t('settings.save')}
                                    </button>
                                </div>
                            </div>
                            <div>
                                <label className="text-sm text-zinc-500 dark:text-zinc-400 block mb-1">{t('settings.output_dir')}</label>
                                <p className="text-xs text-zinc-400 dark:text-zinc-500 mb-2">{t('settings.output_dir_desc')}</p>
                                <div className="flex gap-2">
                                    <input
                                        type="text"
                                        value={outputDir}
                                        onChange={(e) => setOutputDir(e.target.value)}
                                        onBlur={saveOutputDir}
                                        placeholder={t('settings.default_placeholder')}
                                        className="flex-1 rounded-lg border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 px-3 py-2 text-sm text-zinc-900 dark:text-white"
                                    />
                                    <button
                                        type="button"
                                        onClick={saveOutputDir}
                                        className="px-3 py-2 rounded-lg bg-pink-500 text-white text-sm font-medium hover:bg-pink-600"
                                    >
                                        {outputDirSaved ? t('settings.saved') : t('settings.save')}
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* ACE-Step Models */}
                    <div className="space-y-4">
                        <div className="flex items-center gap-2 text-zinc-900 dark:text-white">
                            <Box size={20} />
                            <h3 className="font-semibold">{t('settings.models')}</h3>
                        </div>
                        <div className="pl-7 space-y-4">
                            <p className="text-xs text-zinc-400 dark:text-zinc-500 mb-2">
                                {t('settings.models_desc')}
                            </p>
                            <div>
                                <label className="text-sm text-zinc-500 dark:text-zinc-400 block mb-1">{t('settings.current_model')}</label>
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
                                <label className="text-sm text-zinc-500 dark:text-zinc-400 block mb-1">{t('settings.dit_model')}</label>
                                <p className="text-xs text-zinc-400 dark:text-zinc-500 mb-1">{t('settings.dit_model_desc')}</p>
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
                                <label className="text-sm text-zinc-500 dark:text-zinc-400 block mb-1">{t('settings.lm_planner')}</label>
                                <p className="text-xs text-zinc-400 dark:text-zinc-500 mb-1">{t('settings.lm_planner_desc')}</p>
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
                            {modelsSaved && <span className="text-xs text-green-600 dark:text-green-400">{t('settings.saved')}</span>}
                            {/* Download models */}
                            {aceStepList && (
                                <div className="mt-4 pt-4 border-t border-zinc-200 dark:border-white/5">
                                    <label className="text-sm text-zinc-500 dark:text-zinc-400 block mb-2">{t('settings.download_models')}</label>
                                    <p className="text-xs text-zinc-400 dark:text-zinc-500 mb-2">
                                        {aceStepList.acestep_download_available
                                            ? t('settings.download_models_desc')
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
                                                    {t('common.cancel')}
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
                                                            setDownloadingModel(m.id);
                                                            aceStepModelsApi.download(m.id)
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
                                                            setDownloadingModel(m.id);
                                                            aceStepModelsApi.download(m.id)
                                                                .then((r) => {
                                                                    if (r.error) {
                                                                        setDownloadError(r.error);
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
                            <h3 className="font-semibold">{t('settings.display')}</h3>
                        </div>
                        <div className="pl-7 space-y-3">
                            <div>
                                <label className="text-sm text-zinc-500 dark:text-zinc-400 block mb-1">{t('settings.ui_zoom')}</label>
                                <p className="text-xs text-zinc-400 dark:text-zinc-500 mb-2">{t('settings.ui_zoom_desc')}</p>
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
                                    {uiZoomSaved && <span className="text-xs text-green-600 dark:text-green-400">{t('settings.saved')}</span>}
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
                                    {t('settings.member_since')} {new Date(user.createdAt).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
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
                                    {t('settings.edit_profile')}
                                </button>
                                <button
                                    onClick={() => {
                                        onClose();
                                        onNavigateToProfile?.(user.username);
                                    }}
                                    className="flex items-center gap-2 px-4 py-2 bg-zinc-200 dark:bg-zinc-700 text-zinc-900 dark:text-white rounded-lg text-sm font-medium hover:bg-zinc-300 dark:hover:bg-zinc-600 transition-colors"
                                >
                                    <ExternalLink size={16} />
                                    {t('settings.view_profile')}
                                </button>
                            </div>
                        </div>
                    </div>

                    {/* Account Section */}
                    <div className="space-y-4">
                        <div className="flex items-center gap-2 text-zinc-900 dark:text-white">
                            <UserIcon size={20} />
                            <h3 className="font-semibold">{t('settings.account')}</h3>
                        </div>
                        <div className="pl-7 space-y-3">
                            <div>
                                <label className="text-sm text-zinc-500 dark:text-zinc-400">{t('settings.username')}</label>
                                <p className="text-zinc-900 dark:text-white font-medium">@{user.username}</p>
                            </div>
                        </div>
                    </div>

                    {/* Theme Section */}
                    <div className="space-y-4">
                        <div className="flex items-center gap-2 text-zinc-900 dark:text-white">
                            <Palette size={20} />
                            <h3 className="font-semibold">{t('settings.appearance')}</h3>
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
                                    {t('common.light')}
                                </button>
                                <button
                                    onClick={theme === 'light' ? onToggleTheme : undefined}
                                    className={`flex-1 py-3 px-4 rounded-lg border-2 font-medium transition-colors ${theme === 'dark'
                                            ? 'border-indigo-500 bg-indigo-950 text-indigo-300'
                                            : 'border-zinc-300 dark:border-zinc-700 hover:border-zinc-400 dark:hover:border-zinc-600'
                                        }`}
                                >
                                    {t('common.dark')}
                                </button>
                            </div>
                        </div>
                    </div>

                    {/* About Section */}
                    <div className="space-y-4">
                        <div className="flex items-center gap-2 text-zinc-900 dark:text-white">
                            <Info size={20} />
                            <h3 className="font-semibold">{t('settings.about')}</h3>
                        </div>
                        <div className="pl-7 space-y-3 text-sm text-zinc-600 dark:text-zinc-400">
                            <p>{t('settings.version')} 1.0.0</p>
                            <p>AceForge</p>
                            <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-2">
                                {t('settings.powered_by')}
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
                                        {t('settings.github_repo')}
                                    </a>
                                </div>
                                <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-3">
                                    {t('settings.report_issues')}
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
                        {t('settings.done')}
                    </button>
                </div>
            </div>

            <EditProfileModal
                isOpen={isEditProfileOpen}
                onClose={() => setIsEditProfileOpen(false)}
                onSaved={() => setIsEditProfileOpen(false)}
            />
        </div>
    );
};
