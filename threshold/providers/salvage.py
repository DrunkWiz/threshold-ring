"""Recovering a JSON object from a model that talked around it.

Models fenced in code blocks, prefaced with "Sure! Here's the JSON:", or
appended an explanation. All three still contain the object we asked for, and
throwing the whole turn away costs a retry for no reason.

Brace counting rather than a regex, because a regex cannot tell a closing
brace inside a string from the end of the object, and descriptions in our
schema routinely contain both braces and quotes.
"""

from __future__ import annotations

import json
from typing import Any


def salvage_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None

    # The easy case first.
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    # Strip a code fence if there is one, keeping the contents.
    if "```" in stripped:
        parts = stripped.split("```")
        for part in parts[1:]:
            body = part.split("\n", 1)[-1] if part[:20].lower().startswith(("json", "javascript")) else part
            found = _first_object(body)
            if found is not None:
                return found

    return _first_object(stripped)


def _first_object(text: str) -> dict[str, Any] | None:
    """The first balanced {...} in the text, ignoring braces inside strings."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        parsed = json.loads(candidate)
                    except json.JSONDecodeError:
                        break  # unbalanced or malformed; try the next {
                    if isinstance(parsed, dict):
                        return parsed
                    break
        start = text.find("{", start + 1)
    return None
