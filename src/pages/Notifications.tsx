import { useCallback } from "react";
import TopNavigation from "../components/TopNavigation";
import Loading from "../components/Loading";
import ErrorState from "../components/ErrorState";
import SourceCard from "../components/SourceCard";
import {
  getHealth,
  getSources,
  type Health,
  type SourcesResponse,
} from "../services/api";
import { useQueryResource } from "../hooks/useQueryResource";
import { formatNumber } from "../utils/format";

interface EngineStatus {
  health: Health;
  sources: SourcesResponse;
}

export default function Notifications() {
  const fetcher = useCallback(async (): Promise<EngineStatus> => {
    const [health, sources] = await Promise.all([getHealth(), getSources()]);
    return { health, sources };
  }, []);
  const { data, loading, error, retry } = useQueryResource<EngineStatus>(
    true,
    fetcher
  );

  return (
    <div>
      <TopNavigation />
      <div className="container">
        <h1 className="page-title">Notifications</h1>
        <p className="page-subtitle">
          Live engine status — what MiniSearch has indexed right now.
        </p>

        {error && <ErrorState message={error} onRetry={retry} />}
        {!error && loading && <Loading label="Loading engine status..." />}

        {!error && data && (
          <>
            <div className="card">
              <h2>Engine</h2>
              <div className="card-row">
                <span className="k">Status</span>
                <span>
                  <span className="badge badge-blue">
                    {data.health.ok ? "healthy" : "degraded"}
                  </span>
                </span>
              </div>
              <div className="card-row">
                <span className="k">Index</span>
                <span>
                  <span className="badge">
                    {data.health.indexLoaded ? "loaded" : "empty"}
                  </span>
                </span>
              </div>
              <div className="card-row">
                <span className="k">Pages</span>
                <span>{formatNumber(data.health.pages)}</span>
              </div>
              <div className="card-row">
                <span className="k">Images</span>
                <span>{formatNumber(data.health.images)}</span>
              </div>
              <div className="card-row">
                <span className="k">Terms</span>
                <span>{formatNumber(data.health.terms)}</span>
              </div>
              <div className="card-row">
                <span className="k">Link edges</span>
                <span>{formatNumber(data.health.linkEdges)}</span>
              </div>
              <div className="card-row">
                <span className="k">Scoring engine</span>
                <span>
                  <span className="badge">
                    {data.health.cppAcceleration ? "C++ accelerated" : "pure Python"}
                  </span>
                </span>
              </div>
            </div>

            <div className="card">
              <h2>Indexed sources ({data.sources.total})</h2>
              {data.sources.sources.map((s) => (
                <SourceCard key={s.domain} source={s} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
