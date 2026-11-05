"""PROTOTYPE, throwaway. Draws v1 and v2 of a seeded paper as thesis-shaped PDFs.

The seed_demo papers have titles and a stock abstract but no manuscript, so the
text here is written for the test. Each Version is drawn the way Word lays out a
CIT-U thesis: 1.5in binding margin, running head, page number, chapters on new
pages, justified body text with words hyphenated at line ends, and a ruled table.

It also returns the ground truth: which page each sentence starts on and every
word drawn, so the reader can be scored against what was really on the page.
"""
from copy import deepcopy
from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

TITLE = "Community Waste-to-Energy Feasibility in Metro Cebu"
AUTHORS = "Grace Lim and Miguel Torres"
RUNNING_HEAD = "WASTE-TO-ENERGY FEASIBILITY IN METRO CEBU"

W, H = letter
LEFT, RIGHT, TOP, BOTTOM = 108, 72, 72, 72
BODY, BOLD, SIZE, LEADING = "Times-Roman", "Times-Bold", 12, 24   # double-spaced, as CIT-U theses are
INDENT = 36

# ---------------------------------------------------------------- the paper (v1)
# A block is ("chapter", n, title) | ("heading", "n.n", title) | ("para", [sentences])
# | ("table", caption, header, rows).
V1 = [
    ("chapter", 1, "INTRODUCTION"),
    ("heading", "1.1", "Background of the Study"),
    ("para", [
        "Metro Cebu generates about 1,200 tonnes of municipal solid waste every day, and most of it ends up in the Inayawan and Binaliw landfills.",
        "Both sites have repeatedly exceeded their designed capacity since 2019.",
        "Local governments have considered waste-to-energy facilities as a way to reduce landfill dependence while producing electricity for the regional grid.",
        "However, the feasibility of such facilities depends on the composition, moisture content and calorific value of the waste stream, which no recent study has measured across the metropolitan area.",
    ]),
    ("para", [
        "Earlier assessments relied on national averages published by the Environmental Management Bureau.",
        "These averages understate the share of organic and food waste produced by dense urban barangays, and they say nothing about seasonal variation during the wet months.",
        "A facility designed on those figures risks operating well below its rated output for a large part of the year.",
    ]),
    ("heading", "1.2", "Statement of the Problem"),
    ("para", [
        "This study asks whether a community-scale waste-to-energy facility is technically and financially feasible for Metro Cebu.",
        "Specifically, it seeks to determine the composition and calorific value of the waste stream, the conversion technology best suited to that stream, and the capital and operating costs of a small-scale plant.",
        "It also asks how sensitive the financial outcome is to the tipping fee charged to local governments.",
    ]),
    ("heading", "1.3", "Significance of the Study"),
    ("para", [
        "The findings give local government units a measured basis for procurement decisions that are currently made on borrowed assumptions.",
        "They also give the university's engineering programmes a dataset that later capstone projects can extend.",
        "Communities near the landfills benefit indirectly, since any reduction in landfilled volume shortens the time those sites remain open.",
    ]),
    ("chapter", 2, "REVIEW OF RELATED LITERATURE"),
    ("heading", "2.1", "Waste Generation in Metro Cebu"),
    ("para", [
        "Studies of waste generation in the Visayas report per-capita rates between 0.5 and 0.7 kilograms per day.",
        "Urban centres sit at the upper end of that range, and Cebu City has been measured at 0.69 kilograms per person per day.",
        "Organic waste makes up roughly half of the total by weight, followed by plastics, paper and residual waste.",
    ]),
    ("para", [
        "Seasonal studies are scarce.",
        "The few that exist show the moisture content of mixed waste rising by as much as twelve percentage points during the rainy season, which lowers its heating value considerably.",
    ]),
    ("heading", "2.2", "Conversion Technologies"),
    ("para", [
        "Three families of technology dominate the literature: mass-burn incineration, anaerobic digestion and gasification.",
        "Mass-burn incineration handles mixed waste with little preparation but requires a high calorific value and costly emission controls.",
        "Anaerobic digestion suits wet organic waste and produces biogas at a smaller scale, though it leaves a digestate that must itself be managed.",
    ]),
    ("para", [
        "Gasification converts waste into a synthesis gas that can drive an engine or turbine.",
        "Pilot plants in Southeast Asia report frequent shutdowns caused by tar formation when the feedstock is not dried and sorted beforehand.",
        "For that reason most reviews treat gasification as unsuited to unsorted municipal waste in humid climates.",
    ]),
    ("para", [
        "Hybrid configurations, in which digestion handles the organic fraction and a small incinerator handles the residual fraction, have been proposed for mid-sized cities.",
        "Their economics depend heavily on how reliably the waste can be separated at source.",
    ]),
    ("chapter", 3, "METHODOLOGY"),
    ("heading", "3.1", "Research Design"),
    ("para", [
        "The study uses a descriptive and evaluative design.",
        "Waste characterization establishes the properties of the stream, and a techno-economic model evaluates each candidate technology against those properties.",
        "The model is deterministic, and its sensitivity analysis varies one input at a time.",
    ]),
    ("heading", "3.2", "Data Collection"),
    ("para", [
        "Waste samples were collected from transfer stations serving four cities over eight weeks, covering both the dry and the wet season.",
        "Each sample was sorted by hand into eight categories, weighed, and dried to determine its moisture content.",
        "Table 1 summarizes the daily tonnage reported by each city's environment office during the sampling period.",
    ]),
    ("table", "Table 1. Daily municipal solid waste by city (tonnes)",
     ["City", "Dry season", "Wet season"],
     [["Cebu City", "610", "655"], ["Mandaue City", "240", "262"],
      ["Lapu-Lapu City", "205", "221"], ["Talisay City", "145", "151"]]),
    ("para", [
        "Calorific value was measured with a bomb calorimeter at the university's chemical engineering laboratory.",
        "Three replicates were run for every composite sample, and the mean of the three is reported.",
    ]),
    ("heading", "3.3", "Data Analysis"),
    ("para", [
        "Capital and operating costs were estimated from published vendor quotations, adjusted to 2024 prices.",
        "Net present value and the levelized cost of electricity were computed over a twenty-year horizon at a discount rate of ten percent.",
        "A plant was judged feasible when its net present value was positive at the median tipping fee charged in the region.",
    ]),
    ("chapter", 4, "RESULTS AND DISCUSSION"),
    ("heading", "4.1", "Waste Composition"),
    ("para", [
        "Organic waste made up 52 percent of the sampled stream by weight in the dry season and 57 percent in the wet season.",
        "Mean moisture content rose from 48 percent to 61 percent between the two seasons.",
        "The mean lower heating value of the mixed stream fell below the threshold usually required for self-sustaining combustion during the wet months.",
    ]),
    ("heading", "4.2", "Feasibility of Each Technology"),
    ("para", [
        "Mass-burn incineration returned a negative net present value at every tipping fee tested, because supplementary fuel was needed for much of the year.",
        "Anaerobic digestion of the separated organic fraction returned a positive net present value at the median tipping fee.",
        "The hybrid configuration performed best when source separation exceeded 70 percent, and worst of all when it fell below 40 percent.",
    ]),
    ("chapter", 5, "CONCLUSIONS AND RECOMMENDATIONS"),
    ("heading", "5.1", "Conclusions"),
    ("para", [
        "A community-scale anaerobic digestion facility is feasible for Metro Cebu if the organic fraction is separated at source.",
        "Mass-burn incineration is not feasible given the moisture content measured during the wet season.",
    ]),
    ("heading", "5.2", "Recommendations"),
    ("para", [
        "Local governments should strengthen barangay-level source separation before procuring any waste-to-energy facility.",
        "Further work should measure the waste stream over a full year and test digestate disposal options.",
    ]),
]


