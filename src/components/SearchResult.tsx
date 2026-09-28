import type { SearchResultItem } from "../services/searchApi";
import { timeAgo } from "../utils/format";
import { cleanSnippetHtml } from "../utils/sanitize";

/** URL path without scheme/domain — shown as a readable one-line breadcrumb. */
function urlPath(displayUrl: string): string {
  const rest = displayUrl
    .replace(/^[a-z]+:\/\/[^/]+/i, "")
    .replace(/^\/+/, "");
  let out = rest ? `/${rest}` : "/";
  const truncated = /…$/.test(out);
  if (truncated) out = out.replace(/…$/, "");
  try {
    out = decodeURIComponent(out);
  } catch {
    // Backend truncation ("…") can split a %XX escape or leave a lone
    // incomplete escape at the end — decode run-wise, dropping trailing
    // escapes of a run until it becomes valid UTF-8.
    out = out.replace(/(?:%[0-9a-fA-F]{2})+/g, (m) => {
      let run = m;
      while (run.length >= 3) {
        try {
          return decodeURIComponent(run);
        } catch {
          run = run.slice(0, -3);
        }
      }
      return "";
    });
  }
  out = out.replace(/%[0-9a-fA-F]{0,2}$/, "").replace(/[_\s]+$/, "");
  return out.replace(/_/g, " ") + (truncated ? "…" : "");
}

export default function SearchResult({ item }: { item: SearchResultItem }) {
  return (
    <article className="result">
      <div className="result-head">
        <span className="result-favicon" aria-hidden="true">
          {(item.domain || "?").replace(/^www\./, "").charAt(0).toUpperCase()}
        </span>
        <div className="result-head-text">
          <span className="result-site" title={item.domain}>
            {item.domain || item.url}
          </span>
          <span className="result-path" title={item.displayUrl}>
            {urlPath(item.displayUrl)}
          </span>
        </div>
      </div>
      <h3 className="result-title">
        <a href={item.url} target="_blank" rel="noopener noreferrer">
          {item.title}
        </a>
      </h3>
      <p
        className="result-snippet"
        dangerouslySetInnerHTML={{ __html: cleanSnippetHtml(item.snippet) }}
      />
      <div className="result-foot">
        {item.language && <span>{item.language}</span>}
        {item.crawledAt && <span>indexed {timeAgo(item.crawledAt)}</span>}
      </div>
    </article>
  );
}
