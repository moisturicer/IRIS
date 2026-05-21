from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from .models import Notification, NotificationRead
from .serializers import NotificationSerializer


class NotificationListView(generics.ListAPIView):
    """
    GET /notifications/
    Returns notifications for the current user:
      - direct notifications where recipient = user
      - broadcast notifications where broadcast_to_role = user.role
    Supports ?unread=true to filter unread only.
    """
    serializer_class   = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Notification.objects.filter(
            Q(recipient=user) | Q(broadcast_to_role=user.role)
        ).select_related("notif_type", "record", "sender").order_by("-created_at")

        if self.request.query_params.get("unread") == "true":
            read_ids = NotificationRead.objects.filter(user=user).values_list("notification_id", flat=True)
            qs = qs.exclude(pk__in=read_ids)

        return qs


class MarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        notification = Notification.objects.get(pk=pk)
        NotificationRead.objects.get_or_create(notification=notification, user=request.user)
        return Response({"detail": "Marked as read."})


class MarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        notifications = Notification.objects.filter(
            Q(recipient=user) | Q(broadcast_to_role=user.role)
        )
        for n in notifications:
            NotificationRead.objects.get_or_create(notification=n, user=user)
        return Response({"detail": "All marked as read."})