def _find(blocks, kind, key):
    for i, b in enumerate(blocks):
        if b[0] == kind and (b[2] == key if kind == "heading" else b[1] == key):
            return i
    raise KeyError(key)


def make_v2():
    """v2 makes known edits. CHANGES is what a correct comparison must report."""
    b = deepcopy(V1)
    # 1. A sentence edited: a figure revised.
    i = _find(b, "heading", "Background of the Study") + 1
    b[i][1][0] = b[i][1][0].replace("about 1,200 tonnes", "about 1,350 tonnes")
    # 2. A section added.
    j = _find(b, "heading", "Significance of the Study") + 2
    b[j:j] = [
        ("heading", "1.4", "Scope and Limitations"),
        ("para", [
            "The study covers the four largest cities of Metro Cebu and excludes the municipalities to the north and south.",
            "It does not evaluate the transmission upgrades a plant might need, nor the social acceptability of a site.",
        ]),
        ("para", [
            "Sampling covered eight weeks rather than a full year, so the seasonal figures describe one dry and one wet period only.",
            "Costs are estimated from published vendor quotations and were not confirmed by tender.",
            "The study assumes that the tipping fee and the electricity tariff stay constant in real terms over the twenty-year horizon.",
            "Each of these limits is revisited when the results are discussed in Chapter 4.",
        ]),
        ("para", [
            "The calorific values reported here come from composite samples, which average out the variation between individual collection routes.",
            "A route serving a public market, for example, will deliver far wetter waste than one serving a commercial district, and a plant fed mainly from such routes would perform below the figures reported in this study.",
            "Route-level sampling is therefore recommended before any site is chosen, and the financial model should be rerun with the figures it produces.",
            "Finally, the study does not consider the informal recovery of recyclables by waste pickers, which removes much of the paper and plastic before the waste reaches a transfer station.",
        ]),
        ("para", [
            "Readers should therefore treat the feasibility findings as conditional on the four cities studied and on the sampling period.",
            "Extending them to the rest of the province would require new measurements rather than extrapolation from these results.",
        ]),
        ("para", [
            "The techno-economic model also simplifies the plant itself.",
            "It treats each technology as a single unit with a fixed availability, ignores the staged construction a real project would likely use, and assumes that the digestate from anaerobic digestion can be disposed of at no cost.",
            "Each simplification favours the technologies differently, and the sensitivity analysis in Chapter 4 shows how far the ranking depends on them.",
            "None of them changes the conclusion that mass-burn incineration is unsuited to the wet-season stream.",
        ]),
        ("para", [
            "Lastly, the study was conducted by two researchers over a single semester, which limited the number of transfer stations that could be visited each week.",
            "A longer campaign with more sampling teams would narrow the confidence intervals reported for every figure in Table 1.",
        ]),
    ]
    # 3. A paragraph removed (gasification), and 4. the two literature sections swapped.
    g = _find(b, "heading", "Conversion Technologies")
    del b[g + 2]
    wg = _find(b, "heading", "Waste Generation in Metro Cebu")
    ct = _find(b, "heading", "Conversion Technologies")
    waste = b[wg:ct]
    conv = b[ct:ct + 3]
    b[wg:ct + 3] = [("heading", "2.1", "Conversion Technologies")] + conv[1:] + \
                   [("heading", "2.2", "Waste Generation in Metro Cebu")] + waste[1:]
    # 5. A section renamed, and 6. a table value corrected.
    d = _find(b, "heading", "Data Collection")
    b[d] = ("heading", "3.2", "Data Gathering Procedure")
    t = next(k for k, x in enumerate(b) if x[0] == "table")
    b[t][3][1][2] = "270"
    # 7. A sentence added to the conclusions.
    c = _find(b, "heading", "Conclusions") + 1
    b[c][1].append("A hybrid plant becomes the better option once source separation is reliably above 70 percent.")
    return b


