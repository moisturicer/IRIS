// A small, valid, single-page PDF built in memory: enough for the upload
// validators and for an Extractor to read a page of text. Synthetic content only.
export function manuscriptPdf(title: string, body = "Synthetic manuscript for IR-631 journey verification."): Buffer {
  const esc = (s: string) => s.replace(/[\()]/g, (c) => `\${c}`);
  const stream = `BT /F1 14 Tf 72 720 Td (${esc(title)}) Tj 0 -24 Td /F1 11 Tf (${esc(body)}) Tj ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let out = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((obj, i) => {
    offsets.push(Buffer.byteLength(out));
    out += `${i + 1} 0 obj\n${obj}\nendobj\n`;
  });
  const xref = Buffer.byteLength(out);
  out += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  out += offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("");
  out += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(out, "binary");
}

/**
 * A valid PDF of several pages, each carrying its own text, so a journey that
 * opens a paper "at page N" can tell page N from the page before it (IR-902).
 * `pages[i]` is the text of page i + 1; synthetic content only.
 */
export function multiPagePdf(pages: string[]): Buffer {
  const esc = (s: string) => s.replace(/[\()]/g, (c) => `\${c}`);
  const count = pages.length;
  // Objects: 1 catalog, 2 page tree, 3 font, then a page and its stream per page.
  const pageId = (i: number) => 4 + i * 2;
  const objects: string[] = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    `<< /Type /Pages /Kids [${pages.map((_, i) => `${pageId(i)} 0 R`).join(" ")}] /Count ${count} >>`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  pages.forEach((text, i) => {
    const stream = `BT /F1 14 Tf 72 720 Td (${esc(text)}) Tj ET`;
    objects.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents ${pageId(i) + 1} 0 R /Resources << /Font << /F1 3 0 R >> >> >>`);
    objects.push(`<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`);
  });
  let out = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((obj, i) => {
    offsets.push(Buffer.byteLength(out));
    out += `${i + 1} 0 obj\n${obj}\nendobj\n`;
  });
  const xref = Buffer.byteLength(out);
  out += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  out += offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("");
  out += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(out, "binary");
}
