import { Link } from "react-router-dom";
import type { SearchResponse } from "../services/searchApi";
import { formatNumber } from "../utils/format";
import SearchResult from "./SearchResult";

interface SearchResultsProps {
  data: SearchResponse;
  onPage: (page: number) => void;
}

export default function SearchResults({ data, onPage }: SearchResultsProps) {
  const { results, total, page, limit, did_you_mean: dym, query } = data;

  return (
    <div>
      {dym && (
        <p className="did-you-mean">
          Did you mean{" "}
          <Link
            to={`/search?q=${encodeURIComponent(dym)}`}
            onClick={() => onPage(1)}
          >
            {dym}
          </Link>
          ?
        </p>
      )}

      <p className="result-count">
        About {formatNumber(total)} result{total === 1 ? "" : "s"} for “{query}”
      </p>

      <div>
        {results.map((r) => (
          <SearchResult key={r.url} item={r} />
        ))}
      </div>

      {page * limit < total && (
        <div className="more-search">
          <button
            type="button"
            className="more-search-btn"
            onClick={() => onPage(page + 1)}
          >
            More search
          </button>
        </div>
      )}
    </div>
  );
}
