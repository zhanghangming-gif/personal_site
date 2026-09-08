import { useEffect, useState } from 'react';
import { loadScoreEditor, retargetScore, saveScoreEdits, type EditorScore, type EditorPitch } from '../services/scoreTransposeService';

const letters = ['C', 'D', 'E', 'F', 'G', 'A', 'B'];
const symbols: Record<number, string> = { '-2': '♭♭', '-1': '♭', '0': '♮', '1': '♯', '2': '𝄪' };
const retargetInstruments = [
  ['concert_c', 'C 调乐器 / 原调', 'Concert C'],
  ['piccolo', '短笛', 'Piccolo'],
  ['clarinet_a', 'A 调单簧管', 'A Clarinet'],
  ['clarinet_bb', '降 B 调单簧管', 'Bb Clarinet'],
  ['bass_clarinet_bb', '降 B 调低音单簧管', 'Bb Bass Clarinet'],
  ['trumpet_bb', '降 B 调小号', 'Bb Trumpet'],
  ['soprano_sax_bb', '降 B 调高音萨克斯', 'Bb Soprano Sax'],
  ['tenor_sax_bb', '降 B 调次中音萨克斯', 'Bb Tenor Sax'],
  ['sax_eb', '降 E 调中音萨克斯', 'Eb Alto Sax'],
  ['baritone_sax_eb', '降 E 调上低音萨克斯', 'Eb Baritone Sax'],
  ['horn_f', 'F 调圆号', 'F Horn'],
  ['english_horn_f', 'F 调英国管', 'English Horn'],
] as const;
function pitchLabel(pitch: EditorPitch | null) {
  return pitch ? `${pitch.step}${pitch.alter ? symbols[pitch.alter] : ''}${pitch.octave}` : '休止 / 无固定音高';
}

