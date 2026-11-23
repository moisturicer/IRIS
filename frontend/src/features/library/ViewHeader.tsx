import type { ReactNode } from "react";

import { RowMenu, type RowMenuItem } from "@/features/accounts/RowMenu";

interface ViewHeaderProps {
  /** The view's name, or the field that renames it. */
  title: ReactNode;
  /** The words for the menu's name when `title` is a field. */
  name: string;
  note?: ReactNode;
  /** What the view itself offers (rename a folder, pause history…), behind one ⋯ (IR-1311). */
  menu?: RowMenuItem[];
}

/** The name of the list the rail chose, a line saying what it holds, and its ⋯ menu. */
export function ViewHeader({ title, name, note, menu = [] }: ViewHeaderProps) {
  return (
    <div className="mb-section flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h2 className="break-words font-display text-section font-semibold text-stone-900">{title}</h2>
        {note && <p className="mt-1 text-small text-stone-600">{note}</p>}
      </div>
      {menu.length > 0 && <RowMenu label={`${name} options`} items={menu} />}
    </div>
  );
}
