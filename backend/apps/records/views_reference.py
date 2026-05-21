from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from core.pagination import LargeResultsPagination
from .models import Classification, PSCEDClassification, RecordType
from .serializers import ClassificationSerializer, PSCEDSerializer, RecordTypeSerializer


class ClassificationListView(ListAPIView):
    queryset           = Classification.objects.all()
    serializer_class   = ClassificationSerializer
    pagination_class   = LargeResultsPagination
    permission_classes = [IsAuthenticated]


class PSCEDListView(ListAPIView):
    queryset           = PSCEDClassification.objects.all()
    serializer_class   = PSCEDSerializer
    pagination_class   = LargeResultsPagination
    permission_classes = [IsAuthenticated]


class RecordTypeListView(ListAPIView):
    queryset           = RecordType.objects.all()
    serializer_class   = RecordTypeSerializer
    pagination_class   = LargeResultsPagination
    permission_classes = [IsAuthenticated]
