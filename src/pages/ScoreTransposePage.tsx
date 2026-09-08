import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  Download,
  FileMusic,
  Files,
  FileText,
  Gauge,
  Loader2,
  Music2,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  UploadCloud,
} from 'lucide-react';
import { ChangeEvent, DragEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Reveal } from '../components/Reveal';
import { ScoreEditor } from '../components/ScoreEditor';
import { useToast } from '../components/Toast';
import { useLanguage } from '../context/LanguageContext';
import { useSound } from '../hooks/useSound';
import { transposeScore, waitForScore, type ScoreTransposeResult } from '../services/scoreTransposeService';
import { formatPageSelection, MAX_SCORE_SELECTED_PAGES, MAX_SCORE_SOURCE_PAGES, parsePageSelection, readPdfPageCount } from '../utils/pdfPages';

type Instrument = {
  id: string;
  zh: string;
  en: string;
  offset: number;
};

type TaskState = 'idle' | 'processing' | 'needs_review' | 'completed' | 'failed';
type TransposeMode = 'instrument' | 'custom';
type PageSelectionMode = 'all' | 'custom';

const instruments: Instrument[] = [
  { id: 'concert_c', zh: 'C 调乐器 / 原调', en: 'Concert C', offset: 0 },
  { id: 'piccolo', zh: '短笛', en: 'Piccolo', offset: 12 },
  { id: 'clarinet_a', zh: 'A 调单簧管', en: 'A Clarinet', offset: -3 },
  { id: 'clarinet_bb', zh: '降 B 调单簧管', en: 'Bb Clarinet', offset: -2 },
  { id: 'bass_clarinet_bb', zh: '降 B 调低音单簧管', en: 'Bb Bass Clarinet', offset: -14 },
  { id: 'trumpet_bb', zh: '降 B 调小号', en: 'Bb Trumpet', offset: -2 },
  { id: 'soprano_sax_bb', zh: '降 B 调高音萨克斯', en: 'Bb Soprano Sax', offset: -2 },
  { id: 'tenor_sax_bb', zh: '降 B 调次中音萨克斯', en: 'Bb Tenor Sax', offset: -14 },
  { id: 'sax_eb', zh: '降 E 调中音萨克斯', en: 'Eb Alto Sax', offset: -9 },
  { id: 'baritone_sax_eb', zh: '降 E 调上低音萨克斯', en: 'Eb Baritone Sax', offset: -21 },
  { id: 'horn_f', zh: 'F 调圆号', en: 'F Horn', offset: -7 },
  { id: 'english_horn_f', zh: 'F 调英国管', en: 'English Horn', offset: -7 },
];

const stages = [
  { id: 'queued', zh: '等待处理', en: 'Queued' },
  { id: 'inspecting', zh: '检查原谱', en: 'Inspect score' },
  { id: 'recognizing', zh: '读取音符', en: 'Read notation' },
  { id: 'source_repair', zh: '修复源谱', en: 'Repair source' },
  { id: 'transposing', zh: '音高转调', en: 'Transpose' },
  { id: 'rendering', zh: '生成 PDF', en: 'Generate PDF' },
  { id: 'verifying', zh: '核对结果', en: 'Verify result' },
  { id: 'completed', zh: '完成', en: 'Complete' },
];

const ACTIVE_JOB_KEY = 'score-transpose-active-job';

