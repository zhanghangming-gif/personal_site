export type ChatRole = 'user' | 'assistant';

export interface ChatHistoryItem {
  role: ChatRole;
  content: string;
}

interface ChatResponse {
  success: boolean;
  data?: { answer?: string };
  message?: string;
}

export async function askAboutZhang(
  message: string,
  history: ChatHistoryItem[],
  signal?: AbortSignal,
) {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
    signal,
  });
  const result = (await response.json().catch(() => ({}))) as ChatResponse;
  if (!response.ok || !result.success || !result.data?.answer) {
    throw new Error(result.message || 'AI 助手暂时无法回答，请稍后再试');
  }
  return result.data.answer;
}
