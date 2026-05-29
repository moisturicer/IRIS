import { useEffect, useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { recordsApi } from "@/api/records";
import { reviewsApi } from "@/api/reviews";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/shared/StatusBadge";
import type { RecordDetail } from "@/types/records";
import type { ReviewStatus } from "@/types/reviews";
import { pipelineLabel } from "@/lib/utils";

interface FormData {
  status:  ReviewStatus;
  comment: string;
}

/**
 * Human-readable label for each decision option.
 * "declined" is surfaced as "Request Revision" so users understand it is
 * not a terminal action — the owner can resubmit after addressing feedback.
 */
const DECISION_OPTIONS: { value: ReviewStatus; label: string; description: string; color: string }[] = [
  {
    value:       "approved",
    label:       "Approve",
    description: "Accept and advance to the next stage.",
    color:       "text-green-700",
  },
  {
    value:       "declined",
    label:       "Request Revision",
    description: "Send back to the owner for changes. They may resubmit after revising.",
    color:       "text-amber-700",
  },
  {
    value:       "rejected",
    label:       "Reject",
    description: "Permanently reject. Use only for out-of-scope, ineligible, or serious-violation submissions. The owner cannot resubmit.",
    color:       "text-red-700",
  },
];

/** Map pipeline_status -> readable stage label shown on the review form. */
function stageLabel(pipelineStatus: string): string {
  const map: Record<string, string> = {
    adviser_review:  "Adviser Review",
    rdco_intake:     "RDCO Intake Review",
    itso_review:     "ITSO Technical Review",
    parallel_review: "Parallel Office Review",
    rdco_review:     "RDCO Final Review",
  };
  return map[pipelineStatus] ?? pipelineLabel(pipelineStatus);
}

export default function EvaluationPage() {
  const { id }              = useParams<{ id: string }>();
  const navigate            = useNavigate();
  const [record, setRecord] = useState<RecordDetail | null>(null);
  const [error, setError]   = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    formState: { isSubmitting },
  } = useForm<FormData>({
    defaultValues: { status: "approved", comment: "" },
  });

  const selectedStatus = watch("status");
  const commentRequired = selectedStatus === "declined" || selectedStatus === "rejected";

  useEffect(() => {
    if (id) recordsApi.detail(Number(id)).then(({ data }) => setRecord(data));
  }, [id]);

  const onSubmit = async (data: FormData) => {
    setError(null);
    if (commentRequired && !data.comment.trim()) {
      setError("A comment is required when requesting revision or rejecting.");
      return;
    }
    try {
      await reviewsApi.submit({ record_id: Number(id), ...data });
      navigate("/review/pending");
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Something went wrong. Please try again.";
      setError(msg);
    }
  };

  if (!record) return <div className="p-8 text-gray-400 text-[13px]">Loading...</div>;

  return (
    <div>
      <PageHeader
        title="Review Record"
        description={`Stage: ${stageLabel(record.pipeline_status)}`}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Record info */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-3">
          <p className="text-[13px] font-semibold text-gray-800">Record Details</p>

          <div className="flex items-center gap-2">
            <StatusBadge status={record.pipeline_status} />
          </div>

          <div className="text-[13px] text-gray-600 space-y-1">
            <p><strong>Title:</strong> {record.title}</p>
            <p><strong>Type:</strong> {record.record_type ?? "-"}</p>
            <p><strong>Year:</strong> {record.year_accomplished ?? "-"}</p>
          </div>

          {record.abstract && (
            <div>
              <p className="text-[12px] font-semibold text-gray-700 mb-1">Abstract</p>
              <p className="text-[13px] text-gray-500 leading-relaxed line-clamp-6">
                {record.abstract}
              </p>
            </div>
          )}

          <div>
            <p className="text-[12px] font-semibold text-gray-700 mb-1">Authors</p>
            <div className="flex flex-wrap gap-1.5">
              {record.authors.map((a) => (
                <span key={a.id} className="px-2 py-0.5 bg-gray-100 rounded text-[12px] text-gray-700">
                  {a.name}
                </span>
              ))}
            </div>
          </div>

          <div className="pt-1 flex gap-2">
            <Link
              to={`/records/${id}/documents`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#6B0F12] text-white text-[12px] font-semibold hover:bg-[#7d1215] transition-colors"
            >
              <i className="fas fa-folder-open text-[11px]" />
              View &amp; Attach Documents
            </Link>
            <Link
              to={`/records/${id}`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 text-[12px] font-semibold text-gray-600 hover:bg-gray-50 transition-colors"
            >
              <i className="fas fa-external-link-alt text-[11px]" />
              Record Detail
            </Link>
          </div>
        </div>

        {/* Review form */}
        <form onSubmit={handleSubmit(onSubmit)} className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">
          <p className="text-[13px] font-semibold text-gray-800">Your Decision</p>

          {/* Decision radio group */}
          <div className="space-y-3">
            {DECISION_OPTIONS.map((opt) => (
              <label
                key={opt.value}
                className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                  selectedStatus === opt.value
                    ? "border-[#6B0F12] bg-[#6B0F12]/5"
                    : "border-gray-200 hover:border-gray-300"
                }`}
              >
                <input
                  type="radio"
                  {...register("status")}
                  value={opt.value}
                  className="mt-0.5 accent-[#6B0F12]"
                />
                <div>
                  <p className={`text-[13px] font-semibold ${opt.color}`}>{opt.label}</p>
                  <p className="text-[12px] text-gray-500 mt-0.5">{opt.description}</p>
                </div>
              </label>
            ))}
          </div>

          {/* Comment */}
          <div>
            <label className="block text-[12px] font-semibold text-gray-700 mb-1">
              Comment{" "}
              <span className={commentRequired ? "text-red-500" : "text-gray-400"}>
                {commentRequired ? "(required)" : "(optional)"}
              </span>
            </label>
            <textarea
              {...register("comment")}
              rows={4}
              placeholder={
                selectedStatus === "approved"
                  ? "Add an optional note for the next reviewer or the record owner..."
                  : "Explain what needs to be revised or why the record is being rejected..."
              }
              className="w-full border border-gray-200 rounded-lg p-3 text-[13px] resize-y focus:outline-none focus:border-[#6B0F12]"
            />
          </div>

          {/* Rejection confirmation warning */}
          {selectedStatus === "rejected" && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-[12px] text-red-700">
              <strong>This action is permanent.</strong> Rejecting a record removes it from the
              pipeline and prevents the owner from resubmitting. Make sure a comment explains
              the reason clearly.
            </div>
          )}

          {error && (
            <p className="text-[12px] text-red-500">{error}</p>
          )}

          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="flex-1 border border-gray-200 rounded-lg py-2 text-[13px] font-semibold text-gray-600 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex-1 bg-[#6B0F12] text-white rounded-lg py-2 text-[13px] font-semibold hover:bg-[#7d1215] disabled:opacity-60"
            >
              {isSubmitting ? "Submitting..." : "Submit Decision"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
