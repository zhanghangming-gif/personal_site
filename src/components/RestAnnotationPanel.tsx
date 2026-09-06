import { BoxSelect, Check, Download, RefreshCw, RotateCcw, SkipForward, Trash2, X } from 'lucide-react';
import { PointerEvent, useEffect, useMemo, useRef, useState } from 'react';
import { apiRequest } from '../services/api';

type AnnotationState = 'unreviewed' | 'accepted' | 'corrected' | 'rejected' | 'skipped';
type Target = { class: string; bboxXyxy: number[]; dots: number };
type Sample = {
  sampleId: string; imageUrl: string; imageWidth: number; imageHeight: number;
  documentSha256: string; gapId: string; measureId?: string; page?: number;
  voice?: string; onset?: string; duration?: string; position?: string;
  imageSource?: string; classificationStatus?: string;
  prelabel?: Target & { grade?: number; contextGrade?: number; source?: string };
  state: AnnotationState; annotation?: { targets?: Target[]; reason?: string };
  reviewedAt?: string; revision: string;
};
type Queue = {
  items: Sample[]; offset: number; limit: number; filteredTotal: number;
  counts: Record<AnnotationState | 'total' | 'trainingReady', number>; classes: string[];
};

const stateLabels: Record<string, string> = {
  all: '全部', unreviewed: '待标注', accepted: '已接受', corrected: '已修正',
  rejected: '无休止符', skipped: '无法判断',
};
const classLabels: Record<string, string> = {
  maxima_rest: '八全休止符', long_rest: '四全休止符', breve_rest: '二全休止符',
  whole_rest: '全休止符', half_rest: '二分休止符', quarter_rest: '四分休止符',
  eighth_rest: '八分休止符', '16th_rest': '十六分休止符', '32nd_rest': '三十二分休止符',
  '64th_rest': '六十四分休止符', '128th_rest': '一百二十八分休止符',
  multi_measure_rest: '多小节休止',
};

function cloneTargets(targets: Target[] | undefined) {
  return (targets || []).map(target => ({
    class: target.class, bboxXyxy: [...target.bboxXyxy], dots: target.dots || 0,
  }));
}

