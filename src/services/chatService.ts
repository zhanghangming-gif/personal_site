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
  let lastMessage = 'AI 助手暂时无法回答，请稍后再试';
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, history }),
        signal,
      });
      const result = (await response.json().catch(() => ({}))) as ChatResponse;
      if (response.ok && result.success && result.data?.answer) return result.data.answer;
      lastMessage = result.message || lastMessage;
      if (attempt === 0 && (response.status === 429 || response.status >= 500)) {
        await new Promise((resolve) => window.setTimeout(resolve, 650));
        continue;
      }
      break;
    } catch (error) {
      if (signal?.aborted) throw error;
      if (attempt === 0) {
        await new Promise((resolve) => window.setTimeout(resolve, 650));
        continue;
      }
    }
  }
  throw new Error(lastMessage);
}
