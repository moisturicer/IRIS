from django.db import migrations


ROLES = ["Student", "Adviser", "KTTO", "RDCO", "ITSO", "IERC"]

COLLEGES = [
    {"id": 1, "name": "College of Engineering and Architecture",   "code": "CEA"},
    {"id": 2, "name": "College of Management, Business & Accountancy", "code": "CMBA"},
    {"id": 3, "name": "College of Arts, Sciences, & Education",    "code": "CASE"},
    {"id": 4, "name": "College of Nursing & Allied Health Sciences","code": "CNAHS"},
    {"id": 5, "name": "College of Computer Studies",               "code": "CCS"},
    {"id": 6, "name": "College of Criminal Justice",               "code": "CCJ"},
]

DEPARTMENTS = [
    # CEA
    {"id":  1, "name": "Architecture",              "code": "ARCH", "college_id": 1},
    {"id":  2, "name": "Chemical Engineering",      "code": "ChE",  "college_id": 1},
    {"id":  3, "name": "Civil Engineering",         "code": "CE",   "college_id": 1},
    {"id":  4, "name": "Computer Engineering",      "code": "CpE",  "college_id": 1},
    {"id":  5, "name": "Electrical Engineering",    "code": "EE",   "college_id": 1},
    {"id":  6, "name": "Electronics Engineering",   "code": "ECE",  "college_id": 1},
    {"id":  7, "name": "Industrial Engineering",    "code": "IE",   "college_id": 1},
    {"id":  8, "name": "Mechanical Engineering",    "code": "ME",   "college_id": 1},
    {"id":  9, "name": "Mining Engineering",        "code": "MnE",  "college_id": 1},
    # CMBA
    {"id": 10, "name": "Accountancy",               "code": "ACCT", "college_id": 2},
    {"id": 11, "name": "Business Administration",   "code": "BA",   "college_id": 2},
    {"id": 12, "name": "Hospitality Management",    "code": "HM",   "college_id": 2},
    {"id": 13, "name": "Tourism Management",        "code": "TM",   "college_id": 2},
    {"id": 14, "name": "Office Administration",     "code": "OA",   "college_id": 2},
    {"id": 15, "name": "Public Administration",     "code": "PA",   "college_id": 2},
    # CASE
    {"id": 16, "name": "Communication",             "code": "COM",  "college_id": 3},
    {"id": 17, "name": "English & Applied Linguistics", "code": "EAL", "college_id": 3},
    {"id": 18, "name": "Education",                 "code": "ED",   "college_id": 3},
    {"id": 19, "name": "Multimedia Arts",           "code": "MMA",  "college_id": 3},
    {"id": 20, "name": "Biology",                   "code": "BIO",  "college_id": 3},
    {"id": 21, "name": "Mathematics",               "code": "MATH", "college_id": 3},
    {"id": 22, "name": "Psychology",                "code": "PSY",  "college_id": 3},
    {"id": 23, "name": "Special Needs Education",   "code": "SNE",  "college_id": 3},
    # CNAHS
    {"id": 24, "name": "Nursing",                   "code": "NUR",  "college_id": 4},
    {"id": 25, "name": "Pharmacy",                  "code": "PHAR", "college_id": 4},
    {"id": 26, "name": "Medical Technology",        "code": "MT",   "college_id": 4},
    # CCS
    {"id": 27, "name": "Computer Science",          "code": "CS",   "college_id": 5},
    {"id": 28, "name": "Information Technology",    "code": "IT",   "college_id": 5},
    # CCJ
    {"id": 29, "name": "Criminology",               "code": "CRIM", "college_id": 6},
]

