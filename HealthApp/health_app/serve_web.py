import http.server
import socketserver
import mimetypes
import sys
import os

PORT = 3000
DIRECTORY = "build/web"

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def do_GET(self):
        # 404 for service worker requests to completely disable service worker registrations
        if "flutter_service_worker.js" in self.path:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Service worker disabled")
            return
            
        # Dynamically remove serviceWorkerSettings from flutter_bootstrap.js
        if "flutter_bootstrap.js" in self.path:
            full_path = self.translate_path(self.path)
            if os.path.exists(full_path):
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    import re
                    # Replace _flutter.loader.load with serviceWorkerSettings block
                    modified = re.sub(
                        r'_flutter\.loader\.load\(\{\s*serviceWorkerSettings:\s*\{.*?\}\s*\}\);',
                        '_flutter.loader.load();',
                        content,
                        flags=re.DOTALL
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "application/javascript")
                    self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                    self.end_headers()
                    self.wfile.write(modified.encode("utf-8"))
                    return
                except Exception as e:
                    print(f"Error serving modified flutter_bootstrap.js: {e}")

        # Add Cache-Control no-store for index.html as well to prevent cache issues
        if self.path == "/" or self.path.endswith("index.html"):
            full_path = self.translate_path(self.path)
            if os.path.exists(full_path):
                try:
                    with open(full_path, "rb") as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                    self.end_headers()
                    self.wfile.write(content)
                    return
                except Exception as e:
                    print(f"Error serving index.html: {e}")

        return super().do_GET()

# Register font MIME types to fix browser blocking issues
mimetypes.add_type('font/otf', '.otf')
mimetypes.add_type('font/ttf', '.ttf')
mimetypes.add_type('font/woff', '.woff')
mimetypes.add_type('font/woff2', '.woff2')
mimetypes.add_type('image/svg+xml', '.svg')

# Set working directory to the script's directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

handler = MyHTTPRequestHandler

# Allow reusing address and enable multi-threaded handling of browser requests
socketserver.ThreadingTCPServer.allow_reuse_address = True

print(f"Starting multi-threaded web server on port {PORT}, directory {DIRECTORY}")
with socketserver.ThreadingTCPServer(("", PORT), handler) as httpd:
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping web server...")
        httpd.server_close()
