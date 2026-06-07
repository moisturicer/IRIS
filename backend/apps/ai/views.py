from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsStaff
from .models import RecordEmbedding, EmbeddingJob
from .serializers import SemanticSearchResultSerializer, EmbeddingJobSerializer
from .tasks import embed_record, embed_all_records

class EmbedRecordView(APIView):
    """POST /ai/embed/<id>/ -- queue embedding for one record."""
    permission_classes = [IsAuthenticated, IsStaff]

    def post(self, request, pk):
        job = EmbeddingJob.objects.create(record_id=pk)
        task = embed_record.delay(pk)
        job.celery_task_id = task.id
        job.save(update_fields=["celery_task_id"])
        return Response(EmbeddingJobSerializer(job).data)


class EmbedAllView(APIView):
    """
    POST /ai/embed/all/
    Queries all records that have no RecordEmbedding, creates an EmbeddingJob
    for each, enqueues an embed_record task per record, and returns the count.
    """
    permission_classes = [IsAuthenticated, IsStaff]

    def post(self, request):
        from apps.records.models import Record
        from rest_framework import status as http_status

        missing_ids = list(
            Record.objects.exclude(
                pk__in=RecordEmbedding.objects.values_list("record_id", flat=True)
            ).values_list("pk", flat=True)
        )

        for record_id in missing_ids:
            job = EmbeddingJob.objects.create(record_id=record_id)
            task = embed_record.delay(record_id)
            job.celery_task_id = task.id
            job.save(update_fields=["celery_task_id"])

        return Response({"enqueued": len(missing_ids)}, status=http_status.HTTP_202_ACCEPTED)


class EmbeddingJobListView(APIView):
    """GET /ai/embed/jobs/ -- list recent embedding jobs."""
    permission_classes = [IsAuthenticated, IsStaff]

    def get(self, request):
        jobs = EmbeddingJob.objects.select_related("record").order_by("-created_at")[:50]
        return Response(EmbeddingJobSerializer(jobs, many=True).data)
