import { forwardRef, type InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?:   string;
  error?:   string;
  hint?:    string;
  leading?: React.ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, leading, className = "", id, ...rest }, ref) => {
    const inputId = id ?? label?.toLowerCase().replace(/\s+/g, "-");

    return (
      <div className="flex flex-col gap-1">
        {label && (
          <label htmlFor={inputId} className="text-[13px] font-medium text-gray-700">
            {label}
          </label>
        )}
        <div className="relative">
          {leading && (
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-gray-400">
              {leading}
            </div>
          )}
          <input
            ref={ref}
            id={inputId}
            className={`w-full border rounded-lg text-[13px] px-3 py-2 outline-none transition-colors
              placeholder:text-gray-400 text-gray-900
              ${leading ? "pl-9" : ""}
              ${error
                ? "border-red-400 focus:border-red-500 focus:ring-1 focus:ring-red-500"
                : "border-gray-300 focus:border-[#6B0F12] focus:ring-1 focus:ring-[#6B0F12]"
              }
              disabled:bg-gray-50 disabled:text-gray-500
              ${className}`}
            {...rest}
          />
        </div>
        {error && <p className="text-[12px] text-red-500">{error}</p>}
        {hint && !error && <p className="text-[12px] text-gray-500">{hint}</p>}
      </div>
    );
  }
);

Input.displayName = "Input";
