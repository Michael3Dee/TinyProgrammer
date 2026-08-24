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

Inverted counterparts (prefix i): audio.ilevel, ilow, imid, ihigh,
ibeat. With live audio they are 1 - value (ibeat: 0 on a beat, back to
1 as it decays) - but without an analyzer AND during silence they are
1.0 just like the normal values, so any mix of both keeps programs
looking original when no music plays. Never compute 1 - audio.low
yourself: that would turn the 1.0 fallback into 0 and break programs
on the Pi.

audio.flip alternates with the beat: +1 on even beats, -1 on odd beats
(audio.iflip is the opposite phase). Handy as a direction or mirror
factor, e.g. x = cx + int(dx * audio.flip). Without an analyzer and
during silence both are +1, so programs keep their original look.

audio.active is the liveness factor itself (0 = no music/no analyzer,
1 = live audio) - useful for switching, but multiplying colors by it
will darken programs when no music plays, so prefer the values above.

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

_FMT = "<d7f"  # timestamp, active, level, low, mid, high, beat, flip (roh)
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
        self._ivals = (1.0, 1.0, 1.0, 1.0, 1.0)
        self._flip = 1.0
        self._iflip = 1.0
        self._active = 0.0
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
            # Der Analyzer liefert Rohwerte plus den Liveness-Faktor
            # (blend); normale und invertierte Werte blenden beide bei
            # Stille auf 1.0 - so bleibt jede Mischung im Original-Look.
            blend = max(0.0, min(1.0, rec[1]))
            raw = tuple(0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
                        for v in rec[2:7])
            flip = max(-1.0, min(1.0, rec[7]))
            self._active = blend
            self._vals = tuple(v * blend + (1.0 - blend) for v in raw)
            self._ivals = tuple((1.0 - v) * blend + (1.0 - blend)
                                for v in raw)
            self._flip = flip * blend + (1.0 - blend)
            self._iflip = -flip * blend + (1.0 - blend)
        else:
            self._active = 0.0
            self._vals = (1.0, 1.0, 1.0, 1.0, 1.0)
            self._ivals = (1.0, 1.0, 1.0, 1.0, 1.0)
            self._flip = 1.0
            self._iflip = 1.0

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

    # -- invertierte Werte (1 - x bei Live-Audio, 1.0 im Fallback) ----------

    @property
    def ilevel(self):
        self._refresh()
        return self._ivals[0]

    @property
    def ilow(self):
        self._refresh()
        return self._ivals[1]

    @property
    def imid(self):
        self._refresh()
        return self._ivals[2]

    @property
    def ihigh(self):
        self._refresh()
        return self._ivals[3]

    @property
    def ibeat(self):
        self._refresh()
        return self._ivals[4]

    @property
    def flip(self):
        self._refresh()
        return self._flip

    @property
    def iflip(self):
        self._refresh()
        return self._iflip

    @property
    def active(self):
        self._refresh()
        return self._active


audio = _Audio()