CHANGES = {
    "sections": {
        "background of the study": "changed",
        "scope and limitations": "added",
        "conversion technologies": "changed",
        "data collection": "renamed",       # to "Data Gathering Procedure"; also changed (table)
        "conclusions": "changed",
    },
    "moved_one_of": {"waste generation in metro cebu", "conversion technologies"},
    "edited_sentence": ("about 1,200 tonnes", "about 1,350 tonnes"),
    "removed_sentences": 3,
    "table_row": "Mandaue City",
}


# ---------------------------------------------------------------- layout
class Layout:
    def __init__(self):
        self.buf = BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=letter, invariant=1)
        self.page = 0
        self.y = None
        self.sentence_pages = []   # (sentence text, page it starts on)
        self.words = set()         # every word drawn, before hyphenation

    def new_page(self):
        if self.page:
            self.c.showPage()
        self.page += 1
        self.y = H - TOP
        if self.page > 1:
            self.c.setFont(BODY, 9)
            self.c.drawString(LEFT, H - 40, RUNNING_HEAD)
            self.c.setFont(BODY, 11)
            self.c.drawCentredString(LEFT + (W - LEFT - RIGHT) / 2, 40, str(self.page))

    def need(self, height):
        if self.y - height < BOTTOM:
            self.new_page()

    def title_page(self):
        self.new_page()
        c = self.c
        mid = LEFT + (W - LEFT - RIGHT) / 2
        c.setFont(BOLD, 16)
        c.drawCentredString(mid, H - 250, "COMMUNITY WASTE-TO-ENERGY FEASIBILITY")
        c.drawCentredString(mid, H - 272, "IN METRO CEBU")
        c.setFont(BODY, 12)
        c.drawCentredString(mid, H - 330, "A Thesis Presented to the Faculty of the College of Engineering")
        c.drawCentredString(mid, H - 348, "Cebu Institute of Technology - University")
        c.drawCentredString(mid, H - 420, AUTHORS)
        c.drawCentredString(mid, H - 438, "2023")
        for line in ("COMMUNITY WASTE-TO-ENERGY FEASIBILITY IN METRO CEBU", AUTHORS, "2023",
                     "A Thesis Presented to the Faculty of the College of Engineering",
                     "Cebu Institute of Technology - University"):
            self.words.update(line.split())

    def chapter(self, n, title):
        self.new_page()
        mid = LEFT + (W - LEFT - RIGHT) / 2
        self.c.setFont(BOLD, 12)
        self.c.drawCentredString(mid, self.y, f"CHAPTER {n}")
        self.c.drawCentredString(mid, self.y - LEADING, title)
        self.y -= LEADING * 3

    def heading(self, num, title):
        self.need(LEADING * 3)
        self.c.setFont(BOLD, 12)
        self.c.drawString(LEFT, self.y, f"{num}  {title}")
        self.y -= LEADING * 1.5

    def para(self, sentences):
        words, starts = [], {}
        for s in sentences:
            starts[len(words)] = s
            words.extend(s.split())
            self.words.update(w.strip(".,;:()") for w in s.split())
        width = W - LEFT - RIGHT
        space = stringWidth(" ", BODY, SIZE)
        i, first = 0, True
        while i < len(words):
            self.need(LEADING)
            x0 = LEFT + (INDENT if first else 0)
            avail = width - (x0 - LEFT)
            line, used = [], 0.0
            while i < len(words):
                w = words[i]
                ww = stringWidth(w, BODY, SIZE)
                gap = space if line else 0
                if used + gap + ww <= avail:
                    line.append((i, w)); used += gap + ww; i += 1
                    continue
                # Hyphenate like Word: at an existing hyphen, else inside a long word.
                rest = avail - used - gap
                cut = None
                if "-" in w[:-1]:
                    for k in range(len(w) - 2, 0, -1):
                        if w[k] == "-" and stringWidth(w[:k + 1], BODY, SIZE) <= rest:
                            cut = (w[:k + 1], w[k + 1:]); break
                elif len(w.strip(".,;")) >= 8:
                    for k in range(len(w) - 4, 3, -1):
                        if w[:k].isalpha() and stringWidth(w[:k] + "-", BODY, SIZE) <= rest:
                            cut = (w[:k] + "-", w[k:]); break
                if cut:
                    line.append((i, cut[0])); words[i] = cut[1]
                    starts.setdefault(i, None)  # the rest of this word continues next line
                break
            last = i >= len(words)
            self._draw_line(line, x0, avail, used, justify=not last, starts=starts)
            first = False

    def _draw_line(self, line, x0, avail, used, justify, starts):
        self.c.setFont(BODY, SIZE)
        extra = (avail - used) / (len(line) - 1) if justify and len(line) > 1 else 0
        x = x0
        space = stringWidth(" ", BODY, SIZE)
        for n, (idx, w) in enumerate(line):
            s = starts.pop(idx, None)
            if s:
                self.sentence_pages.append((s, self.page))
            self.c.drawString(x, self.y, w)
            x += stringWidth(w, BODY, SIZE) + space + extra
        self.y -= LEADING

    def table(self, caption, header, rows):
        rowh = 20
        self.need(LEADING + rowh * (len(rows) + 1) + 10)
        self.c.setFont(BODY, 12)
        self.c.drawString(LEFT, self.y, caption)
        self.y -= LEADING * 0.6
        cols = [LEFT, LEFT + 180, LEFT + 300, LEFT + 420]
        top = self.y
        allrows = [header] + rows
        for r, row in enumerate(allrows):
            self.c.setFont(BOLD if r == 0 else BODY, 11)
            for k, cell in enumerate(row):
                self.c.drawString(cols[k] + 6, top - rowh * r - 14, cell)
                self.words.update(cell.split())
        for r in range(len(allrows) + 1):
            self.c.line(cols[0], top - rowh * r, cols[-1], top - rowh * r)
        for x in cols:
            self.c.line(x, top, x, top - rowh * len(allrows))
        self.y = top - rowh * len(allrows) - LEADING * 1.2

    def render(self, blocks):
        self.title_page()
        for b in blocks:
            getattr(self, b[0])(*b[1:])
        self.c.showPage()
        self.c.save()
        return self.buf.getvalue()


