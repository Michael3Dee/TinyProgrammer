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
_CACHE_SECONDS = 0.02             # at most ~50 reads per second
_REOPEN_SECONDS = 0.5             # retry opening the file at most this often


class _Audio:
    """Reads via a persistent file handle: re-opening the file for every
    read would trigger the virus scanner on the freshly written file
    (~15 ms per open on Windows) and stall the calling program. A single
    seek+read on an open handle costs microseconds instead."""

    def __init__(self):
        self._path = os.environ.get("TINY_AUDIO_SHM") or os.path.join(
            tempfile.gettempdir(), "tiny_audio.shm")
        self._fh = None
        self._vals = (1.0, 1.0, 1.0, 1.0, 1.0)
        self._read_at = 0.0
        self._reopen_at = -_REOPEN_SECONDS

    def _close(self):
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None

    def _read_record(self):
        if self._fh is None:
            return None
        try:
            self._fh.seek(0)
            data = self._fh.read(_SIZE)
        except (OSError, ValueError):
            self._close()
            return None
        if len(data) != _SIZE:
            return None
        try:
            return struct.unpack(_FMT, data)
        except struct.error:
            return None

    @staticmethod
    def _is_fresh(rec):
        return rec is not None and abs(time.time() - rec[0]) < _STALE_SECONDS

    def _refresh(self):
        now = time.monotonic()
        if now - self._read_at < _CACHE_SECONDS:
            return
        self._read_at = now
        rec = self._read_record()
        if not self._is_fresh(rec) and now - self._reopen_at >= _REOPEN_SECONDS:
            # Analyzer (neu) gestartet oder Datei ersetzt -> neu oeffnen,
            # aber hoechstens alle _REOPEN_SECONDS (open ist teuer)
            self._reopen_at = now
            self._close()
            try:
                self._fh = open(self._path, "rb")
            except OSError:
                self._fh = None
            rec = self._read_record()
        if self._is_fresh(rec):
            self._vals = tuple(
                0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
                for v in rec[1:6])
        else:
            self._vals = (1.0, 1.0, 1.0, 1.0, 1.0)

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
