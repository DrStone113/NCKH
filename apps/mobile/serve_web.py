import http.server
import mimetypes
import os
import re
import socketserver
from urllib.parse import urlsplit

PORT = 3000
APP_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
DIRECTORY = os.path.join(APP_DIRECTORY, "build", "web")


class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def do_GET(self):
        request_path = urlsplit(self.path).path

        # 404 for service worker requests to completely disable service worker registrations
        if request_path.endswith("/flutter_service_worker.js"):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Service worker disabled")
            return

        # Dynamically remove serviceWorkerSettings from flutter_bootstrap.js
        if request_path.endswith("/flutter_bootstrap.js"):
            full_path = self.translate_path(request_path)
            if os.path.isfile(full_path):
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    # Replace _flutter.loader.load with serviceWorkerSettings block
                    modified = re.sub(
                        r'_flutter\.loader\.load\(\{\s*serviceWorkerSettings:\s*\{.*?\}\s*\}\);',
                        '_flutter.loader.load();',
                        content,
                        flags=re.DOTALL
                    )
                    # Flutter's generated bootstrap uses an unversioned
                    # main.dart.js URL. Safari can keep that bundle after a
                    # rebuild, so give it a version derived from the actual
                    # artifact without modifying generated build output.
                    main_js_path = os.path.join(DIRECTORY, "main.dart.js")
                    if os.path.isfile(main_js_path):
                        main_js_version = os.stat(main_js_path).st_mtime_ns
                        modified = modified.replace(
                            '"mainJsPath":"main.dart.js"',
                            f'"mainJsPath":"main.dart.js?v={main_js_version}"',
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
        if request_path == "/" or request_path.endswith("/index.html"):
            index_path = "/index.html" if request_path == "/" else request_path
            full_path = self.translate_path(index_path)
            if os.path.isfile(full_path):
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
mimetypes.add_type("font/otf", ".otf")
mimetypes.add_type("font/ttf", ".ttf")
mimetypes.add_type("font/woff", ".woff")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("image/svg+xml", ".svg")


class ReusableThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    print(f"Starting multi-threaded web server on port {PORT}, directory build/web")
    with ReusableThreadingTCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping web server...")


if __name__ == "__main__":
    main()