function formatSize(size: number) {
  if (size > 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(size / 1024))} KB`;
}

function shiftLabel(value: number, en: boolean) {
  if (value === 0) return en ? '0 semitones' : '0 半音';
  return en ? `${value > 0 ? '+' : ''}${value} semitones` : `${value > 0 ? '+' : ''}${value} 半音`;
}

function documentTypeLabel(value: string | undefined, en: boolean) {
  if (value === 'vector') return en ? 'Vector PDF' : '电子矢量谱';
  if (value === 'scan') return en ? 'Scanned PDF' : '扫描乐谱';
  if (value === 'mixed') return en ? 'Mixed PDF' : '混合型 PDF';
  return '-';
}

function SelectField({
  label,
  value,
  onChange,
  children,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs font-bold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
        {label}
      </span>
      <span className="relative block">
        <select
          disabled={disabled}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="h-12 w-full appearance-none rounded-xl border border-[rgb(var(--line))] bg-[rgb(var(--surface))] px-3.5 pr-10 text-sm font-semibold outline-none transition focus:border-blue-500"
        >
          {children}
        </select>
        <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" size={17} />
      </span>
    </label>
  );
}

export default function ScoreTransposePage() {
  const { language } = useLanguage();
  const { play } = useSound();
  const toast = useToast();
  const en = language === 'en';
  const [file, setFile] = useState<File | null>(null);
  const [fileUrl, setFileUrl] = useState('');
  const [pdfPageCount, setPdfPageCount] = useState<number | null>(null);
  const [pageCountLoading, setPageCountLoading] = useState(false);
  const [pageCountError, setPageCountError] = useState('');
  const [pageSelectionMode, setPageSelectionMode] = useState<PageSelectionMode>('all');
  const [pageRange, setPageRange] = useState('');
  const [source, setSource] = useState('clarinet_a');
  const [target, setTarget] = useState('clarinet_bb');
  const [transposeMode, setTransposeMode] = useState<TransposeMode>('instrument');
  const [customSemitones, setCustomSemitones] = useState(-1);
  const [accidental, setAccidental] = useState('auto');
  const [taskState, setTaskState] = useState<TaskState>('idle');
  const [stageIndex, setStageIndex] = useState(0);
  const [result, setResult] = useState<ScoreTransposeResult | null>(null);
  const [errorMessage, setErrorMessage] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const uploadRef = useRef<AbortController | null>(null);
  const pageReadIdRef = useRef(0);
  const [activeJob, setActiveJob] = useState<string | null>(() => window.sessionStorage.getItem(ACTIVE_JOB_KEY));
  const [progress, setProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState('');
  const [editorOpen, setEditorOpen] = useState(false);
  const [previousVersions, setPreviousVersions] = useState<ScoreTransposeResult[]>([]);
  const availablePdf = result?.outputAllowed ? result.outputUrl : result?.candidateUrl;
  const originalPdf = result?.originalUrl || fileUrl;

  const sourceInstrument = instruments.find((item) => item.id === source) ?? instruments[0];
  const targetInstrument = instruments.find((item) => item.id === target) ?? instruments[1];
  const semitoneShift = transposeMode === 'custom' ? customSemitones : sourceInstrument.offset - targetInstrument.offset;
  const displayedMode = result?.transposition?.mode ?? result?.summary?.transposeMode ?? transposeMode;
  const displayedSource = instruments.find((item) => item.id === (result?.transposition?.sourceInstrument ?? result?.summary?.sourceInstrument ?? source)) ?? sourceInstrument;
  const displayedTarget = instruments.find((item) => item.id === (result?.transposition?.targetInstrument ?? result?.summary?.targetInstrument ?? target)) ?? targetInstrument;
  const displayedShift = result?.transposition?.semitones ?? result?.summary?.semitones ?? semitoneShift;
  const displayedTitle = displayedMode === 'custom'
    ? (en ? 'Custom shift' : '自定义转调')
    : `${en ? displayedSource.en : displayedSource.zh} → ${en ? displayedTarget.en : displayedTarget.zh}`;
  const parsedPageSelection = useMemo(
    () => pageSelectionMode === 'custom' && pdfPageCount ? parsePageSelection(pageRange, pdfPageCount, en) : { pages: [], error: '' },
    [en, pageRange, pageSelectionMode, pdfPageCount],
  );
  const selectedPageCount = pageSelectionMode === 'all' ? (pdfPageCount ?? 0) : parsedPageSelection.pages.length;
  const pageSelectionInvalid = Boolean(
    file && (pageCountLoading || pageCountError || !pdfPageCount ||
      (pageSelectionMode === 'all' ? pdfPageCount > MAX_SCORE_SELECTED_PAGES : parsedPageSelection.error)),
  );

  useEffect(() => {
    if (!file) {
      setFileUrl('');
      return;
    }
    const url = URL.createObjectURL(file);
    setFileUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => () => uploadRef.current?.abort(), []);

  useEffect(() => {
    if (!activeJob) return;
    const controller = new AbortController();
    setTaskState('processing');
    void waitForScore(activeJob, (job) => {
      setProgress(job.progress ?? 0);
      setStatusMessage(job.message ?? '');
      const index = stages.findIndex((stage) => stage.id === job.stage);
      if (index >= 0) setStageIndex(index);
    }, controller.signal).then((nextResult) => {
      if (controller.signal.aborted) return;
      setResult(nextResult);
      setTaskState(nextResult.status === 'failed' ? 'failed' : nextResult.outputAllowed ? 'completed' : 'needs_review');
      setProgress(100);
      if (nextResult.outputAllowed) setStageIndex(stages.length - 1);
      setErrorMessage(nextResult.outputAllowed ? '' : nextResult.message ?? '结果需要复核');
      window.sessionStorage.removeItem(ACTIVE_JOB_KEY);
      setActiveJob(null);
    }).catch((error: unknown) => {
      if (controller.signal.aborted) return;
      setErrorMessage(error instanceof Error ? error.message : '任务状态读取失败，请刷新页面重试。');
      setTaskState('failed');
      setActiveJob(null);
    });
    return () => controller.abort();
  }, [activeJob]);

  const fileMessage = useMemo(() => {
    if (!file) return en ? 'PDF scores, up to 500 pages and 25 MB; select up to 20 pages per task.' : 'PDF 乐谱最多 500 页、25 MB；每次可选择转换其中最多 20 页。';
    const pages = pdfPageCount ? ` · ${pdfPageCount} ${en ? 'pages' : '页'}` : '';
    return `${file.name} · ${formatSize(file.size)}${pages}`;
  }, [en, file, pdfPageCount]);

  const acceptFile = (nextFile?: File) => {
    if (!nextFile || taskState === 'processing') return;
    if (nextFile.type !== 'application/pdf' && !nextFile.name.toLowerCase().endsWith('.pdf')) {
      play('error');
      toast(en ? 'Please upload a PDF score.' : '请上传 PDF 乐谱。', 'error');
      return;
    }
    if (nextFile.size > 25 * 1024 * 1024) {
      play('error');
      toast(en ? 'The file is larger than 25 MB.' : '文件超过 25 MB。', 'error');
      return;
    }
    setFile(nextFile);
    setPdfPageCount(null);
    setPageCountError('');
    setPageSelectionMode('all');
    setPageRange('');
    setPageCountLoading(true);
    const readId = ++pageReadIdRef.current;
    void readPdfPageCount(nextFile).then((count) => {
      if (readId !== pageReadIdRef.current) return;
      if (count < 1 || count > MAX_SCORE_SOURCE_PAGES) {
        throw new Error(en ? `PDFs must contain 1–${MAX_SCORE_SOURCE_PAGES} pages.` : `PDF 页数必须在 1–${MAX_SCORE_SOURCE_PAGES} 页之间。`);
      }
      setPdfPageCount(count);
      if (count > MAX_SCORE_SELECTED_PAGES) {
        setPageSelectionMode('custom');
        setPageRange(`1-${MAX_SCORE_SELECTED_PAGES}`);
      }
    }).catch((error: unknown) => {
      if (readId !== pageReadIdRef.current) return;
      setPageCountError(error instanceof Error ? error.message : (en ? 'Unable to read this PDF.' : '无法读取这份 PDF。'));
    }).finally(() => {
      if (readId === pageReadIdRef.current) setPageCountLoading(false);
    });
    setTaskState('idle');
    setStageIndex(0);
    setResult(null);
    setEditorOpen(false);
    setPreviousVersions([]);
    setErrorMessage('');
    setProgress(0);
    setStatusMessage('');
    play('click');
  };

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    acceptFile(event.target.files?.[0]);
    event.target.value = '';
  };

  const onDrop = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    acceptFile(event.dataTransfer.files?.[0]);
  };

  const startTask = async () => {
    if (!file) {
      toast(en ? 'Upload a PDF first.' : '请先上传 PDF。', 'error');
      play('error');
      return;
    }
    if (pageSelectionInvalid || !pdfPageCount) {
      const message = pageCountError || parsedPageSelection.error || (en ? 'Wait until the PDF page count is ready.' : '请先完成 PDF 页数读取并正确选择页码。');
      toast(message, 'error');
      play('error');
      return;
    }
    setTaskState('processing');
    setStageIndex(0);
    setProgress(1);
    setStatusMessage(en ? 'Uploading PDF…' : '正在上传 PDF…');
    setResult(null);
    setErrorMessage('');
    play('transition');
    const controller = new AbortController();
    uploadRef.current = controller;
    try {
      const nextResult = await transposeScore({
        file,
        transposeMode,
        sourceInstrument: source,
        targetInstrument: target,
        semitones: transposeMode === 'custom' ? customSemitones : undefined,
        accidentalPreference: accidental,
        pageSelectionMode,
        selectedPages: pageSelectionMode === 'custom' ? parsedPageSelection.pages : undefined,
      }, controller.signal);
      if (controller.signal.aborted) return;
      if (nextResult.status === 'queued' || nextResult.status === 'processing') {
        window.sessionStorage.setItem(ACTIVE_JOB_KEY, nextResult.jobId);
        setActiveJob(nextResult.jobId);
      } else {
        setResult(nextResult as ScoreTransposeResult);
        setTaskState(nextResult.outputAllowed ? 'completed' : 'needs_review');
        setProgress(100);
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      const message = error instanceof Error ? error.message : en ? 'Transposition failed.' : '转调失败。';
      setErrorMessage(message);
      setTaskState('failed');
      play('error');
      toast(message, 'error');
    }
  };

  const resetTask = () => {
    uploadRef.current?.abort();
    setActiveJob(null);
    window.sessionStorage.removeItem(ACTIVE_JOB_KEY);
    setProgress(0);
    setStatusMessage('');
    setTaskState('idle');
    setStageIndex(0);
    setResult(null);
    setErrorMessage('');
    play('panelClose');
  };

  const clearFile = () => {
    pageReadIdRef.current += 1;
    setFile(null);
    setPdfPageCount(null);
    setPageCountLoading(false);
    setPageCountError('');
    setPageSelectionMode('all');
    setPageRange('');
    resetTask();
  };

  const downloadResult = () => {
    if (!result || !availablePdf) return;
    const link = document.createElement('a');
    link.href = availablePdf;
    link.download = (result.outputAllowed ? '' : '待校对-') + (result.fileName || 'transposed-score.pdf');
    link.click();
    play('success');
  };

  return (
    <div className="min-h-screen overflow-hidden pb-24 pt-24">
      <section className="relative border-b border-[rgb(var(--line))] bg-[rgb(var(--surface))]">
        <div className="absolute inset-0 bg-[linear-gradient(120deg,rgba(49,87,213,0.10),transparent_42%,rgba(20,184,166,0.12))]" />
        <div className="container-site relative grid min-h-[calc(100vh-4rem)] items-center gap-10 py-12 lg:grid-cols-[0.92fr_1.08fr]">
          <Reveal>
            <p className="eyebrow">{en ? 'SCORE TRANSPOSITION' : '乐谱转调工作台'}</p>
            <h1 className="max-w-3xl text-4xl font-black leading-tight tracking-[-0.04em] sm:text-6xl">
              {en ? 'Upload a score PDF, choose the transposition, download your new part.' : '上传乐谱 PDF，选择转调，下载新谱。'}
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-8 text-slate-600 dark:text-slate-300">
              {en
                ? 'Preserve the original layout where possible. Download a candidate PDF with review notes, and correct note pitches online.'
                : '优先保留原谱分页、编号、节奏和演奏标记。可下载待校对的候选 PDF 和问题清单，也可在线修改音高后生成新版。'}
            </p>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-500 dark:text-slate-400">
              {en
                ? 'Transpose by instrument or by up to 48 semitones in either direction. Checks cover measures, pitch, rhythm and page breaks; uncertain results include specific review notes.'
                : '按乐器或自定义半音转调，支持上下 48 个半音。系统检查小节、音高、节奏和分页，无法确认的内容会列出复核原因。'}
            </p>
            <div className="mt-7 grid gap-3 sm:grid-cols-3">
              {[
                [en ? 'Input' : '输入', en ? 'PDF score' : 'PDF 乐谱'],
                [en ? 'Mode' : '模式', en ? 'Instrument or custom' : '乐器或自定义半音'],
                [en ? 'Output' : '输出', en ? 'Downloadable PDF' : '可下载 PDF'],
              ].map(([label, value]) => (
                <div key={label} className="rounded-2xl border border-[rgb(var(--line))] bg-[rgb(var(--page))]/70 p-4">
                  <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">{label}</p>
                  <p className="mt-2 text-sm font-black">{value}</p>
                </div>
              ))}
            </div>
          </Reveal>

          <Reveal className="surface rounded-[1.75rem] p-4 sm:p-5">
            <div className="grid gap-4">
              <button
                type="button"
                disabled={taskState === 'processing'}
                onClick={() => inputRef.current?.click()}
                onDragOver={(event) => event.preventDefault()}
                onDrop={onDrop}
                className="group grid min-h-52 place-items-center rounded-2xl border border-dashed border-blue-300/80 bg-blue-50/70 p-6 text-center transition hover:border-blue-500 hover:bg-blue-50 dark:border-blue-400/30 dark:bg-blue-400/10"
              >
                <input ref={inputRef} type="file" accept="application/pdf,.pdf" onChange={onFileChange} className="hidden" />
                <span className="grid h-16 w-16 place-items-center rounded-2xl bg-white text-accent shadow-soft transition group-hover:-translate-y-1 dark:bg-slate-900">
                  <UploadCloud size={28} />
                </span>
                <span className="mt-4 block text-lg font-black">{en ? 'Drop score PDF here' : '拖入乐谱 PDF'}</span>
                <span className="mt-2 block text-sm text-slate-500 dark:text-slate-300">{fileMessage}</span>
              </button>

              <div className="grid grid-cols-2 gap-2 rounded-2xl bg-[rgb(var(--page))] p-1">
                {[
                  ['instrument', en ? 'Instrument' : '按乐器'],
                  ['custom', en ? 'Custom' : '自定义半音'],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    disabled={taskState === 'processing'}
                    onClick={() => {
                      setTransposeMode(value as TransposeMode);
                      play('click');
                    }}
                    className={`h-11 rounded-xl text-sm font-black transition ${
                      transposeMode === value ? 'bg-[rgb(var(--surface))] text-accent shadow-soft' : 'text-slate-500'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {transposeMode === 'instrument' ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  <SelectField disabled={taskState === 'processing'} label={en ? 'Source instrument' : '原乐器 / 原谱记谱'} value={source} onChange={setSource}>
                    {instruments.map((item) => (
                      <option key={item.id} value={item.id}>
                        {en ? item.en : item.zh}
                      </option>
                    ))}
                  </SelectField>
                  <SelectField disabled={taskState === 'processing'} label={en ? 'Target instrument' : '目标乐器 / 新谱记谱'} value={target} onChange={setTarget}>
                    {instruments.map((item) => (
                      <option key={item.id} value={item.id}>
                        {en ? item.en : item.zh}
                      </option>
                    ))}
                  </SelectField>
                </div>
              ) : (
                <label className="block">
                  <span className="mb-2 block text-xs font-bold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                    {en ? 'Semitone shift' : '转调半音数'}
                  </span>
                  <input
                    type="number"
                    disabled={taskState === 'processing'}
                    min={-48}
                    max={48}
                    step={1}
                    value={customSemitones}
                    onChange={(event) => setCustomSemitones(Math.max(-48, Math.min(48, Math.trunc(Number(event.target.value)) || 0)))}
                    className="h-12 w-full rounded-xl border border-[rgb(var(--line))] bg-[rgb(var(--surface))] px-3.5 text-sm font-semibold outline-none transition focus:border-blue-500"
                  />
                </label>
              )}

              <div className="grid gap-3 lg:grid-cols-[1fr_auto_1fr]">
                <div className="rounded-2xl border border-[rgb(var(--line))] p-4">
                  <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-500">{en ? 'Mode' : '转调模式'}</p>
                  <p className="mt-2 text-2xl font-black">{transposeMode === 'custom' ? (en ? 'Custom' : '自定义') : en ? 'Instrument' : '按乐器'}</p>
                </div>
                <div className="hidden place-items-center text-slate-400 lg:grid">
                  <ArrowRight size={24} />
                </div>
                <div className="rounded-2xl border border-[rgb(var(--line))] p-4">
                  <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-500">{en ? 'Notation shift' : '记谱移动'}</p>
                  <p className="mt-2 text-2xl font-black text-accent">{shiftLabel(semitoneShift, en)}</p>
                </div>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      <section className="mx-auto grid w-full max-w-[1680px] gap-6 px-5 py-10 sm:px-7 lg:px-10 xl:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="space-y-5 xl:sticky xl:top-24 xl:self-start">
          <div className="surface rounded-2xl p-5">
            <div className="mb-4 flex items-center gap-2">
              <SlidersHorizontal size={18} className="text-accent" />
              <h2 className="font-black">{en ? 'Processing options' : '处理选项'}</h2>
            </div>
            <div className="rounded-2xl border border-blue-500 bg-blue-50 p-4 text-accent dark:bg-blue-400/10">
              <p className="text-sm font-black">{en ? 'Keep original layout' : '保留原谱'}</p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-300">
                {en ? 'Keep pages, systems, numbering and performance marks; verify before download' : '保留分页、每行小节、左侧编号与演奏标记，核对后提供下载'}
              </p>
            </div>
            <p className="mt-5 rounded-xl bg-[rgb(var(--page))] p-3 text-xs leading-6 text-slate-500">
              {en ? 'Instrument mode preserves concert pitch. A clarinet → B♭ clarinet lowers written notes by one semitone.' : '按乐器转调保持实际音高不变。A 调单簧管 → 降 B 调单簧管，记谱降低半音。'}
            </p>
            <div className="mt-5 border-t border-[rgb(var(--line))] pt-5">
              <div className="mb-3 flex items-center gap-2">
                <Files size={17} className="text-accent" />
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                  {en ? 'Pages to transpose' : '转换页码'}
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2 rounded-xl bg-[rgb(var(--page))] p-1">
                <button
                  type="button"
                  disabled={!file || pageCountLoading || taskState === 'processing' || Boolean(pdfPageCount && pdfPageCount > MAX_SCORE_SELECTED_PAGES)}
                  onClick={() => { setPageSelectionMode('all'); play('click'); }}
                  className={`min-h-10 rounded-lg px-2 text-xs font-black transition disabled:cursor-not-allowed disabled:opacity-40 ${pageSelectionMode === 'all' ? 'bg-[rgb(var(--surface))] text-accent shadow-soft' : 'text-slate-500'}`}
                >
                  {en ? 'All pages' : '全部页码'}
                </button>
                <button
                  type="button"
                  disabled={!file || pageCountLoading || taskState === 'processing'}
                  onClick={() => {
                    setPageSelectionMode('custom');
                    if (!pageRange && pdfPageCount) setPageRange(`1-${Math.min(pdfPageCount, MAX_SCORE_SELECTED_PAGES)}`);
                    play('click');
                  }}
                  className={`min-h-10 rounded-lg px-2 text-xs font-black transition disabled:cursor-not-allowed disabled:opacity-40 ${pageSelectionMode === 'custom' ? 'bg-[rgb(var(--surface))] text-accent shadow-soft' : 'text-slate-500'}`}
                >
                  {en ? 'Selected pages' : '指定页码'}
                </button>
              </div>
              {pageSelectionMode === 'custom' && (
                <label className="mt-3 block">
                  <input
                    type="text"
                    inputMode="text"
                    disabled={!file || pageCountLoading || taskState === 'processing'}
                    value={pageRange}
                    onChange={(event) => setPageRange(event.target.value)}
                    placeholder="1-3, 5, 8"
                    aria-invalid={Boolean(parsedPageSelection.error)}
                    className={`h-11 w-full rounded-xl border bg-[rgb(var(--surface))] px-3 text-sm font-semibold outline-none transition ${parsedPageSelection.error ? 'border-rose-500 focus:border-rose-500' : 'border-[rgb(var(--line))] focus:border-blue-500'}`}
                  />
                  <span className="mt-2 block text-xs leading-5 text-slate-500 dark:text-slate-400">
                    {en ? 'Use commas and ranges, for example 1-3,5,8. Up to 20 pages.' : '用逗号和范围填写，例如 1-3,5,8；每次最多 20 页。'}
                  </span>
                </label>
              )}
              {pageCountLoading ? (
                <p className="mt-3 flex items-center gap-2 text-xs font-semibold text-slate-500"><Loader2 size={14} className="animate-spin" />{en ? 'Reading PDF page count…' : '正在读取 PDF 页数…'}</p>
              ) : pageCountError ? (
                <p className="mt-3 text-xs font-bold leading-5 text-rose-600 dark:text-rose-300">{pageCountError}</p>
              ) : parsedPageSelection.error ? (
                <p className="mt-3 text-xs font-bold leading-5 text-rose-600 dark:text-rose-300">{parsedPageSelection.error}</p>
              ) : pdfPageCount ? (
                <p className="mt-3 rounded-lg bg-blue-50 px-3 py-2 text-xs font-bold leading-5 text-blue-700 dark:bg-blue-400/10 dark:text-blue-300">
                  {pageSelectionMode === 'all'
                    ? (en ? `All ${pdfPageCount} pages will be transposed and exported.` : `将转换并导出全部 ${pdfPageCount} 页。`)
                    : (en ? `Pages ${formatPageSelection(parsedPageSelection.pages)} · ${selectedPageCount} selected.` : `将转换并导出第 ${formatPageSelection(parsedPageSelection.pages)} 页，共 ${selectedPageCount} 页。`)}
                </p>
              ) : null}
            </div>
            <div className="mt-5">
              <SelectField disabled={taskState === 'processing'} label={en ? 'Accidentals' : '升降号偏好'} value={accidental} onChange={setAccidental}>
                <option value="auto">{en ? 'Auto' : '自动'}</option>
                <option value="sharps">{en ? 'Prefer sharps' : '偏向升号'}</option>
                <option value="flats">{en ? 'Prefer flats' : '偏向降号'}</option>
              </SelectField>
            </div>
          </div>

          <div className="surface rounded-2xl p-5">
            <div className="mb-4 flex items-center gap-2">
              <Gauge size={18} className="text-teal-600" />
              <h2 className="font-black">{en ? 'Task status' : '任务状态'}</h2>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
              <div className="h-full rounded-full bg-gradient-to-r from-blue-600 to-teal-500 transition-all duration-500" style={{ width: `${progress}%` }} />
            </div>
            <p role="status" aria-live="polite" className="mt-3 text-sm leading-6 text-slate-500">{statusMessage}</p>
            <div className="mt-4 grid gap-2">
              {stages.map((stage, index) => {
                const done = taskState !== 'idle' && (index < stageIndex || taskState === 'completed');
                const active = taskState === 'processing' && index === stageIndex;
                return (
                  <div key={stage.zh} className="flex items-center justify-between rounded-xl bg-[rgb(var(--page))] px-3 py-2 text-sm">
                    <span className={active ? 'font-black text-accent' : ''}>{en ? stage.en : stage.zh}</span>
                    {active ? <Loader2 className="animate-spin text-accent" size={16} /> : done ? <CheckCircle2 className="text-teal-600" size={16} /> : <span className="h-2 w-2 rounded-full bg-slate-300" />}
                  </div>
                );
              })}
            </div>
            <div className="mt-5 grid gap-2">
              <button type="button" onClick={() => void startTask()} disabled={!file || taskState === 'processing' || pageSelectionInvalid} className="button-primary w-full disabled:cursor-not-allowed disabled:opacity-45">
                {taskState === 'processing' ? <Loader2 className="animate-spin" size={17} /> : <Music2 size={17} />}
                {taskState === 'processing' ? (en ? 'Processing...' : '正在转调...') : en ? 'Start transposition' : '开始转调'}
              </button>
              <div className="grid grid-cols-2 gap-2">
                <button type="button" onClick={resetTask} disabled={taskState === 'processing'} className="button-secondary px-3">
                  <RefreshCw size={16} />
                  {en ? 'Reset' : '重置'}
                </button>
                <button type="button" onClick={clearFile} disabled={taskState === 'processing'} className="button-secondary px-3">
                  <Trash2 size={16} />
                  {en ? 'Clear' : '清空'}
                </button>
              </div>
            </div>
          </div>
        </aside>

        <div className="min-w-0 space-y-6">
          {result && (
            <div className="surface rounded-2xl p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-3">
                    <h2 className="text-xl font-black">{en ? 'Generated result' : '生成结果'}</h2>
                    <span className={`tag ${result.outputAllowed ? '!bg-emerald-50 !text-emerald-700 dark:!bg-emerald-400/10 dark:!text-emerald-300' : '!bg-amber-50 !text-amber-700 dark:!bg-amber-400/10 dark:!text-amber-300'}`}>
                      {result.outputAllowed ? (en ? 'Verified' : '已核验') : (en ? 'Candidate · review needed' : '候选版 · 需要校对')}
                    </span>
                  </div>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500 dark:text-slate-300">
                    {result.verification?.summary || result.message}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={downloadResult} disabled={!availablePdf} className="button-primary disabled:cursor-not-allowed disabled:opacity-45">
                    <Download size={17} />
                    {result.outputAllowed ? (en ? 'Download PDF' : '下载生成的 PDF') : (en ? 'Download candidate' : '下载待校对 PDF')}
                  </button>
                  <a href={availablePdf || '#'} target="_blank" rel="noreferrer" className={`button-secondary ${!availablePdf ? 'pointer-events-none opacity-45' : ''}`}>
                    <FileText size={17} />{en ? 'Open PDF' : '打开 PDF'}
                  </a>
                  {result.reportUrl && <a href={result.reportUrl} className="button-secondary">{en ? 'Review checklist' : '下载校对清单'}</a>}
                  {result.editorAvailable && <button type="button" className="button-secondary" onClick={() => setEditorOpen(v => !v)}>{editorOpen ? (en ? 'Close editor' : '收起在线校谱') : (en ? 'Edit score' : '在线修改乐谱')}</button>}
                </div>
              </div>
              <div className="mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-6">
                {[
                  [en ? 'Shift' : '移动', shiftLabel(result.summary?.semitones ?? semitoneShift, en)],
                  [en ? 'Source' : '原谱类型', documentTypeLabel(result.verification?.inspection?.scoreProfile?.documentType, en)],
                  [en ? 'Notes' : '音符事件', result.summary ? String(result.summary.noteEvents) : '-'],
                  [en ? 'Measures' : '小节数', result.summary ? String(result.summary.measures) : '-'],
                  [en ? 'Pages' : '页码', result.summary ? (result.summary.selectedPages?.length
                    ? `${formatPageSelection(result.summary.selectedPages)} · ${result.summary.sourcePages || '-'} → ${result.summary.outputPages || '-'}`
                    : `${result.summary.sourcePages || '-'} → ${result.summary.outputPages || '-'}`) : '-'],
                  [en ? 'Size' : '结果大小', result.summary ? formatSize(result.summary.outputSize) : '-'],
                ].map(([label, value]) => (
                  <div key={label} className="flex items-center justify-between rounded-xl bg-[rgb(var(--page))] px-3 py-3 text-sm lg:block">
                    <span className="text-slate-500 dark:text-slate-300">{label}</span>
                    <span className="font-black lg:mt-1 lg:block">{value}</span>
                  </div>
                ))}
              </div>
              {result.editorAvailable && (
                <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-[rgb(var(--line))] pt-4">
                  <a className="text-sm underline" href={`/api/score/transpositions/${result.jobId}/musicxml`}>{en ? 'Download editable MusicXML' : '下载可编辑 MusicXML'}</a>
                  {previousVersions.map((version, i) => <button key={version.jobId} type="button" className="text-sm underline" disabled={taskState === 'processing'} onClick={() => {
                    setResult(version); setEditorOpen(false); setTaskState(version.outputAllowed ? 'completed' : 'needs_review');
                  }}>{en ? 'Previous version' : '返回旧版本'} {i + 1}</button>)}
                </div>
              )}
              {result.verification?.systemComposition && (
                <div className="mt-4 rounded-xl border border-[rgb(var(--line))] bg-[rgb(var(--page))] px-4 py-3 text-sm">
                  <p className="font-black">
                    {en ? 'Layout output' : '版式生成'}
                    {' · '}
                    {result.verification.systemComposition.status === 'applied'
                      ? (en ? 'Original page geometry preserved' : '已保留原页面版式')
                      : (en ? 'Full re-engraved candidate' : '完整重排候选版')}
                  </p>
                  <p className="mt-1 text-xs leading-6 text-slate-500 dark:text-slate-300">
                    {result.verification.systemComposition.reason}
                  </p>
                </div>
              )}
            </div>
          )}

          {result && !result.outputAllowed && result.candidateAvailable && (
            <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm leading-7 text-amber-900 dark:border-amber-600/40 dark:bg-amber-400/10 dark:text-amber-100">
              {en ? 'Candidate PDF — not fully verified. You can preview, download and edit it. Review every highlighted problem.' : '当前为待校对候选 PDF，尚未完整核验。你可以立即预览、下载或在线修改，请重点检查下方标出的项目。'}
            </div>
          )}

          {result?.editorAvailable && editorOpen && <ScoreEditor key={result.jobId} jobId={result.jobId} en={en} disabled={taskState === 'processing'} onSaved={jobId => {
            setPreviousVersions(old => old.some(v => v.jobId === result.jobId) ? old : [...old, result]);
            setEditorOpen(false); setActiveJob(jobId); window.sessionStorage.setItem(ACTIVE_JOB_KEY, jobId);
          }} />}

          <div className="grid gap-6 xl:grid-cols-2">
            <div className="surface overflow-hidden rounded-2xl">
              <div className="flex items-center justify-between border-b px-4 py-3">
                <div className="flex items-center gap-2 font-black">
                  <FileText size={18} className="text-accent" />
                  {en ? 'Source score' : '原谱'}
                </div>
                <span className="tag">{file ? 'PDF' : en ? 'Waiting' : '等待上传'}</span>
              </div>
              <div className="grid aspect-[4/5] min-h-[420px] place-items-center bg-slate-100 dark:bg-slate-900">
                {originalPdf ? (
                  <iframe title={en ? 'Source PDF preview' : '原谱 PDF 预览'} src={originalPdf} className="h-full w-full border-0" />
                ) : (
                  <div className="px-8 text-center text-slate-500">
                    <FileMusic className="mx-auto mb-4" size={46} />
                    <p className="font-bold">{en ? 'No score loaded' : '还没有载入乐谱'}</p>
                  </div>
                )}
              </div>
            </div>

            <div className="surface overflow-hidden rounded-2xl">
              <div className="flex items-center justify-between border-b px-4 py-3">
                <div className="flex items-center gap-2 font-black">
                  <ShieldCheck size={18} className="text-teal-600" />
                  {en ? 'Transposed result' : '转调结果'}
                </div>
                <span className={`tag ${taskState === 'completed' || taskState === 'needs_review' ? '!bg-teal-50 !text-teal-700 dark:!bg-teal-400/10 dark:!text-teal-300' : ''}`}>
                  {taskState === 'completed' ? (en ? 'Completed' : '已完成') : taskState === 'needs_review' ? (en ? 'Needs review' : '需复核') : taskState === 'failed' ? (en ? 'Failed' : '失败') : en ? 'Pending' : '待处理'}
                </span>
              </div>
              <div className="aspect-[4/5] min-h-[420px] bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-100">
                {availablePdf ? (
                  <iframe title={en ? 'Generated PDF preview' : '生成 PDF 预览'} src={availablePdf} className="h-full w-full border-0" />
                ) : result ? (
                  <div className="flex h-full items-center justify-center p-8 text-center text-sm font-bold text-slate-500 dark:text-slate-300">
                    {en ? 'No readable candidate PDF was generated. See the report below.' : '尚未生成可读取的候选 PDF，请查看下方原因。有可编辑数据时，可尝试修复后重新生成。'}
                  </div>
                ) : (
                  <div className="h-full p-6">
                    <div className="mb-5 flex items-center justify-between">
                      <div>
                        <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-400">TRANSPOSED SCORE</p>
                        <h3 className="mt-1 text-xl font-black">{displayedTitle}</h3>
                      </div>
                      <p className="rounded-full border px-3 py-1 text-xs font-bold text-accent">{shiftLabel(displayedShift, en)}</p>
                    </div>
                    <div className="grid min-h-64 place-items-center text-center text-slate-400">
                      <div>
                        {taskState === 'processing' ? <Loader2 size={42} className="mx-auto animate-spin text-accent" /> : <FileMusic size={46} className="mx-auto" />}
                        <p className="mt-4 text-sm">{taskState === 'processing' ? statusMessage : en ? 'Your generated score will appear here.' : '生成后的乐谱将在这里显示。'}</p>
                      </div>
                    </div>
                    <div className="mt-8 rounded-xl border border-dashed border-slate-300 p-3 text-xs text-slate-500 dark:border-slate-700 dark:text-slate-400">
                      {taskState === 'processing'
                        ? en
                          ? 'The backend is reading the PDF and generating a real result.'
                          : '后台正在识谱并生成真实 PDF，请稍等。'
                        : taskState === 'failed'
                          ? errorMessage
                          : en
                            ? 'Upload a PDF and start processing to preview the generated result here.'
                            : '上传 PDF 并开始转调后，这里会显示后台生成的真实结果。'}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div>
            <div className="surface rounded-2xl p-5">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-xl font-black">{en ? 'Review notes' : '复核提示'}</h2>
                  <p className="mt-1 text-sm text-slate-500 dark:text-slate-300">
                    {en ? 'Review the checks before downloading. Items requiring attention include a specific reason.' : '查看核对结果后下载乐谱；需要复核的项目会列出具体原因。'}
                  </p>
                </div>
                <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-black text-amber-700 dark:bg-amber-400/10 dark:text-amber-300">
                  {result?.warnings.length ?? 0} {en ? 'warnings' : '提示'}
                </span>
              </div>
              {result?.verification && (
                <div className="mb-4 rounded-2xl border border-[rgb(var(--line))] bg-[rgb(var(--page))] p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-black">{en ? 'Verification results' : '核对结果'}</p>
                      <p className="mt-1 text-xs font-semibold text-slate-500 dark:text-slate-300">
                        {result.verification.summary}
                      </p>
                    </div>
                    <span
                      className={`rounded-full px-3 py-1 text-xs font-black ${
                        result.verification.status === 'passed'
                          ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300'
                          : 'bg-rose-50 text-rose-700 dark:bg-rose-400/10 dark:text-rose-300'
                      }`}
                    >
                      {result.verification.status === 'passed' ? (en ? 'Passed' : '已通过') : en ? 'Needs review' : '需复核'}
                    </span>
                  </div>
                  <div className="mt-4 grid gap-3 lg:grid-cols-2">
                    {result.verification.checks.map((check) => (
                      <details
                        key={check.id}
                        open={!check.passed}
                        className={`rounded-xl border p-3 ${
                          check.passed
                            ? 'border-emerald-200 bg-emerald-50/70 text-emerald-900 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-100'
                            : 'border-rose-200 bg-rose-50/70 text-rose-900 dark:border-rose-400/20 dark:bg-rose-400/10 dark:text-rose-100'
                        }`}
                      >
                        <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-black">
                          {check.passed ? <CheckCircle2 size={17} /> : <AlertTriangle size={17} />}
                          <span className="min-w-0 flex-1">{check.label}</span>
                          <ChevronDown size={16} className="shrink-0 opacity-60" />
                        </summary>
                        <p className="mt-3 border-t border-current/15 pt-3 text-sm font-semibold leading-6 opacity-85">{check.detail}</p>
                      </details>
                    ))}
                  </div>
                  {result.verification.reviewCoverage && (
                    <p className="mt-4 rounded-xl bg-amber-50 p-3 text-xs font-semibold leading-6 text-amber-900 dark:bg-amber-400/10 dark:text-amber-100">
                      {en
                        ? 'Transposition and export checks are separate from checking the original score. The checks above show which steps still need review.'
                        : '转调数据一致，不等于原谱已全部识别正确。上方分别列出了音乐数据检查、原谱对应核验和输出 PDF 核验的结果。'}
                    </p>
                  )}
                  {!!result.verification.issues?.length && (
                    <div className="mt-4 rounded-xl border border-amber-300 p-3 dark:border-amber-600/40">
                      <p className="text-sm font-black">
                        {en ? 'Located differences' : '具体差异'} · {result.verification.issueCount ?? result.verification.issues.length}
                      </p>
                      <p className="mt-1 text-xs text-slate-500 dark:text-slate-300">
                        {en ? 'Locations refer to the recognized or exported score; original PDF coordinates still require confirmation.' : '以下位置来自识谱或输出乐谱的数据；与原 PDF 的坐标对应仍需确认。'}
                      </p>
                      <ol className="mt-3 max-h-80 space-y-3 overflow-y-auto">
                        {result.verification.issues.slice(0, 20).map((issue) => (
                          <li key={issue.id} className="rounded-lg bg-[rgb(var(--page))] p-3 text-xs">
                            <p className="font-black">{issue.message}</p>
                            {issue.location?.page && (
                              <p className="mt-1 text-slate-500 dark:text-slate-300">
                                {en ? 'Indexed score' : '数据中的位置'}：{en ? 'Page' : '第'} {issue.location.page} {en ? ' · System' : '页 · 第'} {issue.location.system} {en ? '' : '行'}
                              </p>
                            )}
                            <p className="mt-2 break-words"><span className="font-bold">{en ? 'Expected: ' : '应为：'}</span>{issue.expected}</p>
                            <p className="mt-1 break-words"><span className="font-bold">{en ? 'Found: ' : '检测到：'}</span>{issue.actual}</p>
                          </li>
                        ))}
                      </ol>
                      {(result.verification.issueCount ?? 0) > 20 && (
                        <p className="mt-2 text-xs text-slate-500 dark:text-slate-300">{en ? 'Showing the first 20 differences.' : '此处显示前 20 处差异。'}</p>
                      )}
                    </div>
                  )}
                  {!!result.verification.repairs?.length && (
                    <div className="mt-4 rounded-xl border border-dashed border-slate-300 p-3 text-xs dark:border-slate-700">
                      <p className="font-black">{en ? 'Auto-fix attempts' : '自动修复尝试'}</p>
                      <div className="mt-2 space-y-2">
                        {result.verification.repairs.map((repair) => (
                          <div key={repair.id} className="flex items-start justify-between gap-3">
                            <span className="font-semibold text-slate-600 dark:text-slate-300">{repair.label}</span>
                            <span className="max-w-[66%] text-right text-slate-500 dark:text-slate-400">{repair.detail}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {result.verification.aiNote && (
                    <div className="mt-4 rounded-xl bg-white/70 p-3 text-sm font-semibold leading-7 text-slate-600 dark:bg-slate-950/40 dark:text-slate-300">
                      {result.verification.aiNote}
                    </div>
                  )}
                </div>
              )}
              <div className="grid gap-3">
                {(result?.warnings.length ? result.warnings : [result ? (result.outputAllowed ? (en ? 'All required checks passed.' : '本次处理的核对项目已通过。') : (result.message || (en ? 'The result requires review.' : '结果需要复核。'))) : (en ? 'No generated result yet.' : '还没有生成结果。')]).map((warning) => (
                  <div key={warning} className="flex items-center gap-3 rounded-2xl border border-[rgb(var(--line))] p-4">
                    <AlertTriangle className={result ? 'text-amber-600' : 'text-slate-400'} size={20} />
                    <span className="font-semibold">{warning}</span>
                  </div>
                ))}
              </div>
            </div>

          </div>
        </div>
      </section>
    </div>
  );
}
