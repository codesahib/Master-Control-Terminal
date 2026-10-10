import { useSyncExternalStore } from "react";

// ponytail: tiny hash router; swap for react-router if routes ever need loaders or nesting.
function subscribe(callback: () => void) {
  window.addEventListener("hashchange", callback);
  return () => window.removeEventListener("hashchange", callback);
}

export function useRoute() {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash);
  const [path, query = ""] = (hash.replace(/^#/, "") || "/overview").split("?");
  const parts = path.split("/").filter(Boolean);
  return { path: `/${parts.join("/")}`, parts, params: new URLSearchParams(query) };
}

export function href(path: string, params?: Record<string, string | undefined>) {
  const query = new URLSearchParams(Object.entries(params ?? {}).filter((entry): entry is [string, string] => Boolean(entry[1]))).toString();
  return `#${path}${query ? `?${query}` : ""}`;
}

export function navigate(path: string, params?: Record<string, string | undefined>) {
  window.location.hash = href(path, params);
}
