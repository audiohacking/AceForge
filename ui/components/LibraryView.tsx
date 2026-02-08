import React, { useState } from 'react';
import { Song, Playlist } from '../types';
import { Heart, Plus, Music, Play, RefreshCw } from 'lucide-react';
import { AlbumCover } from './AlbumCover';
import { useTranslation } from 'react-i18next';

interface LibraryViewProps {
  likedSongs: Song[];
  playlists: Playlist[];
  onPlaySong: (song: Song, list?: Song[]) => void;
  onCreatePlaylist: () => void;
  onSelectPlaylist: (playlist: Playlist) => void;
  onRefreshLibrary?: () => void;
  isRefreshingLibrary?: boolean;
}

export const LibraryView: React.FC<LibraryViewProps> = ({
    likedSongs,
    playlists,
    onPlaySong,
    onCreatePlaylist,
    onSelectPlaylist,
    onRefreshLibrary,
    isRefreshingLibrary = false,
}) => {
    const { t } = useTranslation();
    const [activeTab, setActiveTab] = useState<'playlists' | 'liked'>('liked');

    return (
        <div className="flex-1 bg-white dark:bg-black overflow-y-auto custom-scrollbar p-6 lg:p-10 pb-32 transition-colors duration-300">
             <div className="flex items-center justify-between mb-8">
                <h1 className="text-3xl font-bold text-zinc-900 dark:text-white">{t('library.title')}</h1>
                <div className="flex items-center gap-2">
                  {onRefreshLibrary && (
                    <button
                      type="button"
                      onClick={onRefreshLibrary}
                      disabled={isRefreshingLibrary}
                      className="p-2 rounded-full text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-white/10 disabled:opacity-50 transition-colors"
                      title="Refresh library (e.g. after API generations)"
                      aria-label="Refresh library"
                    >
                      <RefreshCw size={20} className={isRefreshingLibrary ? 'animate-spin' : ''} />
                    </button>
                  )}
                  <button 
                    onClick={onCreatePlaylist}
                    className="flex items-center gap-2 bg-zinc-900 dark:bg-zinc-800 hover:bg-zinc-800 dark:hover:bg-zinc-700 text-white px-4 py-2 rounded-full font-medium transition-colors shadow-lg shadow-zinc-900/10 dark:shadow-none"
                  >
                    <Plus size={18} />
                    <span>{t('library.new_playlist')}</span>
                  </button>
                </div>
             </div>

             {/* Tabs */}
             <div className="flex items-center gap-4 mb-8 border-b border-zinc-200 dark:border-white/10 pb-1">
                 <button 
                    onClick={() => setActiveTab('liked')}
                    className={`pb-3 text-sm font-bold transition-colors relative ${activeTab === 'liked' ? 'text-zinc-900 dark:text-white' : 'text-zinc-500 hover:text-zinc-900 dark:hover:text-white'}`}
                 >
                    {t('library.tab_liked')}
                    {activeTab === 'liked' && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-green-500 rounded-full"></div>}
                 </button>
                 <button 
                    onClick={() => setActiveTab('playlists')}
                    className={`pb-3 text-sm font-bold transition-colors relative ${activeTab === 'playlists' ? 'text-zinc-900 dark:text-white' : 'text-zinc-500 hover:text-zinc-900 dark:hover:text-white'}`}
                 >
                    {t('library.tab_playlists')}
                    {activeTab === 'playlists' && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-green-500 rounded-full"></div>}
                 </button>
             </div>

             {/* Content */}
             {activeTab === 'liked' ? (
                 <div>
                    <div className="bg-gradient-to-b from-indigo-500/10 to-zinc-50 dark:from-indigo-800/50 dark:to-zinc-900/50 p-6 rounded-xl flex items-end gap-6 mb-8 cursor-pointer hover:bg-zinc-100 dark:hover:bg-white/5 transition-colors group border border-zinc-200 dark:border-white/5" onClick={() => likedSongs.length > 0 && onPlaySong(likedSongs[0], likedSongs)}>
                         <div className="w-40 h-40 bg-gradient-to-br from-indigo-500 to-purple-400 rounded shadow-2xl flex items-center justify-center">
                            <Heart fill="white" size={64} className="text-white" />
                         </div>
                         <div className="mb-2">
                             <h2 className="text-sm font-bold uppercase text-zinc-500 dark:text-white mb-2">{t('library.playlist_subtitle')}</h2>
                             <h1 className="text-5xl font-extrabold text-zinc-900 dark:text-white mb-4">{t('library.tab_liked')}</h1>
                             <div className="text-sm text-zinc-500 dark:text-zinc-300 font-medium">
                                 {t('library.song_count', { count: likedSongs.length })}
                             </div>
                         </div>
                         <div className="ml-auto mb-2 opacity-0 group-hover:opacity-100 transition-opacity">
                             <div className="w-14 h-14 rounded-full bg-green-500 flex items-center justify-center shadow-lg hover:scale-105 transition-transform">
                                <Play fill="black" className="text-black ml-1" size={28} />
                             </div>
                         </div>
                    </div>

                    <div className="space-y-1">
                        {likedSongs.map((song, idx) => (
                            <div key={song.id} className="group flex items-center gap-4 p-2 rounded hover:bg-zinc-100 dark:hover:bg-white/10 transition-colors" onClick={() => onPlaySong(song, likedSongs)}>
                                <span className="text-zinc-400 dark:text-zinc-500 w-6 text-center group-hover:hidden">{idx + 1}</span>
                                <span className="text-zinc-900 dark:text-white w-6 text-center hidden group-hover:block"><Play size={14} fill="currentColor" /></span>
                                
                                {song.coverUrl ? (
                                    <img src={song.coverUrl} className="w-10 h-10 rounded object-cover shadow-sm" alt="" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                                ) : (
                                    <AlbumCover seed={song.id || song.title} size="sm" className="w-10 h-10" />
                                )}
                                
                                <div className="flex-1 min-w-0">
                                    <div className="text-zinc-900 dark:text-white font-medium truncate">{song.title}</div>
                                    <div className="text-zinc-500 dark:text-zinc-400 text-xs">{song.style}</div>
                                </div>
                                
                                <div className="text-zinc-500 dark:text-zinc-400 text-sm font-mono">{song.duration}</div>
                                <div className="text-green-500"><Heart fill="#22c55e" size={16} /></div>
                            </div>
                        ))}
                    </div>
                 </div>
             ) : (
                 <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6">
                     {playlists.map((playlist) => (
                         <div key={playlist.id} className="bg-white dark:bg-zinc-900/40 p-4 rounded-lg border border-zinc-200 dark:border-white/5 hover:border-zinc-300 dark:hover:border-white/10 hover:shadow-lg dark:hover:bg-zinc-900 transition-all group cursor-pointer" onClick={() => onSelectPlaylist(playlist)}>
                             <div className="relative aspect-square mb-4 rounded-md overflow-hidden bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center">
                                 {playlist.coverUrl ? (
                                     <img src={playlist.coverUrl} className="w-full h-full object-cover" alt={playlist.name} onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                                 ) : (
                                     <AlbumCover seed={playlist.id || playlist.name} size="full" className="w-full h-full" />
                                 )}
                             </div>
                             <h3 className="font-bold text-zinc-900 dark:text-white truncate">{playlist.name}</h3>
                             <p className="text-sm text-zinc-500 dark:text-zinc-400 line-clamp-2">{playlist.description || t('library.by_you')}</p>
                         </div>
                     ))}
                 </div>
             )}
        </div>
    );
};