def build(blocks):
    lay = Layout()
    pdf = lay.render(blocks)
    for b in blocks:
        if b[0] in ("chapter", "heading"):
            lay.words.update(str(x) for x in b[1:])
            lay.words.update(" ".join(map(str, b[1:])).split())
    return pdf, lay.sentence_pages, lay.words


TITLE_PAGE = ["COMMUNITY WASTE-TO-ENERGY FEASIBILITY", "IN METRO CEBU", "",
              "A Thesis Presented to the Faculty of the College of Engineering",
              "Cebu Institute of Technology - University", "", AUTHORS, "2023"]


def words_of(blocks):
    """Every word in a Version, for scoring a reader that didn't draw it."""
    out = set()
    for line in TITLE_PAGE:
        out.update(line.split())
    for b in blocks:
        if b[0] == "para":
            out.update(w.strip(".,;:()") for s in b[1] for w in s.split())
        elif b[0] in ("chapter", "heading"):
            out.update(" ".join(map(str, b[1:])).split())
            out.update(str(x) for x in b[1:])
        elif b[0] == "table":
            out.update(b[1].split())
            out.update(w for row in [b[2]] + b[3] for cell in row for w in cell.split())
    return out


def to_json(blocks):
    def one(b):
        if b[0] == "chapter":
            return {"kind": "chapter", "n": str(b[1]), "title": b[2]}
        if b[0] == "heading":
            return {"kind": "heading", "n": b[1], "title": b[2]}
        if b[0] == "para":
            return {"kind": "para", "sentences": b[1]}
        return {"kind": "table", "caption": b[1], "header": b[2], "rows": b[3]}
    return {"running_head": RUNNING_HEAD, "title_page": TITLE_PAGE, "blocks": [one(b) for b in blocks]}
