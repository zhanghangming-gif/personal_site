import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { CheckCircle2, XCircle } from 'lucide-react';
import { useSound } from '../hooks/useSound';

type ToastType = 'success' | 'error';
interface ToastItem { id: number; text: string; type: ToastType }
const ToastContext = createContext<((text: string, type?: ToastType) => void) | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const { play } = useSound();
  const show = useCallback((text: string, type: ToastType = 'success') => { const id = Date.now(); play(type === 'success' ? 'success' : 'error'); setItems((v) => [...v, { id, text, type }]); window.setTimeout(() => setItems((v) => v.filter((item) => item.id !== id)), 3000); }, [play]);
  const value = useMemo(() => show, [show]);
  return <ToastContext.Provider value={value}>{children}<div className="fixed right-4 top-20 z-[100] flex w-[min(360px,calc(100%-2rem))] flex-col gap-2" aria-live="polite">{items.map((item) => <div key={item.id} className="surface flex items-center gap-3 rounded-xl p-4 text-sm font-medium">{item.type === 'success' ? <CheckCircle2 className="text-emerald-500" size={19} /> : <XCircle className="text-red-500" size={19} />}{item.text}</div>)}</div></ToastContext.Provider>;
}
export function useToast() { const context = useContext(ToastContext); if (!context) throw new Error('useToast 必须在 ToastProvider 内使用'); return context; }
