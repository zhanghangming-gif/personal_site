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
      className={`opening-root fixed inset-0 z-[200] grid place-items-center overflow-hidden px-5 text-white transition-opacity duration-300 ${exiting ? 'pointer-events-none opacity-0' : 'opacity-100'}`}
    >
      <div className={`mac-opening-window w-full max-w-[520px] overflow-hidden rounded-[28px] transition-[transform,opacity] duration-300 ${exiting ? 'scale-[0.985] opacity-0' : 'scale-100 opacity-100'}`}>
        <div className="flex h-12 items-center justify-between border-b border-white/10 px-4">
          <div className="flex items-center gap-2" aria-hidden="true">
            <span className="h-3 w-3 rounded-full bg-[#ff5f57]" />
            <span className="h-3 w-3 rounded-full bg-[#febc2e]" />
            <span className="h-3 w-3 rounded-full bg-[#28c840]" />
          </div>
          <span className="text-xs font-medium text-white/55">欢迎</span>
          <span className="w-[52px]" aria-hidden="true" />
        </div>

        <div className="px-7 pb-8 pt-10 text-center sm:px-10">
          <span className="mx-auto grid h-[76px] w-[76px] place-items-center rounded-[20px] bg-gradient-to-br from-[#0a84ff] to-[#5e5ce6] shadow-[0_16px_42px_rgba(10,132,255,0.34)]">
            <Sparkles size={34} strokeWidth={1.8} />
          </span>
          <h2 className="mt-7 text-[38px] font-semibold leading-none tracking-[-0.045em] sm:text-[44px]">
            ZHANG<span className="text-[#0a84ff]">.</span>
          </h2>
          <p className="mt-4 text-[13px] font-medium tracking-[0.06em] text-white/55">
            机器人 · 工程 · 人工智能
          </p>
          <p className="mx-auto mt-6 max-w-sm text-[15px] leading-7 text-white/68">
            欢迎来到我的个人网站。这里收录项目、经历与持续完善的在线工具。
          </p>

          <button
            type="button"
            onClick={continueToHome}
            disabled={!ready || exiting}
            data-sound="startup"
            className="mx-auto mt-9 inline-flex min-h-11 items-center gap-2 rounded-xl bg-[#0a84ff] px-5 py-2.5 text-[14px] font-semibold text-white shadow-[0_8px_24px_rgba(10,132,255,0.28)] transition-[background-color,transform,opacity] duration-150 hover:bg-[#0071e3] active:scale-[0.98] disabled:cursor-wait disabled:opacity-45"
          >
            进入网站
            <ArrowRight size={17} strokeWidth={2.2} />
          </button>
        </div>
      </div>
    </div>
  );
}
