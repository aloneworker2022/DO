"""NAS Shorts: a TikTok-style vertical swipe viewer for videos on a NAS.

Only uses the Python standard library. Configure with environment variables:
  VIDEO_DIR      root folder; the settings page can pick folders under it (default /videos)
  PORT           listen port (default 8080)
  SETTINGS_FILE  where the chosen folders are saved (default /config/settings.json)
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
SETTINGS_FILE = os.environ.get("SETTINGS_FILE", "/config/settings.json")
AUTH_USER = os.environ.get("AUTH_USER", "")
AUTH_PASS = os.environ.get("AUTH_PASS", "")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

VIDEO_EXTS = {".mp4", ".m4v", ".webm", ".mov"}
# Synology keeps thumbnails in @eaDir and deleted files in #recycle.
SKIP_DIRS = {"@eaDir", "#recycle", "#snapshot", "@tmp"}
SCAN_TTL = 60
CHUNK = 256 * 1024
MAX_BODY = 64 * 1024

mimetypes.add_type("video/mp4", ".m4v")
mimetypes.add_type("video/quicktime", ".mov")
mimetypes.add_type("video/webm", ".webm")

_cache = {"time": 0.0, "videos": []}
_cache_lock = threading.Lock()


def skip_dir(name):
    return name in SKIP_DIRS or name.startswith(".")


def resolve(rel):
    """Map a relative path to a real path inside VIDEO_DIR, or None on traversal."""
    full = os.path.realpath(os.path.join(VIDEO_DIR, rel.strip("/")))
    if os.path.commonpath([full, VIDEO_DIR]) != VIDEO_DIR:
        return None
    return full


def clean_folders(folders):
    """Keep only existing folders inside VIDEO_DIR, as normalized relative paths."""
    result = []
    for f in folders if isinstance(folders, list) else []:
        full = resolve(f) if isinstance(f, str) else None
        if full and os.path.isdir(full):
            rel = os.path.relpath(full, VIDEO_DIR).replace(os.sep, "/")
            rel = "" if rel == "." else rel
            if rel not in result:
                result.append(rel)
    return result


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    return {"folders": clean_folders(data.get("folders"))}


def save_settings(settings):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SETTINGS_FILE)
    with _cache_lock:
        _cache["time"] = 0.0


def in_folders(rel, folders):
    """True if rel lies in one of the chosen folders (no folders means everything)."""
    return not folders or any(f == "" or rel == f or rel.startswith(f + "/") for f in folders)


def scan_videos():
    with _cache_lock:
        if time.time() - _cache["time"] < SCAN_TTL:
            return _cache["videos"]
        folders = load_settings()["folders"]
        videos = {}
        for top in folders or [""]:
            for root, dirs, files in os.walk(os.path.join(VIDEO_DIR, top)):
                dirs[:] = [d for d in dirs if not skip_dir(d)]
                for name in files:
                    if name.startswith(".") or os.path.splitext(name)[1].lower() not in VIDEO_EXTS:
                        continue
                    full = os.path.join(root, name)
                    rel = os.path.relpath(full, VIDEO_DIR).replace(os.sep, "/")
                    if rel in videos:
                        continue
                    try:
                        st = os.stat(full)
                    except OSError:
                        continue
                    videos[rel] = {
                        "path": rel,
                        "name": os.path.splitext(name)[0],
                        "folder": os.path.dirname(rel),
                        "size": st.st_size,
                        "mtime": int(st.st_mtime),
                    }
        result = sorted(videos.values(), key=lambda v: v["mtime"], reverse=True)
        _cache.update(time=time.time(), videos=result)
        return result


def resolve_video(rel):
    """Map a request path to a video file in the chosen folders, refusing traversal."""
    full = resolve(rel)
    if not full or not os.path.isfile(full):
        return None
    rel = os.path.relpath(full, VIDEO_DIR).replace(os.sep, "/")
    return full if in_folders(rel, load_settings()["folders"]) else None


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
            if hmac.compare_digest(user, AUTH_USER) and hmac.compare_digest(pw, AUTH_PASS):
                return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="NAS Shorts"')
        self.end_headers()
        return False

    def do_GET(self):
        if not self.authorized():
            return
        url = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(url.query)
        if url.path == "/api/videos":
            self.send_video_list(query)
        elif url.path == "/api/settings":
            self.send_json(load_settings())
        elif url.path == "/api/dirs":
            self.send_dirs(query.get("path", [""])[0])
        elif url.path.startswith("/video/"):
            self.send_video(urllib.parse.unquote(url.path[len("/video/"):]))
        else:
            super().do_GET()

    def do_POST(self):
        if not self.authorized():
            return
        if urllib.parse.urlsplit(self.path).path != "/api/settings":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self.send_error(413)
            return
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            data = None
        if not isinstance(data, dict):
            self.send_error(400)
            return
        settings = {"folders": clean_folders(data.get("folders"))}
        try:
            save_settings(settings)
        except OSError as e:
            self.send_error(500, f"Cannot save settings: {e}")
            return
        self.send_json(settings)

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
        order = query.get("order", ["shuffle"])[0]
        if order == "shuffle":
            videos = random.sample(videos, len(videos))
        elif order == "oldest":
            videos = videos[::-1]
        self.send_json({"videos": videos})

    def send_dirs(self, rel):
        full = resolve(rel)
        if not full or not os.path.isdir(full):
            self.send_error(404)
            return
        try:
            dirs = sorted(e.name for e in os.scandir(full) if e.is_dir() and not skip_dir(e.name))
        except OSError:
            dirs = []
        rel = os.path.relpath(full, VIDEO_DIR).replace(os.sep, "/")
        self.send_json({"path": "" if rel == "." else rel, "dirs": dirs})

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
