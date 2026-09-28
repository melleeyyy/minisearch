import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import SearchHeader from "../components/SearchHeader";
import AnswerCard from "../components/AnswerCard";
import Loading from "../components/Loading";
import ErrorState from "../components/ErrorState";
import EmptyState from "../components/EmptyState";
import { getAnswer, type AnswerResponse } from "../services/answerApi";
import { useQueryResource } from "../hooks/useQueryResource";
import { useSearchHistory } from "../hooks/useSearchHistory";

export default function Answers() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [input, setInput] = useState(q);

  useEffect(() => setInput(q), [q]);

  const { add: addToHistory } = useSearchHistory();

  const fetcher = useCallback(() => getAnswer(q), [q]);
  const { data, loading, error, retry } = useQueryResource<AnswerResponse>(
    q !== "",
    fetcher
  );

  // Remember answered queries on this device.
  useEffect(() => {
    if (data && data.ok && data.answer) addToHistory(q);
  }, [data, q, addToHistory]);

  const submit = useCallback(
    (query: string) => setParams({ q: query }),
    [setParams]
  );

  return (
    <div>
      <SearchHeader
        q={q}
        input={input}
        onInput={setInput}
        onSubmit={submit}
        active="answers"
        placeholder="Ask a question..."
      />

      <div className="container">
        {!q && (
          <EmptyState
            title="Ask MiniSearch"
            message="Answers are extracted word-for-word from indexed pages, with citations — no AI generation. Try: What is Kerala? or കേരളം എന്നാൽ എന്ത്?"
          />
        )}
        {q && loading && <Loading label="Finding an answer..." />}
        {q && !loading && error && (
          <ErrorState message={error} onRetry={retry} />
        )}
        {q && !loading && !error && data && data.ok && data.answer && (
          <AnswerCard data={data} />
        )}
        {q && !loading && !error && data && (!data.ok || !data.answer) && (
          <EmptyState
            title="Not enough evidence"
            message={`MiniSearch could not find a reliable answer to “${q}” in its indexed pages. Try rephrasing the question, or search the Web tab for related pages.`}
          />
        )}
      </div>
    </div>
  );
}
