import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { authApi } from "@/api/auth";
import { useAuth } from "@/hooks/useAuth";
import { useRole } from "@/hooks/useRole";
import { pathFor } from "@/lib/access";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";

interface AccountMenuProps {
  /** The desktop rail is collapsed: show the avatar alone, open to the right. */
  collapsed: boolean;
  /** Called after an item is chosen, so the phone drawer can close. */
  onNavigate?: () => void;
}

const ITEM =
  `flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm text-stone-700 hover:bg-stone-100 hover:text-stone-900 ${COLOUR_TRANSITION} ${FOCUS_RING}`;

/**
 * The account menu in the sidebar's user block (IR-413, spec §4.2).
 *
 * Settings & Profile, Help and Sign out live here rather than in the nav
 * list: they are about the person, not places in the research. A disclosure
 * (a button that shows and hides a list of links), not an ARIA `menu` --
 * every item is a plain link or button, so Tab and Enter behave exactly as
 * they do everywhere else on the page.
 *
 * Escape closes it and returns focus to the trigger; so does a click outside
 * or Tab leaving it. It opens upward above the user block, or to the right
 * of the collapsed rail.
 */
export function AccountMenu({ collapsed, onNavigate }: AccountMenuProps) {
  const { user, refreshToken, logout } = useAuth();
  const { roleName } = useRole();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  const fullName = [user?.first_name, user?.last_name].filter(Boolean).join(" ") || user?.email || "Your account";
  const initials = `${user?.first_name?.[0] ?? ""}${user?.last_name?.[0] ?? ""}`.toUpperCase() || "?";
  const subtitle = roleName ?? user?.email ?? "";

  const choose = () => {
    setOpen(false);
    onNavigate?.();
  };

  const handleSignOut = async () => {
    setOpen(false);
    await authApi.logout(refreshToken ?? "").catch(() => {});
    logout();
  };

  return (
    <div
      ref={containerRef}
      className="relative"
      // Escape is handled here, not on the document, so it closes only this
      // menu: stopping it keeps the phone drawer around it open (AppShell
      // listens on the document).
      onKeyDown={(e) => {
        if (e.key !== "Escape" || !open) return;
        e.stopPropagation();
        setOpen(false);
        triggerRef.current?.focus();
      }}
      onBlur={(e) => {
        if (open && !e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(false);
      }}
    >
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={open}
        aria-controls={menuId}
        // The visible name and role, in order, then what the button does.
        aria-label={[fullName, subtitle, "account menu"].filter(Boolean).join(", ")}
        title={collapsed ? fullName : undefined}
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "flex w-full items-center gap-3 rounded-lg p-2 text-left hover:bg-stone-100",
          open && "bg-stone-100",
          collapsed && "md:justify-center md:p-1",
          COLOUR_TRANSITION,
          FOCUS_RING,
        )}
      >
        <span
          aria-hidden
          className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-brand text-2xs font-semibold text-white"
        >
          {initials}
        </span>
        <span className={cn("min-w-0 flex-1", collapsed && "md:sr-only")}>
          <span className="block truncate text-xs font-semibold text-stone-900">{fullName}</span>
          <span className="block truncate text-2xs text-stone-500">{subtitle}</span>
        </span>
        <i
          aria-hidden
          className={cn(
            "fas fa-chevron-up text-3xs text-stone-400 transition-transform duration-150 motion-reduce:transition-none",
            !open && "rotate-180",
            collapsed && "md:hidden",
          )}
        />
      </button>

      {open && (
        <div
          id={menuId}
          className={cn(
            "absolute bottom-full left-0 right-0 z-50 mb-2 rounded-lg border border-stone-200 bg-white p-1.5 shadow-card-md animate-fade-in motion-reduce:animate-none",
            collapsed && "md:bottom-0 md:left-full md:right-auto md:mb-0 md:ml-3 md:w-60",
          )}
        >
          <div className="border-b border-stone-100 px-3 pb-2 pt-1.5">
            <p className="truncate text-xs font-semibold text-stone-900">{fullName}</p>
            {user?.email && <p className="truncate text-2xs text-stone-500">{user.email}</p>}
          </div>
          <ul role="list" className="pt-1.5">
            <li>
              <Link to={pathFor("settings")} onClick={choose} className={ITEM}>
                <i aria-hidden className="fas fa-gear w-4 text-center text-stone-500" />
                Settings &amp; Profile
              </Link>
            </li>
            <li>
              <Link to={pathFor("help")} onClick={choose} className={ITEM}>
                <i aria-hidden className="fas fa-circle-question w-4 text-center text-stone-500" />
                Help
              </Link>
            </li>
            <li className="mt-1.5 border-t border-stone-100 pt-1.5">
              <button type="button" onClick={handleSignOut} className={ITEM}>
                <i aria-hidden className="fas fa-arrow-right-from-bracket w-4 text-center text-stone-500" />
                Sign out
              </button>
            </li>
          </ul>
        </div>
      )}
    </div>
  );
}
