import { BoxSelect, Check, Download, RefreshCw, RotateCcw, SkipForward, Trash2, X } from 'lucide-react';
import { PointerEvent, useEffect, useMemo, useRef, useState } from 'react';
import { apiRequest } from '../services/api';

type AnnotationState = 'unreviewed' | 'accepted' | 'corrected' | 'rejected' | 'skipped';
type Target = { class: string; bboxXyxy: number[]; dots: number; text?: string };
type Sample = {
  sampleId: string; imageUrl: string; imageWidth: number; imageHeight: number;
  documentSha256: string; gapId: string; measureId?: string; page?: number;
  voice?: string; onset?: string; duration?: string; position?: string;
  imageSource?: string; classificationStatus?: string;
  prelabel?: Target & { grade?: number; contextGrade?: number; source?: string };
  prelabels?: Array<Target & { grade?: number; contextGrade?: number; source?: string }>;
  taskType?: 'rest' | 'structure';
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
  barline: '小节线', measure_number: '行首小节号',
  multi_measure_rest_number: '多小节休止数字', rehearsal_mark: '排练标记',
  time_signature: '拍号', staff_system: '完整谱表区域',
};
const classDescriptions: Record<string, string> = {
  maxima_rest: '极少见的八全休止符，只在原谱明确出现这种古老长休止符时选择。',
  long_rest: '四全休止符，只框休止符主体。',
  breve_rest: '二全休止符，只框休止符主体。',
  whole_rest: '悬挂在谱线下方的矩形全休止符；整小节休止也通常使用它。',
  half_rest: '放在谱线上方的矩形二分休止符。',
  quarter_rest: '四分休止符，只框锯齿状主体。',
  eighth_rest: '八分休止符，包含完整符干和一个符尾。',
  '16th_rest': '十六分休止符，包含完整符干和两个符尾。',
  '32nd_rest': '三十二分休止符，包含完整符干和三个符尾。',
  '64th_rest': '六十四分休止符，包含完整符干和四个符尾。',
  '128th_rest': '一百二十八分休止符，包含完整符干和五个符尾。',
  multi_measure_rest: '连续休止多小节的粗横线或专用符号；上方数字要另建目标框。',
  barline: '分隔相邻小节的竖线；双线或终止线作为一个完整目标框。',
  measure_number: '通常位于一行谱左上方的小节序号，并在“框内文字”填写数字。',
  multi_measure_rest_number: '位于多小节休止符上方的计数数字，并填写数字内容。',
  rehearsal_mark: '方框或圆圈中的 A、B、C、数字等排练标记，并填写框内文字。',
  time_signature: '如 4/4、3/4、6/8 或 C 拍号，框住完整拍号并填写内容。',
  staff_system: '框住当前完整谱表行，包括五线和该行左右边界；仅用于谱表结构样本。',
};

const restClasses = new Set([
  'maxima_rest', 'long_rest', 'breve_rest', 'whole_rest', 'half_rest',
  'quarter_rest', 'eighth_rest', '16th_rest', '32nd_rest', '64th_rest',
  '128th_rest', 'multi_measure_rest',
]);
const textClasses = new Set(['measure_number', 'multi_measure_rest_number', 'rehearsal_mark', 'time_signature']);

