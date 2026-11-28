import { accountsApi } from "@/api/accounts";
import { useAuthStore } from "@/store/auth.store";

/**
 * "Don't show tours again" (IR-1349): one account setting, shown on every
 * student tour's card and in Settings › Help › Guided tours. While it is set
 * no tour starts by itself; Help's links still start one.
 */
export const TOURS_OFF_LABEL = "Don't show tours again";

/** Where it is turned back on. */
export const TOURS_SETTINGS_HREF = "/settings?tab=help";

/**
 * Saves it on the account. The store changes at once, so the other place it
 * is shown agrees straight away, and goes back if the server refuses.
 * Resolves to whether it was saved.
 */
export async function saveToursOff(off: boolean): Promise<boolean> {
  const before = useAuthStore.getState().user;
  if (!before) return false;
  const was = before.tours_off === true;
  useAuthStore.getState().updateUser({ ...before, tours_off: off });
  const sameAccount = () => {
    const now = useAuthStore.getState().user;
    return now && now.id === before.id ? now : null;
  };
  try {
    const { data } = await accountsApi.setToursOff(off);
    const now = sameAccount();
    if (now && typeof data?.tours_off === "boolean") {
      useAuthStore.getState().updateUser({ ...now, tours_off: data.tours_off });
    }
    return true;
  } catch {
    const now = sameAccount();
    if (now) useAuthStore.getState().updateUser({ ...now, tours_off: was });
    return false;
  }
}
