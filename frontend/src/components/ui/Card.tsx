import type { ReactNode } from "react";

interface CardProps {
  children:  ReactNode;
  className?: string;
  padding?:   boolean;
}

export function Card({ children, className = "", padding = true }: CardProps) {
  return (
    <div className={`bg-white rounded-xl border border-gray-200 overflow-hidden ${padding ? "p-5" : ""} ${className}`}>
      {children}
    </div>
  );
}

export function CardHeader({ title, description }: { title: string; description?: string }) {
  return (
    <div className="mb-4">
      <h3 className="text-[15px] font-semibold text-gray-900">{title}</h3>
      {description && <p className="text-[13px] text-gray-500 mt-0.5">{description}</p>}
    </div>
  );
}
