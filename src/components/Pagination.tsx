interface PaginationProps {
  page: number;
  totalPages: number;
  onPage: (page: number) => void;
  label?: string;
}

/** A single "More search" button that loads the next page of results. */
export default function Pagination({
  page,
  totalPages,
  onPage,
  label = "results",
}: PaginationProps) {
  if (totalPages <= 1 || page >= totalPages) return null;
  return (
    <div className="more-search">
      <button
        type="button"
        className="more-search-btn"
        onClick={() => onPage(page + 1)}
        aria-label={`Load more ${label}`}
      >
        More search
      </button>
    </div>
  );
}
