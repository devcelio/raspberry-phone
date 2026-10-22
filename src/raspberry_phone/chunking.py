from __future__ import annotations

import re


_BOUNDARY = re.compile(r"[!?\n]|(?<!\d)\.|\.(?!\d|$)")


class SentenceChunker:
    """Turn streamed text deltas into speakable, ordered phrases."""

    def __init__(self, max_chars: int = 180) -> None:
        if max_chars < 8:
            raise ValueError("max_chars must be at least 8")
        self.max_chars = max_chars
        self._buffer = ""
        self._first = True

    def feed(self, delta: str) -> list[str]:
        self._buffer += delta
        emitted: list[str] = []

        if self._first:
            comma = self._buffer.find(",", 25)
            if comma >= 0:
                emitted.append(self._buffer[:comma + 1].strip())
                self._buffer = self._buffer[comma + 1:].lstrip()
                self._first = False

        while match := _BOUNDARY.search(self._buffer):
            end = match.end()
            phrase = self._buffer[:end].strip()
            self._buffer = self._buffer[end:].lstrip()
            if phrase:
                emitted.append(phrase)
                self._first = False

        while len(self._buffer) > self.max_chars:
            split_at = self._buffer.rfind(" ", 0, self.max_chars + 1)
            if split_at <= 0:
                split_at = self.max_chars
            phrase = self._buffer[:split_at].strip()
            self._buffer = self._buffer[split_at:].lstrip()
            if phrase:
                emitted.append(phrase)
                self._first = False

        return emitted

    def flush(self) -> list[str]:
        phrase = self._buffer.strip()
        self._buffer = ""
        return [phrase] if phrase else []