function cloneTargets(targets: Target[] | undefined) {
  return (targets || []).map(target => ({
    class: target.class, bboxXyxy: [...target.bboxXyxy], dots: target.dots || 0,
    ...(target.text ? { text: target.text } : {}),
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
    const prelabels = selected.prelabels?.length ? selected.prelabels : selected.prelabel ? [selected.prelabel] : [];
    setTargets(cloneTargets(saved?.length ? saved : prelabels));
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
    const prelabels = selected?.prelabels?.length ? selected.prelabels : selected?.prelabel ? [selected.prelabel] : [];
    if (!prelabels.length) { setNotice('该样本没有可接受的预标框，请手工画框'); return; }
    const accepted = cloneTargets(prelabels); setTargets(accepted); void save('accepted', accepted);
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
      <div><p className="eyebrow">SCORE STRUCTURE DATA</p><h1 className="text-3xl font-black">乐谱结构训练标注</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">样本包含节奏缺口、休止符候选和完整谱表裁片。每个休止符、小节线、行首号、多小节休止数字、排练标记和拍号都要单独标框；绿色框只是几何或 OMR 预标，人工确认后才进入训练。</p></div>
      <div className="flex flex-wrap gap-2"><button disabled={busy} onClick={() => void refresh()} className="button-secondary"><RefreshCw size={16}/>{busy ? '处理中…' : '刷新样本'}</button><a href="/api/admin/rest-annotations/export" className="button-primary"><Download size={16}/>导出 COCO</a></div>
    </div>
    <div className="mt-6 grid gap-3 sm:grid-cols-3">
      {[['样本总数', allCount], ['可训练样本', reviewedProgress], ['待人工标注', queue?.counts.unreviewed || 0]].map(([label, value]) => <article key={label} className="rounded-2xl border bg-white p-5 dark:border-slate-800 dark:bg-slate-900"><p className="text-sm text-slate-500">{label}</p><strong className="mt-1 block text-3xl">{value}</strong></article>)}
    </div>
    <div className="mt-5 flex flex-wrap gap-2">{['unreviewed','accepted','corrected','rejected','skipped','all'].map(value => <button key={value} onClick={() => { setFilter(value); setOffset(0); }} className={`rounded-full px-4 py-2 text-sm font-semibold ${filter === value ? 'bg-blue-600 text-white' : 'border bg-white dark:bg-slate-900'}`}>{stateLabels[value]} {value !== 'all' && queue ? queue.counts[value as AnnotationState] : ''}</button>)}</div>
    <details className="mt-5 rounded-2xl border bg-white p-4 text-sm dark:border-slate-800 dark:bg-slate-900">
      <summary className="cursor-pointer font-bold">标注哪些内容？点击查看类别说明</summary>
      <div className="mt-4 grid gap-4 leading-6 text-slate-600 md:grid-cols-2 dark:text-slate-300">
        <div><strong className="text-slate-900 dark:text-white">休止符</strong><p>全休止、二分、四分、八分、十六分及更短休止符都要分别框住；附点不单独画框，在“附点数”中选择。罕见的二全、四全、八全休止符只在原谱明确出现时使用。</p></div>
        <div><strong className="text-slate-900 dark:text-white">多小节休止</strong><p>粗横线或专用休止符标为“多小节休止”；上方计数数字另画一个框，选择“多小节休止数字”并填写数字。</p></div>
        <div><strong className="text-slate-900 dark:text-white">小节结构</strong><p>标注每个小节线；双小节线和终止线用一个框包住整个符号。行首小节号、排练标记、拍号分别框住，并填写框内文字。</p></div>
        <div><strong className="text-slate-900 dark:text-white">无需标注</strong><p>音符、谱号、调号、力度、连线、重音和延长记号目前不标；看不见的休止符也不要推测添加。完整谱表区域只在“谱表结构”样本中使用。</p></div>
      </div>
    </details>
    {notice && <p className="mt-4 rounded-xl border border-blue-400/30 bg-blue-500/10 px-4 py-3 text-sm text-blue-700 dark:text-blue-300">{notice}</p>}
    {!selected ? <div className="mt-6 rounded-3xl border bg-white p-14 text-center text-slate-500 dark:bg-slate-900">{allCount ? '这个筛选条件下没有样本。' : '还没有标注样本。点击“刷新样本”，从服务器已有乐谱任务生成裁片。'}</div> :
      <div className="mt-6 grid gap-5 xl:grid-cols-[minmax(0,1.65fr)_minmax(340px,.7fr)]">
        <article className="overflow-hidden rounded-3xl border bg-white dark:border-slate-800 dark:bg-slate-900">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4 dark:border-slate-800"><div><strong>第 {selected.page || '?'} 页 · {selected.taskType === 'structure' ? '谱表结构' : selected.measureId || '未知小节'} · 声部 {selected.voice || '?'}</strong><p className="mt-1 text-xs text-slate-500">文档 {selected.documentSha256?.slice(0, 12)}… · {selected.taskType === 'structure' ? '结构检测裁片' : `缺口 ${selected.duration || '?'}`} · {selected.imageSource === 'audiveris_binary' ? 'OMR 二值图' : '原 PDF 高清裁片'}</p></div><span className="tag">{stateLabels[selected.state]}</span></div>
          <div className="relative m-4 overflow-hidden rounded-2xl border bg-white shadow-inner" style={{ aspectRatio: `${selected.imageWidth}/${selected.imageHeight}` }}>
            <img src={selected.imageUrl} alt="待标注休止符局部谱面" className="absolute inset-0 h-full w-full select-none object-contain" draggable={false}/>
            <svg viewBox={`0 0 ${selected.imageWidth} ${selected.imageHeight}`} className={`absolute inset-0 h-full w-full touch-none ${drawMode ? 'cursor-crosshair' : 'cursor-default'}`} onPointerDown={startDraw} onPointerMove={moveDraw} onPointerUp={finishDraw} onPointerCancel={finishDraw}>
              {boxes.map((box, index) => <g key={`${index}-${box.join('-')}`} onPointerDown={event => { if (!drawMode && index < targets.length) { event.stopPropagation(); setActiveTarget(index); } }}><rect x={box[0]} y={box[1]} width={box[2]-box[0]} height={box[3]-box[1]} fill={index === activeTarget ? 'rgba(10,132,255,.14)' : 'rgba(52,199,89,.10)'} stroke={index === activeTarget ? '#0a84ff' : '#22c55e'} strokeWidth={Math.max(2, selected.imageWidth / 320)} vectorEffect="non-scaling-stroke"/><text x={box[0]} y={Math.max(12, box[1]-4)} fill={index === activeTarget ? '#0a84ff' : '#15803d'} fontSize={Math.max(12, selected.imageWidth / 34)} fontWeight="700">{index + 1}</text></g>)}
            </svg>
          </div>
          <p className="px-5 pb-5 text-xs leading-5 text-slate-500">框要紧贴目标主体并保留少量边缘。多小节休止横线和上方数字必须分别标框；行首号、排练标记和拍号还要填写框内文字。</p>
        </article>
        <aside className="space-y-4">
          <section className="rounded-3xl border bg-white p-5 dark:border-slate-800 dark:bg-slate-900"><h2 className="text-lg font-bold">标注操作</h2><div className="mt-4 grid gap-2"><button disabled={!(selected.prelabels?.length || selected.prelabel) || busy} onClick={acceptPrelabel} className="button-primary w-full"><Check size={16}/>接受全部预标</button><button disabled={busy} onClick={() => setDrawMode(value => !value)} className={`button-secondary w-full ${drawMode ? 'border-blue-500 text-blue-600' : ''}`}><BoxSelect size={16}/>{drawMode ? '请在谱面上拖出目标框' : '新增目标框'}</button></div>
            {active && <div className="mt-5 space-y-4 rounded-2xl bg-slate-50 p-4 dark:bg-slate-950">
              <div className="flex items-center justify-between"><strong className="text-sm">目标框 {activeTarget + 1}</strong><button className="text-red-500" onClick={() => { setTargets(current => current.filter((_, index) => index !== activeTarget)); setActiveTarget(0); }}><Trash2 size={17}/></button></div>
              <label className="block text-sm font-semibold">类别<select value={active.class} onChange={event => setTarget({ class: event.target.value, dots: restClasses.has(event.target.value) ? active.dots : 0, text: textClasses.has(event.target.value) ? active.text : undefined })} className="mt-2 min-h-11 w-full border bg-white px-3 text-slate-900 dark:bg-slate-950 dark:text-white">{queue?.classes.map(value => <option className="bg-white text-slate-900 dark:bg-slate-950 dark:text-white" key={value} value={value}>{classLabels[value] || value}</option>)}</select><span className="mt-2 block text-xs font-normal leading-5 text-slate-500">{classDescriptions[active.class]}</span></label>
              {restClasses.has(active.class) && <label className="block text-sm font-semibold">附点数<select value={active.dots} onChange={event => setTarget({ dots: Number(event.target.value) })} className="mt-2 min-h-11 w-full border bg-white px-3 text-slate-900 dark:bg-slate-950 dark:text-white">{[0,1,2,3].map(value => <option className="bg-white text-slate-900 dark:bg-slate-950 dark:text-white" key={value} value={value}>{value}</option>)}</select></label>}
              {textClasses.has(active.class) && <label className="block text-sm font-semibold">框内文字<input value={active.text || ''} maxLength={24} onChange={event => setTarget({ text: event.target.value })} className="mt-2 min-h-11 w-full border bg-transparent px-3" placeholder="例如：23、A、3/4"/></label>}
              <div className="grid grid-cols-2 gap-2">{active.bboxXyxy.map((value, index) => <label key={index} className="text-xs text-slate-500">{['左 X','上 Y','右 X','下 Y'][index]}<input type="number" step="0.1" value={value} onChange={event => { const box = [...active.bboxXyxy]; box[index] = Number(event.target.value); setTarget({ bboxXyxy: box }); }} className="mt-1 w-full border bg-transparent px-2 py-2 text-slate-900 dark:text-white"/></label>)}</div>
            </div>}
            <div className="mt-4 grid gap-2"><button disabled={!targets.length || busy} onClick={() => void save('corrected')} className="button-primary w-full"><Check size={16}/>保存人工修正</button><button disabled={busy} onClick={() => void save('rejected', [])} className="button-secondary w-full text-amber-600"><X size={16}/>此裁片没有目标</button><button disabled={busy} onClick={() => void save('skipped', [])} className="button-secondary w-full"><SkipForward size={16}/>暂时无法判断</button></div><label className="mt-4 block text-sm font-semibold">跳过原因 / 备注<textarea value={reason} onChange={event => setReason(event.target.value)} className="mt-2 min-h-20 w-full border bg-transparent p-3 font-normal" placeholder="例如：扫描模糊、多个谱表重叠…"/></label><button onClick={() => { const prelabels = selected.prelabels?.length ? selected.prelabels : selected.prelabel ? [selected.prelabel] : []; setTargets(cloneTargets(prelabels)); setReason(''); }} className="mt-2 inline-flex items-center gap-2 text-sm text-slate-500"><RotateCcw size={14}/>恢复预标</button></section>
          <section className="rounded-3xl border bg-white p-5 text-sm leading-6 dark:border-slate-800 dark:bg-slate-900"><h2 className="font-bold">时间轴证据</h2><dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-slate-500"><dt>起点</dt><dd>{selected.onset || '未知'}</dd><dt>时值</dt><dd>{selected.duration || '未知'}</dd><dt>位置</dt><dd>{selected.position || '未知'}</dd><dt>OMR 状态</dt><dd>{selected.classificationStatus || '无候选'}</dd></dl></section>
        </aside>
      </div>}
    <div className="mt-6 flex items-center justify-between text-sm text-slate-500"><span>{queue ? `${queue.offset + (queue.items.length ? 1 : 0)}–${pageEnd} / ${queue.filteredTotal}` : '0 / 0'}</span><div className="flex gap-2"><button disabled={!queue || queue.offset === 0 || busy} onClick={() => setOffset(Math.max(0, offset - 24))} className="button-secondary px-4">上一页</button><button disabled={!queue || pageEnd >= queue.filteredTotal || busy} onClick={() => setOffset(offset + 24)} className="button-secondary px-4">下一页</button></div></div>
  </section>;
}
