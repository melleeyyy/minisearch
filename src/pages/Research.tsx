import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import SearchHeader from "../components/SearchHeader";
import ResearchCard from "../components/ResearchCard";
import Loading from "../components/Loading";
import ErrorState from "../components/ErrorState";
import EmptyState from "../components/EmptyState";
import { getResearch, type ResearchResponse } from "../services/knowledgeApi";
import { useQueryResource } from "../hooks/useQueryResource";

/** Research tab: merged arXiv / PubMed / Crossref / OpenAlex. */
export default function Research() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [input, setInput] = useState(q);

  useEffect(() => setInput(q), [q]);

  const fetcher = useCallback(() => getResearch(q), [q]);
  const { data, loading, error, retry } = useQueryResource<ResearchResponse>(
    q !== "",
    fetcher
  );

  const submit = useCallback(
    (query: string) => setParams({ q: query, page: "1" }),
    [setParams]
  );

  return (
    <div>
      <SearchHeader q={q} input={input} onInput={setInput} onSubmit={submit} active="research" />

      <div className="container">
        {!q && (
          <EmptyState
            title="Research"
            message="Search across arXiv, PubMed, Crossref and OpenAlex — free scholarly sources."
          />
        )}
        {q && loading && <Loading label="Searching papers..." />}
        {q && !loading && error && (
          <ErrorState message={error} onRetry={retry} />
        )}
        {q && !loading && !error && data && data.results.length === 0 && (
          <EmptyState
            title="No papers found"
            message={`No scholarly results matched “${q}”.`}
          />
        )}
        {q && !loading && !error && data && data.results.length > 0 && (
          <div className="research-list">
            {data.results.map((r, i) => (
              <ResearchCard key={`${r.url}-${i}`} item={r} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
