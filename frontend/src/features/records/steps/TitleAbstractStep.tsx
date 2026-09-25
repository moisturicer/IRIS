/**
 * Step 1 of the record creation/edit wizard.
 * Collects title and abstract.
 */
import { useFormContext } from "react-hook-form";
import type { RecordFormValues } from "../recordFormSchema";
import { FieldError } from "./FieldError";
import { LABEL, fieldClasses } from "./fieldClasses";

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
        <label className={LABEL}>
          Title <span className="text-brand">*</span>
        </label>
        <input
          {...register("title")}
          className={fieldClasses(Boolean(errors.title))}
          placeholder="Full title of the research"
        />
        {errors.title && <FieldError>{errors.title.message}</FieldError>}
      </div>

      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="text-[13px] font-medium text-stone-700">
            Abstract <span className="text-brand">*</span>
          </label>
          <span className="text-[11px] text-stone-500">{abstract.length} / 5000</span>
        </div>
        <textarea
          {...register("abstract")}
          rows={8}
          maxLength={5000}
          className={`${fieldClasses(Boolean(errors.abstract))} resize-none`}
          placeholder="Brief summary of the research..."
        />
        {errors.abstract && <FieldError>{errors.abstract.message}</FieldError>}
      </div>
    </div>
  );
}
