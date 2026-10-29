"""
IR-126: reference data seeded with explicit ids must not break ordinary creation.

accounts/0003 inserts Colleges, Departments and Courses with literal ids. On
Postgres an explicit-id insert does not advance the table's id sequence, so the
first create() afterwards asked for id 1 and hit a duplicate primary key. The
test database is built by running the migrations, so it reproduces exactly what
a fresh deployment looks like.
"""
from django.test import TestCase

from apps.accounts.models import College, Course, Department


class SeededReferenceDataAllowsCreationTests(TestCase):

    def test_a_new_college_can_be_created_after_the_seed(self):
        college = College.objects.create(name="College of Maritime Studies", code="CMS")

        self.assertEqual(College.objects.get(code="CMS"), college)

    def test_a_new_department_can_be_created_after_the_seed(self):
        college = College.objects.get(code="CCS")

        department = Department.objects.create(
            name="Data Science", code="DS", college=college,
        )

        self.assertEqual(Department.objects.get(code="DS"), department)

    def test_a_new_course_can_be_created_after_the_seed(self):
        department = Department.objects.get(code="CS")

        course = Course.objects.create(name="BS Data Science", department=department)

        self.assertEqual(Course.objects.get(name="BS Data Science"), course)
