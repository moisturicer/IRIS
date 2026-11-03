"""Read nginx locations for configuration contract tests, including quoted regexes."""

import re


def location_blocks(conf):
    """Return (header, body) pairs without treating quoted braces as block syntax."""
    blocks = []
    header = re.compile(r"^\s*location\b(?:[^\{\"']|\"[^\"]*\"|'[^']*')*\{", re.MULTILINE)
    for match in header.finditer(conf):
        depth, i, quote, escaped = 1, match.end(), None, False
        while depth and i < len(conf):
            char = conf[i]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif quote:
                if char == quote:
                    quote = None
            elif char in ("'", '\"'):
                quote = char
            else:
                depth += {"{": 1, "}": -1}.get(char, 0)
            i += 1
        if depth:
            raise ValueError("unclosed nginx location")
        blocks.append((match.group(0).strip(), conf[match.end():i - 1]))
    return blocks
