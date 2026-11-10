import { useCallback, useEffect, useState } from "react";
import { apiGet } from "@/lib/api";

export type ApiState<T> =
  | { status: "loading"; data: undefined; error: undefined }
  | { status: "success"; data: T; error: undefined }
  | { status: "error"; data: undefined; error: Error };

// In-memory cache so navigating between pages does not refetch static
// synthetic inventory. Cleared on full reload or via `reload()`.
const cache = new Map<string, unknown>();
// Concurrent requests for the same path share one network call.
const inflight = new Map<string, Promise<unknown>>();

function fetchShared<T>(path: string): Promise<T> {
  let p = inflight.get(path) as Promise<T> | undefined;
  if (!p) {
    p = apiGet<T>(path).finally(() => inflight.delete(path));
    inflight.set(path, p);
  }
  return p;
}

const loading = { status: "loading", data: undefined, error: undefined } as const;

/** Drop cached responses whose path starts with any prefix (after a state-changing action). */
export function invalidate(...prefixes: string[]): void {
  for (const key of [...cache.keys()]) if (prefixes.some((p) => key.startsWith(p))) cache.delete(key);
}

export function useApi<T>(path: string | null, opts: { live?: boolean } = {}): ApiState<T> & { reload: () => void } {
  // `live` data (audit events, mandate status) is refetched on every mount.
  const [state, setState] = useState<ApiState<T>>(() => {
    if (opts.live && path) cache.delete(path);
    return path && cache.has(path) ? { status: "success", data: cache.get(path) as T, error: undefined } : loading;
  });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!path) return;
    if (cache.has(path)) {
      setState({ status: "success", data: cache.get(path) as T, error: undefined });
      return;
    }
    let active = true;
    setState(loading);
    fetchShared<T>(path)
      .then((data) => {
        cache.set(path, data);
        if (active) setState({ status: "success", data, error: undefined });
      })
      .catch((error: Error) => {
        if (active) setState({ status: "error", data: undefined, error });
      });
    return () => {
      active = false;
    };
  }, [path, nonce]);

  const reload = useCallback(() => {
    if (path) cache.delete(path);
    setNonce((n) => n + 1);
  }, [path]);

  return { ...state, reload };
}
