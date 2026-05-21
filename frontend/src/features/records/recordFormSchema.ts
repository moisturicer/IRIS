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

  research_type: z.string().min(1, "Research type is required."),

  // TODO: validate minimum 1 author
  authors: z.array(z.string()).default([]),

  keywords: z.array(z.string()).default([]),

  // User IDs of co-owners
  owners: z.array(z.number()).default([]),
});

export type RecordFormValues = z.infer<typeof recordFormSchema>;
