import Logo from "./Logo";

/** Slim page header for non-search pages (Notifications, Activity). */
export default function TopNavigation() {
  return (
    <header className="top-nav">
      <div className="top-nav-inner">
        <Logo size="sm" linked />
      </div>
    </header>
  );
}
