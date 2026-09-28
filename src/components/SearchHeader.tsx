import Logo from "./Logo";
import SearchBar from "./SearchBar";
import SearchTabs, { type TabKey } from "./SearchTabs";
import type { FocusEvent, ReactNode } from "react";

interface SearchHeaderProps {
  q: string;
  input: string;
  onInput: (q: string) => void;
  onSubmit: (q: string) => void;
  active: TabKey;
  placeholder?: string;
  onSearchFocus?: () => void;
  onSearchBlur?: () => void;
  /** Rendered inside the search wrapper (e.g. the suggestions dropdown). */
  children?: ReactNode;
}

/** Shared header for all search pages: logo, search bar and tabs. */
export default function SearchHeader({
  q,
  input,
  onInput,
  onSubmit,
  active,
  placeholder,
  onSearchFocus,
  onSearchBlur,
  children,
}: SearchHeaderProps) {
  return (
    <header className="page-header">
      <div className="page-header-inner">
        <div className="page-header-row">
          <Logo size="sm" linked />
          <div
            className="page-header-search"
            onFocus={(_e: FocusEvent) => onSearchFocus?.()}
            onBlur={(_e: FocusEvent) => onSearchBlur?.()}
          >
            <SearchBar
              value={input}
              onChange={onInput}
              onSubmit={onSubmit}
              size="sm"
              placeholder={placeholder}
            />
            {children}
          </div>
        </div>
        <SearchTabs q={q} active={active} />
      </div>
    </header>
  );
}
