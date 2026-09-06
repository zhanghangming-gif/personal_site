import type { GuestIdentity } from '../types';
import { apiRequest, isDemoMode } from './api';
import { getGuestbookVisitorId } from './messageService';

const IDENTITY_KEY = 'zhm-guestbook-identity';
const DEMO_VERIFIED_KEY = 'zhm-demo-verified-email';

export function readSavedIdentity(): GuestIdentity {
  try {
    const parsed = JSON.parse(localStorage.getItem(IDENTITY_KEY) || '{}') as Partial<GuestIdentity>;
    return {
      nickname: parsed.nickname || '',
      email: parsed.email || '',
      verified: Boolean(parsed.verified),
      remember: parsed.remember !== false,
    };
  } catch {
    return { nickname: '', email: '', verified: false, remember: true };
  }
}

export function saveIdentity(identity: GuestIdentity) {
  if (!identity.remember) {
    localStorage.removeItem(IDENTITY_KEY);
    return;
  }
  localStorage.setItem(IDENTITY_KEY, JSON.stringify(identity));
}

export async function getIdentity(email: string): Promise<{ verified: boolean; nickname?: string }> {
  const normalized = email.trim().toLowerCase();
  if (!normalized) return { verified: false };
  if (isDemoMode) {
    return { verified: localStorage.getItem(DEMO_VERIFIED_KEY) === normalized };
  }
  const query = new URLSearchParams({ email: normalized, visitorId: getGuestbookVisitorId() });
  const result = await apiRequest<{ success: boolean; data: { verified: boolean; nickname?: string } }>(
    `/api/identity?${query}`,
    { headers: { 'X-Visitor-ID': getGuestbookVisitorId() } },
  );
  return result.data;
}

export async function requestEmailCode(email: string): Promise<string> {
  const normalized = email.trim().toLowerCase();
  if (isDemoMode) return '演示模式验证码：123456';
  const result = await apiRequest<{ success: boolean; message: string }>('/api/identity/email-code', {
    method: 'POST',
    body: JSON.stringify({ email: normalized, visitorId: getGuestbookVisitorId() }),
  });
  return result.message;
}

export async function verifyEmailCode(email: string, code: string, nickname: string): Promise<string> {
  const normalized = email.trim().toLowerCase();
  if (isDemoMode) {
    if (code !== '123456') throw new Error('验证码不正确');
    localStorage.setItem(DEMO_VERIFIED_KEY, normalized);
    return '邮箱验证成功';
  }
  const result = await apiRequest<{ success: boolean; message: string }>('/api/identity/verify-email', {
    method: 'POST',
    body: JSON.stringify({ email: normalized, code, nickname, visitorId: getGuestbookVisitorId() }),
  });
  return result.message;
}
