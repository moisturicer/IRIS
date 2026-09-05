"""Ask IRIS endpoints — grounded Q&A and ranked retrieval over the record corpus."""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.ai.services.rag_pipeline import DEFAULT_TOP_K, RAGPipelineService
from apps.ai.services.retrieval import MAX_TOP_K, search_records

MAX_QUESTION_LENGTH = 2000


class AIQueryThrottle(UserRateThrottle):
    """Retrieval hits the DB and may hit a paid provider — cap it per user."""

    scope = "ai_query"


def _parse_top_k(raw, default: int = DEFAULT_TOP_K) -> int:
    try:
        return max(1, min(int(raw), MAX_TOP_K))
    except (TypeError, ValueError):
        return default


class ChatQueryView(APIView):
    """
    POST /api/v1/ai/ask/
    Body: {"question": str, "top_k": int?}

    Returns an answer grounded in readable records, with the record ids it used.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AIQueryThrottle]

    def post(self, request):
        question = (request.data.get("question") or "").strip()
        if not question:
            return Response(
                {"detail": "question is required."}, status=status.HTTP_400_BAD_REQUEST
            )
        if len(question) > MAX_QUESTION_LENGTH:
            return Response(
                {"detail": f"question must be at most {MAX_QUESTION_LENGTH} characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = RAGPipelineService().answer(
            question, top_k=_parse_top_k(request.data.get("top_k"))
        )
        return Response(result)


class SemanticSearchView(APIView):
    """
    POST /api/v1/ai/search/
    Body: {"query": str, "top_k": int?}

    Ranked retrieval without synthesis — the list behind an answer.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AIQueryThrottle]

    def post(self, request):
        query = (request.data.get("query") or "").strip()
        if not query:
            return Response(
                {"detail": "query is required."}, status=status.HTTP_400_BAD_REQUEST
            )

        sources = search_records(query, top_k=_parse_top_k(request.data.get("top_k"), 10))
        return Response({"results": [s.as_dict() for s in sources], "count": len(sources)})


class AIStatusView(APIView):
    """
    GET /api/v1/ai/status/
    Lets the UI tell the user which mode answers will come back in, rather than
    silently degrading.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.ai.services.llm_generator import LLMGenerator
        from apps.records.models import Record

        generator = LLMGenerator()
        return Response(
            {
                "retrieval": "postgres_fts",
                "generative": generator.is_configured(),
                "mode": "generative" if generator.is_configured() else "extractive",
                "indexed_records": Record.objects.publicly_visible().count(),
            }
        )
