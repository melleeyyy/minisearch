import { useCallback } from "react";
import { Link } from "react-router-dom";
import TopNavigation from "../components/TopNavigation";
import Loading from "../components/Loading";
import ErrorState from "../components/ErrorState";
import { getStats, type StatsResponse } from "../services/api";
import { useQueryResource } from "../hooks/useQueryResource";
import { useSearchHistory } from "../hooks/useSearchHistory";
import { formatMs, formatNumber, formatPercent, timeAgo } from "../utils/format";

export default function Activity() {
  const fetcher = useCallback(() => getStats(), []);
  const { data, loading, error, retry } = useQueryResource<StatsResponse>(
    true,
    fetcher
  );
  const { entries, clear } = useSearchHistory();
  const analytics = data?.analytics ?? {};

  return (
    <div>
      <TopNavigation />
      <div className="container">
        <h1 className="page-title">Activity</h1>
        <p className="page-subtitle">
          Your recent searches (stored only on this device) and anonymous engine
          analytics.
        </p>

        <div className="card">
          <h2>Recent searches</h2>
          {entries.length === 0 ? (
            <p className="state-text" style={{ margin: "8px 0" }}>
              No searches yet on this device.
            </p>
          ) : (
            <>
              {entries.slice(0, 12).map((e) => (
                <div className="history-item" key={`${e.q}-${e.ts}`}>
                  <Link className="q" to={`/search?q=${encodeURIComponent(e.q)}`}>
                    {e.q}
                  </Link>
                  <span className="t">{timeAgo(e.ts)}</span>
                </div>
              ))}
              <button className="btn btn-ghost state-action" onClick={clear}>
                Clear history
              </button>
            </>
          )}
        </div>

        {error && <ErrorState message={error} onRetry={retry} />}
        {!error && loading && <Loading label="Loading analytics..." />}

        {!error && data && (
          <>
            <div className="card">
              <h2>Engine analytics</h2>
              <div className="card-row">
                <span className="k">Queries served</span>
                <span>{formatNumber(analytics.queries ?? 0)}</span>
              </div>
              <div className="card-row">
                <span className="k">Avg response</span>
                <span>{formatMs(analytics.avgResponseMs)}</span>
              </div>
              <div className="card-row">
                <span className="k">p50 / p95</span>
                <span>
                  {formatMs(analytics.p50ResponseMs)} / {formatMs(analytics.p95ResponseMs)}
                </span>
              </div>
              <div className="card-row">
                <span className="k">Cache hit rate</span>
                <span>{formatPercent(analytics.cacheHitRate)}</span>
              </div>
            </div>

            {analytics.topQueries && analytics.topQueries.length > 0 && (
              <div className="card">
                <h2>Top queries (anonymous)</h2>
                <div className="chip-list">
                  {analytics.topQueries.map((q) => (
                    <Link
                      key={q}
                      className="chip"
                      to={`/search?q=${encodeURIComponent(q)}`}
                    >
                      {q}
                    </Link>
                  ))}
                </div>
              </div>
            )}

            {analytics.zeroResultQueries && analytics.zeroResultQueries.length > 0 && (
              <div className="card">
                <h2>Queries with no results</h2>
                <div className="chip-list">
                  {analytics.zeroResultQueries.map((q) => (
                    <span key={q} className="chip">
                      {q}
                    </span>
                  ))}
                </div>
                <p className="state-text" style={{ marginTop: 10 }}>
                  These find nothing in the current index — the crawl may not cover
                  them yet.
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
