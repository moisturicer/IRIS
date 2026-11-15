"""
Demo data for Calls & Conferences (IR-121, rewritten for IR-760).

Run with:
    docker compose exec -T backend python manage.py shell < scripts/seed_demo_opportunities.py

Calls for papers only (ADR-050 decision 1): conferences, a congress, a
symposium, a workshop, journals and a book chapter. Each carries about, a
paper deadline, a location, Areas from the catalogue's Classifications and a
link; event dates and fees are filled where an event would have them, and a
journal or book chapter has none (decision 4).

Dates are relative to today so the countdowns and the closed state stay
meaningful whenever this is run. Run `manage.py seed_demo` first: it creates
`rdco@iris.test` and the Classifications used here; any missing Area is created.

These are illustrative examples, not real open calls -- do not present them to
an evaluation participant as live calls for papers.
"""
from datetime import date, timedelta

from apps.accounts.models import User
from apps.opportunities.models import Opportunity
from apps.records.models import Classification
from core.enums import CallStatus

poster = (
    User.objects.filter(email="rdco@iris.test").first()
    or User.objects.filter(role__name="RDCO").first()
)

# Day offsets from today: `due` is the paper deadline, `start`/`end` the event.
SEED = [
    {
        "opportunity_type": Opportunity.TYPE_CONFERENCE,
        "title":            "International Conference on Applied Computing and Intelligent Systems",
        "description":      "Full papers on applied AI, intelligent systems and their deployment "
                            "in industry and government. Accepted papers appear in the proceedings.",
        "location":         "Cebu City, Philippines",
        "areas":            ["Artificial Intelligence", "Internet of Things"],
        "external_url":     "https://example.org/icacis",
        "registration_fee": "PHP 6,500; students PHP 3,500",
        "due": 28, "start": 90, "end": 92,
        "is_featured":      True,
    },
    {
        "opportunity_type": Opportunity.TYPE_CONFERENCE,
        "title":            "Asia-Pacific Conference on Renewable Energy Systems",
        "description":      "Research on solar, wind and storage systems for island grids.",
        "location":         "Davao City, Philippines",
        "areas":            ["Clean Energy"],
        "external_url":     "https://example.org/apcres",
        "registration_fee": "USD 250 (early), USD 320 (regular)",
        "due": 7, "start": 60, "end": 61,
    },
    {
        "opportunity_type": Opportunity.TYPE_CONGRESS,
        "title":            "Philippine Congress on Health Informatics",
        "description":      "Abstracts and full papers on clinical data, telehealth and medical devices.",
        "location":         "Manila, Philippines",
        "areas":            ["Healthcare & MedTech"],
        "external_url":     "https://example.org/pchi",
        "due": 45, "start": 120, "end": 122,
    },
    {
        "opportunity_type": Opportunity.TYPE_SYMPOSIUM,
        "title":            "Visayas Symposium on Smart Agriculture",
        "description":      "Short papers and posters on sensing, automation and data in farming.",
        "location":         "Iloilo City, Philippines",
        "areas":            ["Agriculture Technology", "Internet of Things"],
        "external_url":     "https://example.org/vssa",
        "registration_fee": "Free for students",
        "due": 3, "start": 30,
    },
    {
        "opportunity_type": Opportunity.TYPE_WORKSHOP,
        "title":            "Workshop on Secure Embedded Systems",
        "description":      "Work-in-progress papers on firmware security and trusted hardware.",
        "location":         "Online",
        "areas":            ["Cybersecurity"],
        "external_url":     "https://example.org/wses",
        "due": -4, "start": 20,   # recently closed: greys out in place
    },
    {
        "opportunity_type": Opportunity.TYPE_JOURNAL,
        "title":            "Journal of Engineering and Computing Research: Special Issue on Edge AI",
        "description":      "A special issue on machine learning at the network edge. Rolling review.",
        "location":         "Online",
        "areas":            ["Artificial Intelligence"],
        "external_url":     "https://example.org/jecr-edge-ai",
        "registration_fee": "No article processing charge",
        "due": 60,
    },
    {
        "opportunity_type": Opportunity.TYPE_JOURNAL,
        "title":            "Energy and Sustainability Letters: Call for Papers",
        "description":      "Short communications on energy efficiency and sustainable materials.",
        "location":         "Online",
        "areas":            ["Clean Energy"],
        "external_url":     "https://example.org/esl",
        "registration_fee": "APC USD 800; waivers available",
        "due": 14,
    },
    {
        "opportunity_type": Opportunity.TYPE_BOOK_CHAPTER,
        "title":            "Cybersecurity in Southeast Asia: An Edited Volume",
        "description":      "Chapter proposals on threats, policy and practice in the region.",
        "location":         "Online",
        "areas":            ["Cybersecurity"],
        "external_url":     "https://example.org/cyber-sea",
        "due": 35,
    },
]

today = date.today()
created = 0
for row in SEED:
    row = dict(row)
    area_names = row.pop("areas")
    row["due_date"] = today + timedelta(days=row.pop("due"))
    start = row.pop("start", None)
    end = row.pop("end", None)
    row["start_date"] = today + timedelta(days=start) if start is not None else None
    row["end_date"] = today + timedelta(days=end) if end is not None else None
    # RDCO's own posts are confirmed at once (ADR-050 decision 8, IR-762); the
    # model's default is pending, which would keep these off the board.
    call, was_created = Opportunity.objects.get_or_create(
        title=row["title"], defaults={**row, "posted_by": poster, "status": CallStatus.CONFIRMED},
    )
    if was_created:
        call.areas.set([Classification.objects.get_or_create(name=name)[0] for name in area_names])
    created += int(was_created)

print(f"Calls: {created} created, {Opportunity.objects.count()} total.")
