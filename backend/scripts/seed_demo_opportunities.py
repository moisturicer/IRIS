"""
Demo data for Calls & Conferences (IR-121).

Run with:
    docker compose exec -T backend python manage.py shell < scripts/seed_demo_opportunities.py

Deadlines are set relative to today so the countdown chips and the closed/stale
states stay meaningful whenever this is run, rather than every card reading
"Closed" a month after the file was written.

These are illustrative CIT-U-shaped examples, not real open calls -- do not
present them to an evaluation participant as live funding opportunities.
"""
from datetime import date, timedelta

from apps.accounts.models import User
from apps.opportunities.models import Opportunity

poster = (
    User.objects.filter(email="rdco@cit.edu").first()
    or User.objects.filter(role__name="RDCO").first()
)

SEED = [
    {
        "opportunity_type": Opportunity.TYPE_INSTITUTIONAL_GRANT,
        "title":            "CIT-U University Research & Innovation Seed Grant (AY 2026-2027)",
        "posting_office":   "Research & Development Coordinating Office (RDCO)",
        "audience":         "CIT-U Faculty Researchers & Graduate Students",
        "description": (
            "Competitive institutional seed funding prioritizing projects in artificial "
            "intelligence, agricultural automation, renewable energy, and community-based "
            "digital transformation."
        ),
        "funding_ceiling": 150000,
        "external_url":    "https://www.cit.edu/research/",
        "days_out":        28,
        "is_featured":     True,
        "tags":            ["Seed Grant", "AI & Robotics", "SDG Aligned", "Internal"],
        "source":          Opportunity.SOURCE_INTERNAL,
    },
    {
        "opportunity_type": Opportunity.TYPE_FUNDING_WINDOW,
        "title":            "DOST-PCIEERD Call for Proposals: Smart Agriculture & Sensor Networks",
        "posting_office":   "External Grants Liaison / KTTO",
        "audience":         "Engineering, Computing & Allied Sciences Faculty",
        "description": (
            "National priority grant window for commercializable multi-sensor aerial drone "
            "systems, crop pest detection algorithms, and indigenous agro-tech applications."
        ),
        "funding_ceiling": 5000000,
        "external_url":    "https://pcieerd.dost.gov.ph/",
        "days_out":        43,
        "is_featured":     True,
        "tags":            ["DOST-GIA", "Agriculture", "Commercialization", "External"],
        "source":          Opportunity.SOURCE_EXTERNAL,
    },
    {
        "opportunity_type": Opportunity.TYPE_CONFERENCE_DEADLINE,
        "title":            "IEEE R10 Humanitarian Technology Conference (R10-HTC 2026)",
        "posting_office":   "College of Computer Studies / RDCO",
        "audience":         "All Undergraduate Thesis Students & Faculty",
        "description": (
            "Full-paper submissions for humanitarian technology, disaster informatics and "
            "assistive computing. Accepted papers are indexed in IEEE Xplore."
        ),
        "funding_ceiling": None,
        "external_url":    "https://www.ieee.org/conferences/",
        "days_out":        18,
        "is_featured":     False,
        "tags":            ["IEEE", "Conference", "Undergraduate"],
        "source":          Opportunity.SOURCE_EXTERNAL,
    },
    {
        "opportunity_type": Opportunity.TYPE_FUNDING_WINDOW,
        "title":            "CHED DARE TO Research Grants for Higher Education Institutions",
        "posting_office":   "RDCO / Office of the Vice President for Academic Affairs",
        "audience":         "Interdisciplinary Research Teams (CCS, CEA, CAS)",
        "description": (
            "Discovery-Applied Research and Extension for Trans/Inter-disciplinary "
            "Opportunities. Supports multi-college teams addressing regional development."
        ),
        "funding_ceiling": 3000000,
        "external_url":    "https://ched.gov.ph/",
        "days_out":        60,
        "is_featured":     False,
        "tags":            ["CHED", "Interdisciplinary", "External"],
        "source":          Opportunity.SOURCE_EXTERNAL,
    },
    {
        "opportunity_type": Opportunity.TYPE_INTERNAL_CALL,
        "title":            "Call for Capstone Proposals — CCS Department Review Panel",
        "posting_office":   "College of Computer Studies",
        "audience":         "4th Year BSCS & BSIT Students",
        "description": (
            "Submit capstone proposals for panel scheduling. Proposals must include a "
            "problem statement, review of related systems, and a feasibility assessment."
        ),
        "funding_ceiling": None,
        "external_url":    "",
        "days_out":        5,
        "is_featured":     False,
        "tags":            ["Capstone", "Internal", "CCS"],
        "source":          Opportunity.SOURCE_INTERNAL,
    },
    {
        "opportunity_type": Opportunity.TYPE_INSTITUTIONAL_GRANT,
        "title":            "CIT-U Faculty Travel Support for International Presentations",
        "posting_office":   "Research & Development Coordinating Office (RDCO)",
        "audience":         "Faculty with Accepted Conference Papers",
        "description": (
            "Reimbursement support for registration, airfare and accommodation for faculty "
            "presenting accepted papers at international venues."
        ),
        "funding_ceiling": 80000,
        "external_url":    "https://www.cit.edu/research/",
        "days_out":        -4,   # recently closed: greys out in place, still findable
        "is_featured":     False,
        "tags":            ["Travel Support", "Internal"],
        "source":          Opportunity.SOURCE_INTERNAL,
    },
]

created = 0
for row in SEED:
    days_out = row.pop("days_out")
    row["due_date"] = date.today() + timedelta(days=days_out)
    _, was_created = Opportunity.objects.get_or_create(
        title=row["title"], defaults={**row, "posted_by": poster},
    )
    created += int(was_created)

print(f"Opportunities: {created} created, {Opportunity.objects.count()} total.")
