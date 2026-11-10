"""The signed-in Discover search for people (IR-697)."""

from django.db.models import Count, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce, Lower
from rest_framework.exceptions import ValidationError

from core.enums import RoleName

from . import profile, public_profile

OFFICE_ROLES = (RoleName.ITSO, RoleName.IERC, RoleName.KTTO, RoleName.RDCO)
SEARCH_ROLES = (RoleName.STUDENT, RoleName.ADVISER, *OFFICE_ROLES)
BAD_FILTER = "Provide a valid college or department ID."


def _filter_id(params, key):
    raw = params.get(key)
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError({key: BAD_FILTER})
    if value < 1:
        raise ValidationError({key: BAD_FILTER})
    return value


def _role_filter(queryset, raw):
    if raw is None or raw == "":
        return queryset
    value = raw.strip().casefold()
    if value == "faculty":
        value = RoleName.ADVISER.casefold()
    if value == "office":
        return queryset.filter(role__name__in=OFFICE_ROLES)
    role = next((role for role in SEARCH_ROLES if role.casefold() == value), None)
    if role is None:
        raise ValidationError({"role": "Choose Student, Faculty or an office role."})
    return queryset.filter(role__name=role)


def _base_queryset(request, search):
    # Reuse the profile eligibility rule so a hidden profile can never leak into
    # Discover. Search fields are deliberately limited to names and interests.
    people = public_profile.open_profiles()
    if search:
        name_match = Q()
        for word in search.split():
            name_match &= (
                Q(first_name__icontains=word)
                | Q(middle_initial__icontains=word)
                | Q(last_name__icontains=word)
            )
        people = people.filter(
            name_match | Q(research_interests__name__icontains=search)
        )

    college_id = _filter_id(request.query_params, "college")
    if college_id is not None:
        people = people.filter(
            Q(student_profile__course__department__college_id=college_id)
            | Q(adviser_profile__college_id=college_id)
        )
    department_id = _filter_id(request.query_params, "department")
    if department_id is not None:
        people = people.filter(
            Q(student_profile__course__department_id=department_id)
            | Q(adviser_profile__department_id=department_id)
        )
    people = _role_filter(people, request.query_params.get("role"))

    papers = (
        public_profile.published_papers(request.user)
        .filter(owners__user_id=OuterRef("pk"))
        .order_by()
        .values("owners__user_id")
        .annotate(total=Count("pk", distinct=True))
        .values("total")[:1]
    )
    return (
        people.annotate(published_paper_count=Coalesce(Subquery(papers), Value(0)))
        .select_related(
            "role", "student_profile__course__department__college",
            "adviser_profile__college", "adviser_profile__department",
        )
        .distinct()
        .order_by(Lower("last_name"), Lower("first_name"), "pk")
    )


def _person_payload(person):
    affiliation = profile.affiliation(person)
    role_label = "Faculty" if person.role.name == RoleName.ADVISER else person.role.name
    return {
        "id": person.pk,
        "first_name": person.first_name,
        "middle_initial": person.middle_initial,
        "last_name": person.last_name,
        "role_label": role_label,
        "college_name": affiliation.college,
        "department_name": affiliation.department,
        "course_name": affiliation.course,
        "photo_url": profile.photo_url(person),
        "published_paper_count": person.published_paper_count,
    }


def search(request):
    """Return one page of public people matching Discover's search and filters."""
    try:
        page = int(request.query_params.get("page", 1))
    except (TypeError, ValueError):
        raise ValidationError({"page": public_profile.BAD_PAGE})
    try:
        page_size = int(request.query_params.get("page_size", 20))
    except (TypeError, ValueError):
        raise ValidationError({"page_size": public_profile.BAD_PAGE_SIZE})
    if page < 1:
        raise ValidationError({"page": public_profile.BAD_PAGE})
    if page_size < 1:
        raise ValidationError({"page_size": public_profile.BAD_PAGE_SIZE})
    page_size = min(page_size, public_profile.MAX_PAGE_SIZE)

    queryset = _base_queryset(request, request.query_params.get("search", "").strip())
    start = (page - 1) * page_size
    window = list(queryset[start:start + page_size + 1])
    next_url = None
    if len(window) > page_size:
        from rest_framework.utils.urls import replace_query_param

        next_url = replace_query_param(request.build_absolute_uri(), "page", page + 1)
    return {
        "next": next_url,
        "results": [_person_payload(person) for person in window[:page_size]],
    }
