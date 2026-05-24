import { Link, useMatches } from "react-router-dom";

export type RouteHandle = {
  crumb?: string;
};

export function Breadcrumbs() {
  const matches = useMatches();
  const crumbs = matches.filter((m) => (m.handle as RouteHandle | undefined)?.crumb);

  if (crumbs.length === 0) return null;

  return (
    <nav aria-label="Breadcrumb" className="mb-4">
      <ol className="flex flex-wrap items-center gap-1.5 text-[12px] text-gray-500">
        <li>
          <Link to="/" className="hover:text-brand transition-colors font-medium">
            Home
          </Link>
        </li>
        {crumbs.map((match, index) => {
          const label = (match.handle as RouteHandle).crumb!;
          const isLast = index === crumbs.length - 1;
          const path = match.pathname;

          return (
            <li key={path} className="flex items-center gap-1.5">
              <span className="text-gray-300" aria-hidden>
                /
              </span>
              {isLast ? (
                <span className="text-gray-800 font-semibold" aria-current="page">
                  {label}
                </span>
              ) : (
                <Link to={path} className="hover:text-brand transition-colors font-medium">
                  {label}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
