import { useState } from "react";
import type { NewsCluster } from "../services/knowledgeApi";
import { cleanSnippetText, stripHtml } from "../utils/sanitize";
import { timeAgo } from "../utils/format";

/** One clustered news story with corroboration badge. */
export default function NewsCard({ cluster }: { cluster: NewsCluster }) {
  const [open, setOpen] = useState(false);
  const [top, ...rest] = cluster.items;
  if (!top) return null;
  // Feeds sometimes carry raw HTML (Google News RSS markup) — render clean text only.
  const title = stripHtml(top.title);
  const source = stripHtml(top.source);
  const summary = top.summary ? cleanSnippetText(stripHtml(top.summary)) : "";
  return (
    <article className="news-card">
      <div className="news-card-badges">
        {cluster.reportedBy > 1 && (
          <span className="news-badge">
            reported by {cluster.reportedBy} sources
          </span>
        )}
        {cluster.published && (
          <span className="news-time">{timeAgo(cluster.published)}</span>
        )}
      </div>
      <h3 className="news-title">
        <a href={top.url} target="_blank" rel="noreferrer">{title}</a>
      </h3>
      <p className="news-source">{source}</p>
      {summary && (
        <p className="news-summary">{summary}</p>
      )}
      {rest.length > 0 && (
        <div className="news-rest">
          <button
            type="button"
            className="news-more"
            onClick={() => setOpen(!open)}
            aria-expanded={open}
          >
            {open
              ? "Hide other sources"
              : `+ ${rest.length} more source${rest.length > 1 ? "s" : ""}`}
          </button>
          {open && (
            <ul className="news-rest-list">
              {rest.map((it) => (
                <li key={it.url}>
                  <a href={it.url} target="_blank" rel="noreferrer">{stripHtml(it.title)}</a>
                  <span className="news-rest-source"> — {stripHtml(it.source)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </article>
  );
}
