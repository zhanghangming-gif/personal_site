import { apiRequest } from './api';

export type ScoreTransposeStatus = 'completed' | 'needs_review' | 'failed';
export type PipelineStatus = 'PROCESSING' | 'VERIFIED' | 'VERIFIED_WITH_WARNINGS' | 'NEEDS_REVIEW' | 'REJECTED';

export type ScoreTransposeSummary = {
  transposeMode?: 'instrument' | 'custom';
  sourceInstrument: string;
  targetInstrument: string;
  semitones: number;
  sourcePages: number;
  outputPages: number;
  noteEvents: number;
  measures: number;
  outputSize: number;
  engine?: string;
};

export type ScoreTranspositionDescriptor = {
  mode: 'instrument' | 'custom';
  sourceInstrument: string;
  targetInstrument: string;
  semitones: number;
};

export type ScoreVerificationCheck = {
  id: string;
  label: string;
  passed: boolean;
  detail: string;
};

export type ScoreRepairAttempt = {
  id: string;
  label: string;
  status: 'running' | 'fixed' | 'failed' | 'needs_review' | 'skipped';
  detail: string;
};

export type ScoreVerification = {
  status: 'passed' | 'failed';
  strict: boolean;
  checks: ScoreVerificationCheck[];
  issueCount?: number;
  issues?: Array<{
    id: string;
    phase: string;
    message: string;
    expected: string;
    actual: string;
    location?: {
      part?: number;
      measure?: string;
      page?: number;
      system?: number;
      staff?: string;
      voice?: string;
      onsetQuarter?: string;
      layoutBasis?: string;
    };
  }>;
  reviewCoverage?: {
    sourceRecognition: string;
    outputPdfRecognition: string;
    transposition: string;
    renderComparison: string;
    verifiedSourceEvents: number;
    totalSourceEvents: number;
  };
  repairs?: ScoreRepairAttempt[];
  pitchMismatches?: Array<{
    index: number;
    measure: string;
    expected: number;
    actual: number;
  }>;
  source?: {
    measures: number;
    noteEvents: number;
    pages: number;
  };
  output?: {
    measures: number;
    noteEvents: number;
    pages: number;
  };
  summary: string;
  aiNote?: string;
  inspection?: {
    pageCount?: number;
    scoreProfile?: {
      documentType?: 'vector' | 'scan' | 'mixed';
      structureCandidateSystems?: number;
      structureCandidateMeasures?: number;
      recognitionPlan?: { previewDpi?: number; analysisDpi?: number; detailDpi?: number };
    };
  };
  systemComposition?: {
    status?: 'eligible' | 'applied' | 'skipped' | 'fallback_full_reengrave';
    reason?: string;
    pages?: number;
    systems?: number;
    preservedOutsideSystemRegions?: boolean;
    semanticVerification: false;
    postCompositionLayoutStatus?: string;
  };
  outputPdfOmrAudit?: {
    status?: 'observed_match' | 'conflict' | 'unavailable' | 'skipped';
    reason?: string;
    evidenceLevel?: string;
    checks?: ScoreVerificationCheck[];
    differences?: string[];
    semanticAudit?: { passed?: boolean; issueCount?: number; truncated?: boolean };
    outputAllowed: false;
    verificationAuthority: 'none';
  };
};

export type ScoreTransposeResult = {
  jobId: string;
  status: ScoreTransposeStatus;
  pipelineStatus: PipelineStatus;
  outputAllowed: boolean;
  outputUrl: string;
  candidateAvailable?: boolean;
  candidateUrl?: string;
  reportUrl?: string;
  originalUrl?: string;
  editorAvailable?: boolean;
  inspectionAvailable?: boolean;
  inspectionUrl?: string;
  targetInspectionAvailable?: boolean;
  targetInspectionUrl?: string;
  fileName: string;
  summary?: ScoreTransposeSummary;
  transposition?: ScoreTranspositionDescriptor;
  warnings: string[];
  verification?: ScoreVerification;
  message?: string;
  stage?: string;
  progress?: number;
};

