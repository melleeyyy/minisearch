import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import SearchHeader from "../components/SearchHeader";
import VideoCard from "../components/VideoCard";
import Loading from "../components/Loading";
import ErrorState from "../components/ErrorState";
import EmptyState from "../components/EmptyState";
import { searchVideos, type VideoResultItem } from "../services/videoApi";
import { ApiError } from "../services/api";
import { formatNumber } from "../utils/format";

const PAGE_SIZE = 12;

export default function Videos() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [input, setInput] = useState(q);

  useEffect(() => setInput(q), [q]);

  // Accumulated results: "More search" appends the next page below
  // instead of navigating to a new page.
  const [items, setItems] = useState<VideoResultItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [moreLoading, setMoreLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const gridRef = useRef<HTMLDivElement | null>(null);

  // Fresh query: load page 1 (replaces the list).
  useEffect(() => {
    if (!q) {
      setItems([]);
      setTotal(0);
      setPage(1);
      setError(null);
      setLoading(false);
      return;
    }
    let alive = true;
    setLoading(true);
    setError(null);
    searchVideos(q, 1, PAGE_SIZE)
      .then((res) => {
        if (!alive) return;
        setItems(res.results);
        setTotal(res.total);
        setPage(1);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setError(
          err instanceof ApiError ? err.message : "Unexpected error. Please retry."
        );
        setItems([]);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [q, nonce]);

  const submit = useCallback(
    (query: string) => setParams({ q: query }),
    [setParams]
  );

  const retry = useCallback(() => setNonce((n) => n + 1), []);

  // "More" appends the next page below and scrolls to where the new
  // results start, so the page never navigates away.
  const loadMore = useCallback(() => {
    if (moreLoading) return;
    const next = page + 1;
    const prevCount = items.length;
    setMoreLoading(true);
    searchVideos(q, next, PAGE_SIZE)
      .then((res) => {
        setItems((prev) => [
          ...prev,
          ...res.results.filter((r) => !prev.some((p) => p.url === r.url)),
        ]);
        setTotal(res.total);
        setPage(next);
        requestAnimationFrame(() => {
          const firstNew = gridRef.current?.children[prevCount] as
            | HTMLElement
            | undefined;
          firstNew?.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      })
      .catch(() => {
        /* keep the current list; the user can tap More again */
      })
      .finally(() => setMoreLoading(false));
  }, [q, page, moreLoading, items.length]);

  const hasMore = items.length > 0 && items.length < total;

  return (
    <div>
      <SearchHeader q={q} input={input} onInput={setInput} onSubmit={submit} active="videos" />

      <div className="container">
        {!q && (
          <EmptyState
            title="Video search"
            message="Videos are fetched live from Wikimedia Commons. Try kerala, launch or rocket."
          />
        )}
        {q && loading && <Loading label="Searching videos..." />}
        {q && !loading && error && <ErrorState message={error} onRetry={retry} />}
        {q && !loading && !error && items.length === 0 && (
          <EmptyState
            title="No videos found"
            message={`No Commons videos matched “${q}”.`}
          />
        )}
        {q && !loading && !error && items.length > 0 && (
          <>
            <p className="result-count">
              About {formatNumber(total)} video{total === 1 ? "" : "s"} for “{q}”
            </p>
            <div className="media-grid media-grid-videos" ref={gridRef}>
              {items.map((v) => (
                <VideoCard key={v.url} item={v} />
              ))}
            </div>
            {hasMore && (
              <div className="more-search">
                <button
                  type="button"
                  className="more-search-btn"
                  onClick={loadMore}
                  disabled={moreLoading}
                >
                  {moreLoading ? "Loading more..." : "More search"}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
