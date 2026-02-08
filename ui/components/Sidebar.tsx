import React from 'react';
import { Library, Disc, Search, Terminal, Sun, Moon, GraduationCap, Layers, Mic, Music2, Settings } from 'lucide-react';
import { View } from '../types';
import { useTranslation } from 'react-i18next';

interface SidebarProps {
  currentView: View;
  onNavigate: (view: View) => void;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  user?: { username: string; isAdmin?: boolean; avatar_url?: string } | null;
  onOpenConsole?: () => void;
  onOpenSettings?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentView,
  onNavigate,
  theme,
  onToggleTheme,
  user,
  onOpenConsole,
  onOpenSettings,
}) => {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col h-full bg-white dark:bg-suno-sidebar border-r border-zinc-200 dark:border-white/5 flex-shrink-0 w-[72px] items-center py-4 z-30 transition-colors duration-300 overflow-y-auto scrollbar-hide">
      {/* Logo */}
      <div
        className="w-10 h-10 rounded-full overflow-hidden flex items-center justify-center mb-8 cursor-pointer shadow-lg hover:scale-105 transition-transform bg-zinc-100 dark:bg-zinc-800"
        onClick={() => onNavigate('create')}
        title="AceForge"
      >
        <img src="/static/aceforge_logo.png" alt="AceForge" className="w-full h-full object-cover" />
      </div>

      <nav className="flex-1 flex flex-col gap-4 w-full px-3">
        <NavItem
          icon={<Disc size={24} />}
          label={t('navigation.create')}
          active={currentView === 'create'}
          onClick={() => onNavigate('create')}
        />
        <NavItem
          icon={<Library size={24} />}
          label={t('navigation.library')}
          active={currentView === 'library'}
          onClick={() => onNavigate('library')}
        />
        <NavItem
          icon={<Search size={24} />}
          label={t('navigation.search')}
          active={currentView === 'search'}
          onClick={() => onNavigate('search')}
        />
        <NavItem
          icon={<GraduationCap size={24} />}
          label={t('navigation.training')}
          active={currentView === 'training'}
          onClick={() => onNavigate('training')}
        />
        <NavItem
          icon={<Layers size={24} />}
          label={t('navigation.stem_splitting')}
          active={currentView === 'stem-splitting'}
          onClick={() => onNavigate('stem-splitting')}
        />
        <NavItem
          icon={<Mic size={24} />}
          label={t('navigation.voice_cloning')}
          active={currentView === 'voice-cloning'}
          onClick={() => onNavigate('voice-cloning')}
        />
        <NavItem
          icon={<Music2 size={24} />}
          label={t('navigation.midi')}
          active={currentView === 'midi'}
          onClick={() => onNavigate('midi')}
        />

        <div className="mt-auto flex flex-col gap-4">
          <button
            onClick={onToggleTheme}
            className="w-10 h-10 rounded-full hover:bg-zinc-100 dark:hover:bg-white/10 flex items-center justify-center text-zinc-500 dark:text-zinc-400 hover:text-black dark:hover:text-white transition-colors mx-auto"
            title={theme === 'dark' ? t('common.light') : t('common.dark')}
          >
            {theme === 'dark' ? <Sun size={20} /> : <Moon size={20} />}
          </button>

          <button
            onClick={onOpenSettings}
            className="w-10 h-10 rounded-full hover:bg-zinc-100 dark:hover:bg-white/10 flex items-center justify-center text-zinc-500 dark:text-zinc-400 hover:text-pink-500 transition-colors mx-auto"
            title={t('common.settings')}
          >
            <Settings size={20} />
          </button>

          <div className="flex flex-col items-center gap-2">
            {user && (
              <div
                onClick={onOpenSettings}
                className="w-8 h-8 rounded-full bg-gradient-to-br from-pink-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold cursor-pointer border border-white/20 hover:scale-110 transition-transform overflow-hidden"
                title={`${user.username} - ${t('common.settings')}`}
              >
                {user.avatar_url ? (
                  <img src={user.avatar_url} alt={user.username} className="w-full h-full object-cover" />
                ) : (
                  user.username.charAt(0).toUpperCase()
                )}
              </div>
            )}
            <button
              onClick={onOpenConsole}
              className="w-10 h-10 rounded-full hover:bg-zinc-100 dark:hover:bg-white/10 flex items-center justify-center text-zinc-500 dark:text-zinc-400 hover:text-pink-500 transition-colors mx-auto"
              title={t('common.console')}
            >
              <Terminal size={20} />
            </button>
          </div>
        </div>
      </nav>
    </div>
  );
};

interface NavItemProps {
  icon: React.ReactNode;
  label: string;
  active?: boolean;
  onClick: () => void;
}

const NavItem: React.FC<NavItemProps> = ({ icon, label, active, onClick }) => (
  <button
    onClick={onClick}
    className={`
      w-full aspect-square rounded-xl flex flex-col items-center justify-center gap-1 transition-all duration-200 group relative
      ${active ? 'bg-zinc-100 dark:bg-white/10 text-black dark:text-white' : 'text-zinc-500 hover:text-black dark:hover:text-white hover:bg-zinc-100 dark:hover:bg-white/5'}
    `}
    title={label}
  >
    {active && <div className="absolute left-0 top-1/2 -translate-y-1/2 h-8 w-1 bg-pink-500 rounded-r-full"></div>}
    {icon}
  </button>
);
