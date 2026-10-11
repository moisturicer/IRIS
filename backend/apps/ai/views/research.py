"""Owner-only, read-only run telemetry; no corpus or answer text (IR-512)."""

from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated

from apps.ai.models import ResearchRun, ResearchStep


class ResearchStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResearchStep
        fields = ["id", "position", "kind", "tool", "argument_digest", "status",
                  "duplicate", "latency_ms", "input_tokens", "output_tokens"]
        read_only_fields = fields


class ResearchRunSerializer(serializers.ModelSerializer):
    steps = ResearchStepSerializer(many=True, read_only=True)

    class Meta:
        model = ResearchRun
        fields = ["id", "conversation_id", "created_at", "status", "stop_reason",
                  "latency_ms", "prompt_tokens", "output_tokens", "validation_codes", "steps"]
        read_only_fields = fields


class ResearchRunDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ResearchRunSerializer

    def get_queryset(self):
        return ResearchRun.objects.owned_by(self.request.user).prefetch_related("steps")
