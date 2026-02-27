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

export const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
});

export const isAxiosError = axios.isAxiosError;

export const buildApiUrl = (path: string) => {
  const base = API_BASE_URL;
  if (!path.startsWith('/')) {
    return base ? `${base}/${path}` : path;
  }
  return base ? `${base}${path}` : path;
};
