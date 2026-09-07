import { ArrowRight, Sparkles } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

type OpeningAnimationProps = {
  skip?: boolean;
  onComplete?: () => void;
};

const SEEN_KEY = 'zhang-opening-seen-v2';

export function OpeningAnimation({ skip = false, onComplete }: OpeningAnimationProps) {
  const previousBodyOverflow = useRef('');
  const previousHtmlOverflow = useRef('');
  const callbackSent = useRef(false);
  const [done, setDone] = useState(() => skip || sessionStorage.getItem(SEEN_KEY) === '1');
  const [ready, setReady] = useState(false);
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    if (!done || callbackSent.current) return;
    callbackSent.current = true;
    onComplete?.();
  }, [done, onComplete]);

  useEffect(() => {
    if (done) return;
    previousBodyOverflow.current = document.body.style.overflow;
    previousHtmlOverflow.current = document.documentElement.style.overflow;
    document.body.style.overflow = 'hidden';
    document.documentElement.style.overflow = 'hidden';
    const timer = window.setTimeout(() => setReady(true), 220);

    return () => {
      window.clearTimeout(timer);
      document.body.style.overflow = previousBodyOverflow.current;
      document.documentElement.style.overflow = previousHtmlOverflow.current;
    };
  }, [done]);

  const continueToHome = () => {
    if (exiting) return;
    setExiting(true);
    sessionStorage.setItem(SEEN_KEY, '1');
    window.setTimeout(() => {
      document.body.style.overflow = previousBodyOverflow.current;
      document.documentElement.style.overflow = previousHtmlOverflow.current;
      setDone(true);
    }, 360);
  };

  if (done) return null;

  return (
    <div
      className={`opening-root fixed inset-0 z-[200] grid place-items-center overflow-hidden px-6 text-white transition-opacity duration-500 ${ready ? 'is-ready' : ''} ${exiting ? 'pointer-events-none opacity-0' : 'opacity-100'}`}
    >
      <div className="opening-glow opening-glow-blue" aria-hidden="true" />
      <div className="opening-glow opening-glow-violet" aria-hidden="true" />

      <main
        className={`opening-content relative z-[1] mx-auto flex w-full max-w-[680px] flex-col items-center text-center transition-[transform,opacity,filter] duration-500 ${
          exiting ? 'scale-[0.97] opacity-0 blur-sm' : ''
        }`}
      >
        <div className="opening-icon-wrap opening-reveal opening-reveal-1" aria-hidden="true">
          <span className="opening-icon-halo" />
          <span className="opening-icon grid h-[88px] w-[88px] place-items-center rounded-[25px] sm:h-[96px] sm:w-[96px] sm:rounded-[28px]">
            <Sparkles size={40} strokeWidth={1.65} />
          </span>
        </div>

        <p className="opening-reveal opening-reveal-2 mt-10 text-[11px] font-semibold uppercase tracking-[0.28em] text-white/45 sm:text-xs">
          Welcome to my portfolio
        </p>
        <h2 className="opening-reveal opening-reveal-3 mt-4 text-[52px] font-semibold leading-none tracking-[-0.06em] sm:text-[72px]">
          ZHANG<span className="opening-dot">.</span>
        </h2>
        <p className="opening-reveal opening-reveal-4 mt-5 text-[15px] font-medium tracking-[-0.015em] text-white/55 sm:text-[17px]">
          机器人 · 工程 · 人工智能
        </p>
        <p className="opening-reveal opening-reveal-5 mx-auto mt-7 max-w-[500px] text-[16px] leading-7 tracking-[-0.018em] text-white/72 sm:text-[18px] sm:leading-8">
          欢迎来到我的个人网站。这里收录项目、经历与持续完善的在线工具。
        </p>

        <div className="opening-reveal opening-reveal-6 mt-10 sm:mt-12">
          <button
            type="button"
            onClick={continueToHome}
            disabled={!ready || exiting}
            data-sound="startup"
            className="opening-enter-button group inline-flex min-h-12 items-center gap-2.5 rounded-full px-6 py-3 text-[15px] font-semibold text-white disabled:cursor-wait disabled:opacity-45"
          >
            进入网站
            <ArrowRight className="transition-transform duration-300 group-hover:translate-x-0.5" size={17} strokeWidth={2.2} />
          </button>
        </div>

        <p className="opening-reveal opening-reveal-7 mt-8 text-[11px] font-medium tracking-[0.14em] text-white/25">
          ZHANG · 2026
        </p>
      </main>
    </div>
  );
}
