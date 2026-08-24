"""
Tiny Audio - audio-reactive values for tiny canvas programs.

Reads analysis values (written by an external analyzer, e.g. the archive
browser's loopback capture) from a small shared file. When no analyzer is
running - such as on the TinyProgrammer Pi - every value is exactly 1.0,
so programs using these values look identical to their original form.

All values are in 0..1:

    from tiny_audio import audio

    audio.level   overall dynamics (loudness)
    audio.low     bass band energy
    audio.mid     mid band energy
    audio.high    treble band energy
    audio.beat    jumps to 1.0 on a detected beat, then decays to 0

Example:
    c.fill_circle(x, y, r, int(255 * audio.low), 0, int(255 * audio.high))

The shared file location can be overridden with the TINY_AUDIO_SHM
environment variable; values older than half a second count as stale and
fall back to 1.0.
"""

import os
import struct
import tempfile
import time

_FMT = "<d5f"                     # timestamp, level, low, mid, high, beat
_SIZE = struct.calcsize(_FMT)
_STALE_SECONDS = 0.5
_CACHE_SECONDS = 0.02             # at most ~50 file reads per second


class _Audio:

    def __init__(self):
        self._path = os.environ.get("TINY_AUDIO_SHM") or os.path.join(
            tempfile.gettempdir(), "tiny_audio.shm")
        self._vals = (1.0, 1.0, 1.0, 1.0, 1.0)
        self._read_at = 0.0

    def _refresh(self):
        now = time.monotonic()
        if now - self._read_at < _CACHE_SECONDS:
            return
        self._read_at = now
        vals = (1.0, 1.0, 1.0, 1.0, 1.0)
        try:
            with open(self._path, "rb") as fh:
                data = fh.read(_SIZE)
            if len(data) == _SIZE:
                ts, level, low, mid, high, beat = struct.unpack(_FMT, data)
                if abs(time.time() - ts) < _STALE_SECONDS:
                    vals = tuple(
                        0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
                        for v in (level, low, mid, high, beat))
        except (OSError, ValueError, struct.error):
            pass
        self._vals = vals

    @property
    def level(self):
        self._refresh()
        return self._vals[0]

    @property
    def low(self):
        self._refresh()
        return self._vals[1]

    @property
    def mid(self):
        self._refresh()
        return self._vals[2]

    @property
    def high(self):
        self._refresh()
        return self._vals[3]

    @property
    def beat(self):
        self._refresh()
        return self._vals[4]


audio = _Audio()
