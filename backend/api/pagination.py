from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


def paginated_response(request, queryset, serializer_class):
    """Paginate a queryset. Orders by pk when unordered so pages are stable."""
    if not queryset.ordered:
        queryset = queryset.order_by("pk")
    paginator = StandardPagination()
    page = paginator.paginate_queryset(queryset, request)
    data = serializer_class(page, many=True).data
    return paginator.get_paginated_response(data)
