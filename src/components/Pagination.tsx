interface PaginationProps {
  page: number;
  totalPages: number;
  onPage: (page: number) => void;
  label?: string;
}

/** Simple prev / "page x of y" / next pager for media result pages. */
export default function Pagination({
  page,
  totalPages,
  onPage,
  label = "Pages",
}: PaginationProps) {
  if (totalPages <= 1) return null;
  return (
    <nav className="pagination" aria-label={label}>
      <button
        className="page-btn"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
      >
        ‹ Prev
      </button>
      <span className="page-btn current">
        {page} / {totalPages}
      </span>
      <button
        className="page-btn"
        disabled={page >= totalPages}
        onClick={() => onPage(page + 1)}
      >
        Next ›
      </button>
    </nav>
  );
}
