import type { User } from "@/types/auth";

/** "Maria C. Santos": the order a person's name is read aloud in. */
export function personName(user: Pick<User, "first_name" | "middle_initial" | "last_name">): string {
  const middle = user.middle_initial?.trim();
  const initial = middle ? (middle.endsWith(".") ? middle : `${middle}.`) : "";
  return [user.first_name, initial, user.last_name].map((part) => part?.trim()).filter(Boolean).join(" ");
}
