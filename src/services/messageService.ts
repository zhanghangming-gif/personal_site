import type {
  LikeResult,
  Message,
  MessagePage,
  MessagePayload,
  ReplyPayload,
} from '../types';
import { apiRequest, isDemoMode } from './api';

const STORAGE_KEY = 'zhm-demo-messages';
const VISITOR_KEY = 'zhm-guestbook-visitor';
const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function getGuestbookVisitorId(): string {
  let value = localStorage.getItem(VISITOR_KEY);
  if (!value) {
    value = crypto.randomUUID().replace(/-/g, '');
    localStorage.setItem(VISITOR_KEY, value);
  }
  return value;
}

function readLocal(): Message[] {
  try {
    return (JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]') as Message[]).map((message) => ({
      ...message,
      likeCount: message.likeCount || 0,
      liked: Boolean(message.liked),
      replies: message.replies || [],
    }));
  } catch {
    return [];
  }
}

function writeLocal(items: Message[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

export async function getMessages(page = 1, pageSize = 6): Promise<MessagePage> {
  if (!isDemoMode) {
    const query = new URLSearchParams({
      page: String(page),
      pageSize: String(pageSize),
      visitorId: getGuestbookVisitorId(),
    });
    const result = await apiRequest<{ success: boolean; data: MessagePage }>(
      `/api/messages?${query}`,
      { headers: { 'X-Visitor-ID': getGuestbookVisitorId() } },
    );
    return result.data;
  }
  await delay(300);
  const all = readLocal().sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  const start = (page - 1) * pageSize;
  return { items: all.slice(start, start + pageSize), page, pageSize, total: all.length };
}

export async function submitMessage(payload: MessagePayload): Promise<string> {
  if (!isDemoMode) {
    const result = await apiRequest<{ success: boolean; message: string }>('/api/messages', {
      method: 'POST',
      body: JSON.stringify({ ...payload, visitorId: getGuestbookVisitorId() }),
    });
    return result.message;
  }
  await delay(400);
  if (payload.website) return '留言发布成功';
  const all = readLocal();
  all.unshift({
    id: crypto.randomUUID(),
    nickname: payload.nickname,
    content: payload.content,
    createdAt: new Date().toISOString(),
    likeCount: 0,
    liked: false,
    replies: [],
  });
  writeLocal(all);
  return '留言发布成功';
}

export async function submitReply(messageId: string, payload: ReplyPayload): Promise<string> {
  if (!isDemoMode) {
    const result = await apiRequest<{ success: boolean; message: string }>(
      `/api/messages/${messageId}/replies`,
      { method: 'POST', body: JSON.stringify(payload) },
    );
    return result.message;
  }
  await delay(300);
  const all = readLocal();
  const message = all.find((item) => item.id === messageId);
  if (!message) throw new Error('这条留言不存在');
  message.replies.push({
    id: crypto.randomUUID(),
    nickname: payload.nickname,
    content: payload.content,
    createdAt: new Date().toISOString(),
    likeCount: 0,
    liked: false,
  });
  writeLocal(all);
  return '回复发布成功';
}

export async function toggleLike(
  entityType: 'message' | 'reply',
  entityId: string,
): Promise<LikeResult> {
  if (!isDemoMode) {
    const path =
      entityType === 'message'
        ? `/api/messages/${entityId}/likes`
        : `/api/replies/${entityId}/likes`;
    const result = await apiRequest<{ success: boolean; data: LikeResult }>(path, {
      method: 'POST',
      body: JSON.stringify({ visitorId: getGuestbookVisitorId() }),
    });
    return result.data;
  }
  const all = readLocal();
  const target =
    entityType === 'message'
      ? all.find((item) => item.id === entityId)
      : all.flatMap((item) => item.replies).find((item) => item.id === entityId);
  if (!target) throw new Error('内容不存在');
  target.liked = !target.liked;
  target.likeCount = Math.max(0, target.likeCount + (target.liked ? 1 : -1));
  writeLocal(all);
  return { liked: target.liked, likeCount: target.likeCount };
}

export async function reportContent(entityType: 'message' | 'reply', entityId: string, reason: string): Promise<string> {
  if (isDemoMode) return '举报已提交';
  const path = entityType === 'message' ? `/api/messages/${entityId}/reports` : `/api/replies/${entityId}/reports`;
  const result = await apiRequest<{ success: boolean; message: string }>(path, {
    method: 'POST',
    body: JSON.stringify({ reason, visitorId: getGuestbookVisitorId() }),
  });
  return result.message;
}

export function clearDemoMessages() {
  localStorage.removeItem(STORAGE_KEY);
}
