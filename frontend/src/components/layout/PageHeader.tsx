interface PageHeaderProps {
  title:       string;
  description?: string;
  actions?:    React.ReactNode;
}

/**
 * The head of a page: its one `h1`, a line saying what the page is for, and
 * the page's actions (IR-405; spec §4.12). The title is set in the display
 * face like every content title. On a phone the actions wrap under the title
 * rather than squeezing it.
 */
export function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 mb-section">
      <div className="min-w-0">
        <h1 className="font-display font-semibold text-title sm:text-display text-stone-900">{title}</h1>
        {description && <p className="text-body text-stone-600 mt-1 max-w-prose">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