COURSES = [
    # ── CEA ──────────────────────────────────────────────────────────────────
    {"id":  1, "name": "BS Architecture",                                           "department_id":  1},
    {"id":  2, "name": "BS Chemical Engineering",                                   "department_id":  2},
    {"id":  3, "name": "BS Civil Engineering",                                      "department_id":  3},
    {"id":  4, "name": "BS Computer Engineering",                                   "department_id":  4},
    {"id":  5, "name": "BS Electrical Engineering",                                 "department_id":  5},
    {"id":  6, "name": "BS Electronics Engineering",                                "department_id":  6},
    {"id":  7, "name": "BS Industrial Engineering",                                 "department_id":  7},
    {"id":  8, "name": "BS Mechanical Engineering with Computational Science",      "department_id":  8},
    {"id":  9, "name": "BS Mechanical Engineering with Mechatronics",               "department_id":  8},
    {"id": 10, "name": "BS Mining Engineering",                                     "department_id":  9},
    {"id": 11, "name": "Diploma in Manufacturing and Semiconductor Technology",     "department_id":  7},
    {"id": 12, "name": "Master of Engineering (Chemical, Civil, Industrial, Mechanical)", "department_id": 3},
    {"id": 13, "name": "Master of Engineering Education",                           "department_id":  7},
    {"id": 14, "name": "Professional Science Master in Industrial Automation",      "department_id":  7},
    # ── CMBA ─────────────────────────────────────────────────────────────────
    {"id": 15, "name": "BS Accountancy",                                            "department_id": 10},
    {"id": 16, "name": "BS Accounting Information Systems",                         "department_id": 10},
    {"id": 17, "name": "BS Management Accounting",                                  "department_id": 10},
    {"id": 18, "name": "BS Business Administration – Banking & Financial Management","department_id": 11},
    {"id": 19, "name": "BS Business Administration – Business Analytics",           "department_id": 11},
    {"id": 20, "name": "BS Business Administration – General Business Management",  "department_id": 11},
    {"id": 21, "name": "BS Business Administration – Human Resource Management",    "department_id": 11},
    {"id": 22, "name": "BS Business Administration – Marketing Management",         "department_id": 11},
    {"id": 23, "name": "BS Business Administration – Operations Management",        "department_id": 11},
    {"id": 24, "name": "BS Business Administration – Quality Management",           "department_id": 11},
    {"id": 25, "name": "BS Hospitality Management",                                 "department_id": 12},
    {"id": 26, "name": "BS Tourism Management",                                     "department_id": 13},
    {"id": 27, "name": "BS Office Administration",                                  "department_id": 14},
    {"id": 28, "name": "Associate in Office Administration",                        "department_id": 14},
    {"id": 29, "name": "Bachelor in Public Administration",                         "department_id": 15},
    {"id": 30, "name": "Master in Business Administration",                         "department_id": 11},
    {"id": 31, "name": "Master in Public Administration",                           "department_id": 15},
    {"id": 32, "name": "Doctor of Philosophy in Management",                        "department_id": 11},
    {"id": 33, "name": "Doctor in Business Administration",                         "department_id": 11},
    {"id": 34, "name": "Doctor in Public Administration",                           "department_id": 15},
    # ── CASE ─────────────────────────────────────────────────────────────────
    {"id": 35, "name": "AB Communication",                                          "department_id": 16},
    {"id": 36, "name": "AB English with Applied Linguistics",                       "department_id": 17},
    {"id": 37, "name": "Bachelor of Elementary Education",                          "department_id": 18},
    {"id": 38, "name": "Bachelor of Secondary Education – Major in English",        "department_id": 18},
    {"id": 39, "name": "Bachelor of Secondary Education – Major in Filipino",       "department_id": 18},
    {"id": 40, "name": "Bachelor of Secondary Education – Major in Mathematics",    "department_id": 18},
    {"id": 41, "name": "Bachelor of Secondary Education – Major in Science",        "department_id": 18},
    {"id": 42, "name": "Bachelor of Multimedia Arts",                               "department_id": 19},
    {"id": 43, "name": "BS Biology",                                                "department_id": 20},
    {"id": 44, "name": "BS Math with Applied Industrial Mathematics",               "department_id": 21},
    {"id": 45, "name": "BS Psychology",                                             "department_id": 22},
    {"id": 46, "name": "Bachelor of Special Needs Education – Generalist",          "department_id": 23},
    {"id": 47, "name": "Diploma in Professional Education",                         "department_id": 18},
    {"id": 48, "name": "Master of Arts in Education – English Language Teaching",   "department_id": 18},
    {"id": 49, "name": "Master of Arts in Education – Filipino",                    "department_id": 18},
    {"id": 50, "name": "Master of Arts in Education – Mathematics",                 "department_id": 18},
    {"id": 51, "name": "Master of Arts in Education – Science & Technology",        "department_id": 18},
    {"id": 52, "name": "Master of Arts in Psychology – Social Psychology",          "department_id": 22},
    {"id": 53, "name": "Master of Arts in Psychology – Clinical Psychology",        "department_id": 22},
    {"id": 54, "name": "Master of Arts in Psychology – Industrial Psychology",      "department_id": 22},
    {"id": 55, "name": "Master of Science in Teaching Mathematics",                 "department_id": 21},
    # ── CNAHS ────────────────────────────────────────────────────────────────
    {"id": 56, "name": "BS Nursing",                                                "department_id": 24},
    {"id": 57, "name": "BS Pharmacy",                                               "department_id": 25},
    {"id": 58, "name": "BS Medical Technology",                                     "department_id": 26},
    {"id": 59, "name": "Master of Science in Nursing",                              "department_id": 24},
    # ── CCS ──────────────────────────────────────────────────────────────────
    {"id": 60, "name": "BS Computer Science",                                       "department_id": 27},
    {"id": 61, "name": "BS Information Technology",                                 "department_id": 28},
    {"id": 62, "name": "Master in Computer Science",                                "department_id": 27},
    {"id": 63, "name": "Master of Science in Computer Science",                     "department_id": 27},
    {"id": 64, "name": "Master in Information Technology",                          "department_id": 28},
    {"id": 65, "name": "Diploma in Computing",                                      "department_id": 27},
    {"id": 66, "name": "Doctor in Information Technology",                          "department_id": 28},
    # ── CCJ ──────────────────────────────────────────────────────────────────
    {"id": 67, "name": "BS Criminology",                                            "department_id": 29},
]


def seed_data(apps, schema_editor):
    Role       = apps.get_model("accounts", "Role")
    College    = apps.get_model("accounts", "College")
    Department = apps.get_model("accounts", "Department")
    Course     = apps.get_model("accounts", "Course")

    for name in ROLES:
        Role.objects.get_or_create(name=name)

    for c in COLLEGES:
        College.objects.update_or_create(
            id=c["id"], defaults={"name": c["name"], "code": c["code"]}
        )

    for d in DEPARTMENTS:
        Department.objects.update_or_create(
            id=d["id"],
            defaults={"name": d["name"], "code": d["code"], "college_id": d["college_id"]},
        )

    for c in COURSES:
        Course.objects.update_or_create(
            id=c["id"],
            defaults={"name": c["name"], "department_id": c["department_id"]},
        )


def unseed_data(apps, schema_editor):
    Course.objects.filter(id__in=[c["id"] for c in COURSES]).delete()
    Department.objects.filter(id__in=[d["id"] for d in DEPARTMENTS]).delete()
    College.objects.filter(id__in=[c["id"] for c in COLLEGES]).delete()
    Role.objects.filter(name__in=ROLES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_update_user_model"),
    ]

    operations = [
        migrations.RunPython(seed_data, reverse_code=unseed_data),
    ]
