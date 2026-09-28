import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import SearchHeader from "../components/SearchHeader";
import NewsCard from "../components/NewsCard";
import Loading from "../components/Loading";
import ErrorState from "../components/ErrorState";
import EmptyState from "../components/EmptyState";
import { getNews, type NewsResponse } from "../services/knowledgeApi";
import { searchImages, type ImageResponse } from "../services/imageApi";
import { useQueryResource } from "../hooks/useQueryResource";

/** News tab: clustered, deduplicated news for a query, with a topical
 *  thumbnail from MiniSearch's image index on each story card. */
export default function News() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [input, setInput] = useState(q);
  const [images, setImages] = useState<ImageResponse | null>(null);

  useEffect(() => setInput(q), [q]);

  // Topical thumbnails (best-effort — a missing image never blocks news).
  useEffect(() => {
    if (!q) {
      setImages(null);
      return;
    }
    let alive = true;
    searchImages(q, 1, 12)
      .then((r) => {
        if (alive) setImages(r);
      })
      .catch(() => {
        if (alive) setImages(null);
      });
    return () => {
      alive = false;
    };
  }, [q]);

  const fetcher = useCallback(() => getNews(q), [q]);
  const { data, loading, error, retry } = useQueryResource<NewsResponse>(
    q !== "",
    fetcher
  );

  const submit = useCallback(
    (query: string) => setParams({ q: query, page: "1" }),
    [setParams]
  );

  const thumbs = images?.results ?? [];
  const thumbFor = (i: number) =>
    thumbs.length ? thumbs[i % thumbs.length].imageUrl : undefined;

  return (
    <div>
      <SearchHeader q={q} input={input} onInput={setInput} onSubmit={submit} active="news" />

      <div className="container">
        {!q && (
          <EmptyState
            title="News"
            message="Search a topic to see clustered news — try Kerala, ISRO or monsoon."
          />
        )}
        {q && loading && <Loading label="Loading news..." />}
        {q && !loading && error && (
          <ErrorState message={error} onRetry={retry} />
        )}
        {q && !loading && !error && data && data.clusters.length === 0 && (
          <EmptyState
            title="No news found"
            message={`No recent stories matched “${q}”.`}
          />
        )}
        {q && !loading && !error && data && data.clusters.length > 0 && (
          <div className="news-list">
            {data.clusters.map((c, i) => (
              <NewsCard key={c.id} cluster={c} image={thumbFor(i)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
