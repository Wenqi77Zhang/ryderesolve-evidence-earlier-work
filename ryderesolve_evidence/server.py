from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit, parse_qs

from .core import InputError, parse_json
from .tools import EvidenceTools, TOOL_SPECS
from .version import __version__


def make_server(port=8765, tools=None):
    """Bind only to loopback. There are no remote APIs, write tools, or account credentials."""
    backend = tools or EvidenceTools()

    class Handler(BaseHTTPRequestHandler):
        server_version = f"RydeEvidence/{__version__}"

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, fmt, *args):
            pass  # Avoid writing source excerpts, identifiers or request bodies to logs.

        def local_origin(self):
            origin = self.headers.get("Origin")
            if not origin:
                return None
            try:
                parsed = urlsplit(origin)
                parsed.port  # Reject invalid or out-of-range ports as well as malformed hosts.
                if (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost")
                        and parsed.username is None and parsed.password is None
                        and not parsed.path and not parsed.query and not parsed.fragment):
                    return origin
            except ValueError:
                pass
            return None

        def allowed(self):
            host = self.headers.get("Host", "")
            allowed_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if host not in allowed_hosts:
                self.respond(403, {"error": "Non-loopback Host rejected"})
                return False
            origin = self.headers.get("Origin")
            if origin and not self.local_origin():
                self.respond(403, {"error": "Only loopback development origins are allowed"})
                return False
            return True

        def respond(self, status, data, content_type="application/json; charset=utf-8"):
            payload = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            origin = self.local_origin()
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.end_headers()
            self.wfile.write(payload)

        def do_OPTIONS(self):
            if self.allowed():
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", f"http://127.0.0.1:{self.server.server_port}"))
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

        def do_GET(self):
            if not self.allowed():
                return
            try:
                parsed = urlsplit(self.path)
                if parsed.scheme or parsed.netloc:
                    return self.respond(400, {"error": "Use a local relative endpoint path"})
                parts = [unquote(p) for p in parsed.path.strip("/").split("/") if p]
                query = parse_qs(parsed.query, keep_blank_values=True)
                reference_request = len(parts) == 4 and parts[0] == "cases" and parts[2] in ("evidence", "policies")
                if query and (not reference_request or any(key not in ("source_sha256", "snapshot_id") or len(values) != 1 for key, values in query.items())):
                    return self.respond(400, {"error": "Unknown or repeated query parameter"})
                if not parts:
                    return self.respond(200, (Path(__file__).parent / "ui.html").read_bytes(), "text/html; charset=utf-8")
                if parts == ["ui.js"]:
                    return self.respond(200, (Path(__file__).parent / "ui.js").read_bytes(), "application/javascript; charset=utf-8")
                if parts == ["health"]:
                    return self.respond(200, {"status": "ready", "version": __version__, "case_count": len(backend.list_cases())})
                if parts == ["cases"]:
                    return self.respond(200, backend.list_cases())
                if parts == ["tool-specs"]:
                    return self.respond(200, TOOL_SPECS)
                if len(parts) == 2 and parts[0] == "contracts" and parts[1] in {"evidence-pack.schema.json", "advocate.schema.json", "judge.schema.json"}:
                    return self.respond(200, (Path(__file__).parent / "contracts" / parts[1]).read_bytes())
                if len(parts) >= 2 and parts[0] == "cases":
                    case_id = parts[1]
                    if len(parts) == 2:
                        return self.respond(200, backend.normalize_evidence(case_id))
                    if len(parts) == 3 and parts[2] in ("audit", "raw", "route-comparison", "snapshot"):
                        method = {"audit": backend.audit_case, "raw": backend.load_case, "route-comparison": backend.compare_route, "snapshot": backend.prepare_case}[parts[2]]
                        return self.respond(200, method(case_id))
                    if len(parts) == 4 and parts[2] in ("evidence", "policies"):
                        method = backend.get_evidence if parts[2] == "evidence" else backend.get_policy
                        version = query.get("source_sha256", [None])[0]
                        snapshot = query.get("snapshot_id", [None])[0]
                        return self.respond(200, method(case_id, parts[3], version, snapshot))
                self.respond(404, {"error": "Unknown endpoint"})
            except InputError as exc:
                self.respond(400, {"error": str(exc)})
            except (OSError, ValueError, KeyError, TypeError):
                self.respond(500, {"error": "Case data could not be loaded; check the local dataset"})

        def do_POST(self):
            if not self.allowed():
                return
            try:
                if self.headers.get("Transfer-Encoding") is not None or len(self.headers.get_all("Content-Length", [])) != 1:
                    return self.respond(400, {"error": "Use one Content-Length and no Transfer-Encoding"})
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    return self.respond(415, {"error": "Use application/json"})
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    return self.respond(413, {"error": "Body must contain 1..65536 bytes"})
                parts = self.path.strip("/").split("/")
                if len(parts) != 2 or parts[0] != "tools":
                    return self.respond(404, {"error": "Unknown tool endpoint"})
                body = self.rfile.read(length)
                if len(body) != length:
                    return self.respond(400, {"error": "Incomplete request body"})
                arguments = parse_json(body)
                self.respond(200, backend.call(parts[1], arguments))
            except TimeoutError:
                self.respond(408, {"error": "Request body timed out"})
            except (InputError, ValueError, UnicodeDecodeError, TypeError) as exc:
                self.respond(400, {"error": str(exc)})
            except (OSError, KeyError):
                self.respond(500, {"error": "Case data could not be loaded; check the local dataset"})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(port=8765):
    server = make_server(port)
    print(f"Evidence inspector: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
