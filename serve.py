#!/usr/bin/env python3
"""Run Supernotebook on your computer.

Serves this folder at http://127.0.0.1:1455/ and relays the two OpenAI API calls that
"Sign in with ChatGPT" needs (GET /v1/models and POST /v1/responses). OpenAI's API does not
send CORS headers for ChatGPT-plan tokens, so the page can't call it directly from the browser.

    python3 serve.py          # http://127.0.0.1:1455/
    python3 serve.py 8080     # another port (ChatGPT sign-in works on any port)

Only the Python standard library is used.
"""
import http.server
import os
import sys
import urllib.error
import urllib.request

UPSTREAM = 'https://api.openai.com/v1/'
PROXY_PREFIX = '/api/openai/v1/'
ALLOWED = {('GET', 'models'), ('POST', 'responses')}
REQUEST_HEADERS = ('Authorization', 'Content-Type', 'Accept')
RESPONSE_HEADERS = ('Content-Type', 'X-Request-ID', 'Retry-After')
MAX_BODY = 32 * 1024 * 1024
ROOT = os.path.dirname(os.path.abspath(__file__))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self):
        if self.path.startswith(PROXY_PREFIX):
            return self._proxy('GET')
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith(PROXY_PREFIX):
            return self._proxy('POST')
        self.send_error(405)

    def log_message(self, fmt, *args):
        # Keep OAuth query strings (code, state) out of the terminal.
        sys.stderr.write('%s %s\n' % (self.log_date_time_string(), (fmt % args).split('?', 1)[0]))

    def _same_origin(self):
        # Reject other sites and DNS-rebinding: only this server's own pages may use the relay.
        port = self.server.server_address[1]
        hosts = ('127.0.0.1:%d' % port, 'localhost:%d' % port)
        origin = self.headers.get('Origin')
        return self.headers.get('Host') in hosts and (origin is None or origin in ['http://' + h for h in hosts])

    def _proxy(self, method):
        name = self.path[len(PROXY_PREFIX):].split('?', 1)[0]
        if (method, name) not in ALLOWED:
            return self.send_error(404)
        if not self._same_origin():
            return self.send_error(403)
        body = None
        if method == 'POST':
            length = int(self.headers.get('Content-Length') or 0)
            if not 0 < length <= MAX_BODY:
                return self.send_error(413)
            body = self.rfile.read(length)

        request = urllib.request.Request(UPSTREAM + name, data=body, method=method)
        for header in REQUEST_HEADERS:
            if self.headers.get(header):
                request.add_header(header, self.headers[header])
        request.add_header('User-Agent', 'Supernotebook-local')
        try:
            upstream = urllib.request.urlopen(request, timeout=300)
        except urllib.error.HTTPError as error:
            upstream = error
        except OSError:
            return self.send_error(502, 'Could not reach api.openai.com')

        with upstream:
            self.send_response(upstream.status)
            for header in RESPONSE_HEADERS:
                if upstream.headers.get(header):
                    self.send_header(header, upstream.headers[header])
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Supernotebook-Proxy', '1')
            self.end_headers()
            # Pass the event stream through as it arrives instead of buffering the whole answer.
            read = getattr(upstream, 'read1', upstream.read)
            try:
                while True:
                    chunk = read(16384)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
        self.close_connection = True


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 1455
    server = http.server.ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print('Supernotebook: http://127.0.0.1:%d/  (Ctrl+C to stop)' % port, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
