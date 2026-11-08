"""Role-aware requisition API."""

from rest_framework import exceptions, permissions, viewsets
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q

from accounts.models import UserRole
from accounts.permissions import IsHRStaff, has_full_access
from audit.models import log_audit
from .models import Requisition, RequisitionStatus
from .serializers import RequisitionSerializer


class RequisitionPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class RequisitionViewSet(viewsets.ModelViewSet):
    serializer_class = RequisitionSerializer
    pagination_class = RequisitionPagination
    lookup_field = "reference_code"
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if getattr(self, "action", None) in {"create", "update", "partial_update", "destroy"}:
            return [IsHRStaff()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        queryset = Requisition.objects.select_related("created_by", "hiring_manager")
        if has_full_access(user):
            pass
        elif user.role == UserRole.RECRUITER:  # interviewer only: requisitions of the candidates assigned to them
            queryset = queryset.filter(interviews__interviewer=user).exclude(interviews__status="CANCELLED").distinct()
        else:
            return queryset.none()

        status_filter = self.request.query_params.get("status")
        if status_filter:
            valid_statuses = {choice for choice, _label in RequisitionStatus.choices}
            if status_filter not in valid_statuses:
                raise exceptions.ValidationError({"status": "Invalid requisition status."})
            queryset = queryset.filter(status=status_filter)

        department = self.request.query_params.get("department")
        if department:
            queryset = queryset.filter(department__iexact=department.strip())

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(department__icontains=search)
                | Q(location__icontains=search)
                | Q(description__icontains=search)
            )
        return queryset

    def perform_create(self, serializer):
        requisition = serializer.save(created_by=self.request.user)
        log_audit(self.request.user, "REQUISITION_CREATED", "requisition", requisition.reference_code,
                  title=requisition.title, status=requisition.status)

    def perform_update(self, serializer):
        current_status = serializer.instance.status
        next_status = serializer.validated_data.get("status", current_status)
        allowed_transitions = {
            RequisitionStatus.DRAFT: {
                RequisitionStatus.DRAFT, RequisitionStatus.OPEN, RequisitionStatus.CLOSED,
            },
            RequisitionStatus.OPEN: {
                RequisitionStatus.OPEN, RequisitionStatus.ON_HOLD, RequisitionStatus.CLOSED,
            },
            RequisitionStatus.ON_HOLD: {
                RequisitionStatus.ON_HOLD, RequisitionStatus.OPEN, RequisitionStatus.CLOSED,
            },
            RequisitionStatus.CLOSED: {RequisitionStatus.CLOSED},
        }
        if next_status not in allowed_transitions[current_status]:
            raise exceptions.ValidationError(
                {"status": f"Cannot change a {current_status} requisition to {next_status}."}
            )
        changed = sorted(
            key for key, value in serializer.validated_data.items()
            if getattr(serializer.instance, key, None) != value
        )
        requisition = serializer.save()
        if changed:
            log_audit(self.request.user, "REQUISITION_UPDATED", "requisition", requisition.reference_code,
                      changed_fields=changed, status_from=current_status, status_to=requisition.status)

    def perform_destroy(self, instance):
        if instance.status != RequisitionStatus.DRAFT:
            raise exceptions.ValidationError(
                "Only draft requisitions can be deleted. Close an active requisition instead."
            )
        log_audit(self.request.user, "REQUISITION_DELETED", "requisition", instance.reference_code, title=instance.title)
        instance.delete()
