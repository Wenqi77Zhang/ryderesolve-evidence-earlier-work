import http.client
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

from ryderesolve_evidence.server import make_server


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(2)

    def request(self, path, method="GET", body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        status, payload, result_headers = response.status, response.read(), dict(response.getheaders())
        connection.close()
        return status, payload, result_headers

    def test_real_http_pack_and_citation_round_trip(self):
        status, payload, _ = self.request("/cases/DISP-002")
        self.assertEqual(status,200)
        pack = json.loads(payload)
        status, payload, _ = self.request("/cases/DISP-002/evidence/"+pack["facts"][0]["evidence_id"])
        self.assertEqual(status,200)
        self.assertTrue(json.loads(payload)["excerpts"])

    def test_both_cases_audit_raw_and_contract_are_readable(self):
        for path in ("/health", "/cases", "/cases/SYN-ROUTE-001", "/cases/DISP-002/raw", "/cases/DISP-002/audit", "/cases/SYN-ROUTE-001/route-comparison", "/contracts/evidence-pack.schema.json", "/tool-specs"):
            with self.subTest(path=path):
                status, payload, _ = self.request(path)
                self.assertEqual(status,200)
                json.loads(payload)

    def test_ui_and_no_store_headers(self):
        status, payload, headers=self.request("/")
        self.assertEqual(status,200)
        self.assertIn("text/html",headers["Content-Type"])
        self.assertEqual(headers["Cache-Control"],"no-store")
        self.assertIn("证据核对台",payload.decode("utf-8"))

    def test_external_origin_and_host_rejected(self):
        for headers in ({"Origin":"https://example.com"},{"Host":"example.com"},{"Origin":"null"},{"Origin":"http://localhost@evil.example"}):
            self.assertEqual(self.request("/cases",headers=headers)[0],403)

    def test_local_frontend_origin_supported(self):
        status, _, headers=self.request("/cases",headers={"Origin":"http://localhost:5173"})
        self.assertEqual(status,200)
        self.assertEqual(headers["Access-Control-Allow-Origin"],"http://localhost:5173")

    def test_malformed_origin_returns_rejection_without_disconnect(self):
        for origin in ("http://[", "http://localhost:invalid", "http://localhost:99999", "http://localhost/path", "http://@localhost"):
            with self.subTest(origin=origin):
                status, payload, headers = self.request("/cases", headers={"Origin":origin})
                self.assertEqual(status,403)
                self.assertIn("error",json.loads(payload))
                self.assertNotIn("Access-Control-Allow-Origin",headers)

    def test_post_is_read_only_tool_dispatch(self):
        status,payload,_=self.request("/tools/get_evidence","POST",json.dumps({"case_id":"DISP-002","evidence_id":"E-002"}),{"Content-Type":"application/json"})
        self.assertEqual(status,200)
        self.assertEqual(json.loads(payload)["kind"],"party_statement")

    def test_invalid_json_nan_unknown_tool_and_size_rejected(self):
        for path, body, expected in (("/tools/load_case","{",400),("/tools/load_case",'{"case_id":NaN}',400),("/tools/write_file","{}",400),("/tools/load_case"," "*65537,413)):
            self.assertEqual(self.request(path,"POST",body,{"Content-Type":"application/json"})[0],expected)

    def test_wrong_media_type_and_unknown_path_rejected(self):
        self.assertEqual(self.request("/tools/load_case","POST","{}",{"Content-Type":"text/plain"})[0],415)
        self.assertEqual(self.request("/evaluation/official_expected.json")[0],404)

    def test_bad_reference_and_stale_version_do_not_succeed(self):
        for path in ("/cases/DISP-002/evidence/E-999", "/cases/DISP-002/evidence/E-001?source_sha256="+"0"*64, "/cases/%2E%2E%2Fevaluation/raw"):
            self.assertEqual(self.request(path)[0],400)

    def test_atomic_snapshot_http_round_trip_and_guard(self):
        status, payload, _ = self.request("/cases/DISP-002/snapshot")
        self.assertEqual(status,200)
        snapshot = json.loads(payload)
        self.assertEqual(snapshot["snapshot_id"], snapshot["audit"]["snapshot_id"])
        path = "/cases/DISP-002/evidence/E-002?snapshot_id="
        status, payload, _ = self.request(path + snapshot["snapshot_id"])
        self.assertEqual(status,200)
        self.assertEqual(json.loads(payload)["snapshot_id"],snapshot["snapshot_id"])
        self.assertEqual(self.request(path + "0" * 64)[0],400)

    def test_empty_duplicate_and_unknown_version_queries_fail(self):
        for suffix in ("snapshot_id=", "source_sha256=", "snapshot_id="+"0"*64+"&snapshot_id="+"1"*64, "unexpected=value"):
            with self.subTest(suffix=suffix):
                self.assertEqual(self.request("/cases/DISP-002/evidence/E-002?"+suffix)[0],400)

    def test_duplicate_deep_and_overflow_json_are_rejected_over_http(self):
        for body in ('{"case_id":"DISP-002","case_id":"SYN-ROUTE-001"}', '{"case_id":1e400}', '['*70+'0'+']'*70):
            self.assertEqual(self.request("/tools/load_case","POST",body,{"Content-Type":"application/json"})[0],400)

    def test_ui_uses_external_script_and_restricts_inline_scripts(self):
        status, html, headers = self.request("/")
        self.assertEqual(status,200)
        self.assertIn(b'<script src="/ui.js"', html)
        self.assertIn("script-src 'self';",headers["Content-Security-Policy"])
        status, _, headers = self.request("/ui.js")
        self.assertEqual(status,200)
        self.assertIn("application/javascript",headers["Content-Type"])

    def test_malformed_optional_output_reports_schema_error_over_http(self):
        body = json.dumps({"case_id":"DISP-002", "judge":{"case_id":"DISP-002","decision":"review","findings":[],"uncertainties":123}})
        status, payload, _ = self.request("/tools/validate_outputs","POST",body,{"Content-Type":"application/json"})
        self.assertEqual(status,200)
        self.assertFalse(json.loads(payload)["structurally_valid"])


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable,"-m","ryderesolve_evidence",*args],capture_output=True,text=True,encoding="utf-8",timeout=20)

    def test_pack_cli_outputs_json(self):
        result=self.run_cli("pack","DISP-002")
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)["case_id"],"DISP-002")

    def test_export_can_be_opened_by_other_languages(self):
        with tempfile.TemporaryDirectory() as folder:
            result=self.run_cli("export","DISP-002","--out",folder)
            self.assertEqual(result.returncode,0,result.stderr)
            for path in json.loads(result.stdout)["written"]:
                self.assertEqual(json.loads(Path(path).read_text(encoding="utf-8"))["case_id"],"DISP-002")

    def test_invalid_case_returns_failure_exit(self):
        result=self.run_cli("pack","UNKNOWN")
        self.assertEqual(result.returncode,2)
        self.assertIn("error",json.loads(result.stderr))

    def test_prepare_cli_produces_versioned_snapshot(self):
        result = self.run_cli("prepare", "DISP-002")
        self.assertEqual(result.returncode,0,result.stderr)
        snapshot = json.loads(result.stdout)
        self.assertEqual(snapshot["snapshot_id"],snapshot["audit"]["snapshot_id"])

    def test_invalid_optional_field_makes_validate_cli_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "judge.json"
            path.write_text(json.dumps({"case_id":"DISP-002","decision":"review","findings":[],"uncertainties":123}),encoding="utf-8")
            result = self.run_cli("validate", "DISP-002", "--judge", str(path))
            self.assertEqual(result.returncode,1,result.stderr)
            self.assertFalse(json.loads(result.stdout)["structurally_valid"])
