from rest_framework.pagination import PageNumberPagination


class StandardResultsPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class LargeResultsPagination(PageNumberPagination):
    """Use for reference data endpoints (colleges, depts, courses)."""
    page_size = 200
    max_page_size = 500
