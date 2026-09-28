import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import SearchHeader from "../components/SearchHeader";
import VideoCard from "../components/VideoCard";
import Pagination from "../components/Pagination";
import Loading from "../components/Loading";
import ErrorState from "../components/ErrorState";
import EmptyState from "../components/EmptyState";
import { searchVideos, type VideoResponse } from "../services/videoApi";
import { useQueryResource } from "../hooks/useQueryResource";
import { formatNumber } from "../utils/format";

export default function Videos() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const [input, setInput] = useState(q);

  useEffect(() => setInput(q), [q]);

  const fetcher = useCallback(
    () => searchVideos(q, page, 12),
    [q, page]
  );
  const { data, loading, error, retry } = useQueryResource<VideoResponse>(
    q !== "",
    fetcher
  );

  const submit = useCallback(
    (query: string) => setParams({ q: query, page: "1" }),
    [setParams]
  );

  const goPage = useCallback(
    (p: number) => {
      setParams({ q, page: String(p) });
      window.scrollTo(0, 0);
    },
    [q, setParams]
  );

  const totalPages = data ? Math.ceil(data.total / data.limit) : 0;

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
        {q && !loading && error && (
          <ErrorState message={error} onRetry={retry} />
        )}
        {q && !loading && !error && data && data.results.length === 0 && (
          <EmptyState
            title="No videos found"
            message={`No Commons videos matched “${q}”.`}
          />
        )}
        {q && !loading && !error && data && data.results.length > 0 && (
          <>
            <p className="result-count">
              About {formatNumber(data.total)} video{data.total === 1 ? "" : "s"} for “{q}”
            </p>
            <div className="media-grid media-grid-videos">
              {data.results.map((v) => (
                <VideoCard key={v.url} item={v} />
              ))}
            </div>
            <Pagination
              page={page}
              totalPages={totalPages}
              onPage={goPage}
              label="Video pages"
            />
          </>
        )}
      </div>
    </div>
  );
}
