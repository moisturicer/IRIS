/**
 * Step 2 of the record creation/edit wizard.
 * Collects: year, record type, research type, authors (free text), keywords (tag input).
 * TODO: replace authors free-text with user search autocomplete.
 * TODO: replace keyword input with a tag-chips component.
 */
import { useState } from "react";
import { useFormContext } from "react-hook-form";
import { Input } from "@/components/ui/Input";
import type { RecordFormValues } from "../recordFormSchema";

// TODO: fetch these from /api/v1/record-types/ and /api/v1/research-types/
const RECORD_TYPE_OPTIONS = [
  { value: "1", label: "Thesis" },
  { value: "2", label: "Capstone" },
  { value: "3", label: "Research Paper" },
  { value: "4", label: "Project" },
];

const RESEARCH_TYPE_OPTIONS = [
  { value: "1", label: "Applied" },
  { value: "2", label: "Basic" },
  { value: "3", label: "Action" },
  { value: "4", label: "Mixed" },
];

export function RecordDetailsStep() {
  const {
    register,
    formState: { errors },
    watch,
    setValue,
  } = useFormContext<RecordFormValues>();

  const authors  = watch("authors") ?? [];
  const keywords = watch("keywords") ?? [];

  const [authorInput, setAuthorInput]   = useState("");
  const [keywordInput, setKeywordInput] = useState("");

  const addAuthor = () => {
    const trimmed = authorInput.trim();
    if (trimmed && !authors.includes(trimmed)) {
      setValue("authors", [...authors, trimmed], { shouldValidate: true });
    }
    setAuthorInput("");
  };

  const removeAuthor = (idx: number) => {
    setValue("authors", authors.filter((_, i) => i !== idx), { shouldValidate: true });
  };

  const addKeyword = () => {
    const trimmed = keywordInput.trim().toLowerCase();
    if (trimmed && !keywords.includes(trimmed)) {
      setValue("keywords", [...keywords, trimmed], { shouldValidate: true });
    }
    setKeywordInput("");
  };

  const removeKeyword = (idx: number) => {
    setValue("keywords", keywords.filter((_, i) => i !== idx), { shouldValidate: true });
  };

  return (
    <div className="flex flex-col gap-5">
      {/* Year */}
      <Input
        label="Publication Year"
        type="number"
        {...register("year", { valueAsNumber: true })}
        error={errors.year?.message}
      />

      {/* Record type */}
      <div>
        <label className="block text-[13px] font-medium text-gray-700 mb-1">
          Record Type <span className="text-red-500">*</span>
        </label>
        <select
          {...register("record_type")}
          className={`w-full border rounded-lg px-3 py-2 text-[13px] outline-none transition-colors
            ${errors.record_type
              ? "border-red-400 focus:border-red-500"
              : "border-gray-300 focus:border-[#6B0F12]"
            } focus:ring-1`}
        >
          <option value="">Select record type</option>
          {RECORD_TYPE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        {errors.record_type && (
          <p className="text-[12px] text-red-500 mt-1">{errors.record_type.message}</p>
        )}
      </div>

      {/* Research type */}
      <div>
        <label className="block text-[13px] font-medium text-gray-700 mb-1">
          Research Type <span className="text-red-500">*</span>
        </label>
        <select
          {...register("research_type")}
          className={`w-full border rounded-lg px-3 py-2 text-[13px] outline-none transition-colors
            ${errors.research_type
              ? "border-red-400 focus:border-red-500"
              : "border-gray-300 focus:border-[#6B0F12]"
            } focus:ring-1`}
        >
          <option value="">Select research type</option>
          {RESEARCH_TYPE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        {errors.research_type && (
          <p className="text-[12px] text-red-500 mt-1">{errors.research_type.message}</p>
        )}
      </div>

      {/* Authors */}
      <div>
        <label className="block text-[13px] font-medium text-gray-700 mb-1">Authors</label>
        <div className="flex gap-2 mb-2">
          <input
            value={authorInput}
            onChange={(e) => setAuthorInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addAuthor())}
            placeholder="Type author name and press Enter"
            className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-[13px] outline-none
              focus:border-[#6B0F12] focus:ring-1 focus:ring-[#6B0F12]"
          />
          <button
            type="button"
            onClick={addAuthor}
            className="px-3 py-2 bg-gray-100 rounded-lg text-[13px] text-gray-600 hover:bg-gray-200"
          >
            Add
          </button>
        </div>
        {authors.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {authors.map((a, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-gray-100 rounded-full text-[12px] text-gray-700"
              >
                {a}
                <button
                  type="button"
                  onClick={() => removeAuthor(i)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  <i className="fa fa-times text-[10px]" />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Keywords */}
      <div>
        <label className="block text-[13px] font-medium text-gray-700 mb-1">Keywords</label>
        <div className="flex gap-2 mb-2">
          <input
            value={keywordInput}
            onChange={(e) => setKeywordInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addKeyword())}
            placeholder="Type keyword and press Enter"
            className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-[13px] outline-none
              focus:border-[#6B0F12] focus:ring-1 focus:ring-[#6B0F12]"
          />
          <button
            type="button"
            onClick={addKeyword}
            className="px-3 py-2 bg-gray-100 rounded-lg text-[13px] text-gray-600 hover:bg-gray-200"
          >
            Add
          </button>
        </div>
        {keywords.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {keywords.map((k, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-blue-50 border border-blue-200 rounded-full text-[12px] text-blue-700"
              >
                {k}
                <button
                  type="button"
                  onClick={() => removeKeyword(i)}
                  className="text-blue-400 hover:text-blue-600"
                >
                  <i className="fa fa-times text-[10px]" />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
