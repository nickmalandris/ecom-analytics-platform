import axios from 'axios';

const normalizeBaseUrl = (value: string | undefined) => {
  if (!value) return '';
  return value.endsWith('/') ? value.slice(0, -1) : value;
};

export const API_BASE_URL = normalizeBaseUrl(import.meta.env.VITE_BACKEND_HOST);

export const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
});

export const isAxiosError = axios.isAxiosError;
