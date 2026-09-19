from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import GenericAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.accounts.models import Notification, Role
from apps.accounts.notification_serializers import NotificationSerializer
from apps.accounts.permissions import IsEnabledAuthenticated, active_roles


class NotificationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


class NotificationScopeMixin:
    permission_classes = (IsEnabledAuthenticated,)

    def recipient_role(self):
        role = self.request.query_params.get("role", "")
        if role not in (Role.OWNER, Role.CUSTOMER, Role.PHYSIOTHERAPIST):
            raise PermissionDenied("Notification role is unavailable.")
        has_role = active_roles(self.request.user, self.request.organization).filter(role=role).exists()
        if not has_role and role == Role.PHYSIOTHERAPIST:
            from apps.practitioners.models import PractitionerApplication

            has_role = PractitionerApplication.objects.filter(
                applicant=self.request.user,
                organization=self.request.organization,
            ).exists()
        if not has_role:
            raise PermissionDenied("Notification access is unavailable.")
        return role

    def scoped_queryset(self):
        return Notification.objects.filter(
            organization=self.request.organization,
            recipient=self.request.user,
            recipient_role=self.recipient_role(),
        )


class NotificationListView(NotificationScopeMixin, GenericAPIView):
    serializer_class = NotificationSerializer
    pagination_class = NotificationPagination

    def get(self, request):
        queryset = self.scoped_queryset().filter(read_at__isnull=True)
        unread_count = queryset.count()
        category_counts = {
            row["category"]: row["count"]
            for row in queryset.values("category").annotate(count=Count("id"))
        }
        page = self.paginate_queryset(queryset)
        paginator = self.paginator
        return Response({
            "count": paginator.page.paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "unread_count": unread_count,
            "category_counts": category_counts,
            "results": self.get_serializer(page, many=True).data,
        })


class NotificationUnreadCountView(NotificationScopeMixin, GenericAPIView):
    def get(self, request):
        counts = self.scoped_queryset().filter(read_at__isnull=True).aggregate(
            unread_count=Count("id"),
            appointments=Count("id", filter=Q(category=Notification.Category.APPOINTMENTS)),
            practitioners=Count("id", filter=Q(category=Notification.Category.PRACTITIONERS)),
            payments=Count("id", filter=Q(category=Notification.Category.PAYMENTS)),
            reviews=Count("id", filter=Q(category=Notification.Category.REVIEWS)),
        )
        return Response({
            "unread_count": counts["unread_count"],
            "category_counts": {
                Notification.Category.APPOINTMENTS: counts["appointments"],
                Notification.Category.PRACTITIONERS: counts["practitioners"],
                Notification.Category.PAYMENTS: counts["payments"],
                Notification.Category.REVIEWS: counts["reviews"],
            },
        })


class NotificationReadView(NotificationScopeMixin, GenericAPIView):
    serializer_class = NotificationSerializer

    def post(self, request, pk):
        notification = self.scoped_queryset().filter(pk=pk).first()
        if notification is None:
            from rest_framework.exceptions import NotFound
            raise NotFound("Notification is unavailable.")
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=("read_at",))
        return Response(self.get_serializer(notification).data)
