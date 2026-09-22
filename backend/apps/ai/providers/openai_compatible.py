"""One adapter for every vendor that speaks the OpenAI chat format (ADR-021).

Groq, OpenRouter, OpenAI, Together, Fireworks, vLLM and Ollama differ in a base
URL, an API key and a model string. **Adapters key on the protocol, not the
vendor**: one adapter per vendor would be five near-identical files that drift,
where this makes switching Groq for OpenRouter a `.env` change with no new code.

Groq in development, OpenRouter in production, per ADR-021.

**No silent fall-through.** An absent key raises rather than degrading to a
mock or a local model -- the failure mode ADR-021 records the previous
`if/else` provider factory for, and the same rule the chunker registry applies
to an unknown strategy id.

Carries no retries, rate limiting or circuit breaking. Those compose around the
port in `apps/ai/resilience/` (IR-132), for the same reason the Voyage adapter
carries none: an adapter that retries internally cannot be tested for the
failure it hides.
"""

from __future__ import annotations

from typing import Any, Optional

from django.conf import settings

from .errors import ClassifiedError, ErrorKind, classify_message, classify_status_code


class LLMUnavailable(RuntimeError):
    """The model could not answer.

    One exception type for every vendor failure -- a Groq 429, an OpenRouter
    timeout, a malformed response -- so the resilience stack has one thing to
    catch and the domain never learns a vendor's exception hierarchy. This is
    the anti-corruption boundary; vendor quirks stop here.

    ``kind`` adds *why*, without widening that boundary (IR-320): every
    existing catch site still just catches ``LLMUnavailable``, and a caller
    that wants to branch on the reason reads ``.kind`` rather than the vendor
    exception this type replaced.
    """

    def __init__(self, message: str, kind: ErrorKind = ErrorKind.UNKNOWN) -> None:
        super().__init__(message)
        self.kind = kind


def is_configured() -> bool:
    """Whether this adapter has what it needs to reach a vendor.

    Here rather than on ``LLMProvider``: the port transports a prompt and
    nothing else, and asking every implementation "are you configured?" would
    oblige a fake to answer a question about a vendor account it does not
    have. Here rather than read off ``settings`` by a caller, because *which*
    setting configures this adapter is the adapter's own knowledge — and a
    caller holding a second copy of it is how a status endpoint ends up
    reporting "generative" against a key the adapter never reads.
    """
    return bool(getattr(settings, "LLM_API_KEY", ""))


def _classify(exc: Exception) -> ClassifiedError:
    """Classify a raw failure from ``client.chat.completions.create`` (IR-320).

    The ``openai`` SDK is the client for every vendor this adapter reaches
    (ADR-021), so its exception hierarchy -- not a per-vendor one -- is the
    first thing read: it already carries the HTTP status apart from a
    malformed response. Only a failure the SDK does not model (a raw
    ``RuntimeError`` a test double raises, or a connection error the SDK
    itself did not wrap) falls through to the message heuristic.
    """
    import openai

    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return ClassifiedError(ErrorKind.AUTH, exc)
    if isinstance(exc, openai.RateLimitError):
        return ClassifiedError(ErrorKind.RATE_LIMIT, exc)
    if isinstance(exc, openai.APITimeoutError):
        return ClassifiedError(ErrorKind.TIMEOUT, exc)
    if isinstance(exc, openai.APIConnectionError):
        return ClassifiedError(ErrorKind.NETWORK, exc)
    if isinstance(exc, openai.APIStatusError):
        kind = classify_status_code(
            exc.status_code, getattr(exc, "code", None), str(exc)
        )
        return ClassifiedError(kind, exc)
    return ClassifiedError(classify_message(str(exc)), exc)


class OpenAICompatibleAdapter:
    """`LLMProvider` over any OpenAI-compatible chat-completions endpoint."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        client: Any = None,
        temperature: Optional[float] = None,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._client = client
        self._temperature = temperature

    # -- configuration ------------------------------------------------------

    @property
    def model(self) -> str:
        return self._model or getattr(settings, "LLM_MODEL", "")

    def _resolved_key(self) -> str:
        key = self._api_key or getattr(settings, "LLM_API_KEY", "")
        if not key:
            raise LLMUnavailable(
                "LLM_API_KEY is not set. There is no unauthenticated lane and no "
                "local model to fall back to (ADR-008, ADR-021), so this fails "
                "rather than defaulting silently.",
                kind=ErrorKind.AUTH,
            )
        return key

    def _build_client(self):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise LLMUnavailable(
                "the openai package is not installed; it is the client for every "
                "OpenAI-compatible vendor, not only OpenAI (ADR-021)"
            ) from exc

        return OpenAI(
            api_key=self._resolved_key(),
            base_url=self._base_url or getattr(settings, "LLM_BASE_URL", None),
        )

    # -- the port -----------------------------------------------------------

    def generate(self, system: str, user: str) -> str:
        # An injected client is already configured -- it is how the request
        # shaping is tested without an account. Only the real one needs a key,
        # and `_build_client` is where that is demanded.
        client = self._client or self._build_client()

        temperature = (
            self._temperature
            if self._temperature is not None
            else getattr(settings, "LLM_TEMPERATURE", 0.1)
        )

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
            )
        except LLMUnavailable:
            raise
        except Exception as exc:
            classified = _classify(exc)
            raise LLMUnavailable(
                f"{type(exc).__name__}: {exc}", kind=classified.kind
            ) from exc

        choices = getattr(response, "choices", None) or []
        if not choices:
            raise LLMUnavailable("the model returned no choices")

        content = getattr(choices[0].message, "content", None)
        if not content or not content.strip():
            # An empty string would render as an answer with no content and no
            # indication that anything went wrong.
            raise LLMUnavailable("the model returned an empty message")
        return content
