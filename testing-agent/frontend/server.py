import http.server
import socketserver
import urllib.request
import urllib.error
import json
import sys
import os

PORT = int(os.environ.get("PORT", 8002))
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8085")

class ProxyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence default request logging to keep console clean, or log custom
        sys.stdout.write("%s - - [%s] %s\n" %
                         (self.address_string(),
                          self.log_date_time_string(),
                          format%args))

    def do_POST(self):
        if self.path.startswith("/api/"):
            self.proxy_request("POST")
        else:
            super().do_POST()

    def do_GET(self):
        if self.path.startswith("/api/"):
            self.proxy_request("GET")
        else:
            super().do_GET()

    def proxy_request(self, method):
        # Calculate target URL (strip /api prefix to forward to backend)
        target_path = self.path[len("/api"):] 
        target_url = f"{BACKEND_URL}{target_path}"
        
        # Read content length for POST body
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else None

        # Build request headers (skip host and other standard headers that urllib generates)
        headers = {}
        for key, val in self.headers.items():
            if key.lower() not in ('host', 'content-length', 'connection'):
                headers[key] = val

        req = urllib.request.Request(
            target_url,
            data=post_data,
            headers=headers,
            method=method
        )

        try:
            with urllib.request.urlopen(req) as response:
                self.send_response(response.status)
                for key, val in response.getheaders():
                    # Avoid sending duplicate transfer-encoding headers
                    if key.lower() not in ('transfer-encoding', 'connection'):
                        self.send_header(key, val)
                self.end_headers()
                self.wfile.write(response.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            for key, val in e.headers.items():
                if key.lower() not in ('transfer-encoding', 'connection'):
                    self.send_header(key, val)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            error_msg = json.dumps({"detail": f"Proxy error to backend: {str(e)}"})
            self.wfile.write(error_msg.encode('utf-8'))

if __name__ == "__main__":
    # Change working dir to directory of this script to serve local static files correctly
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # Use ThreadingTCPServer or socketserver.TCPServer
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), ProxyHTTPRequestHandler) as httpd:
        print("=========================================================")
        print(f"Testing Agent Frontend Server started at: http://localhost:{PORT}")
        print(f"Proxying API calls /api/* -> {BACKEND_URL}/*")
        print("Press Ctrl+C to terminate.")
        print("=========================================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
            sys.exit(0)
