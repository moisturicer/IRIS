/**
 * Zod schema shared by AddRecordPage and EditRecordPage.
 * Keep validation rules here so both wizard forms stay in sync.
 */
import { z } from "zod";

export const recordFormSchema = z.object({
  title: z
    .string()
    .min(5, "Title must be at least 5 characters.")
    .max(500, "Title is too long."),

  abstract: z
    .string()
    .min(30, "Abstract must be at least 30 characters.")
    .max(5000, "Abstract is too long."),

  year: z
    .number({ invalid_type_error: "Year is required." })
    .min(1990, "Year must be 1990 or later.")
    .max(new Date().getFullYear() + 1, "Year cannot be in the future."),

  record_type: z.string().min(1, "Record type is required."),

  /**
   * Adviser is only required for Proposal records.
   * Thesis/Research and Project records submit without an adviser.
   * Server-side validation enforces the Proposal constraint; we make
   * this field optional here so non-Proposal forms pass step-2 validation.
   */
  adviser: z.number().int().positive().optional(),

  authors: z
    .array(z.string().min(1))
    .min(1, "At least one author is required.")
    .default([]),

  // Keywords are collected for future use but have no backend field yet.
  keywords: z.array(z.string()).default([]),

  // User IDs of co-owners
  owners: z.array(z.number()).default([]),

  // Reference-data ids. Both optional: RecordWriteSerializer accepts either
  // null or a valid pk, and neither field blocks submission on its own.
  classification: z.number().int().positive().optional(),
  psced:          z.number().int().positive().optional(),

  // IP flags — submitter-settable. `ip_type` itself is deliberately absent:
  // the model's help_text says it is "set by RDCO/KTTO after final review",
  // and RecordViewSet.tags() (staff-only) is the only endpoint that writes it.
  is_ip:                 z.boolean().default(false),
  for_commercialization: z.boolean().default(false),
  community_extension:   z.boolean().default(false),

  // Ethics trigger + conditional office routing (ADR-018, Proposed).
  // requires_ethics_review has no upstream flag to derive from -- it's its
  // own question. requested_itso/ierc/ktto are the submitter's actual
  // request; PaperDetailsStep pre-checks them from the flags above but the
  // student can override before continuing.
  requires_ethics_review: z.boolean().default(false),
  requested_itso: z.boolean().default(false),
  requested_ierc: z.boolean().default(false),
  requested_ktto: z.boolean().default(false),
});

export type RecordFormValues = z.infer<typeof recordFormSchema>;
