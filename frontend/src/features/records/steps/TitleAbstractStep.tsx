/**
 * Step 1 of the record creation/edit wizard.
 * Collects title and abstract.
 */
import { useFormContext } from "react-hook-form";
import { Input }  from "@/components/ui/Input";
import type { RecordFormValues } from "../recordFormSchema";

export function TitleAbstractStep() {
  const {
    register,
    watch,
    formState: { errors },
  } = useFormContext<RecordFormValues>();

  const abstract = watch("abstract") ?? "";

  return (
    <div className="flex flex-col gap-5">
      <div>
        <label className="block text-[13px] font-medium text-gray-700 mb-1">
          Title <span className="text-red-500">*</span>
        </label>
        <input
          {...register("title")}
          className={`w-full border rounded-lg px-3 py-2 text-[13px] outline-none transition-colors
            ${errors.title
              ? "border-red-400 focus:border-red-500"
              : "border-gray-300 focus:border-[#6B0F12]"
            } focus:ring-1`}
          placeholder="Full title of the research"
        />
        {errors.title && (
          <p className="text-[12px] text-red-500 mt-1">{errors.title.message}</p>
        )}
      </div>

      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="text-[13px] font-medium text-gray-700">
            Abstract <span className="text-red-500">*</span>
          </label>
          <span className="text-[11px] text-gray-400">{abstract.length} / 5000</span>
        </div>
        <textarea
          {...register("abstract")}
          rows={8}
          maxLength={5000}
          className={`w-full border rounded-lg px-3 py-2 text-[13px] outline-none transition-colors resize-none
            ${errors.abstract
              ? "border-red-400 focus:border-red-500"
              : "border-gray-300 focus:border-[#6B0F12]"
            } focus:ring-1`}
          placeholder="Brief summary of the research..."
        />
        {errors.abstract && (
          <p className="text-[12px] text-red-500 mt-1">{errors.abstract.message}</p>
        )}
      </div>
    </div>
  );
}
