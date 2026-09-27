import axios from "axios";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
});

let pendingRequests = 0;
const pendingConfigs = new WeakSet<object>();
const loadingListeners = new Set<() => void>();

function notifyLoadingListeners() {
  loadingListeners.forEach((listener) => listener());
}

function startLoading(config: object) {
  if (!pendingConfigs.has(config)) {
    pendingConfigs.add(config);
    pendingRequests += 1;
    notifyLoadingListeners();
  }
}

function stopLoading(config?: object) {
  if (config && pendingConfigs.delete(config)) {
    pendingRequests -= 1;
    notifyLoadingListeners();
  }
}

export function subscribeToApiLoading(listener: () => void) {
  loadingListeners.add(listener);
  return () => loadingListeners.delete(listener);
}

export function isApiLoading() {
  return pendingRequests > 0;
}

api.interceptors.request.use((config) => {
  startLoading(config);
  return config;
});

api.interceptors.response.use(
  (response) => {
    stopLoading(response.config);
    return response;
  },
  (error) => {
    stopLoading(error.config);
    return Promise.reject(error);
  }
);
