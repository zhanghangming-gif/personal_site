import { ArrowUp, Award, BriefcaseBusiness, ChevronDown, FolderKanban, House, Languages, LayoutGrid, Mail, Menu, MessageCircle, Moon, Music2, Sun, UserRound, Volume2, VolumeX, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { AiAssistant } from '../components/AiAssistant';
import { useContent } from '../context/ContentContext';
import { useTheme } from '../hooks/useTheme';
import { useLanguage } from '../context/LanguageContext';
import { useSound } from '../hooks/useSound';

export function SiteLayout() {
  const { siteData } = useContent();
  const [open, setOpen] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [top, setTop] = useState(true);
  const [activeHash, setActiveHash] = useState('#home');
  const { theme, toggle } = useTheme();
  const { language, toggleLanguage } = useLanguage();
  const { enabled: soundEnabled, toggle: toggleSound, play } = useSound();
  const visitedLocation = useRef(false);
  const desktopToolsRef = useRef<HTMLDivElement>(null);
  const mobileToolsRef = useRef<HTMLDivElement>(null);
  const en = language === 'en';
  const nav = [
    { label: en ? 'Home' : '首页', href: '/#home', icon: House },
    { label: en ? 'About' : '关于我', href: '/#about', icon: UserRound },
    { label: en ? 'Projects' : '项目', href: '/#projects', icon: FolderKanban },
    { label: en ? 'Experience' : '经历', href: '/#experience', icon: BriefcaseBusiness },
    { label: en ? 'Honors' : '荣誉', href: '/#honors', icon: Award },
    { label: en ? 'Messages' : '留言', href: '/#messages', icon: MessageCircle },
    { label: en ? 'Contact' : '联系方式', href: '/#contact', icon: Mail },
  ];
  const location = useLocation();
  const getIsActive = (href: string) => {
    if (!href.startsWith('/#')) return location.pathname === href;
    return location.pathname === '/' && activeHash === href.slice(1);
  };
  useEffect(() => {
    setOpen(false);
    setToolsOpen(false);
    if (!location.hash) window.scrollTo({ top: 0 });
  }, [location.pathname, location.hash]);
  useEffect(() => {
    if (!toolsOpen) return;
    const closeOutside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!desktopToolsRef.current?.contains(target) && !mobileToolsRef.current?.contains(target)) setToolsOpen(false);
    };
    const closeWithEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setToolsOpen(false);
    };
    document.addEventListener('pointerdown', closeOutside);
    document.addEventListener('keydown', closeWithEscape);
    return () => {
      document.removeEventListener('pointerdown', closeOutside);
      document.removeEventListener('keydown', closeWithEscape);
    };
  }, [toolsOpen]);
  useEffect(() => {
    if (location.pathname !== '/') return;
    if (location.hash) setActiveHash(location.hash);
  }, [location.pathname, location.hash]);
  useEffect(() => {
    if (visitedLocation.current) play('transition');
    visitedLocation.current = true;
  }, [location.pathname, location.hash, play]);
  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : '';
    return () => {
      document.body.style.overflow = '';
    };
  }, [open]);
  useEffect(() => {
    const fn = () => setTop(scrollY < 480);
    fn();
    addEventListener('scroll', fn, { passive: true });
    return () => removeEventListener('scroll', fn);
  }, []);
  useEffect(() => {
    if (location.pathname !== '/') return;
    const ids = ['home', 'about', 'projects', 'experience', 'honors', 'messages', 'contact'];
    let frame = 0;
    const updateActiveSection = () => {
      frame = 0;
      const sections = ids
        .map((id) => document.getElementById(id))
        .filter(Boolean)
        .sort((a, b) => (a as HTMLElement).offsetTop - (b as HTMLElement).offsetTop) as HTMLElement[];
      if (!sections.length) return;

      const activationLine = Math.min(260, Math.max(96, window.innerHeight * 0.3));
      let current = sections[0];
      for (const section of sections) {
        if (section.getBoundingClientRect().top <= activationLine) current = section;
        else break;
      }
      if (window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2) {
        current = sections[sections.length - 1];
      }
      const nextHash = `#${current.id}`;
      setActiveHash((previous) => previous === nextHash ? previous : nextHash);
    };
    const scheduleUpdate = () => {
      if (!frame) frame = window.requestAnimationFrame(updateActiveSection);
    };

    scheduleUpdate();
    window.addEventListener('scroll', scheduleUpdate, { passive: true });
    window.addEventListener('resize', scheduleUpdate);
    return () => {
      window.removeEventListener('scroll', scheduleUpdate);
      window.removeEventListener('resize', scheduleUpdate);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [location.pathname]);
  const handleHash = (hash: string) => {
    setOpen(false);
    setActiveHash(hash);
    window.setTimeout(() => document.querySelector(hash)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
  };
  return (
    <div className="min-h-screen">
      <a
        href="#main"
        className="fixed -top-20 left-4 z-[100] rounded-lg bg-accent px-4 py-2 text-white focus:top-4"
      >
        {en ? 'Skip to main content' : '跳到主要内容'}
      </a>
      <header className="pointer-events-none fixed inset-x-0 top-0 z-50 py-2">
        <div className="container-site flex h-16 items-center justify-between gap-2 sm:gap-4">
          <Link to="/" className="mac-toolbar pointer-events-auto rounded-[18px] px-3 py-2 text-[17px] font-semibold tracking-[-0.03em] sm:px-4">
            ZHANG<span className="text-accent">.</span>
          </Link>
          <nav className={`mac-dock pointer-events-auto hidden h-16 items-center gap-3 rounded-[26px] px-3 py-1.5 lg:flex ${!top ? 'mac-dock-scrolled' : ''}`} aria-label={en ? 'Main navigation' : '主导航'}>
            {nav.map(({ label, href, icon: Icon }) => {
              const active = getIsActive(href);
              return (
                <Link
                  key={label}
                  to={href}
                  onClick={() => handleHash(href.slice(1))}
                  aria-label={label}
                  aria-current={active ? 'page' : undefined}
                  className={`group relative flex h-[58px] w-[52px] shrink-0 flex-col items-center justify-center gap-0.5 rounded-[16px] transition-[transform,color] duration-150 ease-out hover:-translate-y-0.5 focus-visible:-translate-y-0.5 ${active ? '-translate-y-0.5 text-accent dark:text-blue-300' : 'text-slate-600 hover:text-accent dark:text-slate-300 dark:hover:text-blue-300'}`}
                >
                  <span className={`grid place-items-center rounded-full transition-[width,height,background-color,box-shadow] duration-200 ${active ? 'nav-orb-active h-10 w-10 text-white' : 'nav-orb h-8 w-8 group-hover:bg-blue-100/70 dark:group-hover:bg-blue-400/20'}`}>
                    <Icon size={active ? 19 : 17} strokeWidth={active ? 2.35 : 2} />
                  </span>
                  <span className={`whitespace-nowrap text-[10px] font-medium leading-none tracking-[-0.02em] ${active ? 'text-accent dark:text-blue-300' : 'text-slate-600 dark:text-slate-300'}`}>{label}</span>
                </Link>
              );
            })}
          </nav>
          <div className="mac-toolbar pointer-events-auto flex items-center gap-1 p-1">
            <div ref={desktopToolsRef} className="relative hidden lg:block">
              <button
                type="button"
                onClick={() => setToolsOpen(value => !value)}
                aria-haspopup="menu"
                aria-expanded={toolsOpen}
                className={`inline-flex h-10 items-center justify-center gap-2 rounded-xl border px-3 text-sm font-bold transition ${toolsOpen || location.pathname === '/score-transpose' ? 'border-blue-600 bg-accent text-white shadow-lg shadow-blue-600/15' : 'border-blue-200 bg-blue-50 text-accent hover:border-blue-500 hover:bg-blue-100 dark:border-blue-400/30 dark:bg-blue-400/10 dark:text-blue-300 dark:hover:bg-blue-400/20'}`}
              >
                <LayoutGrid size={17} />
                {en ? 'Tools' : '工具'}
                <ChevronDown size={15} className={`transition-transform ${toolsOpen ? 'rotate-180' : ''}`} />
              </button>
              {toolsOpen && (
                <div role="menu" className="liquid-popover absolute right-0 top-[calc(100%+0.75rem)] w-[370px] text-slate-900 dark:text-slate-100">
                  <div className="flex items-center justify-between border-b border-slate-200/80 px-4 py-3 dark:border-slate-700/80">
                    <div className="flex gap-1.5" aria-hidden="true">
                      <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
                      <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
                      <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
                    </div>
                    <p className="text-xs font-bold tracking-[0.16em] text-slate-500 dark:text-slate-400">{en ? 'TOOL CENTER' : '工具中心'}</p>
                  </div>
                  <div className="p-3">
                    <Link to="/score-transpose" role="menuitem" className={`group flex items-center gap-4 rounded-2xl p-3 transition ${location.pathname === '/score-transpose' ? 'bg-blue-50 ring-1 ring-blue-200 dark:bg-blue-400/10 dark:ring-blue-400/30' : 'hover:bg-slate-100 dark:hover:bg-slate-800'}`}>
                      <span className="grid h-12 w-12 shrink-0 place-items-center rounded-[14px] bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-lg shadow-blue-600/20"><Music2 size={23} /></span>
                      <span className="min-w-0">
                        <span className="block font-black">{en ? 'Score transposition' : '乐谱转调'}</span>
                        <span className="mt-0.5 block text-xs leading-5 text-slate-500 dark:text-slate-400">{en ? 'Transpose PDF scores and review the result' : 'PDF 乐谱识别、转调与在线校对'}</span>
                      </span>
                    </Link>
                    <p className="px-3 pb-1 pt-3 text-xs text-slate-400">{en ? 'New music tools will appear here.' : '后续音乐工具会统一收纳在这里。'}</p>
                  </div>
                </div>
              )}
            </div>
            <button
              onClick={toggleLanguage}
              className="glass-control inline-flex h-10 min-w-[4.25rem] items-center justify-center gap-1.5 rounded-[14px] px-2.5 text-sm font-bold transition hover:text-accent"
              aria-label={en ? '切换到中文' : 'Switch to English'}
            >
              <Languages size={17} />
              <span>{en ? '中' : 'EN'}</span>
            </button>
            <button
              type="button"
              onClick={toggleSound}
              data-sound-off="true"
              className="glass-control hidden h-10 w-10 items-center justify-center gap-1.5 rounded-[14px] text-sm font-bold transition hover:text-accent min-[480px]:inline-flex sm:w-auto sm:min-w-[6.5rem] sm:px-2.5"
              aria-label={soundEnabled ? (en ? 'Turn sound effects off' : '关闭音效') : (en ? 'Turn sound effects on' : '开启音效')}
              aria-pressed={soundEnabled}
              title={soundEnabled ? (en ? 'Sound on' : '音效开启') : (en ? 'Sound off' : '音效关闭')}
            >
              {soundEnabled ? <Volume2 size={17} /> : <VolumeX size={17} />}
              <span className="hidden sm:inline">{soundEnabled ? (en ? 'Sound on' : '音效开启') : (en ? 'Sound off' : '音效关闭')}</span>
            </button>
            <button
              onClick={toggle}
              className="glass-control grid h-10 w-10 place-items-center rounded-[14px] transition hover:text-accent"
              aria-label={theme === 'dark' ? (en ? 'Switch to light mode' : '切换到浅色模式') : (en ? 'Switch to dark mode' : '切换到深色模式')}
            >
              {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <button
              onClick={() => setOpen((v) => !v)}
              className="glass-control grid h-10 w-10 place-items-center rounded-[14px] transition lg:hidden"
              aria-label={open ? (en ? 'Close menu' : '关闭菜单') : (en ? 'Open menu' : '打开菜单')}
              aria-expanded={open}
            >
              {open ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>
      </header>
      {open && (
        <div className="liquid-sheet fixed inset-0 z-40 px-6 pt-24 lg:hidden">
          <nav className="liquid-popover mx-auto max-w-lg rounded-[30px] p-5" aria-label={en ? 'Mobile navigation' : '移动端导航'}>
            <p className="mb-5 text-center text-xs font-bold tracking-[0.2em] text-slate-400">{en ? 'NAVIGATION' : '导航中心'}</p>
            <div className="grid grid-cols-4 gap-x-3 gap-y-5">
            {nav.map(({ label, href, icon: Icon }) => {
              const active = getIsActive(href);
              return (
              <Link
                key={label}
                to={href}
                onClick={() => handleHash(href.slice(1))}
                className="group flex min-w-0 flex-col items-center gap-2 text-center"
                aria-label={label}
              >
                <span className={`grid rounded-full transition-all ${active ? 'nav-orb-active h-14 w-14 -translate-y-1 text-white' : 'nav-orb h-12 w-12 text-slate-600 dark:text-slate-300'}`}><Icon className="m-auto" size={active ? 23 : 20} /></span>
                <span className={`w-full truncate text-xs font-bold ${active ? 'text-accent dark:text-blue-300' : 'text-slate-500 dark:text-slate-400'}`}>{label}</span>
              </Link>
              );
            })}
            </div>
            <div ref={mobileToolsRef} className="mt-5 overflow-hidden rounded-2xl border border-blue-200 bg-blue-50/70 dark:border-blue-400/30 dark:bg-blue-400/10">
              <button type="button" onClick={() => setToolsOpen(value => !value)} aria-expanded={toolsOpen} className="flex min-h-12 w-full items-center gap-3 px-4 text-left text-lg font-bold text-accent dark:text-blue-300">
                <LayoutGrid size={20} />
                <span className="flex-1">{en ? 'Tools' : '工具箱'}</span>
                <ChevronDown size={18} className={`transition-transform ${toolsOpen ? 'rotate-180' : ''}`} />
              </button>
              {toolsOpen && (
                <div className="border-t border-blue-200 p-2 dark:border-blue-400/20">
                  <Link to="/score-transpose" className={`flex items-center gap-3 rounded-xl p-3 ${location.pathname === '/score-transpose' ? 'bg-accent text-white' : 'bg-white/80 text-slate-900 dark:bg-slate-900/70 dark:text-slate-100'}`}>
                    <span className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white"><Music2 size={20} /></span>
                    <span><span className="block font-black">{en ? 'Score transposition' : '乐谱转调'}</span><span className={`block text-xs ${location.pathname === '/score-transpose' ? 'text-blue-100' : 'text-slate-500 dark:text-slate-400'}`}>{en ? 'PDF score tool' : 'PDF 识别、转调与校对'}</span></span>
                  </Link>
                </div>
              )}
            </div>
          </nav>
        </div>
      )}
      <main id="main">
        <Outlet />
      </main>
      <footer className="border-t py-9">
        <div className="container-site flex flex-col items-center justify-between gap-3 text-sm text-slate-500 sm:flex-row">
          <p>
            © {new Date().getFullYear()} {siteData.name}
          </p>
          <a
            href="https://beian.miit.gov.cn/"
            target="_blank"
            rel="noreferrer"
            className="transition hover:text-accent"
          >
            渝ICP备2026018073号-1
          </a>
          <p>{en ? 'Explore real problems. Build reliable systems.' : '探索真实问题，构建可靠系统。'}</p>
        </div>
      </footer>
      <div className="fixed bottom-[max(1rem,env(safe-area-inset-bottom))] right-3 z-[70] flex flex-col items-end gap-2 sm:bottom-5 sm:right-5">
        {!top && (
          <button
            type="button"
            onClick={() => scrollTo({ top: 0, behavior: 'smooth' })}
            className="liquid-glass grid h-12 w-12 place-items-center rounded-full text-accent transition hover:-translate-y-0.5 hover:border-blue-400"
            aria-label={en ? 'Back to top' : '返回顶部'}
          >
            <ArrowUp size={19} />
          </button>
        )}
        <AiAssistant docked />
      </div>
    </div>
  );
}
