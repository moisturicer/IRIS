"""The switches a run can move, and what it records about them (IR-394).

ADR-033 §5 puts six techniques behind six settings, each defaulting to today's
behaviour, and a default moves only on a run of this harness. That makes the
harness the gate on all six, so the configuration surface lives here rather
than accreting one flag per technique ticket.

Two properties carry the weight. Every run records all six at the values it
used, because a results file that omits a switch cannot be compared with a
later one that moved it. And a technique is "built" only when its setting is
really present in `django.conf.settings` -- never because this file names it --
so asking for one meanwhile is refused rather than recorded as measured.

The setting names are this file's guess until each ticket lands one; when a
ticket names its setting differently, one line here changes.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Optional

from django.conf import settings
from django.test import override_settings


class TechniqueError(Exception):
    """A run asked for a technique that is unknown, unbuilt, or misspelled."""


def _spell(value: Any) -> str:
    """One vocabulary for a switch, so the CLI and the results file agree."""
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value)


@dataclass(frozen=True)
class Technique:
    """One ADR-033 §5 switch: its name to an operator, its setting in code."""

    name: str
    setting: str
    kind: str
    adr: str
    ticket: str
    note: str = ""
    #: For `kind="choice"`, the only values accepted.
    choices: tuple[str, ...] = ()

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
        if self.kind == "choice":
            if text.lower() in self.choices:
                return text.lower()
            raise TechniqueError(
                f"{self.name} takes one of {', '.join(self.choices)}, not {raw!r}"
            )
        try:
            return int(text) if self.kind == "int" else float(text)
        except ValueError:
            raise TechniqueError(f"{self.name} takes a number, not {raw!r}")


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
    Technique(
        name="evidence_decision",
        setting="AI_EVIDENCE_DECISION",
        kind="choice",
        adr="ADR-035 §1",
        ticket="IR-466",
        note="record a shadow evidence decision per Turn; `on` is rejected, not unbuilt",
        choices=("off", "shadow"),
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

    An unbuilt technique is refused here rather than at apply time, so a run
    stops before spending a vendor credit on what would measure the baseline
    under another name.
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


@dataclass(frozen=True)
class ResolvedTechniques:
    """Every technique at the value one run used. Serializes as it records.

    A value rather than a bare mapping so the run, the report and the command
    all ask it the same questions instead of reaching into its keys.
    """

    states: tuple[tuple[str, dict[str, Any]], ...] = ()

    @property
    def moved(self) -> tuple[str, ...]:
        """The names this run changed from the deployment's own settings."""
        return tuple(name for name, state in self.states if state["overridden"])

    @property
    def changes(self) -> tuple[str, ...]:
        """What moved, spelled as the CLI spells it.

        ADR-023 §Amendment's "one change at a time" is reported rather than
        capped: it is a rule about runs, not one code can enforce, since
        fusion without keyword retrieval is one technique in two settings.
        See that ADR's IR-394 divergence note.
        """
        return tuple(
            f"{name}={_spell(state['value'])}"
            for name, state in self.states
            if state["overridden"]
        )

    @contextmanager
    def applied(self) -> Iterator[None]:
        """Run the block with the overridden settings in place, then restore.

        `override_settings` rather than writing to the settings object: it
        restores on the way out and emits `setting_changed`, so anything
        caching a value off a setting is invalidated the way it is in tests.
        """
        changed = {
            state["setting"]: state["value"]
            for _, state in self.states
            if state["overridden"]
        }
        if not changed:
            yield
            return
        with override_settings(**changed):
            yield

    def as_dict(self) -> dict[str, dict[str, Any]]:
        return dict(self.states)

    def __getitem__(self, name: str) -> dict[str, Any]:
        return self.as_dict()[name]

    def __iter__(self):
        return iter(name for name, _ in self.states)

    def __len__(self) -> int:
        return len(self.states)


def resolve(
    overrides: Optional[Iterable[tuple[str, Any]]] = None,
) -> ResolvedTechniques:
    """Every technique, at the value this run will use."""
    asked = dict(overrides or ())
    for name in asked:
        technique(name)

    return ResolvedTechniques(
        states=tuple(
            (
                item.name,
                {
                    "setting": item.setting,
                    "value": asked[item.name] if item.name in asked else item.value,
                    "implemented": item.implemented,
                    "overridden": item.name in asked,
                    "ticket": item.ticket,
                },
            )
            for item in TECHNIQUES
        )
    )


def render_registry() -> str:
    """The switches, for an operator deciding what to run."""
    lines = [
        f"{'technique':<19} {'setting':<32} {'state':<14} lands with",
        "-" * 80,
    ]
    for item in TECHNIQUES:
        state = _spell(item.value) if item.implemented else "not built yet"
        lines.append(
            f"{item.name:<19} {item.setting:<32} {state:<14} {item.ticket} ({item.adr})"
        )
        if item.note:
            lines.append(f"{'':<19} {item.note}")
    return "\n".join(lines)