export type EditorPitch = { step: string; alter: number; octave: number };
export type EditorEvent = {
  id: string; kind: string; pitch: EditorPitch | null; duration: string; onset: string;
  staff: string; voice: string; grace: boolean; clef: string[] | null; ties: string[];
};
export type EditorScore = {
  revision: string;
  measures: Array<{ id: string; location: { part: number; measure: string; page: number; system: number }; events: EditorEvent[] }>;
  structureGaps?: Array<{
    id: string; page?: number; system?: number; lineStart?: number; nextLineStart?: number;
    missingMeasures: number; reason: string; contentKnown: false; requiresConfirmation: true;
    candidateMeasures: Array<{ measureId: string; measureNumber: string; positionInSystem: number; isRest?: boolean }>;
    systemMeasures: Array<{ measureId: string; measureNumber: string; positionInSystem: number }>;
  }>;
  restSuggestions?: Array<{
    gapId: string; measureId: string; location: { part?: number; measure?: string; page?: number; system?: number };
    voice: string; onset: string; duration: string; position: 'leading' | 'internal' | 'trailing' | 'full_measure';
    reviewRegion?: { page?: number; bbox?: [number, number, number, number]; basis?: string };
    status: 'supported_by_omr_object' | 'weak_omr_candidate' | 'ambiguous_candidates' | 'visual_confirmation_required';
    notation?: string; notationLabel?: string; dots: number; grade?: number; contextGrade?: number;
    riskReasons: string[]; confirmable: boolean; requiresSourceConfirmation: true;
  }>;
};

export async function loadScoreEditor(jobId: string) {
  const result = await apiRequest<{ success: boolean; data: EditorScore }>(`/api/score/transpositions/${encodeURIComponent(jobId)}/editor`);
  return result.data;
}

export async function saveScoreEdits(jobId: string, revision: string, changes: Array<{ eventId: string; pitch: EditorPitch } | { type: 'insertRests'; measureId: string; count: number } | { type: 'confirmRest'; gapId: string }>) {
  const result = await apiRequest<{ success: boolean; data: ScoreJobSnapshot }>(`/api/score/transpositions/${encodeURIComponent(jobId)}/edits`, {
    method: 'POST', body: JSON.stringify({ revision, changes }),
  });
  return result.data;
}

export type ScoreJobSnapshot = Omit<ScoreTransposeResult, 'status'> & {
  status: ScoreTransposeStatus | 'queued' | 'processing';
};

export type ScoreTransposeRequest = {
  file: File;
  transposeMode: 'instrument' | 'custom';
  sourceInstrument: string;
  targetInstrument: string;
  semitones?: number;
  accidentalPreference: string;
};

async function fileToBase64(file: File) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}

export async function transposeScore(request: ScoreTransposeRequest, signal?: AbortSignal) {
  const data = await fileToBase64(request.file);
  const result = await apiRequest<{ success: boolean; message: string; data: ScoreJobSnapshot }>('/api/score/transpositions', {
    method: 'POST',
    signal,
    body: JSON.stringify({
      async: true,
      name: request.file.name,
      type: request.file.type || 'application/pdf',
      data,
      sourceInstrument: request.sourceInstrument,
      transposeMode: request.transposeMode,
      targetInstrument: request.targetInstrument,
      semitones: request.semitones,
      accidentalPreference: request.accidentalPreference,
    }),
  });
  return result.data;
}

function pause(milliseconds: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const stop = () => {
      window.clearTimeout(timer);
      reject(new DOMException('Aborted', 'AbortError'));
    };
    const timer = window.setTimeout(() => {
      signal.removeEventListener('abort', stop);
      resolve();
    }, milliseconds);
    if (signal.aborted) stop();
    else signal.addEventListener('abort', stop, { once: true });
  });
}

export async function waitForScore(
  jobId: string,
  onProgress: (job: ScoreJobSnapshot) => void,
  signal: AbortSignal,
): Promise<ScoreTransposeResult> {
  let failures = 0;
  const started = Date.now();
  while (!signal.aborted) {
    let job: ScoreJobSnapshot;
    try {
      const response = await apiRequest<{ success: boolean; data: ScoreJobSnapshot }>(
        `/api/score/transpositions/${encodeURIComponent(jobId)}`, { signal },
      );
      job = response.data;
      failures = 0;
    } catch (error) {
      if (signal.aborted || ++failures >= 5) throw error;
      await pause(2000, signal);
      continue;
    }
    onProgress(job);
    if (job.status !== 'queued' && job.status !== 'processing') return job as ScoreTransposeResult;
    if (Date.now() - started > 20 * 60 * 1000) {
      throw new Error('处理时间较长，任务仍保存在服务器；刷新页面可继续查看。');
    }
    await pause(1500, signal);
  }
  throw new DOMException('Aborted', 'AbortError');
}
