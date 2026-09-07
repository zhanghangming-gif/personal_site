import { Bot, GripHorizontal, RotateCcw, Send, Sparkles, X } from 'lucide-react';
import { FormEvent, PointerEvent as ReactPointerEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { askAboutZhang, type ChatHistoryItem } from '../services/chatService';
import { useLanguage } from '../context/LanguageContext';
import { useSound } from '../hooks/useSound';

interface DisplayMessage extends ChatHistoryItem {
  id: string;
  transient?: boolean;
}

type Suggestion = {
  label: string;
  question: string;
};

type PanelPosition = { x: number; y: number };
type DragState = { pointerId: number; offsetX: number; offsetY: number };

const POSITION_KEY = 'ai-assistant-position';

function initialPanelPosition(): PanelPosition | null {
  try {
    const value = JSON.parse(window.localStorage.getItem(POSITION_KEY) || 'null');
    if (Number.isFinite(value?.x) && Number.isFinite(value?.y)) return value;
  } catch {
    // Ignore obsolete or manually edited browser storage.
  }
  return null;
}

export function AiAssistant({ docked = false }: { docked?: boolean }) {
  const { language } = useLanguage();
  const { play } = useSound();
  const en = language === 'en';
  const welcome = useMemo<DisplayMessage>(
    () => ({
      id: `welcome-${language}`,
      role: 'assistant',
      content: en
        ? "Ask about Zhang's projects, awards, skills, or site terms."
        : '可以问项目、获奖、技能或站内名词。',
      transient: true,
    }),
    [en, language],
  );
  const suggestions: Suggestion[] = en
    ? [
        { label: 'Projects', question: "Summarize Zhang Hangming's strongest projects." },
        { label: 'Awards', question: "What are Zhang Hangming's main awards?" },
        { label: 'Mingyue', question: 'What is the Mingyue Program, and how is Zhang Hangming connected to it?' },
        { label: 'ROBOCON', question: 'What is ROBOCON, and what did Zhang Hangming do in it?' },
        { label: 'FAST-LIO2', question: 'Explain FAST-LIO2 and its relation to Zhang Hangming’s project.' },
        { label: 'Contact', question: 'How can I contact Zhang Hangming?' },
      ]
    : [
        { label: '项目亮点', question: '总结一下张航铭最有代表性的项目。' },
        { label: '获奖情况', question: '张航铭有哪些主要获奖？' },
        { label: '明月班', question: '什么是明月班？它和张航铭有什么关系？' },
        { label: 'ROBOCON', question: 'ROBOCON 是什么？张航铭在里面做了什么？' },
        { label: 'FAST-LIO2', question: 'FAST-LIO2 是什么？和张航铭的项目有什么关系？' },
        { label: '联系他', question: '我怎么联系张航铭？' },
      ];
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<DisplayMessage[]>([welcome]);
  const [loading, setLoading] = useState(false);
  const [hintVisible, setHintVisible] = useState(false);
  const [panelPosition, setPanelPosition] = useState<PanelPosition | null>(initialPanelPosition);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const dragRef = useRef<DragState | null>(null);

  const boundedPosition = useCallback((x: number, y: number) => {
    const panel = panelRef.current;
    const width = panel?.offsetWidth ?? Math.min(380, window.innerWidth - 24);
    const height = panel?.offsetHeight ?? Math.min(560, window.innerHeight - 144);
    const margin = 12;
    return {
      x: Math.max(margin, Math.min(x, window.innerWidth - width - margin)),
      y: Math.max(margin, Math.min(y, window.innerHeight - height - margin)),
    };
  }, []);

  const startDragging = (event: ReactPointerEvent<HTMLElement>) => {
    if (event.button !== 0 || (event.target as HTMLElement).closest('button')) return;
    const panel = panelRef.current;
    if (!panel) return;
    const rect = panel.getBoundingClientRect();
    dragRef.current = {
      pointerId: event.pointerId,
      offsetX: event.clientX - rect.left,
      offsetY: event.clientY - rect.top,
    };
    setPanelPosition({ x: rect.left, y: rect.top });
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  };

  const dragPanel = (event: ReactPointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    setPanelPosition(boundedPosition(event.clientX - drag.offsetX, event.clientY - drag.offsetY));
  };

  const stopDragging = (event: ReactPointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    dragRef.current = null;
    const next = boundedPosition(event.clientX - drag.offsetX, event.clientY - drag.offsetY);
    setPanelPosition(next);
    window.localStorage.setItem(POSITION_KEY, JSON.stringify(next));
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [open, messages, loading]);

  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setOpen(false);
      play('panelClose');
    };
    addEventListener('keydown', close);
    return () => removeEventListener('keydown', close);
  }, [play]);

  useEffect(() => {
    setMessages([welcome]);
  }, [welcome]);
  useEffect(() => {
    if (open) {
      setHintVisible(false);
      return;
    }
    const showTimer = window.setTimeout(() => setHintVisible(true), 1500);
    const hideTimer = window.setTimeout(() => setHintVisible(false), 6200);
    return () => {
      window.clearTimeout(showTimer);
      window.clearTimeout(hideTimer);
    };
  }, [open, language]);

  useEffect(() => {
    if (!open) return;
    const keepVisible = () => setPanelPosition((current) => {
      if (!current) return current;
      const next = boundedPosition(current.x, current.y);
      return next.x === current.x && next.y === current.y ? current : next;
    });
    keepVisible();
    window.addEventListener('resize', keepVisible);
    return () => window.removeEventListener('resize', keepVisible);
  }, [boundedPosition, open]);

  const send = async (question: string) => {
    const content = question.trim();
    if (!content || loading) return;
    const history = messages
      .filter((item) => !item.transient)
      .slice(-8)
      .map(({ role, content: text }) => ({ role, content: text }));
    const userMessage: DisplayMessage = { id: crypto.randomUUID(), role: 'user', content };
    setMessages((current) => [...current, userMessage]);
    play('send');
    setInput('');
    setLoading(true);
    try {
      const answer = await askAboutZhang(content, history);
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'assistant', content: answer }]);
      play('aiDone');
    } catch (error) {
      play('error');
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content:
            error instanceof Error
              ? error.message
              : en
                ? 'The AI assistant is temporarily unavailable. Please try again later.'
                : 'AI 助手暂时无法回答，请稍后再试',
          transient: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void send(input);
  };

  return (
    <>
      {open && (
        <section
          ref={panelRef}
          className={`fixed z-[70] flex w-[calc(100vw-1.5rem)] max-w-[380px] max-h-[min(560px,calc(100vh-1.5rem))] flex-col overflow-hidden rounded-2xl border bg-[rgb(var(--surface))] shadow-2xl ${panelPosition ? '' : 'bottom-28 left-3 sm:left-auto sm:right-5'}`}
          style={panelPosition ? { left: panelPosition.x, top: panelPosition.y } : undefined}
          aria-label={en ? 'Zhang Hangming AI assistant' : '张航铭 AI 助手'}
        >
          <header
            className="relative flex touch-none cursor-grab select-none items-center justify-between border-b bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2.5 text-white active:cursor-grabbing"
            onPointerDown={startDragging}
            onPointerMove={dragPanel}
            onPointerUp={stopDragging}
            onPointerCancel={stopDragging}
            title={en ? 'Drag to move' : '按住拖动窗口'}
          >
            <div className="flex items-center gap-3">
              <span className="grid h-8 w-8 place-items-center rounded-xl bg-white/15">
                <Sparkles size={18} />
              </span>
              <div>
                <h2 className="text-sm font-bold">{en ? 'Zhang Hangming AI' : '张航铭 AI 助手'}</h2>
              </div>
            </div>
            <GripHorizontal className="pointer-events-none absolute left-1/2 -translate-x-1/2 text-white/65" size={20} />
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() => setMessages([welcome])}
                className="grid h-8 w-8 place-items-center rounded-lg hover:bg-white/15"
                aria-label={en ? 'Clear conversation' : '清空对话'}
              >
                <RotateCcw size={16} />
              </button>
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  play('panelClose');
                }}
                data-sound-off="true"
                className="grid h-8 w-8 place-items-center rounded-lg hover:bg-white/15"
                aria-label={en ? 'Close AI assistant' : '关闭 AI 助手'}
              >
                <X size={18} />
              </button>
            </div>
          </header>

          <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto p-3.5" aria-live="polite">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <p
                  className={`max-w-[82%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-sm leading-6 ${
                    message.role === 'user'
                      ? 'rounded-br-md bg-accent text-white'
                      : 'rounded-bl-md bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200'
                  }`}
                >
                  {message.content}
                </p>
              </div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="flex gap-1 rounded-2xl rounded-bl-md bg-slate-100 px-4 py-3 dark:bg-slate-800">
                  {[0, 1, 2].map((item) => (
                    <span
                      key={item}
                      className="h-1.5 w-1.5 animate-pulse rounded-full bg-slate-400"
                      style={{ animationDelay: `${item * 150}ms` }}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>

          {messages.length === 1 && (
            <div className="flex flex-wrap gap-2 px-3.5 pb-3">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion.label}
                  type="button"
                  onClick={() => void send(suggestion.question)}
                  className="rounded-full border px-3 py-1.5 text-xs text-slate-600 transition hover:border-blue-400 hover:text-accent dark:text-slate-300"
                >
                  {suggestion.label}
                </button>
              ))}
            </div>
          )}

          <form onSubmit={submit} className="flex items-end gap-2 border-t p-3">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(event) => setInput(event.target.value.slice(0, 400))}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void send(input);
                }
              }}
              rows={1}
              placeholder={en ? 'Ask anything…' : '问点什么…'}
              className="max-h-20 min-h-10 flex-1 resize-none rounded-xl border bg-transparent px-3 py-2 text-sm outline-none focus:border-blue-500"
              disabled={loading}
              aria-label={en ? 'Enter a question' : '输入问题'}
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent text-white transition disabled:cursor-not-allowed disabled:opacity-40"
              aria-label={en ? 'Send question' : '发送问题'}
            >
              <Send size={17} />
            </button>
          </form>
          <p className="pb-2 text-center text-[10px] text-slate-400">
            {en ? 'Based on site content' : '回答以本站资料为准'}
          </p>
        </section>
      )}

      <div className={`${docked ? 'contents' : 'fixed bottom-4 right-3 z-[70] flex flex-col items-end gap-2 sm:bottom-5 sm:right-5'}`}>
        {!open && hintVisible && (
          <div className="relative max-w-[210px] rounded-2xl border border-blue-200/80 bg-[rgb(var(--surface))]/95 px-3.5 py-2.5 text-left shadow-[0_14px_40px_rgba(37,99,235,0.18)] dark:border-blue-500/30">
            <span className="block text-sm font-bold text-slate-900 dark:text-white">
              {en ? 'Need context?' : '想快速了解？'}
            </span>
            <span className="mt-0.5 block text-xs text-slate-500 dark:text-slate-300">
              {en ? 'Ask about me or related terms' : '可以问我，也可以问相关名词'}
            </span>
            <span className="absolute -bottom-1.5 right-7 h-3 w-3 rotate-45 border-b border-r border-blue-200/80 bg-[rgb(var(--surface))] dark:border-blue-500/30" />
          </div>
        )}

        <button
          type="button"
          onClick={() => {
            setOpen((current) => {
              play(current ? 'panelClose' : 'panelOpen');
              return !current;
            });
          }}
          data-sound-off="true"
          className={`group relative isolate flex items-center border border-white/25 bg-gradient-to-r from-blue-600 via-blue-600 to-indigo-600 text-left text-white shadow-[0_14px_34px_rgba(37,99,235,0.34)] transition hover:-translate-y-1 hover:shadow-[0_18px_44px_rgba(37,99,235,0.48)] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-blue-400/50 ${open ? 'min-h-16 gap-3 rounded-2xl px-4 py-3' : 'h-14 w-14 justify-center rounded-full p-0 sm:h-15 sm:w-15'}`}
          aria-label={
            open
              ? en
                ? 'Close Zhang Hangming AI assistant'
                : '关闭张航铭 AI 助手'
              : en
                ? 'Open Zhang Hangming AI assistant'
                : '打开张航铭 AI 助手'
          }
          aria-expanded={open}
        >
          <span className={`absolute -inset-1 -z-10 bg-blue-500/20 blur-md ${open ? 'rounded-[20px]' : 'rounded-full'}`} />
          <span className={`grid shrink-0 place-items-center bg-white/15 ring-1 ring-white/20 transition group-hover:scale-105 ${open ? 'h-10 w-10 rounded-xl' : 'h-full w-full rounded-full'}`}>
            {open ? <X size={21} /> : <Bot size={22} />}
          </span>
          <span className={`pr-1 ${open ? 'block' : 'sr-only'}`}>
            <span className="block text-sm font-black leading-5">
              {open ? (en ? 'Hide AI assistant' : '收起 AI 助手') : en ? 'AI introduction' : 'AI 介绍助手'}
            </span>
            <span className="block text-[11px] font-medium text-blue-100">
              {open
                ? en
                  ? 'Return to the website'
                  : '返回浏览网站'
                : en
                  ? 'Ask about projects or terms'
                  : '问项目或相关名词'}
            </span>
          </span>
        </button>
      </div>
    </>
  );
}
