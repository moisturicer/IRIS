/**
 * A record type's section on Guidelines (IR-974): "Thesis / Research" is
 * `/guidelines#thesis-research`. Its own module, so Publish can link to a
 * section without loading the page.
 */
export function sectionId(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export function guidelinesHref(recordTypeName?: string | null): string {
  return recordTypeName ? `/guidelines#${sectionId(recordTypeName)}` : "/guidelines";
}
