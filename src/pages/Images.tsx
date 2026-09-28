import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import SearchHeader from "../components/SearchHeader";
import ImageCard from "../components/ImageCard";
import Pagination from "../components/Pagination";
import Loading from "../components/Loading";
import ErrorState from "../components/ErrorState";
import EmptyState from "../components/EmptyState";
import { searchImages, type ImageResponse } from "../services/imageApi";
import { useQueryResource } from "../hooks/useQueryResource";
import { formatNumber } from "../utils/format";

export default function Images() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const [input, setInput] = useState(q);

  useEffect(() => setInput(q), [q]);

  const fetcher = useCallback(
    () => searchImages(q, page, 24),
    [q, page]
  );
  const { data, loading, error, retry } = useQueryResource<ImageResponse>(
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
      <SearchHeader q={q} input={input} onInput={setInput} onSubmit={submit} active="images" />

      <div className="container">
        {!q && (
          <EmptyState
            title="Image search"
            message="Search images indexed from crawled pages. Try kerala, kochi or rocket."
          />
        )}
        {q && loading && <Loading label="Searching images..." />}
        {q && !loading && error && (
          <ErrorState message={error} onRetry={retry} />
        )}
        {q && !loading && !error && data && data.results.length === 0 && (
          <EmptyState
            title="No images found"
            message={`No indexed images matched “${q}”. Images are never re-hosted — only indexed with a link to the original.`}
          />
        )}
        {q && !loading && !error && data && data.results.length > 0 && (
          <>
            <p className="result-count">
              About {formatNumber(data.total)} image{data.total === 1 ? "" : "s"} for “{q}”
            </p>
            <div className="media-grid">
              {data.results.map((img) => (
                <ImageCard key={img.imageUrl} item={img} />
              ))}
            </div>
            <Pagination
              page={page}
              totalPages={totalPages}
              onPage={goPage}
              label="Image pages"
            />
          </>
        )}
      </div>
    </div>
  );
}
