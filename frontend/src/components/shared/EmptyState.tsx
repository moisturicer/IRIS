interface EmptyStateProps {
  icon?:    string;
  title:    string;
  message?: string;
}

export function EmptyState({ icon = "fa-inbox", title, message }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-gray-400">
      <i className={`fas ${icon} text-4xl mb-3`} />
      <p className="text-[14px] font-semibold text-gray-500">{title}</p>
      {message && <p className="text-[12px] mt-1">{message}</p>}
    </div>
  );
}
