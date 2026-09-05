"""
Seed published demo records so the Discover feed has something to show.

Creates classifications, a student owner per college (needed for the `college`
filter, which joins Record -> owners -> student_profile -> course -> department
-> college), and a spread of published records across years, IP types and
commercialisation flags.

Run with:  python manage.py shell < scripts/seed_demo_records.py
Dev only. Idempotent — re-running updates rather than duplicates.
"""
from django.contrib.auth import get_user_model

from apps.accounts.models import College, Course, Role, StudentProfile
from apps.records.models import (
    Author,
    Classification,
    Record,
    RecordOwner,
    RecordType,
)

User = get_user_model()
PASSWORD = "IrisDemo123!"

CLASSIFICATIONS = [
    "Artificial Intelligence",
    "Internet of Things",
    "Clean Energy",
    "Healthcare & MedTech",
    "Cybersecurity",
    "Agriculture Technology",
]

for name in CLASSIFICATIONS:
    Classification.objects.get_or_create(name=name)
print(f"classifications: {Classification.objects.count()}")

student_role, _ = Role.objects.get_or_create(name="Student")


def owner_for(college_code, first, last):
    """A verified student whose course sits under `college_code`."""
    college = College.objects.filter(code=college_code).first()
    course = Course.objects.filter(department__college=college).first() if college else None

    email = f"{first.lower()}.{last.lower()}@cit.edu"
    user, _ = User.objects.get_or_create(
        email=email, defaults={"first_name": first, "last_name": last}
    )
    user.first_name = first
    user.last_name = last
    user.role = student_role
    user.is_verified = True
    user.set_password(PASSWORD)
    user.save()

    if course:
        StudentProfile.objects.update_or_create(user=user, defaults={"course": course})
    return user


# title, classification, record_type, year, is_ip, ip_type, commercial, extension, college, author names
RECORDS = [
    ("Retrieval-Augmented Generation for Institutional Research Discovery",
     "Artificial Intelligence", "Thesis / Research", 2026, True, "patent", True, False, "CCS",
     ["Sam Student", "Ana Adviser"]),
    ("A Low-Cost IoT Flood Sensor Network for Cebu Barangays",
     "Internet of Things", "Project", 2025, True, "utility_model", True, True, "CEA",
     ["Miguel Torres", "Rita Cruz"]),
    ("Solar-Assisted Water Purification for Off-Grid Island Communities",
     "Clean Energy", "Thesis / Research", 2025, False, "", False, True, "CEA",
     ["Liza Fernandez"]),
    ("Machine Learning Triage Support for Rural Health Units",
     "Healthcare & MedTech", "Thesis / Research", 2024, True, "copyright", False, False, "CNAHS",
     ["Joy Ramirez", "Paolo Diaz"]),
    ("Phishing Resistance Training Outcomes Among University Staff",
     "Cybersecurity", "Thesis / Research", 2024, False, "", False, False, "CCS",
     ["Karl Tan"]),
    ("Vision-Based Ripeness Grading for Smallholder Mango Farms",
     "Agriculture Technology", "Project", 2023, True, "trade_secret", True, False, "CCS",
     ["Elena Reyes", "Ivan Santos"]),
    ("Blockchain-Backed Academic Credential Verification",
     "Cybersecurity", "Project", 2026, True, "patent", True, False, "CCS",
     ["Noel Abad"]),
    ("Community Waste-to-Energy Feasibility in Metro Cebu",
     "Clean Energy", "Thesis / Research", 2023, False, "", False, True, "CEA",
     ["Grace Lim", "Miguel Torres"]),
]

ABSTRACT = (
    "This study investigates {topic} within the context of Cebu Institute of "
    "Technology – University's institutional research programme. The work "
    "documents the design, implementation and evaluation of the proposed "
    "approach, reporting measured outcomes against a baseline and discussing "
    "the implications for adoption across the university and its partner "
    "communities. Limitations and directions for further work are outlined."
)

created = 0
for (title, classification_name, type_name, year, is_ip, ip_type,
     commercial, extension, college_code, author_names) in RECORDS:

    owner = owner_for(college_code, author_names[0].split()[0], author_names[0].split()[-1])

    record, was_created = Record.objects.get_or_create(
        title=title,
        defaults={"abstract": ABSTRACT.format(topic=classification_name.lower())},
    )
    record.abstract = ABSTRACT.format(topic=classification_name.lower())
    record.classification = Classification.objects.filter(name=classification_name).first()
    record.record_type = RecordType.objects.filter(name=type_name).first()
    record.year_accomplished = year
    record.is_ip = is_ip
    record.ip_type = ip_type
    record.for_commercialization = commercial
    record.community_extension = extension
    record.pipeline_status = "published"
    record.added_by = owner
    record.access_count = (year - 2020) * 7 + len(title) % 13
    record.save()

    RecordOwner.objects.get_or_create(record=record, user=owner, defaults={"is_primary": True})

    record.authors.all().delete()
    Author.objects.bulk_create([Author(record=record, name=n) for n in author_names])

    created += int(was_created)
    print(f"{'created' if was_created else 'updated'}  {title[:58]}")

print(f"\n{created} new, {len(RECORDS) - created} updated")
print(f"published records: {Record.objects.filter(pipeline_status='published').count()}")
