import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../services/api";

interface QueryResource<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  retry: () => void;
}

/**
 * Shared data-fetching state for query pages: loading, error and retry,
 * with cancellation of stale responses. `fetcher` should be memoized
 * (useCallback) and change identity exactly when the query changes.
 */
export function useQueryResource<T>(
  enabled: boolean,
  fetcher: () => Promise<T>
): QueryResource<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!enabled) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    let alive = true;
    setLoading(true);
    setError(null);
    fetcher()
      .then((res) => {
        if (alive) setData(res);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setError(
          err instanceof ApiError ? err.message : "Unexpected error. Please retry."
        );
        setData(null);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [enabled, fetcher, nonce]);

  const retry = useCallback(() => setNonce((n) => n + 1), []);
  return { data, loading, error, retry };
}