export function RestAnnotationPanel() {
  const [queue, setQueue] = useState<Queue | null>(null);
  const [filter, setFilter] = useState('unreviewed');
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState('');
  const [targets, setTargets] = useState<Target[]>([]);
  const [activeTarget, setActiveTarget] = useState(0);
  const [drawMode, setDrawMode] = useState(false);
  const [draft, setDraft] = useState<number[] | null>(null);
  const [reason, setReason] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const drawStart = useRef<[number, number] | null>(null);
  const selected = queue?.items.find(item => item.sampleId === selectedId) || queue?.items[0];

  const load = async (nextFilter = filter, nextOffset = offset, preferredId?: string) => {
    setBusy(true); setNotice('');
    try {
      const response = await apiRequest<{ data: Queue }>(`/api/admin/rest-annotations?state=${encodeURIComponent(nextFilter)}&offset=${nextOffset}&limit=24`);
      setQueue(response.data);
      const id = preferredId && response.data.items.some(item => item.sampleId === preferredId)
        ? preferredId : response.data.items[0]?.sampleId || '';
      setSelectedId(id);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '训练样本加载失败');
    } finally { setBusy(false); }
  };

  useEffect(() => { void load(filter, offset); }, [filter, offset]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!selected) { setTargets([]); setReason(''); return; }
    const saved = selected.annotation?.targets;
    setTargets(cloneTargets(saved?.length ? saved : selected.prelabel ? [selected.prelabel] : []));
    setReason(selected.annotation?.reason || ''); setActiveTarget(0); setDrawMode(false); setDraft(null);
  }, [selected?.sampleId, selected?.revision]); // eslint-disable-line react-hooks/exhaustive-deps

  const active = targets[activeTarget];
  const selectedClass = active?.class || selected?.prelabel?.class || queue?.classes[0] || 'quarter_rest';
  const reviewedProgress = queue ? queue.counts.trainingReady : 0;
  const allCount = queue?.counts.total || 0;

  const point = (event: PointerEvent<SVGSVGElement>) => {
    if (!selected) return [0, 0] as [number, number];
    const rect = event.currentTarget.getBoundingClientRect();
    return [
      Math.max(0, Math.min(selected.imageWidth, (event.clientX - rect.left) / rect.width * selected.imageWidth)),
      Math.max(0, Math.min(selected.imageHeight, (event.clientY - rect.top) / rect.height * selected.imageHeight)),
    ] as [number, number];
  };
  const startDraw = (event: PointerEvent<SVGSVGElement>) => {
    if (!drawMode || !selected) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    const start = point(event); drawStart.current = start; setDraft([start[0], start[1], start[0], start[1]]);
  };
  const moveDraw = (event: PointerEvent<SVGSVGElement>) => {
    if (!drawMode || !drawStart.current) return;
    const current = point(event); const start = drawStart.current;
    setDraft([Math.min(start[0], current[0]), Math.min(start[1], current[1]), Math.max(start[0], current[0]), Math.max(start[1], current[1])]);
  };
  const finishDraw = () => {
    if (!draft || draft[2] - draft[0] < 2 || draft[3] - draft[1] < 2) {
      setDraft(null); drawStart.current = null; return;
    }
    setTargets(current => [...current, { class: selectedClass, bboxXyxy: draft.map(value => Math.round(value * 10) / 10), dots: 0 }]);
    setActiveTarget(targets.length); setDraft(null); drawStart.current = null; setDrawMode(false);
  };

  const save = async (state: Exclude<AnnotationState, 'unreviewed'>, nextTargets: Target[] = targets) => {
    if (!selected) return;
    setBusy(true); setNotice('');
    try {
      await apiRequest(`/api/admin/rest-annotations/${selected.sampleId}`, {
        method: 'PUT', body: JSON.stringify({ revision: selected.revision, state, targets: nextTargets, reason }),
      });
      setNotice('已保存，正在进入下一条');
      await load(filter, offset);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '标注保存失败');
    } finally { setBusy(false); }
  };
  const acceptPrelabel = () => {
    if (!selected?.prelabel) { setNotice('该样本没有可接受的预标框，请手工画框'); return; }
    const accepted = cloneTargets([selected.prelabel]); setTargets(accepted); void save('accepted', accepted);
  };
  const refresh = async () => {
    setBusy(true); setNotice('正在扫描乐谱任务并生成局部裁片…');
    try {
      const response = await apiRequest<{ message: string }>('/api/admin/rest-annotations/refresh', { method: 'POST', body: '{}' });
      setNotice(response.message); setOffset(0); await load(filter, 0);
    } catch (error) { setNotice(error instanceof Error ? error.message : '刷新失败'); }
    finally { setBusy(false); }
  };
  const setTarget = (patch: Partial<Target>) => setTargets(current => current.map((target, index) => index === activeTarget ? { ...target, ...patch } : target));
  const pageEnd = queue ? Math.min(queue.filteredTotal, queue.offset + queue.limit) : 0;
  const boxes = useMemo(() => draft ? [...targets.map(target => target.bboxXyxy), draft] : targets.map(target => target.bboxXyxy), [targets, draft]);

  return <section>
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div><p className="eyebrow">REST DETECTOR DATA</p><h1 className="text-3xl font-black">休止符训练标注</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">样本包含节奏缺口和全谱限量抽取的休止符候选。绿色框是 OMR 预标；裁片里每一个清楚可见的休止符都要单独标框，人工接受或修正后才会进入模型训练。</p></div>
      <div className="flex flex-wrap gap-2"><button disabled={busy} onClick={() => void refresh()} className="button-secondary"><RefreshCw size={16}/>{busy ? '处理中…' : '刷新样本'}</button><a href="/api/admin/rest-annotations/export" className="button-primary"><Download size={16}/>导出 COCO</a></div>
    </div>
    <div className="mt-6 grid gap-3 sm:grid-cols-3">
      {[['样本总数', allCount], ['可训练样本', reviewedProgress], ['待人工标注', queue?.counts.unreviewed || 0]].map(([label, value]) => <article key={label} className="rounded-2xl border bg-white p-5 dark:border-slate-800 dark:bg-slate-900"><p className="text-sm text-slate-500">{label}</p><strong className="mt-1 block text-3xl">{value}</strong></article>)}
    </div>
    <div className="mt-5 flex flex-wrap gap-2">{['unreviewed','accepted','corrected','rejected','skipped','all'].map(value => <button key={value} onClick={() => { setFilter(value); setOffset(0); }} className={`rounded-full px-4 py-2 text-sm font-semibold ${filter === value ? 'bg-blue-600 text-white' : 'border bg-white dark:bg-slate-900'}`}>{stateLabels[value]} {value !== 'all' && queue ? queue.counts[value as AnnotationState] : ''}</button>)}</div>
    {notice && <p className="mt-4 rounded-xl border border-blue-400/30 bg-blue-500/10 px-4 py-3 text-sm text-blue-700 dark:text-blue-300">{notice}</p>}
    {!selected ? <div className="mt-6 rounded-3xl border bg-white p-14 text-center text-slate-500 dark:bg-slate-900">{allCount ? '这个筛选条件下没有样本。' : '还没有标注样本。点击“刷新样本”，从服务器已有乐谱任务生成裁片。'}</div> :
      <div className="mt-6 grid gap-5 xl:grid-cols-[minmax(0,1.65fr)_minmax(340px,.7fr)]">
        <article className="overflow-hidden rounded-3xl border bg-white dark:border-slate-800 dark:bg-slate-900">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4 dark:border-slate-800"><div><strong>第 {selected.page || '?'} 页 · {selected.measureId || '未知小节'} · 声部 {selected.voice || '?'}</strong><p className="mt-1 text-xs text-slate-500">文档 {selected.documentSha256?.slice(0, 12)}… · 缺口 {selected.duration || '?'} · {selected.imageSource === 'audiveris_binary' ? 'OMR 二值图' : '原 PDF 高清裁片'}</p></div><span className="tag">{stateLabels[selected.state]}</span></div>
          <div className="relative m-4 overflow-hidden rounded-2xl border bg-white shadow-inner" style={{ aspectRatio: `${selected.imageWidth}/${selected.imageHeight}` }}>
            <img src={selected.imageUrl} alt="待标注休止符局部谱面" className="absolute inset-0 h-full w-full select-none object-contain" draggable={false}/>
            <svg viewBox={`0 0 ${selected.imageWidth} ${selected.imageHeight}`} className={`absolute inset-0 h-full w-full touch-none ${drawMode ? 'cursor-crosshair' : 'cursor-default'}`} onPointerDown={startDraw} onPointerMove={moveDraw} onPointerUp={finishDraw} onPointerCancel={finishDraw}>
              {boxes.map((box, index) => <g key={`${index}-${box.join('-')}`} onPointerDown={event => { if (!drawMode && index < targets.length) { event.stopPropagation(); setActiveTarget(index); } }}><rect x={box[0]} y={box[1]} width={box[2]-box[0]} height={box[3]-box[1]} fill={index === activeTarget ? 'rgba(10,132,255,.14)' : 'rgba(52,199,89,.10)'} stroke={index === activeTarget ? '#0a84ff' : '#22c55e'} strokeWidth={Math.max(2, selected.imageWidth / 320)} vectorEffect="non-scaling-stroke"/><text x={box[0]} y={Math.max(12, box[1]-4)} fill={index === activeTarget ? '#0a84ff' : '#15803d'} fontSize={Math.max(12, selected.imageWidth / 34)} fontWeight="700">{index + 1}</text></g>)}
            </svg>
          </div>
          <p className="px-5 pb-5 text-xs leading-5 text-slate-500">框要紧贴休止符主体；保留少量边缘，不要包含相邻音符、谱号或小节号。多小节休止只框横线主体，数字单独由 OCR 处理。</p>
        </article>
        <aside className="space-y-4">
          <section className="rounded-3xl border bg-white p-5 dark:border-slate-800 dark:bg-slate-900"><h2 className="text-lg font-bold">标注操作</h2><div className="mt-4 grid gap-2"><button disabled={!selected.prelabel || busy} onClick={acceptPrelabel} className="button-primary w-full"><Check size={16}/>接受 OMR 预标</button><button disabled={busy} onClick={() => setDrawMode(value => !value)} className={`button-secondary w-full ${drawMode ? 'border-blue-500 text-blue-600' : ''}`}><BoxSelect size={16}/>{drawMode ? '请在谱面上拖出目标框' : '新增目标框'}</button></div>
            {active && <div className="mt-5 space-y-4 rounded-2xl bg-slate-50 p-4 dark:bg-slate-950"><div className="flex items-center justify-between"><strong className="text-sm">目标框 {activeTarget + 1}</strong><button className="text-red-500" onClick={() => { setTargets(current => current.filter((_, index) => index !== activeTarget)); setActiveTarget(0); }}><Trash2 size={17}/></button></div><label className="block text-sm font-semibold">类别<select value={active.class} onChange={event => setTarget({ class: event.target.value })} className="mt-2 min-h-11 w-full border bg-transparent px-3">{queue?.classes.map(value => <option key={value} value={value}>{classLabels[value] || value}</option>)}</select></label><label className="block text-sm font-semibold">附点数<select value={active.dots} onChange={event => setTarget({ dots: Number(event.target.value) })} className="mt-2 min-h-11 w-full border bg-transparent px-3">{[0,1,2,3].map(value => <option key={value} value={value}>{value}</option>)}</select></label><div className="grid grid-cols-2 gap-2">{active.bboxXyxy.map((value, index) => <label key={index} className="text-xs text-slate-500">{['左 X','上 Y','右 X','下 Y'][index]}<input type="number" step="0.1" value={value} onChange={event => { const box = [...active.bboxXyxy]; box[index] = Number(event.target.value); setTarget({ bboxXyxy: box }); }} className="mt-1 w-full border bg-transparent px-2 py-2 text-slate-900 dark:text-white"/></label>)}</div></div>}
            <div className="mt-4 grid gap-2"><button disabled={!targets.length || busy} onClick={() => void save('corrected')} className="button-primary w-full"><Check size={16}/>保存人工修正</button><button disabled={busy} onClick={() => void save('rejected', [])} className="button-secondary w-full text-amber-600"><X size={16}/>此裁片没有休止符</button><button disabled={busy} onClick={() => void save('skipped', [])} className="button-secondary w-full"><SkipForward size={16}/>暂时无法判断</button></div><label className="mt-4 block text-sm font-semibold">跳过原因 / 备注<textarea value={reason} onChange={event => setReason(event.target.value)} className="mt-2 min-h-20 w-full border bg-transparent p-3 font-normal" placeholder="例如：扫描模糊、框内有多个声部…"/></label><button onClick={() => { setTargets(cloneTargets(selected.prelabel ? [selected.prelabel] : [])); setReason(''); }} className="mt-2 inline-flex items-center gap-2 text-sm text-slate-500"><RotateCcw size={14}/>恢复预标</button></section>
          <section className="rounded-3xl border bg-white p-5 text-sm leading-6 dark:border-slate-800 dark:bg-slate-900"><h2 className="font-bold">时间轴证据</h2><dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-slate-500"><dt>起点</dt><dd>{selected.onset || '未知'}</dd><dt>时值</dt><dd>{selected.duration || '未知'}</dd><dt>位置</dt><dd>{selected.position || '未知'}</dd><dt>OMR 状态</dt><dd>{selected.classificationStatus || '无候选'}</dd></dl></section>
        </aside>
      </div>}
    <div className="mt-6 flex items-center justify-between text-sm text-slate-500"><span>{queue ? `${queue.offset + (queue.items.length ? 1 : 0)}–${pageEnd} / ${queue.filteredTotal}` : '0 / 0'}</span><div className="flex gap-2"><button disabled={!queue || queue.offset === 0 || busy} onClick={() => setOffset(Math.max(0, offset - 24))} className="button-secondary px-4">上一页</button><button disabled={!queue || pageEnd >= queue.filteredTotal || busy} onClick={() => setOffset(offset + 24)} className="button-secondary px-4">下一页</button></div></div>
  </section>;
}
