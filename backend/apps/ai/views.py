from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsStaff
from .models import RecordEmbedding, EmbeddingJob
from .serializers import SemanticSearchResultSerializer, EmbeddingJobSerializer
from .tasks import embed_record, embed_all_records


class SemanticSearchView(APIView):
    """
    POST /ai/search/
    Body: { "query": "...", "top_k": 10 }
    Returns: { "results": [{ id, title, abstract, authors, year, score }, ...] }

    Performs cosine-similarity semantic search over all stored RecordEmbeddings
    and returns the top-k most relevant records with their similarity scores.

    TODO (AI engineer): Optionally extend this endpoint to also return an
    LLM-generated summary of the top results (RAG pass over ranked records).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        query = request.data.get("query", "").strip()
        top_k = int(request.data.get("top_k", 10))

        if not query:
            return Response({"detail": "query is required."}, status=400)

        # TODO (AI engineer — FR-M4-01 architecture change):
        # Replace SentenceTransformer + numpy cosine sim with:
        #   1. Embed query via third-party API (same as embed_record task)
        #   2. Query pgvector:
        #        from pgvector.django import L2Distance, CosineDistance
        #        results = (
        #            RecordEmbedding.objects
        #            .select_related("record")
        #            .prefetch_related("record__authors")
        #            .annotate(score=1 - CosineDistance("embedding", q_vec))
        #            .order_by("-score")[:top_k]
        #        )
        #   3. Build results list from queryset (no manual loop needed).
        # Remove: sentence_transformers, pickle, numpy imports below.

        from django.conf import settings
        from sentence_transformers import SentenceTransformer
        import pickle
        import numpy as np

        model = SentenceTransformer(settings.AI_EMBEDDING_MODEL)
        q_vec = model.encode(query)

        embeddings = RecordEmbedding.objects.select_related("record").prefetch_related("record__authors").all()
        if not embeddings.exists():
            return Response({"results": []})

        scores = []
        for emb in embeddings:
            vec = pickle.loads(emb.embedding)
            sim = float(np.dot(q_vec, vec) / (np.linalg.norm(q_vec) * np.linalg.norm(vec) + 1e-9))
            scores.append((sim, emb.record))

        top_pairs = sorted(scores, key=lambda x: x[0], reverse=True)[:top_k]

        results = [
            {
                "id":       record.id,
                "title":    record.title,
                "abstract": record.abstract or None,
                "authors":  ", ".join(a.name for a in record.authors.all()) or None,
                "year":     record.year_accomplished,
                "score":    round(sim, 4),
            }
            for sim, record in top_pairs
        ]

        return Response({"results": results})


class AskView(APIView):
    """
    POST /ai/ask/
    Body: { "question": "..." }
    Returns: { "answer": str|null, "citations": [record_id, ...], "message": str|null }

    Finds the top-5 most relevant records by semantic similarity and returns
    their IDs as citations. Returns a message when the knowledge base is empty.
    LLM answer generation is not yet implemented.

    TODO (AI engineer): Add RAG answer generation here.
      1. Build a context string from the top records' titles + abstracts.
      2. Call the OpenAI API: client.chat.completions.create(model="gpt-4.1-mini", ...).
      3. Replace `answer: None` with the LLM-generated response string.
      4. Consider extracting shared embedding logic into apps/ai/services.py.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        question = request.data.get("question", "").strip()
        if not question:
            return Response({"detail": "question is required."}, status=400)

        # TODO (AI engineer — FR-M4-02 architecture change):
        # Replace SentenceTransformer + numpy cosine sim with pgvector query (same pattern
        # as SemanticSearchView above), then implement LLM answer generation:
        #   1. Embed question via third-party API → q_vec
        #   2. pgvector top-5 query (see SemanticSearchView TODO for pattern)
        #   3. Build context string from top-5 titles + abstracts
        #   4. Read optional history from request.data.get("history", [])
        #   5. Call GPT-4.1-mini:
        #        import openai
        #        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        #        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        #        messages += history            # prior turns
        #        messages += [{"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}]
        #        resp = client.chat.completions.create(model="gpt-4.1-mini", messages=messages)
        #        answer = resp.choices[0].message.content
        #   6. Return {"answer": answer, "citations": citation_ids, "message": None}
        # Remove: sentence_transformers, pickle, numpy below.

        from django.conf import settings
        from sentence_transformers import SentenceTransformer
        import pickle
        import numpy as np

        model = SentenceTransformer(settings.AI_EMBEDDING_MODEL)
        q_vec = model.encode(question)

        embeddings = RecordEmbedding.objects.select_related("record").all()
        if not embeddings.exists():
            return Response({
                "answer":    None,
                "citations": [],
                "message":   "No embeddings found. Run /ai/embed/all/ to index records first.",
            })

        scores = []
        for emb in embeddings:
            vec = pickle.loads(emb.embedding)
            sim = float(np.dot(q_vec, vec) / (np.linalg.norm(q_vec) * np.linalg.norm(vec) + 1e-9))
            scores.append((sim, emb.record))

        top_k     = 5
        top_pairs = sorted(scores, key=lambda x: x[0], reverse=True)[:top_k]
        citations = [r.id for _, r in top_pairs]

        # TODO: replace None with GPT-4.1-mini answer (see docstring above)
        return Response({"answer": None, "citations": citations, "message": None})


class SummarizeView(APIView):
    """
    POST /ai/summarize/<pk>/
    Body: (empty)
    Returns: { "summary": { "objectives": str, "methodology": str, "findings": str, "conclusion": str } }

    Generates a four-part structured summary of a record by passing its extracted
    PDF text to GPT-4.1-mini. Returns 404 if no completed PdfExtraction exists.

    TODO (AI engineer — FR-M4-02):
      1. Fetch the completed PdfExtraction for the given record pk (status="done").
         Return 404 if none exists.
      2. Build a prompt instructing GPT-4.1-mini to produce four sections:
         objectives, methodology, findings, conclusion.
      3. Call GPT-4.1-mini:
           import openai
           client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
           resp = client.chat.completions.create(
               model="gpt-4.1-mini",
               messages=[
                   {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
                   {"role": "user", "content": extraction.extracted_text},
               ],
           )
      4. Parse the structured response and return:
           { "summary": { "objectives": ..., "methodology": ..., "findings": ..., "conclusion": ... } }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        # TODO (AI engineer): implement summarization — see docstring above
        return Response(
            {"detail": "Summarization not yet implemented."},
            status=501,
        )


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