export function ScoreEditor({ jobId, onSaved, disabled, en }: {
  jobId: string; onSaved: (jobId: string) => void; disabled: boolean; en: boolean;
}) {
  const [score, setScore] = useState<EditorScore | null>(null);
  const [measureIndex, setMeasureIndex] = useState(0);
  const [selected, setSelected] = useState('');
  const [edits, setEdits] = useState<Record<string, EditorPitch>>({});
  const [history, setHistory] = useState<Array<Record<string, EditorPitch>>>([]);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [restCount, setRestCount] = useState(1);
  const [restPlacement, setRestPlacement] = useState<'before' | 'after'>('before');
  const [restConfirmed, setRestConfirmed] = useState(false);
  const [activeRestGap, setActiveRestGap] = useState('');
  const [eventRestConfirmed, setEventRestConfirmed] = useState(false);
  const [retargetInstrument, setRetargetInstrument] = useState('');
  const [retargetAccidental, setRetargetAccidental] = useState('auto');
  useEffect(() => {
    let active = true;
    void loadScoreEditor(jobId).then(data => {
      if (active) { setScore(data); setMeasureIndex(0); setSelected(''); setEdits({}); setHistory([]); setRestPlacement('before'); setRestConfirmed(false); setActiveRestGap(''); setEventRestConfirmed(false); setRetargetInstrument(data.targetInstrument ?? ''); setRetargetAccidental('auto'); }
    }).catch((e: unknown) => { if (active) setError(e instanceof Error ? e.message : '加载失败'); });
    return () => { active = false; };
  }, [jobId]);
  const measure = score?.measures[measureIndex];
  const event = measure?.events.find(item => item.id === selected);
  const pitch = event ? edits[event.id] ?? event.pitch : null;
  const count = Object.keys(edits).length;
  function update(next: EditorPitch) {
    if (!event || disabled || saving) return;
    setHistory(previous => [...previous, edits]);
    setEdits(previous => ({ ...previous, [event.id]: next }));
  }
  async function save() {
    if (!score || !count) return;
    setSaving(true); setError('');
    try {
      const job = await saveScoreEdits(jobId, score.revision, Object.entries(edits).map(([eventId, p]) => ({ eventId, pitch: p })));
      onSaved(job.jobId);
    } catch (e) { setError(e instanceof Error ? e.message : '保存失败'); }
    finally { setSaving(false); }
  }
  async function addRests() {
    if (!score || !measure || !restConfirmed || count || saving || disabled) return;
    setSaving(true); setError('');
    try {
      const job = await saveScoreEdits(jobId, score.revision, [{ type: 'insertRests', measureId: measure.id, count: restCount, placement: restPlacement }]);
      setRestConfirmed(false); onSaved(job.jobId);
    } catch (e) { setError(e instanceof Error ? e.message : '保存失败'); }
    finally { setSaving(false); }
  }
  async function confirmRestGap(gapId: string) {
    if (!score || !eventRestConfirmed || count || saving || disabled) return;
    setSaving(true); setError('');
    try {
      const job = await saveScoreEdits(jobId, score.revision, [{ type: 'confirmRest', gapId }]);
      setEventRestConfirmed(false); onSaved(job.jobId);
    } catch (e) { setError(e instanceof Error ? e.message : '保存失败'); }
    finally { setSaving(false); }
  }
  async function createRetarget() {
    if (!score?.canRetarget || !retargetInstrument || count || saving || disabled) return;
    setSaving(true); setError('');
    try {
      const job = await retargetScore(jobId, retargetInstrument, retargetAccidental);
      onSaved(job.jobId);
    } catch (e) { setError(e instanceof Error ? e.message : '重新转调失败'); }
    finally { setSaving(false); }
  }
  function focusMeasure(measureId: string, missingMeasures?: number) {
    if (!score) return;
    const index = score.measures.findIndex(item => item.id === measureId);
    if (index < 0) return;
    setMeasureIndex(index); setSelected(''); setRestPlacement('before'); setRestConfirmed(false);
    if (missingMeasures) setRestCount(missingMeasures);
    window.setTimeout(() => document.getElementById('score-rest-repair')?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 0);
  }
  return <section className="surface rounded-2xl p-5">
    <h2 className="text-xl font-black">{en ? 'Edit score' : '在线校谱 · 音高与空拍小节'}</h2>
    <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
      {en ? 'Edit pitches or insert missing empty bars, then regenerate the target from the corrected source score.' : '可以修改音高或补入空拍小节。新任务会先保存校正版源谱，再重新转调生成目标 PDF。'}
    </p>
    <p className="mt-1 text-xs leading-6 text-slate-500 dark:text-slate-300">
      {en ? 'The diagram shows pitches only. You can also insert confirmed whole-bar rests in a single-staff part. Other duration, note and notation edits require a MusicXML editor.' : '下方是音高选择示意，完整节奏与演奏标记请看 PDF。支持单声部单谱表补入整小节休止；改时值、增删有音高的音符及连线等，请下载 MusicXML 在制谱软件中完成。'}
    </p>
    <button type="button" className="button-secondary mt-3" disabled={disabled || saving} onClick={() => document.getElementById('score-rest-repair')?.scrollIntoView({ behavior: 'smooth', block: 'center' })}>
      {en ? '+ Insert missing empty bars' : '＋ 人工补入空拍小节'}
    </button>
    {error && <p role="alert" className="mt-3 text-sm text-rose-600 dark:text-rose-300">{error}</p>}
    {!score ? <p className="mt-4">{en ? 'Loading…' : '正在读取可编辑乐谱…'}</p> : <>
      {!!score.restSuggestions?.length && <div className="mt-5 rounded-2xl border border-sky-500/40 bg-sky-500/10 p-4">
        <h3 className="font-black">{en ? 'Possible missing rests' : '疑似漏识别的休止符'}</h3>
        <p className="mt-1 text-sm leading-6">{en ? 'The timing gap and the Audiveris internal object are shown together. Open the source crop and confirm only when the rest and its position are clear.' : '这里把节奏缺口和 Audiveris 内部保留的休止对象放在一起。请打开原谱局部，只有看清休止符及位置后才确认补入。'}</p>
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          {score.restSuggestions.map(item => {
            const active = activeRestGap === item.gapId;
            const box = item.reviewRegion?.bbox;
            const page = item.reviewRegion?.page ?? item.location.page;
            const sequenceLabel = item.notationSequenceLabels?.join(' + ');
            const regionUrl = box && page ? `/api/score/transpositions/${encodeURIComponent(jobId)}/region-image?role=source&page=${page}&dpi=800&x0=${encodeURIComponent(box[0])}&y0=${encodeURIComponent(box[1])}&x1=${encodeURIComponent(box[2])}&y1=${encodeURIComponent(box[3])}` : '';
            return <article key={item.gapId} className="rounded-xl border border-sky-500/25 bg-[rgb(var(--surface))] p-4">
              <p className="font-bold">{en ? `Measure ${item.location.measure ?? '?'}, voice ${item.voice}` : `第 ${item.location.measure ?? '?'} 小节 · 声部 ${item.voice}`}</p>
              <p className="mt-1 text-sm">{en ? `Gap at ${item.onset}, duration ${item.duration} quarter notes` : `起点 ${item.onset}，缺少 ${item.duration} 个四分音符时值`}</p>
              <p className="mt-1 text-sm">{item.notationLabel ? (en ? `Candidate: ${item.notationLabel}` : `候选：${item.notationLabel}${item.dots ? `（${item.dots} 个附点）` : ''}`) : sequenceLabel ? (en ? `Candidate sequence: ${sequenceLabel}` : `候选组合：${sequenceLabel}`) : (en ? 'No unique rest candidate' : '没有唯一的休止符候选')}</p>
              <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-300">{item.confirmable ? (en ? 'Strong OMR object match; source confirmation is still required.' : 'OMR 内部对象与缺失时值唯一匹配，仍须对照原谱确认。') : (en ? 'Evidence is weak or ambiguous. Inspect and edit the exported MusicXML manually.' : '证据较弱或存在歧义，只提供定位；请在导出的 MusicXML 中人工修改。')}</p>
              {regionUrl && <button type="button" className="button-secondary mt-3 text-sm" onClick={() => { setActiveRestGap(active ? '' : item.gapId); setEventRestConfirmed(false); }}>{active ? (en ? 'Close source crop' : '收起原谱局部') : (en ? 'Inspect source crop' : '查看原谱局部')}</button>}
              {active && regionUrl && <div className="mt-3 overflow-hidden rounded-xl border bg-white p-2"><img src={regionUrl} alt={en ? `Source measure ${item.location.measure ?? ''}` : `原谱第 ${item.location.measure ?? ''} 小节局部`} className="max-h-72 w-full object-contain" /></div>}
              {active && item.confirmable && <div className="mt-3 rounded-xl border border-emerald-500/35 bg-emerald-500/10 p-3">
                <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={eventRestConfirmed} disabled={saving || disabled || !!count} onChange={event => setEventRestConfirmed(event.target.checked)} />{en ? 'I checked the source crop and confirm this rest type, voice and timing position.' : '我已对照原谱局部，确认休止符种类、声部和拍点位置都正确。'}</label>
                {!!count && <p className="mt-2 text-sm">{en ? 'Save or discard pitch changes first.' : '请先保存或放弃音高修改。'}</p>}
                <button type="button" className="button-primary mt-3 disabled:opacity-40" disabled={!eventRestConfirmed || !!count || saving || disabled} onClick={() => void confirmRestGap(item.gapId)}>{saving ? (en ? 'Generating…' : '正在生成…') : (en ? 'Insert this rest and generate PDF' : '补入这个休止符并生成新版 PDF')}</button>
              </div>}
            </article>;
          })}
        </div>
      </div>}
      {!!score.structureGaps?.length && <div className="mt-5 space-y-3 rounded-2xl border border-amber-500/50 bg-amber-500/10 p-4">
        <div>
          <h3 className="font-black">{en ? 'Located structure gaps' : '已定位的结构缺口'}</h3>
          <p className="mt-1 text-sm leading-6">{en ? 'The system detected a bar-count mismatch, but cannot prove that the missing content is rests. Use the source page and system below to inspect it before making a repair.' : '系统已发现小节跨度不一致，但不能证明缺失内容是休止。请先根据下面的原 PDF 页码和谱表行对照检查。'}</p>
        </div>
        {score.structureGaps.map(gap => {
          const choices = gap.candidateMeasures.length ? gap.candidateMeasures : gap.systemMeasures;
          return <article key={gap.id} className="rounded-xl border border-amber-500/30 bg-[rgb(var(--surface))] p-4">
            <p className="font-bold">{en ? `Source page ${gap.page ?? '?'}, system ${gap.system ?? '?'}` : `原谱第 ${gap.page ?? '?'} 页 · 第 ${gap.system ?? '?'} 行`} · {en ? `${gap.missingMeasures} bars missing` : `识谱时间轴少 ${gap.missingMeasures} 小节`}</p>
            {gap.lineStart != null && gap.nextLineStart != null && <p className="mt-1 text-sm">{en ? `Printed line starts: ${gap.lineStart} → ${gap.nextLineStart}` : `原谱行首小节号：${gap.lineStart} → ${gap.nextLineStart}`}</p>}
            <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-300">{gap.reason}</p>
            {!!choices.length && <div className="mt-3 flex flex-wrap gap-2">
              {choices.map(item => <button key={item.measureId} type="button" className="button-secondary text-sm" disabled={saving || disabled} onClick={() => focusMeasure(item.measureId, gap.missingMeasures)}>
                {en ? `Use measure ${item.measureNumber || item.positionInSystem} as reference` : `以第 ${item.measureNumber || item.positionInSystem} 小节为插入参照`}{'isRest' in item && item.isRest ? (en ? ' (rest)' : '（休止）') : ''}
              </button>)}
            </div>}
          </article>;
        })}
      </div>}
      <label className="mt-4 block text-sm font-bold">{en ? 'Measure' : '选择小节'}
        <select className="mt-2 w-full rounded-xl border bg-[rgb(var(--surface))] p-3" value={measureIndex} disabled={saving || disabled}
          onChange={e => { setMeasureIndex(Number(e.target.value)); setSelected(''); setRestConfirmed(false); }}>
          {score.measures.map((m, i) => <option key={m.id} value={i}>
            {en ? 'Part' : '乐器声部'} {m.location.part} · {en ? 'Measure' : '小节'} {m.location.measure} · {en ? 'Indexed page' : '数据页'} {m.location.page}
          </option>)}
        </select>
      </label>
      {measure && [...new Set(measure.events.map(e => e.staff))].map(staff => {
        const events = measure.events.filter(e => e.staff === staff);
        const clef = events.find(e => e.clef)?.clef;
        const clefName = clef?.[0] ?? 'G';
        const clefLine = Number(clef?.[1] || (clefName === 'F' ? 4 : clefName === 'C' ? 3 : 2));
        const reference = clefName === 'F' ? 3 * 7 + 3 : clefName === 'C' ? 4 * 7 : 4 * 7 + 4;
        const bottom = reference - (clefLine - 1) * 2 + Number(clef?.[2] || 0) * 7;
        const width = Math.max(520, events.length * 64 + 80);
        return <div key={staff} className="mt-4 overflow-x-auto rounded-xl border bg-white p-2 text-slate-900">
          <p className="text-xs">{en ? 'Staff' : '谱表'} {staff} · {clefName} {en ? 'clef · Pitch selection' : '谱号 · 音高选择示意'}</p>
          <svg role="group" aria-label={en ? 'Select a note' : '点击选择音符'} width={width} height={230}>
            {[0, 1, 2, 3, 4].map(i => <line key={i} x1={20} x2={width - 20} y1={85 + i * 12} y2={85 + i * 12} stroke="#64748b" />)}
            {events.map((e, i) => {
              const p = edits[e.id] ?? e.pitch;
              const rawY = p ? 133 - ((p.octave * 7 + letters.indexOf(p.step)) - bottom) * 6 : 109;
              const y = Math.max(25, Math.min(185, rawY)), x = 60 + i * 64;
              const active = selected === e.id;
              return <g key={e.id} role="button" tabIndex={p && !disabled && !saving ? 0 : -1} aria-label={`${pitchLabel(p)} · ${en ? 'voice' : '声部'} ${e.voice}`}
                aria-pressed={active} onClick={() => { if (p && !disabled && !saving) setSelected(e.id); }}
                onKeyDown={key => { if (p && !disabled && !saving && (key.key === 'Enter' || key.key === ' ')) { key.preventDefault(); setSelected(e.id); } }}
                className={p ? 'cursor-pointer focus:outline-none' : ''}>
                <rect x={x - 25} y={12} width={50} height={201} rx={8} fill={active ? '#dbeafe' : edits[e.id] ? '#fef3c7' : 'transparent'} />
                {p && rawY === y && Array.from({ length: 20 }, (_, k) => 25 + k * 12).filter(ly => (ly < 85 && ly >= y - 1) || (ly > 133 && ly <= y + 1)).map(ly => <line key={ly} x1={x - 15} x2={x + 15} y1={ly} y2={ly} stroke="#334155" />)}
                {p ? <><ellipse cx={x} cy={y} rx={9} ry={6} transform={`rotate(-18 ${x} ${y})`} fill={active ? '#1d4ed8' : '#0f172a'} />
                  {p.alter !== 0 && <text x={x - 23} y={y + 5} fontSize={18}>{symbols[p.alter]}</text>}</> : <text x={x - 9} y={y} fontSize={20}>𝄽</text>}
                <text x={x} y={205} textAnchor="middle" fontSize={11}>{p ? pitchLabel(p) : '休止'}</text>
                <title>{pitchLabel(p)}；声部 {e.voice}；起点 {e.onset}；时值 {e.duration} 个四分音符</title>
              </g>;
            })}
          </svg>
        </div>;
      })}
      {event && pitch && <div className="mt-4 rounded-xl border p-4">
        <p className="text-sm font-bold">{pitchLabel(event.pitch)} → {pitchLabel(pitch)} · {en ? 'Voice' : '声部'} {event.voice}</p>
        {!!event.ties.length && <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">{en ? 'This note is tied. Update the connected notes to the same pitch.' : '此音有延音线，请把相连音符一起改为相同音高。'}</p>}
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <label>{en ? 'Note' : '音名'}<select aria-label={en ? 'Note name' : '修改音名'} disabled={disabled || saving} value={pitch.step} onChange={e => update({ ...pitch, step: e.target.value })} className="mt-1 block w-full rounded-lg border bg-[rgb(var(--surface))] p-2">{letters.map(l => <option key={l}>{l}</option>)}</select></label>
          <label>{en ? 'Accidental' : '升降号'}<select aria-label={en ? 'Accidental' : '修改升降号'} disabled={disabled || saving} value={pitch.alter} onChange={e => update({ ...pitch, alter: Number(e.target.value) })} className="mt-1 block w-full rounded-lg border bg-[rgb(var(--surface))] p-2">{[-2, -1, 0, 1, 2].map(a => <option key={a} value={a}>{symbols[a]}</option>)}</select></label>
          <label>{en ? 'Octave' : '八度'}<select aria-label={en ? 'Octave' : '修改八度'} disabled={disabled || saving} value={pitch.octave} onChange={e => update({ ...pitch, octave: Number(e.target.value) })} className="mt-1 block w-full rounded-lg border bg-[rgb(var(--surface))] p-2">{Array.from({ length: 10 }, (_, i) => <option key={i}>{i}</option>)}</select></label>
        </div>
      </div>}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button type="button" className="button-primary disabled:opacity-40" disabled={!count || disabled || saving} onClick={() => void save()}>{saving ? (en ? 'Saving…' : '正在保存…') : (en ? `Generate PDF (${count} notes)` : `保存修改并生成 PDF（${count} 个音）`)}</button>
        <button type="button" className="button-secondary disabled:opacity-40" disabled={!history.length || disabled || saving} onClick={() => { setEdits(history[history.length - 1]); setHistory(h => h.slice(0, -1)); }}>{en ? 'Undo' : '撤销一步'}</button>
        <button type="button" className="button-secondary disabled:opacity-40" disabled={!count || disabled || saving} onClick={() => { setEdits({}); setHistory([]); }}>{en ? 'Discard changes' : '放弃本次修改'}</button>
        <a className="text-sm underline" href={`/api/score/transpositions/${jobId}/musicxml`}>{en ? 'Export MusicXML' : '下载 MusicXML'}</a>
      </div>
      <div id="score-rest-repair" className="mt-5 rounded-xl border border-amber-500/40 p-4">
        <h3 className="font-bold">{en ? 'Manually insert empty bars' : '人工补入空拍小节'}</h3>
        <p className="mt-2 text-sm leading-6">{en ? 'Choose a reference measure, insert before or after it, and enter the printed count. Counts above one are written as one compact multi-measure rest.' : '先选择一个参照小节，再选择在它之前或之后插入，并填写原谱印刷的数字。数量大于 1 时，会生成一个带数字的多小节休止，例如“23”。'}</p>
        {measure && <p className="mt-3 rounded-lg bg-amber-500/10 px-3 py-2 text-sm font-bold">{en ? `Reference: measure ${measure.location.measure}` : `当前参照：第 ${measure.location.measure} 小节`}</p>}
        <fieldset className="mt-3">
          <legend className="text-sm font-bold">{en ? 'Insert position' : '插入位置'}</legend>
          <div className="mt-2 flex flex-wrap gap-3">
            <label className={`cursor-pointer rounded-xl border px-4 py-3 text-sm ${restPlacement === 'before' ? 'border-blue-500 bg-blue-500/15 font-bold' : ''}`}><input type="radio" className="mr-2" name={`rest-placement-${jobId}`} checked={restPlacement === 'before'} disabled={saving || disabled} onChange={() => { setRestPlacement('before'); setRestConfirmed(false); }} />{en ? 'Before this measure' : '在当前小节之前'}</label>
            <label className={`cursor-pointer rounded-xl border px-4 py-3 text-sm ${restPlacement === 'after' ? 'border-blue-500 bg-blue-500/15 font-bold' : ''}`}><input type="radio" className="mr-2" name={`rest-placement-${jobId}`} checked={restPlacement === 'after'} disabled={saving || disabled} onChange={() => { setRestPlacement('after'); setRestConfirmed(false); }} />{en ? 'After this measure' : '在当前小节之后'}</label>
          </div>
        </fieldset>
        <label className="mt-3 block text-sm">{en ? 'Printed multi-rest count (1–64)' : '原谱标出的空拍小节总数（1–64）'}<input type="number" min={1} max={64} value={restCount} disabled={saving || disabled} onChange={e => { setRestCount(Number(e.target.value)); setRestConfirmed(false); }} className="ml-3 w-24 rounded-lg border bg-[rgb(var(--surface))] p-2" /></label>
        {restCount > 1 && restCount <= 64 && <p className="mt-2 text-sm text-blue-600 dark:text-blue-300">{en ? `The PDF will show a compact multi-measure rest labelled ${restCount}.` : `新版 PDF 将显示一个标有“${restCount}”的多小节休止。`}</p>}
        <label className="mt-3 flex items-start gap-2 text-sm"><input type="checkbox" checked={restConfirmed} disabled={saving || disabled} onChange={e => setRestConfirmed(e.target.checked)} />{en ? 'I checked the source: these bars are rests and the insertion position is correct.' : '我已对照原谱，确认缺失的是休止，且选中的插入位置正确。'}</label>
        {!!count && <p className="mt-2 text-sm">{en ? 'Save or discard pitch changes before inserting bars.' : '请先保存或放弃音高修改，再补入小节。'}</p>}
        <button type="button" className="button-primary mt-3 disabled:opacity-40" disabled={!restConfirmed || !!count || saving || disabled || !Number.isInteger(restCount) || restCount < 1 || restCount > 64} onClick={() => void addRests()}>{saving ? (en ? 'Generating…' : '正在生成…') : en ? 'Repair empty bars and generate PDF' : `按原谱补入标为 ${restCount} 的空拍小节并生成 PDF`}</button>
      </div>
      {score.canRetarget && <div className="mt-5 rounded-xl border border-blue-500/35 bg-blue-500/5 p-4">
        <h3 className="font-bold">{en ? 'Generate another instrument version' : '用校正版源谱生成其他乐器版本'}</h3>
        <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">{en ? 'Reuse this corrected source without running score recognition again.' : '直接复用这份校正版源谱，不再重新识谱。此前确认的源谱修正会保留。'}</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="text-sm font-bold">{en ? 'Target instrument' : '目标乐器'}
            <select className="mt-2 w-full rounded-xl border bg-[rgb(var(--surface))] p-3" value={retargetInstrument} disabled={saving || disabled || !!count} onChange={event => setRetargetInstrument(event.target.value)}>
              {retargetInstruments.map(([id, zh, english]) => <option key={id} value={id}>{en ? english : zh}</option>)}
            </select>
          </label>
          <label className="text-sm font-bold">{en ? 'Accidentals' : '升降号偏好'}
            <select className="mt-2 w-full rounded-xl border bg-[rgb(var(--surface))] p-3" value={retargetAccidental} disabled={saving || disabled || !!count} onChange={event => setRetargetAccidental(event.target.value)}>
              <option value="auto">{en ? 'Auto' : '自动'}</option>
              <option value="sharps">{en ? 'Prefer sharps' : '偏向升号'}</option>
              <option value="flats">{en ? 'Prefer flats' : '偏向降号'}</option>
            </select>
          </label>
        </div>
        {!!count && <p className="mt-2 text-sm">{en ? 'Save or discard pitch changes first.' : '请先保存或放弃当前音高修改。'}</p>}
        <button type="button" className="button-primary mt-3 disabled:opacity-40" disabled={!retargetInstrument || !!count || saving || disabled} onClick={() => void createRetarget()}>{saving ? (en ? 'Generating…' : '正在生成…') : (en ? 'Generate from corrected source' : '从校正版源谱重新转调并生成 PDF')}</button>
      </div>}
    </>}
  </section>;
}
