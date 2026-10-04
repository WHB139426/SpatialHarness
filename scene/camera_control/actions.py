"""Parse camera key sequences with optional per-key distances and angles."""

import re


MAGNITUDE_KEYS = frozenset('wasdijkl')
SIMPLE_KEYS = frozenset('qe+-')
NUMBER = re.compile(r'(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)')


def parse_actions(command):
    """Return (key, magnitude, label) actions, preserving compact key sequences."""
    actions = []
    index = 0
    while index < len(command):
        if command[index].isspace():
            index += 1
            continue
        key = command[index].lower()
        if key not in MAGNITUDE_KEYS | SIMPLE_KEYS:
            raise ValueError(f'Unknown key at position {index + 1}: {command[index]!r}')
        index += 1
        magnitude = None
        label = key
        if key in MAGNITUDE_KEYS:
            while index < len(command) and command[index].isspace():
                index += 1
            match = NUMBER.match(command, index)
            if match:
                label += match.group()
                magnitude = float(match.group())
                index = match.end()
        actions.append((key, magnitude, label))
    return actions
