import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useApp } from "../context";

interface ApiState<T> {
  data?: T;
  error?: any;
  loading: boolean;
}

// GET helper that refetches when the path, params, or global data version change. Pass null to skip.
export function useApi<T>(path: string | null, params?: Record<string, unknown>) {
  const { version } = useApp();
  const key = path ? `${path}?${JSON.stringify(params ?? {})}` : null;
  const [state, setState] = useState<ApiState<T>>({ loading: Boolean(path) });

  useEffect(() => {
    if (!path) {
      setState({ loading: false });
      return;
    }
    let live = true;
    setState((current) => ({ ...current, loading: true }));
    api
      .get<T>(path, { params })
      .then((response) => live && setState({ data: response.data, loading: false }))
      .catch((error) => live && setState({ error, loading: false }));
    return () => {
      live = false;
    };
    // `key` captures path and params.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, version]);

  return state;
}
