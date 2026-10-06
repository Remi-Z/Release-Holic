import { ref } from 'vue';
import type { LoginOut, RunOut, UserOut } from './contracts';
import { resetUI } from '../composables/ui';

const base = (process.env.API_BASE_URL || '/api').replace(/\/$/, '');
export const token = ref(sessionStorage.getItem('release-holic-token') || '');
export const user = ref<UserOut | null>(null);
export const activeRuns = ref<RunOut[]>([]);
const readCache = new Map<string, unknown>();
const runTimers = new Map<string, number>();

export class APIError extends Error {
  constructor(message: string, public status = 0) { super(message); }
}

export function clearSession() {
  token.value = '';
  user.value = null;
  activeRuns.value = [];
  readCache.clear();
  for (const timer of runTimers.values()) window.clearInterval(timer);
  runTimers.clear();
  resetUI();
  sessionStorage.removeItem('release-holic-token');
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = options.method || 'GET';
  const requestToken = token.value;
  const headers = new Headers(options.headers);
  if (token.value) headers.set('Authorization', `Bearer ${token.value}`);
  if (options.body) headers.set('Content-Type', 'application/json');
  if (!navigator.onLine && method !== 'GET') throw new APIError('You are offline. Changes can be saved when you reconnect.');
  let response: Response;
  try {
    response = await fetch(base + path, { ...options, headers, signal: options.signal || AbortSignal.timeout(110000) });
  } catch {
    if (requestToken === token.value && method === 'GET' && readCache.has(path)) return readCache.get(path) as T;
    throw new APIError('Could not reach the server. Check your connection and try again.');
  }
  const body = await response.json().catch(() => ({})) as { detail?: unknown };
  if (requestToken !== token.value) throw new APIError('The account changed while this request was running.');
  if (!response.ok) {
    if (response.status === 401 && path !== '/auth/login') window.dispatchEvent(new Event('session-expired'));
    const detail = typeof body.detail === 'string' ? body.detail : response.status === 422 ? 'Check the entered fields and date precision.' : 'The request could not be completed.';
    throw new APIError(detail, response.status);
  }
  if (method === 'GET') readCache.set(path, body);
  else readCache.clear();
  return body as T;
}

export const json = (value: unknown, method = 'POST'): RequestInit => ({ method, body: JSON.stringify(value) });

export async function signIn(username: string, password: string) {
  clearSession();
  const result = await api<LoginOut>('/auth/login', json({ username, password }));
  token.value = result.token;
  user.value = result.user;
  sessionStorage.setItem('release-holic-token', result.token);
  return result.user;
}

export async function restoreSession() {
  if (user.value) return user.value;
  try { user.value = await api<UserOut>('/auth/me'); return user.value; }
  catch { clearSession(); return null; }
}

export function queryString(values: Record<string, unknown>) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value !== '' && value !== null && value !== undefined) query.set(key, String(value));
  return query.toString();
}

export function trackRun(run: RunOut) {
  activeRuns.value = [run, ...activeRuns.value.filter(item => item.id !== run.id)].slice(0, 20);
  if (!['queued', 'running'].includes(run.status)) return;
  if (runTimers.has(run.id)) return;
  const timer = window.setInterval(() => {
    void api<RunOut>(`/runs/${run.id}`).then(updated => {
      activeRuns.value = activeRuns.value.map(item => item.id === updated.id ? updated : item);
      if (!['queued', 'running'].includes(updated.status)) {
        window.clearInterval(timer);
        runTimers.delete(run.id);
        window.dispatchEvent(new CustomEvent('catalogue-updated', { detail: updated }));
      }
    }).catch(() => { window.clearInterval(timer); runTimers.delete(run.id); });
  }, 2000);
  runTimers.set(run.id, timer);
  window.setTimeout(() => { window.clearInterval(timer); runTimers.delete(run.id); }, 180000);
}
