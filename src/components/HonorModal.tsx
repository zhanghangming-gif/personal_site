import { ExternalLink, X } from 'lucide-react';
import { useEffect, useRef } from 'react';
import type { Honor } from '../types';
import { useLanguage } from '../context/LanguageContext';
import { useSound } from '../hooks/useSound';

export function HonorModal({ honor, onClose }: { honor: Honor | null; onClose: () => void }) {
  const { language } = useLanguage();
  const { play } = useSound();
  const en = language === 'en';
  const closeRef = useRef<HTMLButtonElement>(null);
  const closeWithSound = () => {
    play('panelClose');
    onClose();
  };
  useEffect(() => { if (!honor) return; play('panelOpen'); const previous = document.activeElement as HTMLElement | null; const oldOverflow = document.body.style.overflow; closeRef.current?.focus(); document.body.style.overflow = 'hidden'; const key = (event: KeyboardEvent) => { if (event.key === 'Escape') closeWithSound(); }; addEventListener('keydown', key); return () => { removeEventListener('keydown', key); document.body.style.overflow = oldOverflow; previous?.focus(); }; }, [honor, onClose, play]);
  if (!honor) return null;
  return <div className="fixed inset-0 z-[90] grid place-items-center overflow-y-auto bg-slate-950/70 p-4 backdrop-blur-md sm:p-6" onMouseDown={(e) => e.target === e.currentTarget && closeWithSound()} role="dialog" aria-modal="true" aria-labelledby="honor-title"><div className="liquid-popover relative my-auto grid max-h-[92vh] w-full max-w-6xl overflow-hidden rounded-[30px] lg:grid-cols-[1.4fr_.6fr]"><button ref={closeRef} data-sound-off="true" className="glass-control absolute right-4 top-4 z-10 grid h-11 w-11 place-items-center rounded-full bg-slate-950/45 text-white transition hover:bg-slate-950/70" onClick={closeWithSound} aria-label={en ? 'Close certificate preview' : '关闭证书预览'}><X size={20} /></button><div className="grid min-h-[320px] place-items-center overflow-auto bg-slate-950 p-4 sm:p-7"><img src={honor.image} alt={en ? `${honor.title} ${honor.level} certificate` : `${honor.title}${honor.level}证书`} className="max-h-[78vh] w-full rounded-lg object-contain shadow-2xl" /></div><div className="flex flex-col justify-center p-7 sm:p-9"><p className="eyebrow">{honor.year} · {honor.category}</p><h2 id="honor-title" className="text-2xl font-bold leading-9">{honor.title}</h2><p className="mt-3 text-lg font-semibold text-accent">{honor.level}</p><p className="mt-5 leading-8 text-slate-600 dark:text-slate-300">{honor.description}</p><a href={honor.image} target="_blank" rel="noreferrer" className="button-secondary mt-8 w-fit"><ExternalLink size={17} />{en ? 'Open original image' : '打开原图'}</a><p className="mt-5 text-xs leading-5 text-slate-400">{en ? 'Press Esc or click the backdrop to close' : '按 Esc 键或点击背景区域关闭'}</p></div></div></div>;
}
