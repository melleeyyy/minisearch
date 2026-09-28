import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import SearchHeader from "../components/SearchHeader";
import NewsCard from "../components/NewsCard";
import Loading from "../components/Loading";
import ErrorState from "../components/ErrorState";
import EmptyState from "../components/EmptyState";
import { getNews, type NewsResponse } from "../services/knowledgeApi";
import { useQueryResource } from "../hooks/useQueryResource";

/** News tab: clustered, deduplicated news for a query. */
export default function News() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [input, setInput] = useState(q);

  useEffect(() => setInput(q), [q]);

  const fetcher = useCallback(() => getNews(q), [q]);
  const { data, loading, error, retry } = useQueryResource<NewsResponse>(
    q !== "",
    fetcher
  );

  const submit = useCallback(
    (query: string) => setParams({ q: query, page: "1" }),
    [setParams]
  );

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
            {data.clusters.map((c) => (
              <NewsCard key={c.id} cluster={c} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
