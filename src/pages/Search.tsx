import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import SearchHeader from "../components/SearchHeader";
import SearchSuggestions from "../components/SearchSuggestions";
import SearchResults from "../components/SearchResults";
import EntityCardView from "../components/EntityCard";
import Loading from "../components/Loading";
import ErrorState from "../components/ErrorState";
import EmptyState from "../components/EmptyState";
import { search, type SearchResponse } from "../services/searchApi";
import {
  getEntityCard,
  getPlaceCard,
  type EntityCard,
} from "../services/knowledgeApi";
import { useQueryResource } from "../hooks/useQueryResource";
import { useSuggestions } from "../hooks/useSuggestions";
import { useEntityPreview } from "../hooks/useEntityPreview";
import { useSearchHistory } from "../hooks/useSearchHistory";

export default function Search() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const page = Math.max(1, Number(params.get("page")) || 1);

  const [input, setInput] = useState(q);
  const [focused, setFocused] = useState(false);
  const [entity, setEntity] = useState<EntityCard | null>(null);

  useEffect(() => setInput(q), [q]);

  const suggestions = useSuggestions(input, focused && input.trim().length >= 2);
  const entityPreview = useEntityPreview(
    input,
    focused && input.trim().length >= 3
  );
  const { add: addToHistory } = useSearchHistory();

  const fetcher = useCallback(
    () => search(q, page, 10),
    [q, page]
  );
  const { data, loading, error, retry } = useQueryResource<SearchResponse>(
    q !== "",
    fetcher
  );

  // Remember successful first-page searches on this device.
  useEffect(() => {
    if (page === 1 && data && data.results.length > 0) addToHistory(q);
  }, [data, page, q, addToHistory]);

  // Knowledge card for entity-like queries (place cards carry weather +
  // flag). Failures degrade silently — web results still show.
  useEffect(() => {
    if (!q) return;
    let alive = true;
    setEntity(null);
    getPlaceCard(q)
      .then((r) => {
        if (!alive) return;
        if (r.place) {
          setEntity(r.place);
          return;
        }
        return getEntityCard(q).then((r2) => {
          if (alive) setEntity(r2.entity ?? null);
        });
      })
      .catch(() => {
        if (alive) setEntity(null);
      });
    return () => {
      alive = false;
    };
  }, [q]);

  const submit = useCallback(
    (query: string) => {
      setFocused(false);
      setParams({ q: query, page: "1" });
    },
    [setParams]
  );

  const goPage = useCallback(
    (p: number) => {
      setParams({ q, page: String(p) });
      window.scrollTo(0, 0);
    },
    [q, setParams]
  );

  return (
    <div>
      <SearchHeader
        q={q}
        input={input}
        onInput={setInput}
        onSubmit={submit}
        active="web"
        onSearchFocus={() => setFocused(true)}
        onSearchBlur={() => setFocused(false)}
      >
        {focused && (suggestions.length > 0 || entityPreview) && (
          <SearchSuggestions
            suggestions={suggestions}
            onPick={submit}
            entity={entityPreview}
          />
        )}
      </SearchHeader>

      <div className="container">
        {!q && (
          <EmptyState
            title="Search MiniSearch"
            message="Type a query above — try കേരളം, search engine, or ISRO."
          />
        )}

        {q && loading && <Loading label="Searching..." />}
        {q && !loading && error && (
          <ErrorState message={error} onRetry={retry} />
        )}
        {q && !loading && !error && data && data.results.length === 0 && (
          <EmptyState
            title="No results found"
            message={
              data.did_you_mean
                ? `No pages matched “${q}”. Did you mean “${data.did_you_mean}”?`
                : `No pages matched “${q}”. The crawl is focused — try a different or broader query.`
            }
          />
        )}
        {q && !loading && !error && entity && (
          <EntityCardView data={entity} />
        )}
        {q && !loading && !error && data && data.results.length > 0 && (
          <SearchResults data={data} onPage={goPage} />
        )}
      </div>
    </div>
  );
}
