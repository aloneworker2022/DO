"""NAS Shorts: a TikTok-style vertical swipe viewer for videos on a NAS.

Only uses the Python standard library. Configure with environment variables:
  VIDEO_DIR   folder to scan for videos (default /videos)
  PORT        listen port (default 8080)
  AUTH_USER / AUTH_PASS   optional HTTP basic auth
"""
import base64
import hmac
import json
import mimetypes
import os
import random
import threading
import time
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

VIDEO_DIR = os.path.realpath(os.environ.get("VIDEO_DIR", "/videos"))
PORT = int(os.environ.get("PORT", "8080"))
AUTH_USER = os.environ.get("AUTH_USER", "")
AUTH_PASS = os.environ.get("AUTH_PASS", "")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

VIDEO_EXTS = {".mp4", ".m4v", ".webm", ".mov"}
# Synology keeps thumbnails in @eaDir and deleted files in #recycle.
SKIP_DIRS = {"@eaDir", "#recycle", "#snapshot", "@tmp"}
SCAN_TTL = 60
CHUNK = 256 * 1024

mimetypes.add_type("video/mp4", ".m4v")
mimetypes.add_type("video/quicktime", ".mov")
mimetypes.add_type("video/webm", ".webm")

_cache = {"time": 0.0, "videos": []}
_cache_lock = threading.Lock()


def scan_videos():
    with _cache_lock:
        if time.time() - _cache["time"] < SCAN_TTL:
            return _cache["videos"]
        videos = []
        for root, dirs, files in os.walk(VIDEO_DIR):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for name in files:
                if name.startswith(".") or os.path.splitext(name)[1].lower() not in VIDEO_EXTS:
                    continue
                full = os.path.join(root, name)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                rel = os.path.relpath(full, VIDEO_DIR).replace(os.sep, "/")
                videos.append({
                    "path": rel,
                    "name": os.path.splitext(name)[0],
                    "folder": os.path.dirname(rel),
                    "size": st.st_size,
                    "mtime": int(st.st_mtime),
                })
        videos.sort(key=lambda v: v["mtime"], reverse=True)
        _cache.update(time=time.time(), videos=videos)
        return videos


def resolve_video(rel):
    """Map a request path to a file inside VIDEO_DIR, refusing traversal."""
    full = os.path.realpath(os.path.join(VIDEO_DIR, rel))
    if os.path.commonpath([full, VIDEO_DIR]) != VIDEO_DIR or not os.path.isfile(full):
        return None
    return full


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def log_message(self, fmt, *args):
        pass

    def authorized(self):
        if not AUTH_USER:
            return True
        header = self.headers.get("Authorization", "")
        if header.startswith("Basic "):
            try:
                user, _, pw = base64.b64decode(header[6:]).decode().partition(":")
            except ValueError:
                return False
            return hmac.compare_digest(user, AUTH_USER) and hmac.compare_digest(pw, AUTH_PASS)
        return False

    def do_GET(self):
        if not self.authorized():
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="NAS Shorts"')
            self.end_headers()
            return
        url = urllib.parse.urlsplit(self.path)
        if url.path == "/api/videos":
            self.send_video_list(urllib.parse.parse_qs(url.query))
        elif url.path.startswith("/video/"):
            self.send_video(urllib.parse.unquote(url.path[len("/video/"):]))
        else:
            super().do_GET()

    def send_json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_video_list(self, query):
        videos = scan_videos()
        folder = query.get("folder", [""])[0].strip("/")
        if folder:
            videos = [v for v in videos if v["folder"] == folder or v["folder"].startswith(folder + "/")]
        folders = sorted({v["folder"] for v in scan_videos() if v["folder"]})
        order = query.get("order", ["shuffle"])[0]
        if order == "shuffle":
            videos = random.sample(videos, len(videos))
        elif order == "oldest":
            videos = videos[::-1]
        self.send_json({"videos": videos, "folders": folders})

    def send_video(self, rel):
        full = resolve_video(rel)
        if not full:
            self.send_error(404)
            return
        size = os.path.getsize(full)
        start, end = 0, size - 1
        status = 200
        rng = self.headers.get("Range", "")
        if rng.startswith("bytes="):
            first, _, last = rng[6:].split(",")[0].strip().partition("-")
            try:
                if first:
                    start = int(first)
                    end = min(int(last), size - 1) if last else size - 1
                else:
                    start = max(size - int(last), 0)
            except ValueError:
                start, end = 0, size - 1
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", mimetypes.guess_type(full)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        try:
            with open(full, "rb") as f:
                f.seek(start)
                while length > 0:
                    data = f.read(min(CHUNK, length))
                    if not data:
                        break
                    self.wfile.write(data)
                    length -= len(data)
        except (BrokenPipeError, ConnectionResetError):
            # Browsers drop connections constantly while swiping; that's fine.
            pass


if __name__ == "__main__":
    print(f"NAS Shorts serving {VIDEO_DIR} on http://0.0.0.0:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
