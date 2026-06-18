import atexit
import math
import os
import json
import sys
import time


DEFAULT_BATCH_MAX = 512


def _read_batch_max() -> int:
    try:
        value = int(os.environ.get("TINY_CANVAS_BATCH_MAX", DEFAULT_BATCH_MAX))
    except (TypeError, ValueError):
        return DEFAULT_BATCH_MAX
    return value if value > 0 else DEFAULT_BATCH_MAX

class Canvas:
    """
    A simple interface for drawing on the Tiny Programmer canvas.
    Outputs commands to stdout that the main process interprets.
    Canvas dimensions come from TINY_CANVAS_W/H env vars set by the
    runtime, falling back to the 480x320 reference size.
    """

    def __init__(self, w=None, h=None):
        self.width = w if w is not None else int(os.environ.get("TINY_CANVAS_W", 416))
        self.height = h if h is not None else int(os.environ.get("TINY_CANVAS_H", 218))
        self._batch_enabled = os.environ.get("TINY_CANVAS_BATCH", "1").lower() not in ("0", "false", "no")
        self._batch_max = _read_batch_max()
        self._commands = []
        self._frame_dirty = False
        # Affine transform [a, b, c, d, e, f] mapping local -> world:
        #   world_x = a*x + c*y + e ; world_y = b*x + d*y + f
        # Identity by default; translate/rotate/push/pop mutate it.
        self._m = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
        self._stack = []
        # Flush immediately so animation is smooth
        sys.stdout.reconfigure(line_buffering=True)
        atexit.register(self._flush_at_exit)

    def update(self):
        """Flush and render the current frame."""
        self.show()

    def move(self, *args):
        """Dummy method for compatibility."""
        pass

    # -- Transform stack (Processing/p5-style) -------------------------------

    def translate(self, dx, dy):
        """Shift the origin by (dx, dy). Affects all subsequent draws."""
        a, b, c, d, e, f = self._m
        self._m[4] = e + a * dx + c * dy
        self._m[5] = f + b * dx + d * dy

    def rotate(self, theta):
        """Rotate subsequent draws by theta radians around the current origin."""
        a, b, c, d, e, f = self._m
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)
        self._m[0] = a * cos_t + c * sin_t
        self._m[1] = b * cos_t + d * sin_t
        self._m[2] = -a * sin_t + c * cos_t
        self._m[3] = -b * sin_t + d * cos_t

    def push(self):
        """Save the current transform onto the stack."""
        self._stack.append(list(self._m))

    def pop(self):
        """Restore the most recently pushed transform."""
        if self._stack:
            self._m = self._stack.pop()

    def _apply(self, x, y):
        """Map a local point through the current transform to world coords."""
        a, b, c, d, e, f = self._m
        return (int(a * x + c * y + e), int(b * x + d * y + f))

    def _axis_aligned(self):
        """True when the linear part is identity (translate-only)."""
        m = self._m
        return m[0] == 1.0 and m[1] == 0.0 and m[2] == 0.0 and m[3] == 1.0

    def _emit(self, command, *args):
        if self._batch_enabled:
            self._commands.append([command, *args])
            if len(self._commands) >= self._batch_max:
                self._flush()
            return
        print("CMD:" + ",".join(str(part) for part in (command, *args)))

    def _flush(self):
        if not self._commands:
            return
        print("CMDS:" + json.dumps(self._commands, separators=(",", ":")))
        self._commands = []
        self._frame_dirty = True

    def _flush_at_exit(self):
        if not self._batch_enabled:
            return
        self._flush()
        if self._frame_dirty:
            print("CMD:FLIP")
            self._frame_dirty = False

    def clear(self, r=0, g=0, b=0):
        """Clear screen with color."""
        self._emit("CLEAR", r, g, b)

    def pixel(self, x, y, r=255, g=255, b=255):
        """Draw a single pixel."""
        px, py = self._apply(x, y)
        self._emit("PIXEL", px, py, r, g, b)

    def line(self, x1, y1, x2, y2, r=255, g=255, b=255):
        """Draw a line."""
        ax, ay = self._apply(x1, y1)
        bx, by = self._apply(x2, y2)
        self._emit("LINE", ax, ay, bx, by, r, g, b)

    def rect(self, x, y, w, h, r=255, g=255, b=255):
        """Draw a rectangle outline.

        Axis-aligned (translate-only) draws a fast RECT; under rotation the
        four corners are transformed and emitted as a quad instead.
        """
        if self._axis_aligned():
            px, py = self._apply(x, y)
            self._emit("RECT", px, py, int(w), int(h), r, g, b)
        else:
            self.quad(x, y, x + w, y, x + w, y + h, x, y + h, r, g, b)

    def fill_rect(self, x, y, w, h, r=255, g=255, b=255):
        """Draw a filled rectangle (see rect for rotation behavior)."""
        if self._axis_aligned():
            px, py = self._apply(x, y)
            self._emit("FILLRECT", px, py, int(w), int(h), r, g, b)
        else:
            self.fill_quad(x, y, x + w, y, x + w, y + h, x, y + h, r, g, b)

    def circle(self, x, y, radius, r=255, g=255, b=255):
        """Draw a circle outline (center transformed; radius unchanged)."""
        px, py = self._apply(x, y)
        self._emit("CIRCLE", px, py, int(radius), r, g, b)

    def fill_circle(self, x, y, radius, r=255, g=255, b=255):
        """Draw a filled circle (center transformed; radius unchanged)."""
        px, py = self._apply(x, y)
        self._emit("FILLCIRCLE", px, py, int(radius), r, g, b)

    def triangle(self, x1, y1, x2, y2, x3, y3, r=255, g=255, b=255):
        """Draw a triangle outline from three points."""
        ax, ay = self._apply(x1, y1)
        bx, by = self._apply(x2, y2)
        cx, cy = self._apply(x3, y3)
        self._emit("TRIANGLE", ax, ay, bx, by, cx, cy, r, g, b)

    def fill_triangle(self, x1, y1, x2, y2, x3, y3, r=255, g=255, b=255):
        """Draw a filled triangle from three points."""
        ax, ay = self._apply(x1, y1)
        bx, by = self._apply(x2, y2)
        cx, cy = self._apply(x3, y3)
        self._emit("FILLTRIANGLE", ax, ay, bx, by, cx, cy, r, g, b)

    def quad(self, x1, y1, x2, y2, x3, y3, x4, y4, r=255, g=255, b=255):
        """Draw a quadrilateral outline from four points (in order)."""
        ax, ay = self._apply(x1, y1)
        bx, by = self._apply(x2, y2)
        cx, cy = self._apply(x3, y3)
        dx, dy = self._apply(x4, y4)
        self._emit("QUAD", ax, ay, bx, by, cx, cy, dx, dy, r, g, b)

    def fill_quad(self, x1, y1, x2, y2, x3, y3, x4, y4, r=255, g=255, b=255):
        """Draw a filled quadrilateral from four points (in order)."""
        ax, ay = self._apply(x1, y1)
        bx, by = self._apply(x2, y2)
        cx, cy = self._apply(x3, y3)
        dx, dy = self._apply(x4, y4)
        self._emit("FILLQUAD", ax, ay, bx, by, cx, cy, dx, dy, r, g, b)

    def show(self):
        """Mark the end of a frame so the host can render it cleanly."""
        self._flush()
        print("CMD:FLIP")
        self._frame_dirty = False

    def sleep(self, seconds):
        """Sleep for seconds."""
        self._flush()
        time.sleep(seconds)
