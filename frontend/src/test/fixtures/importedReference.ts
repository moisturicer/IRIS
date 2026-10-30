import type { RecordListItem } from "@/types/records";

/** Verified against https://arxiv.org/abs/1706.03762 on 2026-10-30.
 * Publication is 2017; the latest revision date does not replace that year.
 */
export const importedReference: Pick<RecordListItem, "title" | "authors" | "origin" | "publication_year"> = {
  title: "Attention Is All You Need",
  authors: ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit", "Llion Jones",
    "Aidan N. Gomez", "Lukasz Kaiser", "Illia Polosukhin"].map((name, index) => ({ id: index + 1, name, role: null })),
  origin: "imported_reference",
  publication_year: 2017,
};
