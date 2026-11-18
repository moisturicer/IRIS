import { create } from "zustand";
import { useNoticeStore } from "./notice.store";
import { isAcceptanceRequired } from "@/lib/noticeErrors";
import type { User } from "@/types/auth";
import { authApi } from "@/api/auth";
import { clearAuthSession } from "@/lib/authStorage";
import { __resetRefreshState, refreshOnce, withRefreshLock } from "@/lib/tokenRefresh";
import { clearOldBrowserLibrary } from "@/lib/recordLibrary";
import { REVIEWER_ROLES, STAFF_ROLES, type RoleName } from "@/lib/constants";

/** The server's answer to a refresh with no cookie: signed out, not a session that ended (ADR-072). */
export const NO_SESSION = "no_session";

interface AuthState {
  user:            User | null;
  accessToken:     string | null;
  isAuthenticated: boolean;
  /**
   * "Keep me signed in" (ADR-072): the session lasts 30 days from sign-in and
   * the idle rule doesn't end it, so the browser's idle watch stays off.
   */
  remembered:      boolean;
  /** False until we have asked the server for a session on load (ADR-072). */
  authReady:       boolean;
  /**
   * Bumped by `login`/`logout`/`clearTokens`. `client.ts` captures this before starting a
   * refresh and checks it again after the refresh resolves: if it moved, the
   * session that requested the refresh no longer exists, so the result is
   * discarded instead of reviving a session the user already signed out of.
   * `__resetRefreshState` alone doesn't cover this -- it only stops a *future*
   * caller from joining a stale in-flight promise; it can't reach into the one a
   * request is already `await`ing.
   */
  sessionEpoch: number;
  /**
   * Set when a session this browser held could not be restored on load
   * (IR-1081, audit FB-01), with the server's reason if it gave one. Without
   * it the route guard cannot tell that from never having signed in, and a
   * reload that ended on sign-in said nothing. Cleared by the next sign-in.
   */
  sessionLost: { code: string | null } | null;

  login:      (user: User, access: string, remembered?: boolean) => void;
  logout:     () => void;
  updateUser: (user: User) => void;
  setTokens:  (access: string, remembered?: boolean) => void;
  clearTokens: () => void;
  hydrateAuth: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()((set, get) => ({
  user:            null,
  accessToken:     null,
  isAuthenticated: false,
  remembered:      false,
  authReady:       false,
  sessionEpoch:    0,
  sessionLost:     null,

  login: (user, access, remembered = false) => {
    // The refresh token is in the server's HttpOnly cookie (ADR-072); this only
    // clears keys earlier versions stored.
    clearAuthSession();
    // Delete what an older build kept of the library in this browser (history,
    // folders, stars; the account holds the library now, IR-566/572/756/579).
    // A sign-in may follow someone who closed the tab without signing out, so
    // their copy must not greet the next person.
    clearOldBrowserLibrary();
    // A sign-in is a new session even with no sign-out before it: `/login` has
    // no guard, so a signed-in account can open it and sign in as someone else
    // (IR-746). Anything still in flight for the session it replaces -- a token
    // refresh, a notifications fetch -- must be discarded, not applied to it.
    set((s) => ({
      user,
      accessToken: access,
      remembered,
      isAuthenticated: true,
      sessionLost: null,
      sessionEpoch: s.sessionEpoch + 1,
    }));
  },

  logout: () => {
    // Drop any refresh already in flight so a *future* caller doesn't join it.
    // This alone is not enough: a request already `await`ing the old promise in
    // client.ts still resolves and would otherwise call setTokens after logout,
    // quietly re-authenticating the browser the user just signed out of. Bumping
    // sessionEpoch is what lets that caller notice and discard its result.
    __resetRefreshState();
    useNoticeStore.getState().clear();
    clearAuthSession();
    clearOldBrowserLibrary();
    set((s) => ({
      user: null,
      accessToken: null,
      remembered: false,
      isAuthenticated: false,
      sessionEpoch: s.sessionEpoch + 1,
    }));
  },

  updateUser: (user) => set({ user }),

  setTokens: (access, remembered) => {
    set((s) => ({
      accessToken: access,
      remembered: remembered ?? s.remembered,
      isAuthenticated: true,
    }));
  },

  clearTokens: () => {
    __resetRefreshState();
    clearAuthSession();
    clearOldBrowserLibrary();
    set((s) => ({
      accessToken: null,
      remembered: false,
      isAuthenticated: false,
      sessionEpoch: s.sessionEpoch + 1,
    }));
  },

  hydrateAuth: async () => {
    // Keys an earlier version kept in this browser's own storage (ADR-072).
    clearAuthSession();
    // Whether the server gave this browser a session before anything failed.
    let restored = false;
    try {
      /**
       * Always asked, never assumed (ADR-072 decision 2).
       *
       * The refresh token is in an HttpOnly cookie this code can't see, so the
       * only way to know whether this browser is signed in is to ask. The
       * browser sends the cookie; with none, the server answers `no_session`.
       *
       * Through the gate and the lock, not around them (IR-238, decision 6).
       * `React.StrictMode` double-invokes effects in development, and every tab
       * presents the same cookie, which the server rotates and blacklists:
       * `refreshOnce` joins this tab's calls, and `withRefreshLock` makes tabs
       * take turns, so the cookie is never presented twice.
       */
      const tokens = await refreshOnce(() => withRefreshLock(() => authApi.refreshToken()));

      restored = true;
      set({
        accessToken: tokens.access,
        remembered: tokens.remembered,
        isAuthenticated: true,
      });

      const { data: user } = await authApi.me();
      set({ user });
    } catch (err) {
      // The session is good but the current data notice is unanswered, so the
      // server refuses `me` (IR-790). Keep the session: the guard shows the
      // notice screen, and the account loads once they answer.
      if (isAcceptanceRequired(err)) {
        useNoticeStore.getState().require();
        return;
      }
      get().logout();
      const response = (err as { response?: { status?: number; data?: { code?: unknown } } })?.response;
      const code = response?.data?.code;
      // Say a session ended only when one did: the server refused this
      // browser's session (a 401 naming why), or restored it and the account
      // then failed to load. No cookie (`no_session`) is a signed-out visitor,
      // and a server that couldn't be reached says nothing either way: the
      // cookie can't be read here, so there may never have been a session.
      const refused = response?.status === 401 && code !== NO_SESSION;
      if (!restored && !refused) return;
      // After `logout`, which would otherwise be read as an ordinary sign-out.
      set({ sessionLost: { code: typeof code === "string" ? code : null } });
    } finally {
      set({ authReady: true });
    }
  },
}));

export const useRole    = () => useAuthStore((s) => s.user?.role_name ?? null);
export const useIsReviewer = () => useAuthStore((s) => REVIEWER_ROLES.includes(s.user?.role_name as RoleName));
export const useIsStaff    = () => useAuthStore((s) => STAFF_ROLES.includes(s.user?.role_name as RoleName));
