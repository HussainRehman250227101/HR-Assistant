from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsRecruiterOrAdmin
from .models import AuditEvent


class AuditPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class AuditEventListView(APIView):
    permission_classes = [IsRecruiterOrAdmin]

    def get(self, request):
        qs = AuditEvent.objects.select_related("actor")
        for param in ("action", "entity_type", "entity_id"):
            if request.query_params.get(param):
                qs = qs.filter(**{param: request.query_params[param]})
        paginator = AuditPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([{
            "id": str(e.public_id), "action": e.action, "entity_type": e.entity_type, "entity_id": e.entity_id,
            "actor_name": (e.actor.get_full_name() or e.actor.username) if e.actor else "System",
            "details": e.details, "created_at": e.created_at,
        } for e in page])
