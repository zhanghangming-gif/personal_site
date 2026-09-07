import { GlobalWorkerOptions, getDocument } from 'pdfjs-dist';
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

export const MAX_SCORE_SOURCE_PAGES = 500;
export const MAX_SCORE_SELECTED_PAGES = 20;

export type PageSelection = {
  pages: number[];
  error: string;
};

export async function readPdfPageCount(file: File) {
  const loadingTask = getDocument({ data: new Uint8Array(await file.arrayBuffer()) });
  const document = await loadingTask.promise;
  try {
    return document.numPages;
  } finally {
    await document.destroy();
  }
}

export function parsePageSelection(value: string, pageCount: number, en = false): PageSelection {
  const input = value.trim();
  if (!input) return { pages: [], error: en ? 'Enter at least one page.' : '请至少输入一个页码。' };

  const pages: number[] = [];
  const seen = new Set<number>();
  const tokens = input.replace(/[，、]/g, ',').split(',').map((token) => token.trim()).filter(Boolean);
  if (!tokens.length) return { pages: [], error: en ? 'Enter at least one page.' : '请至少输入一个页码。' };

  for (const token of tokens) {
    const match = token.match(/^(\d+)\s*(?:-|–|—|~|至)\s*(\d+)$/);
    const values: number[] = [];
    if (match) {
      const start = Number(match[1]);
      const end = Number(match[2]);
      if (start > end) {
        return { pages: [], error: en ? `Invalid descending range: ${token}.` : `页码范围不能倒序：${token}。` };
      }
      for (let page = start; page <= end; page += 1) values.push(page);
    } else if (/^\d+$/.test(token)) {
      values.push(Number(token));
    } else {
      return { pages: [], error: en ? `Invalid page expression: ${token}.` : `无法识别页码：${token}。` };
    }

    for (const page of values) {
      if (page < 1 || page > pageCount) {
        return { pages: [], error: en ? `Page ${page} is outside 1–${pageCount}.` : `第 ${page} 页超出原 PDF 的 1–${pageCount} 页范围。` };
      }
      if (seen.has(page)) {
        return { pages: [], error: en ? `Page ${page} is selected more than once.` : `第 ${page} 页被重复选择。` };
      }
      seen.add(page);
      pages.push(page);
      if (pages.length > MAX_SCORE_SELECTED_PAGES) {
        return { pages: [], error: en ? 'Select no more than 20 pages per task.' : '每次最多选择 20 页。' };
      }
    }
  }

  return { pages: pages.sort((left, right) => left - right), error: '' };
}

export function formatPageSelection(pages: number[]) {
  if (!pages.length) return '';
  const sorted = [...pages].sort((left, right) => left - right);
  const ranges: string[] = [];
  let start = sorted[0];
  let end = start;
  for (const page of sorted.slice(1)) {
    if (page === end + 1) {
      end = page;
      continue;
    }
    ranges.push(start === end ? String(start) : `${start}-${end}`);
    start = page;
    end = page;
  }
  ranges.push(start === end ? String(start) : `${start}-${end}`);
  return ranges.join(', ');
}
