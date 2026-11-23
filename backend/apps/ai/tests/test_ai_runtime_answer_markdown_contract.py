"""A delivered answer keeps the Markdown the model wrote (IR-1280).

An answer still failing its checks after every repair is delivered whole, with
unbindable citations removed and unsupported sentences marked (IR-995). That
used to rejoin its lines with single newlines and strip their indentation, so
paragraphs, sections and nested lists reached the reader as one block.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from ai.agent import assurance  # noqa: E402
from ai.agent.assurance import QUALIFIER  # noqa: E402
from ai.agent.tools import Investigation  # noqa: E402
from .test_ai_runtime_agent_loop_contract import ask, call, handle, recording, reply, tools  # noqa: E402


def test_an_answer_delivered_after_failed_repairs_keeps_its_paragraphs_lists_and_code():
    cite = f"[{handle('P', 1)}]"
    draft = (
        f"**Participants.** It predicted 87 floods {cite}.\n"
        "\n"
        "**Timing.** Some 40 more papers agree.\n"
        "\n"
        "- Gauges were read hourly.\n"
        "  - Some gauges failed.\n"
        "\n"
        "```\n"
        "rain  =  read(gauge)\n"
        "```\n"
        "\n"
        "| Gauge | Floods |\n"
        "|---|---|\n"
        "| A | 87 |"
    )
    provider = recording(tools(call("a", "search", query="flood")), reply(draft), reply(draft), reply(draft))
    result, _ = ask(provider)
    assert result.answer == (
        "**Participants.** It predicted 87 floods [1].\n"
        "\n"
        f"**Timing.** Some 40 more papers agree. {QUALIFIER}\n"
        "\n"
        "- Gauges were read hourly.\n"
        "  - Some gauges failed.\n"
        "\n"
        "```\n"
        "rain  =  read(gauge)\n"
        "```\n"
        "\n"
        "| Gauge | Floods |\n"
        "|---|---|\n"
        # A row cites nothing, so its figure is marked, inside the last cell where a table shows it.
        f"| A | 87 {QUALIFIER} |"
    )


def test_removing_a_citation_closes_its_gap_but_never_a_lines_indentation():
    found = Investigation(None)
    text = "- Gauges [P99].\n    - Read  hourly [9] .\n\n```\nx  =  1\n```"
    assert assurance.bindable(text, found) == "- Gauges.\n    - Read hourly.\n\n```\nx  =  1\n```"
