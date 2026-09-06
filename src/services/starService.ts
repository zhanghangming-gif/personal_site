import type { StarState } from '../types';
import { apiRequest, isDemoMode } from './api';

const VISITOR_KEY = 'zhm-site-star-visitor';
const DEMO_STARRED_KEY = 'zhm-demo-site-starred';
const DEMO_COUNT_KEY = 'zhm-demo-site-stars';

function visitorId(): string {
  let value = localStorage.getItem(VISITOR_KEY);
  if (!value) {
    value = crypto.randomUUID().replace(/-/g, '');
    localStorage.setItem(VISITOR_KEY, value);
  }
  return value;
}

function demoState(): StarState {
  return {
    starred: localStorage.getItem(DEMO_STARRED_KEY) === '1',
    starCount: Math.max(0, Number(localStorage.getItem(DEMO_COUNT_KEY) || '0')),
  };
}

export async function getSiteStars(): Promise<StarState> {
  if (!isDemoMode) {
    const result = await apiRequest<{ success: boolean; data: StarState }>('/api/stars', {
      headers: { 'X-Visitor-ID': visitorId() },
    });
    return result.data;
  }
  return demoState();
}

export async function toggleSiteStar(): Promise<StarState> {
  if (!isDemoMode) {
    const result = await apiRequest<{ success: boolean; data: StarState }>('/api/stars', {
      method: 'POST',
      body: JSON.stringify({ visitorId: visitorId() }),
    });
    return result.data;
  }

  const current = demoState();
  const next: StarState = {
    starred: !current.starred,
    starCount: Math.max(0, current.starCount + (current.starred ? -1 : 1)),
  };
  localStorage.setItem(DEMO_STARRED_KEY, next.starred ? '1' : '0');
  localStorage.setItem(DEMO_COUNT_KEY, String(next.starCount));
  return next;
}
