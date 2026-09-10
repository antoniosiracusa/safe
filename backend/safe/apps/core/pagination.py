from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Paginazione uniforme: {count, next, previous, results}; page_size default 50, max 200."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
