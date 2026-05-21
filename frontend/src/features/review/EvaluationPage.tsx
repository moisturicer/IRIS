import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { recordsApi } from "@/api/records";
import { reviewsApi } from "@/api/reviews";
import { PageHeader } from "@/components/layout/PageHeader";
import type { RecordDetail } from "@/types/records";

interface FormData {
  status:  "approved" | "declined";
  comment: string;
}

export default function EvaluationPage() {
  const { id }              = useParams<{ id: string }>();
  const navigate            = useNavigate();
  const [record, setRecord] = useState<RecordDetail | null>(null);

  const { register, handleSubmit, watch, formState: { isSubmitting } } = useForm<FormData>({
    defaultValues: { status: "approved", comment: "" },
  });

  useEffect(() => {
    if (id) recordsApi.detail(Number(id)).then(({ data }) => setRecord(data));
  }, [id]);

  const onSubmit = async (data: FormData) => {
    await reviewsApi.submit({ record_id: Number(id), ...data });
    navigate("/review/pending");
  };

  if (!record) return <div className="p-8 text-gray-400 text-[13px]">Loading...</div>;

  return (
    <div>
      <PageHeader title="Review Record" description={record.title} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Record info */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <p className="text-[13px] font-semibold text-gray-800 mb-3">Record Details</p>
          <p className="text-[13px] text-gray-600 mb-2"><strong>Type:</strong> {record.record_type ?? "-"}</p>
          <p className="text-[13px] text-gray-600 mb-2"><strong>Year:</strong> {record.year_accomplished ?? "-"}</p>
          <p className="text-[13px] text-gray-600 mb-3"><strong>Abstract:</strong></p>
          <p className="text-[13px] text-gray-500 leading-relaxed">{record.abstract || "No abstract provided."}</p>
          {/* TODO: show uploaded documents list with download links */}
        </div>

        {/* Review form */}
        <form onSubmit={handleSubmit(onSubmit)} className="bg-white rounded-xl border border-gray-200 p-6">
          <p className="text-[13px] font-semibold text-gray-800 mb-4">Your Decision</p>

          <div className="flex gap-3 mb-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="radio" {...register("status")} value="approved" className="accent-[#6B0F12]" />
              <span className="text-[13px] font-medium text-green-700">Approve</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="radio" {...register("status")} value="declined" className="accent-[#6B0F12]" />
              <span className="text-[13px] font-medium text-red-700">Decline</span>
            </label>
          </div>

          <div className="mb-4">
            <label className="block text-[12px] font-semibold text-gray-700 mb-1">
              Comment {watch("status") === "declined" ? "(required)" : "(optional)"}
            </label>
            <textarea
              {...register("comment")}
              rows={4}
              className="w-full border border-gray-200 rounded-lg p-3 text-[13px] resize-y focus:outline-none focus:border-[#6B0F12]"
              placeholder="Leave a comment for the record owner..."
            />
          </div>

          <div className="flex gap-2">
            <button type="button" onClick={() => navigate(-1)} className="flex-1 border border-gray-200 rounded-lg py-2 text-[13px] font-semibold text-gray-600 hover:bg-gray-50">
              Cancel
            </button>
            <button type="submit" disabled={isSubmitting} className="flex-1 bg-[#6B0F12] text-white rounded-lg py-2 text-[13px] font-semibold hover:bg-[#7d1215] disabled:opacity-60">
              {isSubmitting ? "Submitting..." : "Submit Review"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
