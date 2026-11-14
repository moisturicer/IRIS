import { Outlet } from "react-router-dom";

import { useRouteDocumentTitle } from "@/hooks/useDocumentTitle";

/**
 * The root of the route table (IR-1073). It sits above the shell, not in it, so
 * the public pages -- sign in, sign up, recovery -- are named too.
 */
export function RouteTitle() {
  useRouteDocumentTitle();
  return <Outlet />;
}
