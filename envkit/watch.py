"""Watching a run: a tap that films the screen with a panel beside it (the step, the return so far, the last event
and the agent's reason for its move), written as an animated GIF when the run stops. A tap never reaches a world,
so filming can't change what the agent does.

    python3 -m envkit.run mario --film run.gif [--film-every 2]

`Live` shows the same picture as it happens: a page on http://127.0.0.1:8765/ (an MJPEG stream any browser plays,
and which OBS can capture as a browser source to stream). Use it with the realtime scheduler:

    python3 -m envkit.run mario --realtime --live 8765
"""
from __future__ import annotations

import numpy as np

from envkit.core import Module, Port

PANEL = 200


def _font(size=11):
    from PIL import ImageFont
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "DejaVuSansMono.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _wrap(text, width=28):
    out, line = [], ""
    for word in str(text).split():
        if len(line) + len(word) + 1 > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return out + [line] if line else out


class Film(Module):
    kind = "tap"

    def __init__(self, name, path: str, every: int = 2, scale: int = 2, fps: float = 15.0, grid: bool = False):
        self.inputs = {"screen": Port("rgb"), "reward": Port("scalar", keep="all"), "event": Port("event", keep="all"),
                       "why": Port("text"), "tick": Port("event"), "things": Port("json"), "camera": Port("json")}
        super().__init__(name)
        self.path, self.every, self.scale, self.fps, self.grid = path, int(every), int(scale), fps, grid
        self.frames, self.screen, self.why, self.total, self.events, self.n = [], None, "", 0.0, [], 0
        self.things, self.cam = [], None

    def on(self, port, msg):
        if port == "screen":
            self.screen = msg.data
        elif port == "reward":
            self.total += float(msg.data)
        elif port == "things":
            self.things = msg.data
        elif port == "camera":
            self.cam = msg.data
        elif port == "why":
            self.why = msg.data
        elif port == "event":
            e = msg.data
            if e.get("kind") != "start":
                self.events.append(f"t{msg.t} {e.get('kind')}" + (f" ({e['left']} left)" if "left" in e else ""))
        elif port == "tick" and self.screen is not None:
            if self.n % self.every == 0:
                self.frames.append(self._draw(msg.t))
            self.n += 1

    def _draw(self, t):
        from PIL import Image, ImageDraw
        img = np.asarray(self.screen)
        if img.ndim == 2:  # a grid of colour indices: a fixed palette, enlarged
            pal = np.array([[0, 0, 0], [0, 116, 217], [255, 65, 54], [46, 204, 64], [255, 220, 0], [170, 170, 170],
                            [240, 18, 190], [255, 133, 27], [127, 219, 255], [135, 12, 37], [255, 255, 255],
                            [60, 60, 60], [120, 60, 20], [0, 90, 50], [100, 0, 160], [200, 200, 120]], dtype=np.uint8)
            img = pal[np.clip(img, 0, 15)].repeat(4, 0).repeat(4, 1)
        pic = Image.fromarray(img.astype(np.uint8)).resize((img.shape[1] * self.scale, img.shape[0] * self.scale),
                                                           Image.NEAREST)
        if self.things and self.cam is not None:  # what the sight sees: a box per thing, its id; yellow if it moves
            dp, k, cx = ImageDraw.Draw(pic), self.scale, self.cam["x"]
            for th in self.things:
                x0, y0, x1, y1 = th["box"]
                col = (255, 230, 0) if th.get("moved") else (0, 220, 255)
                dp.rectangle([(x0 - cx) * k, y0 * k, (x1 - cx) * k - 1, y1 * k - 1], outline=col)
                dp.text(((x0 - cx) * k, y1 * k + 1), str(th["id"]), fill=col, font=_font(10))
        out = Image.new("RGB", (pic.width + PANEL, pic.height), (16, 16, 20))
        out.paste(pic, (0, 0))
        d, f = ImageDraw.Draw(out), _font()
        y = 8
        cam = [f"camera {self.cam['x']} area {self.cam['area']}"] if self.cam else []
        for line in [f"step {t}", f"return {self.total:.0f}"] + cam + [""] + ["why:"] + _wrap(self.why) + [""] + \
                ["events:"] + self.events[-6:]:
            d.text((pic.width + 8, y), line, fill=(220, 220, 220), font=f)
            y += 14
        return out

    def stop(self):
        if not self.frames:
            return
        self.frames[0].save(self.path, save_all=True, append_images=self.frames[1:], loop=0,
                            duration=int(1000 * self.every / self.fps), optimize=True)


class Live(Film):
    """The film's picture, served as it is drawn instead of saved. Only this machine can reach it (127.0.0.1)."""

    def __init__(self, name, port: int = 8765, every: int = 1, scale: int = 2):
        super().__init__(name, path="", every=every, scale=scale)
        self.port, self.jpeg, self.cv, self.server = int(port), None, None, None

    def start(self):
        import http.server
        import io
        import threading
        self.cv = threading.Condition()
        live = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path != "/stream":
                    body = (b"<html><body style='margin:0;background:#101014'>"
                            b"<img src='/stream' style='image-rendering:pixelated'></body></html>")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.end_headers()
                last = None
                try:
                    while live.server is not None:
                        with live.cv:
                            live.cv.wait_for(lambda: live.jpeg is not last or live.server is None, timeout=1)
                            last = live.jpeg
                        if last is None:
                            continue
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + last + b"\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self._io = io

    def on(self, port, msg):
        n = len(self.frames)
        super().on(port, msg)
        if len(self.frames) > n:
            buf = self._io.BytesIO()
            self.frames.pop().save(buf, "JPEG", quality=85)
            with self.cv:
                self.jpeg = buf.getvalue()
                self.cv.notify_all()

    def stop(self):
        if self.server is not None:
            s, self.server = self.server, None
            with self.cv:
                self.cv.notify_all()
            s.shutdown()
