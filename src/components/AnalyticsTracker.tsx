import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { apiRequest, isDemoMode } from '../services/api';

const VISITOR_KEY = 'zhm-analytics-visitor';
const SESSION_KEY = 'zhm-analytics-session';

function id(storage: Storage, key: string) {
  let value = storage.getItem(key);
  if (!value) {
    value = crypto.randomUUID();
    storage.setItem(key, value);
  }
  return value;
}

export function AnalyticsTracker() {
  const location = useLocation();
  useEffect(() => {
    if (isDemoMode || location.pathname.startsWith('/admin')) return;
    let referrerHost = '';
    try { referrerHost = document.referrer ? new URL(document.referrer).hostname : ''; } catch { /* ignore */ }
    void apiRequest('/api/analytics', {
      method: 'POST',
      body: JSON.stringify({
        path: `${location.pathname}${location.search}`,
        visitorId: id(localStorage, VISITOR_KEY),
        sessionId: id(sessionStorage, SESSION_KEY),
        referrerHost,
      }),
    }).catch(() => undefined);
  }, [location.pathname, location.search]);
  return null;
}
