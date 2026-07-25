"""Preview the site locally with caching turned off.

    python3 serve.py [port]        # default 8131

`python -m http.server` sends Last-Modified but no Cache-Control, so a browser
is free to reuse a stale style.css after a rebuild. That failure is hard to
read: the page is correct, the CSS is correct, and what you see is the old
styling applied to the new markup.
"""

import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def log_message(self, fmt, *args):
        if not args or not str(args[0]).startswith(("GET /favicon", "GET /img")):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8131
    handler = partial(NoCacheHandler, directory=str(Path(__file__).parent))
    print(f"  http://localhost:{port}/   (no-store — Ctrl-C to stop)")
    try:
        ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
    except KeyboardInterrupt:
        pass
