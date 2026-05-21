from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import RecordEmbedding, EmbeddingJob
from .serializers import SemanticSearchResultSerializer, EmbeddingJobSerializer
from .tasks import embed_record, embed_all_records


class SemanticSearchView(APIView):
    """
    POST /ai/search/
    Body: { "query": "...", "top_k": 5 }
    Returns: { "answer": "...", "sources": [...] }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        query = request.data.get("query", "").strip()
        top_k = int(request.data.get("top_k", 5))

        if not query:
            return Response({"detail": "query is required."}, status=400)

        # Embed the query
        from django.conf import settings
        from sentence_transformers import SentenceTransformer
        import pickle
        import numpy as np

        model    = SentenceTransformer(settings.AI_EMBEDDING_MODEL)
        q_vec    = model.encode(query)

        # Cosine similarity against all stored embeddings
        embeddings = RecordEmbedding.objects.select_related("record").all()
        scores = []
        for emb in embeddings:
            vec = pickle.loads(emb.embedding)
            sim = float(np.dot(q_vec, vec) / (np.linalg.norm(q_vec) * np.linalg.norm(vec) + 1e-9))
            scores.append((sim, emb.record))

        top_records = [r for _, r in sorted(scores, key=lambda x: x[0], reverse=True)[:top_k]]

        # Build context and call Anthropic
        import anthropic
        context = "\n\n".join(
            f"Title: {r.title}\nAbstract: {r.abstract[:300]}"
            for r in top_records
        )
        client  = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system="You are an assistant for IRIS, an Intelligent Research and IP System. Answer based only on the provided research records.",
            messages=[{"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"}],
        )
        answer = message.content[0].text

        from apps.records.serializers import RecordListSerializer
        return Response({
            "answer":  answer,
            "sources": RecordListSerializer(top_records, many=True, context={"request": request}).data,
        })


class AskView(APIView):
    """
    POST /ai/ask/
    Body: { "question": "..." }
    Returns: { "answer": "...", "citations": [record_id, ...] }

    Runs RAG: embeds question, fetches top-k records, calls Anthropic for an answer.
    Reuses SemanticSearchView logic but returns only the answer (no full source objects).
    TODO: extract shared RAG logic into a service function.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        question = request.data.get("question", "").strip()
        if not question:
            return Response({"detail": "question is required."}, status=400)

        from django.conf import settings
        from sentence_transformers import SentenceTransformer
        import pickle
        import numpy as np

        model = SentenceTransformer(settings.AI_EMBEDDING_MODEL)
        q_vec = model.encode(question)

        embeddings = RecordEmbedding.objects.select_related("record").all()
        scores = []
        for emb in embeddings:
            vec = pickle.loads(emb.embedding)
            sim = float(np.dot(q_vec, vec) / (np.linalg.norm(q_vec) * np.linalg.norm(vec) + 1e-9))
            scores.append((sim, emb.record))

        top_k      = 5
        top_pairs  = sorted(scores, key=lambda x: x[0], reverse=True)[:top_k]
        top_records = [r for _, r in top_pairs]
        citations   = [r.id for r in top_records]

        context = "\n\n".join(
            f"Title: {r.title}\nAbstract: {r.abstract[:400]}"
            for r in top_records
        )

        import anthropic
        client  = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=(
                "You are a research assistant for IRIS, an Intelligent Research and IP System. "
                "Answer the user's question using only the provided research records as context. "
                "Be concise and accurate. If the context does not contain enough information, say so."
            ),
            messages=[{"role": "user", "content": f"Research context:\n{context}\n\nQuestion: {question}"}],
        )

        return Response({"answer": message.content[0].text, "citations": citations})


class EmbedRecordView(APIView):
    """POST /ai/embed/<id>/ -- queue embedding for one record."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        job = EmbeddingJob.objects.create(record_id=pk)
        task = embed_record.delay(pk)
        job.celery_task_id = task.id
        job.save(update_fields=["celery_task_id"])
        return Response(EmbeddingJobSerializer(job).data)


class EmbedAllView(APIView):
    """POST /ai/embed/all/ -- queue embeddings for all records missing one."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        embed_all_records.delay()
        return Response({"detail": "Bulk embedding queued."})


class EmbeddingJobListView(APIView):
    """GET /ai/embed/jobs/ -- list recent embedding jobs."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        jobs = EmbeddingJob.objects.select_related("record").order_by("-created_at")[:50]
        return Response(EmbeddingJobSerializer(jobs, many=True).data)
