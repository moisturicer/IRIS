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
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Skeleton } from "@/components/ui/Skeleton";
import { clearReviewDraft, readReviewDraft, writeReviewDraft } from "@/lib/reviewDraft";

interface FormData {
  status:  ReviewStatus;
  comment: string;
}

/**
 * Human-readable label for each decision option.
 * "declined" is surfaced as "Request Revision" so users understand it is
 * not a terminal action — the owner can resubmit after addressing feedback.
 */
const DECISION_OPTIONS: { value: ReviewStatus; label: string; description: string; color: string; icon: string }[] = [
  {
    value:       "approved",
    label:       "Approve",
    description: "Accept and advance to the next stage.",
    color:       "text-green-700",
    icon:        "fa-check",
  },
  {
    value:       "declined",
    label:       "Request Revision",
    description: "Send back to the owner for changes. They may resubmit after revising.",
    color:       "text-amber-700",
    icon:        "fa-arrow-rotate-left",
  },
  {
    value:       "rejected",
    label:       "Reject",
    description: "Permanently reject. Use only for out-of-scope, ineligible, or serious-violation submissions. The owner cannot resubmit.",
    color:       "text-red-700",
    icon:        "fa-xmark",
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
  /** A rejection held back until it is explicitly confirmed. */
  const [pendingReject, setPendingReject] = useState<FormData | null>(null);
  const [rejecting, setRejecting] = useState(false);

  /**
   * Read once, at mount. `useForm` only consults `defaultValues` on its first
   * render, and re-reading later would fight the reviewer's typing.
   */
  const [restoredDraft] = useState(() => (id ? readReviewDraft(id) : null));

  const {
    register,
    handleSubmit,
    watch,
    formState: { isSubmitting },
  } = useForm<FormData>({
    defaultValues: {
      status:  restoredDraft?.status  ?? "approved",
      comment: restoredDraft?.comment ?? "",
    },
  });

  /**
   * Keep the unsent decision, so reading the evidence cannot cost the reviewer
   * their comment (IR-237).
   *
   * `watch` with a callback subscribes to changes. `watch()` bare returns a
   * fresh object every render, so an effect depending on it would loop.
   */
  useEffect(() => {
    if (!id) return;
    const subscription = watch((values) => {
      writeReviewDraft(id, {
        status:  (values.status as ReviewStatus) ?? "approved",
        comment: values.comment ?? "",
      });
    });
    return () => subscription.unsubscribe();
  }, [watch, id]);

  const selectedStatus = watch("status");
  const commentRequired = selectedStatus === "declined" || selectedStatus === "rejected";

  useEffect(() => {
    if (id) recordsApi.detail(Number(id)).then(({ data }) => setRecord(data));
  }, [id]);

  const send = async (data: FormData) => {
    try {
      await reviewsApi.submit({ record_id: Number(id), ...data });
      // The decision is recorded, so the draft is spent. Left behind, it would
      // greet the next visit to this record with a stale comment.
      if (id) clearReviewDraft(id);
      navigate("/review");
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Something went wrong. Please try again.";
      setError(msg);
    }
  };

  const onSubmit = async (data: FormData) => {
    setError(null);
    if (commentRequired && !data.comment.trim()) {
      setError("A comment is required when requesting revision or rejecting.");
      return;
    }
    // Rejection is terminal -- the owner cannot resubmit -- and it was firing
    // on a single click. `ConfirmDialog` already existed and was unused here
    // (IR-143).
    if (data.status === "rejected") {
      setPendingReject(data);
      return;
    }
    await send(data);
  };

  const confirmReject = async () => {
    if (!pendingReject) return;
    setRejecting(true);
    await send(pendingReject);
    setRejecting(false);
    setPendingReject(null);
  };

  if (!record) return <Skeleton />;

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
            {/* Ordinary in-app navigation -- **do not make these open a new
                tab** (IR-237).

                They did, from IR-143 until IR-237, because navigating away
                unmounted this form and silently discarded a typed comment.
                That cure was worse: a new tab is a fresh top-level browsing
                context, browsers do not clone `sessionStorage` into one, and
                the refresh token lives in `sessionStorage` and nowhere else
                (FR-M6-01) -- so the reviewer arrived at the login screen
                instead of the evidence.

                IR-235 tried to rescue the new tab by removing
                `rel="noopener noreferrer"`, on the theory that `noopener` was
                what suppressed the clone. **It is not, and that change was a
                no-op**: since Chrome 88 (Firefox 79, Safari 12.1)
                `target="_blank"` *implies* `noopener`, so the tab was a fresh
                context either way. Measured both ways on a bare same-origin
                page before this was written -- neither spelling cloned
                anything.

                So the form's state is what gets protected now, by
                `lib/reviewDraft.ts`, and the links are left alone. That covers
                strictly more than the new tab ever did: an accidental back, a
                reload and an expired session all used to lose the comment too. */}
            <Link
              to={`/records/${id}/documents`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#6B0F12] text-white text-[12px] font-semibold hover:bg-[#7d1215] transition-colors"
            >
              <i className="fas fa-folder-open text-[11px]" aria-hidden />
              View &amp; Attach Documents
            </Link>
            <Link
              to={`/records/${id}`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 text-[12px] font-semibold text-gray-600 hover:bg-gray-50 transition-colors"
            >
              <i className="fas fa-external-link-alt text-[11px]" aria-hidden />
              Record Detail
            </Link>
          </div>
        </div>

        {/* Review form */}
        <form onSubmit={handleSubmit(onSubmit)} className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">
          <div>
            <p className="text-[13px] font-semibold text-gray-800">Your Decision</p>
            {/* At parallel_review, approving records ONE office's clearance --
                not the record's approval. Saying so is the difference between
                a reviewer knowing what they just did and assuming they
                published it (IR-143). Server-supplied label (IR-139). */}
            {record.your_office_label ? (
              <p className="mt-1 text-[12px] text-gray-600">
                You are recording{" "}
                <strong className="text-gray-900">{record.your_office_label} clearance</strong> for
                this record. The other offices decide separately.
              </p>
            ) : (
              <p className="mt-1 text-[12px] text-gray-600">
                This decision moves the record on from{" "}
                <strong className="text-gray-900">{record.stage_label}</strong>.
              </p>
            )}
          </div>

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
                  {/* Icon *and* word. Colour alone fails for the ~8% of men
                      with a colour vision deficiency, and these three options
                      are green/amber/red -- the worst possible triple. */}
                  <p className={`text-[13px] font-semibold flex items-center gap-1.5 ${opt.color}`}>
                    <i className={`fas ${opt.icon} text-[11px]`} aria-hidden />
                    {opt.label}
                  </p>
                  <p className="text-[12px] text-gray-500 mt-0.5">{opt.description}</p>
                </div>
              </label>
            ))}
          </div>

          {/* Comment */}
          <div>
            <label className="block text-[12px] font-semibold text-gray-700 mb-1">
              Comment{" "}
              <span className={commentRequired ? "text-red-500" : "text-gray-500"}>
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

      <ConfirmDialog
        open={pendingReject !== null}
        title="Reject this record permanently?"
        message={
          record.your_office_label
            ? `This records a ${record.your_office_label} rejection and is terminal — the owner cannot resubmit. Request Revision instead if they should be able to fix it.`
            : "Rejection is terminal — the owner cannot resubmit. Request Revision instead if they should be able to fix it."
        }
        confirmLabel="Reject permanently"
        danger
        confirming={rejecting}
        onConfirm={confirmReject}
        onCancel={() => setPendingReject(null)}
      />
    </div>
  );
}
