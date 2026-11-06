"""Auditable routing hints, never authorization to execute a tool."""
import re


def tool_intent(prompt, names):
    """Conservative syntactic hints; not a general natural-language interpreter.

    Inspect the full original request, not the classifier's truncated excerpt.
    Discussion/quoted examples alone do not constitute an execution request.
    Explicit prohibitions win over positive hints and classifier predictions.
    """
    prohibited = bool(re.search(
        r"\b(?:no tools?|without (?:using )?(?:any )?tools?|"
        r"(?:do not|don't|never)\s+(?:use|call|run|invoke|execute)\s+(?:any\s+)?tools?)\b",
        prompt, re.I))
    requested = []
    for name in sorted(names):
        tool = r"`?" + re.escape(name) + r"`?\b"
        if re.search(r"\b(?:do not|don't|never)\s+(?:use|call|run|invoke|execute)\s+" + tool, prompt, re.I):
            prohibited = True
        # Anchor direct imperatives to clause starts; avoid matching 'explain
        # how to use', 'what happens if I run', and quoted code examples.
        if re.search(r"(?:^|[.!?;\n])\s*(?:please\s+)?(?:use|call|run|invoke|execute)\s+" + tool, prompt, re.I):
            requested.append(name)
    return prohibited, requested
