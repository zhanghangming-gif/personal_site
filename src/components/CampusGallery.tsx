import { ChevronLeft, ChevronRight, Expand, X } from 'lucide-react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import type { CampusPhoto } from '../types';
import { useLanguage } from '../context/LanguageContext';
import { useSound } from '../hooks/useSound';

interface CampusGalleryProps {
  photos: CampusPhoto[];
  eyebrow: string;
  title: string;
  description: string;
  ariaLabel: string;
  swipeLabel?: string;
}

export function CampusGallery({
  photos,
  eyebrow,
  title,
  description,
  ariaLabel,
  swipeLabel = '左右滑动浏览',
}: CampusGalleryProps) {
  const { language } = useLanguage();
  const { play } = useSound();
  const en = language === 'en';
  const [index, setIndex] = useState(0);
  const [viewerOpen, setViewerOpen] = useState(false);
  const startX = useRef<number | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const reducedMotion = useReducedMotion();
  const go = useCallback(
    (target: number) => setIndex((target + photos.length) % photos.length),
    [photos.length],
  );
  const previous = useCallback(
    () => setIndex((current) => (current - 1 + photos.length) % photos.length),
    [photos.length],
  );
  const next = useCallback(() => setIndex((current) => (current + 1) % photos.length), [photos.length]);
  const openViewer = useCallback(() => {
    play('panelOpen');
    setViewerOpen(true);
  }, [play]);
  const closeViewer = useCallback(() => {
    play('panelClose');
    setViewerOpen(false);
  }, [play]);

  useEffect(() => {
    if (!viewerOpen) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeViewer();
      if (event.key === 'ArrowLeft') previous();
      if (event.key === 'ArrowRight') next();
    };
    addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
      previousFocus?.focus();
    };
  }, [viewerOpen, previous, next, closeViewer]);

  const onPointerDown = (event: ReactPointerEvent) => {
    startX.current = event.clientX;
  };
  const onPointerUp = (event: ReactPointerEvent) => {
    if (startX.current === null) return;
    const distance = event.clientX - startX.current;
    if (Math.abs(distance) > 48) {
      if (distance > 0) previous();
      else next();
    }
    startX.current = null;
  };
  const onGalleryKey = (event: ReactKeyboardEvent) => {
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      previous();
    }
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      next();
    }
  };

  return (
    <>
      <section
        data-motion-card
        className="surface overflow-hidden rounded-3xl"
        aria-roledescription={en ? 'carousel' : '轮播图'}
        aria-label={ariaLabel}
      >
        <div className="grid lg:grid-cols-[1.35fr_.65fr]">
          <div
            data-motion-image
            className="group relative min-h-[300px] touch-pan-y overflow-hidden bg-slate-950 sm:min-h-[430px]"
            tabIndex={0}
            onKeyDown={onGalleryKey}
            onPointerDown={onPointerDown}
            onPointerUp={onPointerUp}
          >
            <AnimatePresence mode="wait" initial={false}>
              <motion.img
                key={photos[index].src}
                src={photos[index].src}
                alt={photos[index].alt}
                loading="lazy"
                draggable={false}
                className={`absolute inset-0 h-full w-full select-none ${photos[index].contain ? 'object-contain' : 'object-cover'}`}
                initial={reducedMotion ? false : { opacity: 0, scale: 1.015 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={reducedMotion ? undefined : { opacity: 0 }}
                transition={{ duration: 0.35 }}
              />
            </AnimatePresence>
            <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-slate-950/70 via-transparent to-transparent" />
            <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-4 p-5 text-white sm:p-7">
              <div>
                <p className="text-xs font-bold tracking-[.18em] text-blue-200">
                  CAMPUS / {String(index + 1).padStart(2, '0')}
                </p>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-100 sm:text-base">
                  {photos[index].caption}
                </p>
              </div>
              <button
                onClick={openViewer}
                data-sound-off="true"
                className="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-white/25 bg-black/25 backdrop-blur transition hover:bg-white/20"
                aria-label={en ? 'View full image' : '查看大图'}
              >
                <Expand size={18} />
              </button>
            </div>
            <button
              onClick={previous}
              className="absolute left-4 top-1/2 grid h-11 w-11 -translate-y-1/2 place-items-center rounded-full border border-white/20 bg-black/30 text-white opacity-100 backdrop-blur transition hover:bg-black/55 sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100"
              aria-label={en ? 'Previous photo' : '上一张照片'}
            >
              <ChevronLeft size={22} />
            </button>
            <button
              onClick={next}
              className="absolute right-4 top-1/2 grid h-11 w-11 -translate-y-1/2 place-items-center rounded-full border border-white/20 bg-black/30 text-white opacity-100 backdrop-blur transition hover:bg-black/55 sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100"
              aria-label={en ? 'Next photo' : '下一张照片'}
            >
              <ChevronRight size={22} />
            </button>
          </div>
          <div className="flex flex-col justify-between p-6 sm:p-8">
            <div>
              <p className="eyebrow">{eyebrow}</p>
              <h3 className="text-2xl font-bold tracking-tight">{title}</h3>
              <p className="mt-5 text-sm leading-7 text-slate-600 dark:text-slate-300">{description}</p>
            </div>
            <div className="mt-8">
              <div className="mb-4 flex items-center justify-between text-xs text-slate-500">
                <span>{swipeLabel}</span>
                <span>
                  {index + 1} / {photos.length}
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                {photos.map((photo, photoIndex) => (
                  <button
                    key={photo.src}
                    onClick={() => go(photoIndex)}
                    className={`h-2 rounded-full transition-all ${photoIndex === index ? 'w-8 bg-accent' : 'w-2 bg-slate-300 hover:bg-slate-400 dark:bg-slate-600'}`}
                    aria-label={en ? `View photo ${photoIndex + 1}` : `查看第 ${photoIndex + 1} 张照片`}
                    aria-current={photoIndex === index ? 'true' : undefined}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>
      {viewerOpen && (
        <div
          className="fixed inset-0 z-[100] grid place-items-center bg-slate-950/95 p-4"
          role="dialog"
          aria-modal="true"
          aria-label={en ? `${ariaLabel} full-screen preview` : `${ariaLabel}大图预览`}
          onMouseDown={(event) => event.target === event.currentTarget && closeViewer()}
        >
          <button
            ref={closeRef}
            onClick={closeViewer}
            data-sound-off="true"
            className="absolute right-5 top-5 grid h-11 w-11 place-items-center rounded-full border border-white/20 bg-white/10 text-white"
            aria-label={en ? 'Close full image' : '关闭大图'}
          >
            <X size={20} />
          </button>
          <button
            onClick={previous}
            className="absolute left-3 top-1/2 grid h-12 w-12 -translate-y-1/2 place-items-center rounded-full bg-white/10 text-white sm:left-6"
            aria-label={en ? 'Previous photo' : '上一张照片'}
          >
            <ChevronLeft size={25} />
          </button>
          <img
            src={photos[index].src}
            alt={photos[index].alt}
            className="max-h-[86vh] max-w-[92vw] rounded-xl object-contain shadow-2xl"
          />
          <button
            onClick={next}
            className="absolute right-3 top-1/2 grid h-12 w-12 -translate-y-1/2 place-items-center rounded-full bg-white/10 text-white sm:right-6"
            aria-label={en ? 'Next photo' : '下一张照片'}
          >
            <ChevronRight size={25} />
          </button>
          <p className="absolute bottom-5 left-1/2 w-[min(760px,85vw)] -translate-x-1/2 text-center text-sm text-slate-200">
            {photos[index].caption}
          </p>
        </div>
      )}
    </>
  );
}
