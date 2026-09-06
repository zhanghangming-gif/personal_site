import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

export type SoundName =
  | 'click'
  | 'transition'
  | 'panelOpen'
  | 'panelClose'
  | 'success'
  | 'error'
  | 'send'
  | 'aiDone'
  | 'startup'
  | 'toggleOn';

type SoundValue = {
  enabled: boolean;
  toggle: () => void;
  play: (name: SoundName) => void;
  stop: () => void;
};

const STORAGE_KEY = 'zhm-sound-enabled';
const SoundContext = createContext<SoundValue | null>(null);

const throttleMs: Record<SoundName, number> = {
  click: 75,
  transition: 520,
  panelOpen: 240,
  panelClose: 240,
  success: 650,
  error: 650,
  send: 280,
  aiDone: 900,
  startup: 1800,
  toggleOn: 300,
};

export function SoundProvider({ children }: { children: ReactNode }) {
  const [enabled, setEnabled] = useState(() => localStorage.getItem(STORAGE_KEY) === 'true');
  const audioRef = useRef<AudioContext | null>(null);
  const masterRef = useRef<GainNode | null>(null);
  const activeRef = useRef<Set<AudioScheduledSourceNode>>(new Set());
  const lastPlayedRef = useRef<Partial<Record<SoundName, number>>>({});

  const ensureAudio = useCallback(() => {
    const AudioCtor = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtor) return null;
    if (!audioRef.current) {
      const context = new AudioCtor();
      const master = context.createGain();
      master.gain.value = 0.28;
      master.connect(context.destination);
      audioRef.current = context;
      masterRef.current = master;
    }
    if (audioRef.current.state === 'suspended') void audioRef.current.resume();
    return audioRef.current;
  }, []);

  const stop = useCallback(() => {
    activeRef.current.forEach((node) => {
      try {
        node.stop();
      } catch {
        // The node may already have finished.
      }
    });
    activeRef.current.clear();
  }, []);

  const tone = useCallback(
    (
      context: AudioContext,
      options: {
        start?: number;
        duration: number;
        from: number;
        to?: number;
        type?: OscillatorType;
        volume?: number;
        attack?: number;
      },
    ) => {
      const master = masterRef.current;
      if (!master) return;
      const start = context.currentTime + (options.start ?? 0);
      const duration = options.duration;
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.type = options.type ?? 'sine';
      oscillator.frequency.setValueAtTime(options.from, start);
      if (options.to) oscillator.frequency.exponentialRampToValueAtTime(options.to, start + duration);
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(options.volume ?? 0.18, start + (options.attack ?? 0.012));
      gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
      oscillator.connect(gain);
      gain.connect(master);
      activeRef.current.add(oscillator);
      oscillator.onended = () => activeRef.current.delete(oscillator);
      oscillator.start(start);
      oscillator.stop(start + duration + 0.02);
    },
    [],
  );

  const noise = useCallback(
    (context: AudioContext, options: { start?: number; duration: number; volume?: number; frequency?: number }) => {
      const master = masterRef.current;
      if (!master) return;
      const start = context.currentTime + (options.start ?? 0);
      const duration = options.duration;
      const buffer = context.createBuffer(1, Math.max(1, Math.floor(context.sampleRate * duration)), context.sampleRate);
      const data = buffer.getChannelData(0);
      for (let index = 0; index < data.length; index += 1) data[index] = (Math.random() * 2 - 1) * (1 - index / data.length);

      const source = context.createBufferSource();
      const filter = context.createBiquadFilter();
      const gain = context.createGain();
      filter.type = 'highpass';
      filter.frequency.value = options.frequency ?? 1200;
      gain.gain.setValueAtTime(options.volume ?? 0.08, start);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
      source.buffer = buffer;
      source.connect(filter);
      filter.connect(gain);
      gain.connect(master);
      activeRef.current.add(source);
      source.onended = () => activeRef.current.delete(source);
      source.start(start);
      source.stop(start + duration + 0.01);
    },
    [],
  );

  const playPattern = useCallback(
    (name: SoundName, force = false) => {
      if (!force && !enabled) return;
      const now = performance.now();
      if (now - (lastPlayedRef.current[name] ?? 0) < throttleMs[name]) return;
      lastPlayedRef.current[name] = now;

      const context = ensureAudio();
      if (!context) return;

      switch (name) {
        case 'click':
          noise(context, { duration: 0.032, volume: 0.058, frequency: 1800 });
          tone(context, { start: 0.006, duration: 0.045, from: 980, to: 720, type: 'triangle', volume: 0.048 });
          break;
        case 'transition':
          tone(context, { duration: 0.18, from: 260, to: 520, type: 'sine', volume: 0.068 });
          tone(context, { start: 0.08, duration: 0.22, from: 620, to: 920, type: 'triangle', volume: 0.043 });
          noise(context, { start: 0.02, duration: 0.14, volume: 0.034, frequency: 2400 });
          break;
        case 'panelOpen':
          tone(context, { duration: 0.12, from: 360, to: 640, type: 'triangle', volume: 0.07 });
          tone(context, { start: 0.08, duration: 0.15, from: 720, to: 1040, type: 'sine', volume: 0.043 });
          break;
        case 'panelClose':
          tone(context, { duration: 0.12, from: 620, to: 340, type: 'triangle', volume: 0.058 });
          noise(context, { start: 0.03, duration: 0.045, volume: 0.03, frequency: 1600 });
          break;
        case 'success':
          tone(context, { duration: 0.1, from: 620, to: 820, type: 'sine', volume: 0.068 });
          tone(context, { start: 0.09, duration: 0.16, from: 920, to: 1240, type: 'sine', volume: 0.066 });
          break;
        case 'error':
          tone(context, { duration: 0.15, from: 210, to: 150, type: 'triangle', volume: 0.078 });
          tone(context, { start: 0.08, duration: 0.13, from: 170, to: 130, type: 'sine', volume: 0.048 });
          break;
        case 'send':
          tone(context, { duration: 0.08, from: 760, to: 1160, type: 'triangle', volume: 0.06 });
          noise(context, { start: 0.02, duration: 0.038, volume: 0.03, frequency: 3000 });
          break;
        case 'aiDone':
          tone(context, { duration: 0.14, from: 520, to: 760, type: 'sine', volume: 0.052 });
          tone(context, { start: 0.13, duration: 0.18, from: 780, to: 980, type: 'triangle', volume: 0.046 });
          break;
        case 'startup':
          tone(context, { duration: 0.42, from: 86, to: 150, type: 'sine', volume: 0.096, attack: 0.04 });
          noise(context, { start: 0.12, duration: 0.28, volume: 0.048, frequency: 1800 });
          tone(context, { start: 0.46, duration: 0.18, from: 420, to: 840, type: 'triangle', volume: 0.064 });
          tone(context, { start: 0.68, duration: 0.16, from: 980, to: 1320, type: 'sine', volume: 0.058 });
          break;
        case 'toggleOn':
          tone(context, { duration: 0.09, from: 500, to: 720, type: 'sine', volume: 0.055 });
          tone(context, { start: 0.08, duration: 0.1, from: 860, to: 1120, type: 'sine', volume: 0.055 });
          break;
      }
    },
    [enabled, ensureAudio, noise, tone],
  );

  const play = useCallback((name: SoundName) => playPattern(name), [playPattern]);

  const toggle = useCallback(() => {
    setEnabled((current) => {
      const next = !current;
      localStorage.setItem(STORAGE_KEY, String(next));
      if (next) {
        window.setTimeout(() => playPattern('toggleOn', true), 0);
      } else {
        stop();
      }
      return next;
    });
  }, [playPattern, stop]);

  useEffect(() => {
    const handleClick = (event: MouseEvent) => {
      const target = event.target as Element | null;
      const control = target?.closest<HTMLElement>('button, a, [role="button"], [data-sound]');
      if (!control || control.dataset.soundOff === 'true') return;
      if (control instanceof HTMLButtonElement && control.disabled) return;
      if (control.getAttribute('aria-disabled') === 'true') return;
      const requested = control.dataset.sound as SoundName | undefined;
      play(requested || 'click');
    };

    document.addEventListener('click', handleClick, true);
    return () => document.removeEventListener('click', handleClick, true);
  }, [play]);

  const value = useMemo(() => ({ enabled, toggle, play, stop }), [enabled, toggle, play, stop]);
  return <SoundContext.Provider value={value}>{children}</SoundContext.Provider>;
}

export function useSound() {
  const context = useContext(SoundContext);
  if (!context) throw new Error('useSound must be used inside SoundProvider');
  return context;
}

declare global {
  interface Window {
    webkitAudioContext?: typeof AudioContext;
  }
}
