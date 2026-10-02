from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit, parse_qs

from .core import InputError
from .tools import EvidenceTools, TOOL_SPECS


def make_server(port=8765, tools=None):
    """Bind only to loopback. There are no remote APIs, write tools, or account credentials."""
    backend = tools or EvidenceTools()

    class Handler(BaseHTTPRequestHandler):
        server_version = "RydeEvidence/0.1"

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
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
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
            parsed = urlsplit(self.path)
            parts = [unquote(p) for p in parsed.path.strip("/").split("/") if p]
            try:
                if not parts:
                    return self.respond(200, (Path(__file__).parent / "ui.html").read_bytes(), "text/html; charset=utf-8")
                if parts == ["health"]:
                    return self.respond(200, {"status": "ready", "version": "0.1.0", "case_count": len(backend.list_cases())})
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
                    if len(parts) == 3 and parts[2] in ("audit", "raw", "route-comparison"):
                        method = {"audit": backend.audit_case, "raw": backend.load_case, "route-comparison": backend.compare_route}[parts[2]]
                        return self.respond(200, method(case_id))
                    if len(parts) == 4 and parts[2] in ("evidence", "policies"):
                        method = backend.get_evidence if parts[2] == "evidence" else backend.get_policy
                        version = parse_qs(parsed.query).get("source_sha256", [None])[0]
                        return self.respond(200, method(case_id, parts[3], version))
                self.respond(404, {"error": "Unknown endpoint"})
            except InputError as exc:
                self.respond(400, {"error": str(exc)})
            except (OSError, ValueError, KeyError, TypeError):
                self.respond(500, {"error": "Case data could not be loaded; check the local dataset"})

        def do_POST(self):
            if not self.allowed():
                return
            try:
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    return self.respond(415, {"error": "Use application/json"})
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    return self.respond(413, {"error": "Body must contain 1..65536 bytes"})
                parts = self.path.strip("/").split("/")
                if len(parts) != 2 or parts[0] != "tools":
                    return self.respond(404, {"error": "Unknown tool endpoint"})
                def reject_constant(value):
                    raise InputError("Non-finite JSON numbers are rejected")
                arguments = json.loads(self.rfile.read(length), parse_constant=reject_constant)
                self.respond(200, backend.call(parts[1], arguments))
            except (InputError, ValueError, UnicodeDecodeError, TypeError) as exc:
                self.respond(400, {"error": str(exc)})

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
