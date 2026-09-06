const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
const API_BASE_URL = (configuredApiBaseUrl || '').replace(/\/$/, '');
// Development stays self-contained unless an API URL is provided. Production
// uses the same-origin /api endpoint served by Nginx.
export const isDemoMode = import.meta.env.DEV && !configuredApiBaseUrl;

export async function apiRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...options?.headers } });
  let body: unknown;
  try { body = await response.json(); } catch { throw new Error('服务器返回了无法识别的数据'); }
  if (!response.ok) throw new Error((body as { message?: string }).message || `请求失败（${response.status}）`);
  return body as T;
}
