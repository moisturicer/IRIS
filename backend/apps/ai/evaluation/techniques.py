"""The switches a run can move, and what it records about them (IR-394).

ADR-033 §5 puts six techniques behind six settings, each defaulting to today's
behaviour, and says a default moves only on a harness run. That makes the
harness the gate on all six, so the configuration surface belongs here rather
than accreting one flag per technique ticket.

Three rules hold this together:

- **Every technique is recorded on every run**, at the value the run actually
  used, including the ones whose setting does not exist yet. A results file
  that omits a switch cannot be compared against a later one.
- **A technique that is not implemented yet cannot be overridden.** Asking for
  fusion before fusion exists would produce a baseline number under a results
  file claiming to have measured fusion -- the one failure this registry is
  here to make impossible.
- **The setting names are the registry's guess until each ticket lands.** A
  name is resolved against `django.conf.settings` at run time, so a technique
  is "implemented" when its setting is really there, never because this file
  says so. When a ticket names its setting differently, one line changes here.

`applied()` uses `override_settings` rather than writing to the settings
object: it restores on the way out and emits `setting_changed`, so anything
caching a value off a setting is invalidated the way it is in tests.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from django.conf import settings
from django.test import override_settings


class TechniqueError(Exception):
    """A run asked for a technique that is unknown, unbuilt, or misspelled."""


@dataclass(frozen=True)
class Technique:
    """One ADR-033 §5 switch: its name to an operator, its setting in code."""

    name: str
    setting: str
    kind: str
    adr: str
    ticket: str
    note: str = ""

    @property
    def implemented(self) -> bool:
        return hasattr(settings, self.setting)

    @property
    def value(self) -> Any:
        return getattr(settings, self.setting, None)

    def parse(self, raw: str) -> Any:
        text = raw.strip()
        if self.kind == "bool":
            if text.lower() in {"on", "true", "yes", "1"}:
                return True
            if text.lower() in {"off", "false", "no", "0"}:
                return False
            raise TechniqueError(
                f"{self.name} is a switch: give it on or off, not {raw!r}"
            )
        try:
            return int(text) if self.kind == "int" else float(text)
        except ValueError:
            raise TechniqueError(
                f"{self.name} takes {'a whole number' if self.kind == 'int' else 'a number'}, not {raw!r}"
            )


TECHNIQUES: tuple[Technique, ...] = (
    Technique(
        name="fusion",
        setting="AI_RETRIEVAL_FUSION_ENABLED",
        kind="bool",
        adr="ADR-033 §1",
        ticket="IR-395",
        note="merge the keyword and vector result lists by rank before reranking",
    ),
    Technique(
        name="keyword_retrieval",
        setting="AI_KEYWORD_RETRIEVAL_ENABLED",
        kind="bool",
        adr="ADR-033 §1-2",
        ticket="IR-395",
        note="search the stored chunk keyword index on the healthy path, not only while the vendor is down",
    ),
    Technique(
        name="relevance_cut_off",
        setting="AI_RELEVANCE_MIN_SCORE",
        kind="float",
        adr="ADR-033 §3",
        ticket="IR-396",
        note="drop passages the reranker scored below this; 0 keeps every one",
    ),
    Technique(
        name="per_paper_cap",
        setting="AI_MAX_PASSAGES_PER_RECORD",
        kind="int",
        adr="ADR-033 §4",
        ticket="IR-397",
        note="how many passages one Record may contribute; 0 is uncapped",
    ),
    Technique(
        name="neighbour_joining",
        setting="AI_JOIN_ADJACENT_PASSAGES",
        kind="bool",
        adr="ADR-033 §4",
        ticket="IR-397",
        note="join adjacent surviving chunks of one document into one passage",
    ),
    Technique(
        name="token_budget",
        setting="AI_PASSAGE_TOKEN_BUDGET",
        kind="int",
        adr="ADR-033 §4",
        ticket="IR-397",
        note="token ceiling on the assembled passage set; 0 is unbudgeted",
    ),
)


def technique(name: str) -> Technique:
    for candidate in TECHNIQUES:
        if candidate.name == name:
            return candidate
    known = ", ".join(t.name for t in TECHNIQUES)
    raise TechniqueError(f"no technique named {name!r}. Known: {known}")


def parse_override(text: str) -> tuple[str, Any]:
    """``"fusion=on"`` to ``("fusion", True)``, refusing what cannot be run.

    An unbuilt technique is refused here rather than at apply time, so the
    command stops before it spends a vendor credit on a run that would have
    measured the baseline under another name.
    """
    name, _, raw = text.partition("=")
    name = name.strip()
    if not _:
        raise TechniqueError(
            f"say which value: --technique {name or 'NAME'}=on (or off, or a number)"
        )
    found = technique(name)
    if not found.implemented:
        raise TechniqueError(
            f"{found.name} is not built yet -- {found.setting} does not exist in "
            f"this deployment's settings. It lands with {found.ticket} "
            f"({found.adr}). A run cannot measure it meanwhile, and recording "
            f"it as measured would be a false result."
        )
    return found.name, found.parse(raw)


def resolve(
    overrides: Optional[Iterable[tuple[str, Any]]] = None,
) -> dict[str, dict[str, Any]]:
    """Every technique, at the value this run will use, ready to serialize."""
    asked = dict(overrides or ())
    unknown = set(asked) - {t.name for t in TECHNIQUES}
    if unknown:
        raise TechniqueError(f"no technique named {sorted(unknown)[0]!r}")

    resolved: dict[str, dict[str, Any]] = {}
    for item in TECHNIQUES:
        overridden = item.name in asked
        resolved[item.name] = {
            "setting": item.setting,
            "value": asked[item.name] if overridden else item.value,
            "implemented": item.implemented,
            "overridden": overridden,
            "ticket": item.ticket,
        }
    return resolved


def changes(resolved: dict[str, dict[str, Any]]) -> tuple[str, ...]:
    """What this run changed from the deployment's own configuration.

    ADR-023 §Amendment's "one change at a time" is a rule about runs, not a
    thing code can enforce -- fusion without keyword retrieval is one
    technique in two settings. So this reports the count rather than capping
    it, and the command says so out loud when more than one moved.
    """
    return tuple(
        f"{name}={state['value']}"
        for name, state in resolved.items()
        if state["overridden"]
    )


@contextmanager
def applied(resolved: dict[str, dict[str, Any]]):
    """Run the block with the overridden settings in place, then restore."""
    changed = {
        state["setting"]: state["value"]
        for state in resolved.values()
        if state["overridden"]
    }
    if not changed:
        yield
        return
    with override_settings(**changed):
        yield


def render_registry() -> str:
    """The switches, for an operator deciding what to run."""
    lines = [
        f"{'technique':<19} {'setting':<32} {'state':<14} lands with",
        "-" * 80,
    ]
    for item in TECHNIQUES:
        state = f"{item.value}" if item.implemented else "not built yet"
        lines.append(
            f"{item.name:<19} {item.setting:<32} {state:<14} {item.ticket} ({item.adr})"
        )
        if item.note:
            lines.append(f"{'':<19} {item.note}")
    return "\n".join(lines)
