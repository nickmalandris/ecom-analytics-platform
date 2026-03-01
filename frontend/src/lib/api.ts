import axios from 'axios';

declare global {
  interface Window {
    __APP_BACKEND_HOST__?: string;
  }
}

const normalizeBaseUrl = (value: string | undefined) => {
  if (!value) return '';
  return value.endsWith('/') ? value.slice(0, -1) : value;
};

const inferRuntimeBackendHost = (): string => {
  if (typeof window === 'undefined') return '';
  if (window.__APP_BACKEND_HOST__) {
    return window.__APP_BACKEND_HOST__;
  }

  const origin = window.location.origin;
  if (origin.includes('frontend')) {
    return origin.replace('frontend', 'backend');
  }
  return '';
};

const rawBaseUrl = import.meta.env.VITE_BACKEND_HOST || inferRuntimeBackendHost();

export const API_BASE_URL = normalizeBaseUrl(rawBaseUrl);

if (!API_BASE_URL && typeof window !== 'undefined') {
  console.warn('[api] No backend host configured; falling back to same-origin requests.');
}

// ─── Token helpers ──────────────────────────────────────

const TOKEN_KEY = 'analytics_token';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

// ─── Capture OAuth token from redirect URL ──────────────
// After a Google/Facebook OAuth login the backend redirects to
// <frontend>/?token=<jwt>.  We grab it, persist it, and strip
// the query parameter so it doesn't leak into bookmarks/history.
if (typeof window !== 'undefined') {
  const params = new URLSearchParams(window.location.search);
  const urlToken = params.get('token');
  if (urlToken) {
    setToken(urlToken);
    // Remove ?token=... from the address bar without a page reload
    params.delete('token');
    const clean = params.toString();
    const newUrl = window.location.pathname + (clean ? `?${clean}` : '') + window.location.hash;
    window.history.replaceState({}, '', newUrl);
  }
}

// ─── Axios instance ─────────────────────────────────────

export const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true, // still needed for OAuth cookie-based sessions
});

// Attach the bearer token (if present) to every outgoing request.
// OAuth sessions fall back to the cookie automatically.
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Clear a stale/expired token on 401 so the next page navigation
// doesn't loop between the dashboard and the login page.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      clearToken();
    }
    return Promise.reject(error);
  },
);

export const isAxiosError = axios.isAxiosError;
