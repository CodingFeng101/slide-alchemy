"""Serve bounded font matching requests behind Nginx on a loopback port."""
import argparse
import base64
import io
import json
import threading
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
from PIL import Image

import match_fonts


def handler(matcher):
    busy = threading.Lock()
    assets = {(font["path"], font["index"]): font["asset_id"] for font in matcher.fonts}

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def respond(self, status, payload):
            body = json.dumps(payload, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self.respond(200, {"status": "ok", "font_faces": len(matcher.fonts)})
            else:
                self.respond(404, {"error": "not_found"})

        def do_POST(self):
            if self.path != "/match":
                self.respond(404, {"error": "not_found"})
                return
            if not busy.acquire(blocking=False):
                self.respond(503, {"error": "matcher_busy"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024 * 1024:
                    raise ValueError("request must be at most 1 MiB")
                request = json.loads(self.rfile.read(length))
                text, top_k = request["text"], request.get("top_k", 10)
                if not isinstance(text, str) or not text.strip() or len(text) > 64 or any(c in text for c in "\r\n"):
                    raise ValueError("text must be a single line of 1 to 64 characters")
                if type(top_k) is not int or not 1 <= top_k <= 10:
                    raise ValueError("top_k must be between 1 and 10")
                data = base64.b64decode(request["mask_png"], validate=True)
                with Image.open(io.BytesIO(data)) as image:
                    width, height = image.size
                    if image.format != "PNG" or width > 2048 or height > 512 or width * height > 1024 * 1024:
                        raise ValueError("mask must be a PNG up to 2048 by 512 pixels")
                    mask = np.array(image.convert("L"))
                result = matcher.match(mask, text, top_k)
                for candidate in result["candidates"]:
                    candidate["asset_id"] = assets[(candidate.pop("path"), candidate["index"])]
                self.respond(200, result)
            except (ValueError, KeyError, TypeError, OSError) as error:
                self.respond(400, {"error": str(error)})
            finally:
                match_fonts.load_face.cache_clear()
                busy.release()

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    # Keep a bounded FreeType cache on the small shared server.
    match_fonts.load_face = lru_cache(maxsize=8)(match_fonts.load_face.__wrapped__)
    matcher = match_fonts.FontMatcher(args.root / "server-index.json", args.root / "font_encoder.onnx")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(matcher))
    print(f"Font matcher ready with {len(matcher.fonts)} faces", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
