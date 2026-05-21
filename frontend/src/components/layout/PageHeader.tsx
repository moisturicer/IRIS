interface PageHeaderProps {
  title:       string;
  description?: string;
  actions?:    React.ReactNode;
}

export function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <div className="flex items-start justify-between mb-6">
      <div>
        <h1 className="text-[20px] font-bold text-gray-900">{title}</h1>
        {description && <p className="text-[13px] text-gray-500 mt-1">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
