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
});

export type RecordFormValues = z.infer<typeof recordFormSchema>;
