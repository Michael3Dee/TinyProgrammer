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

Divided beats (the analyzer tracks the tempo, rejects off-beat onsets
and keeps a flywheel running, so these stay steady even when a beat is
buried in the mix):

    audio.beat05  every half beat (twice per beat)
    audio.beat2   every 2nd beat
    audio.beat4   every 4th beat
    audio.beat8   every 8th beat

Inverted counterparts (prefix i): audio.ilevel, ilow, imid, ihigh,
ibeat, ibeat05, ibeat2, ibeat4, ibeat8. With live audio they are
1 - value (ibeat: 0 on a beat, back to 1 as it decays) - but without
an analyzer AND during silence they are 1.0 just like the normal
values, so any mix of both keeps programs looking original when no
music plays. Never compute 1 - audio.low yourself: that would turn the
1.0 fallback into 0 and break programs on the Pi.

audio.ramp is the beat phase: 0.0 right after a beat, rising to 1.0
when the next one is due (audio.iramp runs the other way). Great for
rotations or sweeps locked to the tempo. Without a tempo lock, an
analyzer or during silence it is constant 1.0.

audio.flip alternates with the beat: +1 on even beats, -1 on odd beats
(audio.iflip is the opposite phase). Handy as a direction or mirror
factor, e.g. x = cx + int(dx * audio.flip). The divided variants
audio.flip05 / flip2 / flip4 / flip8 alternate on the corresponding
divided beats (flip8: side change every 8 beats), each with an
inverted i-counterpart. Without an analyzer and during silence all
flips are +1, so programs keep their original look.

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

# timestamp, active, level, low, mid, high, beat, beat05, beat2, beat4,
# beat8, ramp, flip, flip05, flip2, flip4, flip8 (Rohwerte)
_FMT = "<d16f"
_NVALS = 10       # level..beat8 plus ramp (alle 0..1)
_NFLIPS = 5       # flip, flip05, flip2, flip4, flip8 (alle -1..+1)
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
        self._vals = (1.0,) * _NVALS
        self._ivals = (1.0,) * _NVALS
        self._flips = (1.0,) * _NFLIPS
        self._iflips = (1.0,) * _NFLIPS
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
                        for v in rec[2:2 + _NVALS])
            flips = tuple(max(-1.0, min(1.0, v))
                          for v in rec[2 + _NVALS:2 + _NVALS + _NFLIPS])
            self._active = blend
            self._vals = tuple(v * blend + (1.0 - blend) for v in raw)
            self._ivals = tuple((1.0 - v) * blend + (1.0 - blend)
                                for v in raw)
            self._flips = tuple(f * blend + (1.0 - blend) for f in flips)
            self._iflips = tuple(-f * blend + (1.0 - blend) for f in flips)
        else:
            self._active = 0.0
            self._vals = (1.0,) * _NVALS
            self._ivals = (1.0,) * _NVALS
            self._flips = (1.0,) * _NFLIPS
            self._iflips = (1.0,) * _NFLIPS

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

    @property
    def beat05(self):
        self._refresh()
        return self._vals[5]

    @property
    def beat2(self):
        self._refresh()
        return self._vals[6]

    @property
    def beat4(self):
        self._refresh()
        return self._vals[7]

    @property
    def beat8(self):
        self._refresh()
        return self._vals[8]

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
    def ibeat05(self):
        self._refresh()
        return self._ivals[5]

    @property
    def ibeat2(self):
        self._refresh()
        return self._ivals[6]

    @property
    def ibeat4(self):
        self._refresh()
        return self._ivals[7]

    @property
    def ibeat8(self):
        self._refresh()
        return self._ivals[8]

    @property
    def ramp(self):
        self._refresh()
        return self._vals[9]

    @property
    def iramp(self):
        self._refresh()
        return self._ivals[9]

    # -- Paritaets-Flips (+1/-1 im Wechsel; 1.0 im Fallback) ----------------

    @property
    def flip(self):
        self._refresh()
        return self._flips[0]

    @property
    def flip05(self):
        self._refresh()
        return self._flips[1]

    @property
    def flip2(self):
        self._refresh()
        return self._flips[2]

    @property
    def flip4(self):
        self._refresh()
        return self._flips[3]

    @property
    def flip8(self):
        self._refresh()
        return self._flips[4]

    @property
    def iflip(self):
        self._refresh()
        return self._iflips[0]

    @property
    def iflip05(self):
        self._refresh()
        return self._iflips[1]

    @property
    def iflip2(self):
        self._refresh()
        return self._iflips[2]

    @property
    def iflip4(self):
        self._refresh()
        return self._iflips[3]

    @property
    def iflip8(self):
        self._refresh()
        return self._iflips[4]

    @property
    def active(self):
        self._refresh()
        return self._active


audio = _Audio()
