#!/usr/bin/env python3
"""Small threaded test server with CGI support for PHP fixtures."""

import http.server
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Optional
from urllib.parse import unquote, urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


class TestRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serve repository files and execute PHP files through php-cgi."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(REPOSITORY_ROOT), **kwargs)

    def do_GET(self) -> None:
        self._dispatch_request()

    def do_HEAD(self) -> None:
        self._dispatch_request()

    def do_POST(self) -> None:
        self._dispatch_request()

    def _dispatch_request(self) -> None:
        path = unquote(urlsplit(self.path).path)
        if re.search(r"\.php(?:/|$)", path, re.IGNORECASE):
            self._run_php(path)
        else:
            super().do_GET() if self.command == "GET" else super().do_HEAD()

    def _run_php(self, request_path: str) -> None:
        php_end = re.search(r"\.php(?=/|$)", request_path, re.IGNORECASE)
        if php_end is None:
            self.send_error(http.server.HTTPStatus.NOT_FOUND)
            return
        script_path = request_path[: php_end.end()]
        path_info = request_path[php_end.end() :]
        script = self._script_path(script_path)
        if script is None or not script.is_file():
            self.send_error(http.server.HTTPStatus.NOT_FOUND)
            return

        body = b""
        content_length = self.headers.get("Content-Length")
        if content_length:
            try:
                body = self.rfile.read(int(content_length))
            except ValueError:
                self.send_error(http.server.HTTPStatus.BAD_REQUEST)
                return

        split_path = urlsplit(self.path)
        host, _, port = self.headers.get("Host", "localhost:8000").partition(":")
        if not port:
            port = "443" if self.server.server_port == 443 else str(self.server.server_port)
        environment = {
            "GATEWAY_INTERFACE": "CGI/1.1",
            "SERVER_SOFTWARE": "Python ThreadingHTTPServer",
            "SERVER_PROTOCOL": self.request_version,
            "SERVER_NAME": host,
            "SERVER_PORT": port,
            "REQUEST_METHOD": self.command,
            "QUERY_STRING": split_path.query,
            "SCRIPT_NAME": script_path,
            "SCRIPT_FILENAME": str(script),
            "PATH_INFO": path_info,
            "PATH_TRANSLATED": str(script),
            "REQUEST_URI": self.path,
            "REMOTE_ADDR": self.client_address[0],
            "DOCUMENT_ROOT": str(REPOSITORY_ROOT),
            "REDIRECT_STATUS": "1",
            "CONTENT_LENGTH": str(len(body)) if body else content_length or "",
        }
        for name, value in self.headers.items():
            cgi_name = name.upper().replace("-", "_")
            if cgi_name == "CONTENT_TYPE":
                environment[cgi_name] = value
            elif cgi_name != "CONTENT_LENGTH":
                environment["HTTP_" + cgi_name] = value

        try:
            result = subprocess.run(
                ["php-cgi"],
                input=body,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(REPOSITORY_ROOT),
                env={**os.environ, **environment},
                check=False,
            )
        except OSError as error:
            self.send_error(http.server.HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
            return

        if result.returncode != 0 and not result.stdout:
            self.send_error(
                http.server.HTTPStatus.INTERNAL_SERVER_ERROR,
                result.stderr.decode("utf-8", "replace"),
            )
            return

        header_bytes, separator, response_body = result.stdout.partition(b"\r\n\r\n")
        if not separator:
            header_bytes, separator, response_body = result.stdout.partition(b"\n\n")
        if not separator:
            self.send_error(http.server.HTTPStatus.INTERNAL_SERVER_ERROR, "Invalid CGI response")
            return

        status = http.server.HTTPStatus.OK
        headers = []
        for line in header_bytes.decode("iso-8859-1").splitlines():
            if not line.strip() or ":" not in line:
                continue
            name, value = line.split(":", 1)
            if name.lower() == "status":
                status = int(value.strip().split(" ", 1)[0])
            else:
                headers.append((name.strip(), value.lstrip()))

        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        if not any(name.lower() == "content-length" for name, _ in headers):
            self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(response_body)

    @staticmethod
    def _script_path(request_path: str) -> Optional[Path]:
        php_end = re.search(r"\.php(?=/|$)", request_path, re.IGNORECASE)
        if php_end is None:
            return None
        relative_path = Path(request_path[: php_end.end()].lstrip("/"))
        candidate = (REPOSITORY_ROOT / relative_path).resolve()
        try:
            candidate.relative_to(REPOSITORY_ROOT)
        except ValueError:
            return None
        return candidate

    def log_message(self, format_string: str, *args: object) -> None:
        super().log_message(format_string, *args)


class ThreadingHTTPServer(http.server.ThreadingHTTPServer):
    """HTTP server that allows concurrent browser requests."""

    daemon_threads = True
    allow_reuse_address = True


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = ThreadingHTTPServer(("127.0.0.1", port), TestRequestHandler)
    print("Serving {} on port {}".format(REPOSITORY_ROOT, port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
