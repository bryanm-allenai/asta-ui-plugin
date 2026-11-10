"""Serve web/ over HTTP without auto-decompressing .gz databases (sql.js needs raw gzip bytes)."""
import http.server
import socketserver


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory='web', **kwargs)

    def guess_type(self, path):
        if str(path).endswith('.gz'):
            return 'application/octet-stream'
        return super().guess_type(path)


class Server(socketserver.TCPServer):
    allow_reuse_address = True


with Server(('127.0.0.1', 8000), Handler) as httpd:
    httpd.serve_forever()
