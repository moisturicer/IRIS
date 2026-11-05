# PROTOTYPE, throwaway. Builds a .docx in Microsoft Word from blocks.json, exports it
# to PDF, and writes the page each sentence starts on as Word paginated it.
#   powershell -File word_export.ps1 <blocks.json> <out.docx> <out.pdf> <pages.json>
param([string]$Blocks, [string]$Docx, [string]$Pdf, [string]$Pages)

$ErrorActionPreference = "Stop"
$spec = Get-Content -Raw -Encoding UTF8 $Blocks | ConvertFrom-Json
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.Options.AutoFormatAsYouTypeReplaceQuotes = $false
try {
    $doc = $word.Documents.Add()
    $doc.AutoHyphenation = $true
    $ps = $doc.PageSetup
    $ps.LeftMargin = 108; $ps.RightMargin = 72; $ps.TopMargin = 72; $ps.BottomMargin = 72
    $ps.DifferentFirstPageHeaderFooter = $true

    foreach ($name in @("Normal")) {
        $st = $doc.Styles.Item($name)
        $st.Font.Name = "Times New Roman"; $st.Font.Size = 12
        $st.ParagraphFormat.LineSpacingRule = 2          # double
        $st.ParagraphFormat.SpaceAfter = 0; $st.ParagraphFormat.SpaceBefore = 0
    }
    foreach ($name in @("Heading 1", "Heading 2")) {
        $st = $doc.Styles.Item($name)
        $st.Font.Name = "Times New Roman"; $st.Font.Size = 12; $st.Font.Bold = $true
        $st.Font.Color = 0; $st.Font.Italic = $false
        $st.ParagraphFormat.SpaceBefore = 12; $st.ParagraphFormat.SpaceAfter = 0
    }
    $doc.Styles.Item("Heading 1").ParagraphFormat.Alignment = 1   # centred

    $sec = $doc.Sections.Item(1)
    $sec.Headers.Item(1).Range.Text = $spec.running_head
    $sec.Headers.Item(1).Range.Font.Size = 9
    $null = $sec.Footers.Item(1).PageNumbers.Add(1, $false)        # centred, not on page 1

    $sel = $word.Selection
    function Para([string]$text, [string]$style, [int]$align, [double]$indent) {
        $sel.Style = $doc.Styles.Item($style)
        $sel.ParagraphFormat.Alignment = $align
        $sel.ParagraphFormat.FirstLineIndent = $indent
        $start = $sel.Range.Start
        $sel.TypeText($text)
        $sel.TypeParagraph()
        return $start
    }

    foreach ($line in $spec.title_page) { $null = Para $line "Normal" 1 0 }
    $starts = @()
    $first = $true
    foreach ($b in $spec.blocks) {
        switch ($b.kind) {
            "chapter" {
                $sel.InsertBreak(7)                                  # page break
                $null = Para ("CHAPTER " + $b.n) "Heading 1" 1 0
                $null = Para $b.title "Heading 1" 1 0
            }
            "heading" { $null = Para ($b.n + "  " + $b.title) "Heading 2" 0 0 }
            "para" {
                $text = ($b.sentences -join " ")
                $start = Para $text "Normal" 3 36                    # justified, indented
                $offset = 0
                foreach ($s in $b.sentences) {
                    $starts += [pscustomobject]@{ text = $s; at = $start + $offset }
                    $offset += $s.Length + 1
                }
            }
            "table" {
                $null = Para $b.caption "Normal" 0 0
                $rows = $b.rows.Count + 1; $cols = $b.header.Count
                $t = $doc.Tables.Add($sel.Range, $rows, $cols)
                $t.Borders.Enable = $true
                $t.Range.ParagraphFormat.LineSpacingRule = 0
                $t.Range.ParagraphFormat.FirstLineIndent = 0
                $t.Range.ParagraphFormat.Alignment = 0
                for ($c = 0; $c -lt $cols; $c++) {
                    $t.Cell(1, $c + 1).Range.Text = $b.header[$c]
                    $t.Cell(1, $c + 1).Range.Font.Bold = $true
                }
                for ($r = 0; $r -lt $b.rows.Count; $r++) {
                    for ($c = 0; $c -lt $cols; $c++) { $t.Cell($r + 2, $c + 1).Range.Text = $b.rows[$r][$c] }
                }
                $sel.EndKey(6) | Out-Null                            # past the table
            }
        }
    }
    $doc.Repaginate()
    $out = foreach ($s in $starts) {
        [pscustomobject]@{ text = $s.text; page = $doc.Range($s.at, $s.at + 1).Information(3) }
    }
    $out | ConvertTo-Json -Depth 3 | Set-Content -Encoding UTF8 $Pages
    $doc.SaveAs2($Docx, 16)
    $doc.ExportAsFixedFormat($Pdf, 17)
    $doc.Close($false)
} finally {
    $word.Quit()
}
