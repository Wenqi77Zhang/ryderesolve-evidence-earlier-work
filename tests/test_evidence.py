import copy
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from ryderesolve_evidence import CaseRepository, EvidenceTools, InputError, normalize_evidence
from ryderesolve_evidence.core import build_bundle, pointer, read_json, source_hash


ROOT = Path(__file__).resolve().parents[1]


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tools = EvidenceTools()
        self.raw = self.tools.load_case("DISP-002")

    def codes(self, bundle):
        return {i["code"] for i in bundle.audit["issues"]}

    def test_official_timing_ambiguity_is_preserved(self):
        bundle = self.tools.repository.bundle("DISP-002")
        self.assertEqual(bundle.audit["metrics"]["trip_wait"]["seconds"], 480)
        self.assertEqual(bundle.audit["metrics"]["app_wait_5"]["seconds"], 470)
        self.assertTrue({"WAIT_START_DISAGREEMENT", "POLICY_CLOCK_BASIS_UNSPECIFIED"} <= self.codes(bundle))
        self.assertTrue(bundle.audit["requires_policy_or_data_review"])
        self.assertNotIn("decision", bundle.pack)

    def test_public_normalization_is_a_pack_not_an_internal_bundle(self):
        pack = normalize_evidence(self.raw)
        self.assertEqual(set(pack), {"case_id", "dispute_type", "facts", "policy"})
        self.assertEqual(set(pack["facts"][0]), {"evidence_id", "fact", "source"})

    def test_statement_has_a_source_but_is_not_verified(self):
        result = self.tools.get_evidence("DISP-002", "E-002")
        self.assertEqual(result["kind"], "party_statement")
        self.assertEqual(result["excerpts"][0]["value"], self.raw["dispute_ticket"]["description"])
        self.assertEqual(result["source_refs"], ["/dispute_ticket/description"])

    def test_gps_observation_points_and_source_are_exact(self):
        result = self.tools.get_evidence("DISP-002", "E-001")
        self.assertEqual(result["kind"], "derived_observation")
        self.assertEqual(result["source_refs"][:4], [f"/gps_telemetry/{i}" for i in range(4, 8)])
        self.assertEqual(len(result["excerpts"]), 5)

    def test_every_evidence_and_policy_reference_resolves(self):
        for case in self.tools.list_cases():
            pack = self.tools.normalize_evidence(case["case_id"])
            for item in pack["facts"]:
                self.assertTrue(self.tools.get_evidence(case["case_id"], item["evidence_id"])["excerpts"])
            for item in pack["policy"]:
                self.assertTrue(self.tools.get_policy(case["case_id"], item["policy_id"])["excerpts"])

    def test_official_and_synthetic_pack_match_published_schema(self):
        schema = read_json(ROOT / "ryderesolve_evidence/contracts/evidence-pack.schema.json")
        Draft202012Validator.check_schema(schema)
        for case in self.tools.list_cases():
            Draft202012Validator(schema).validate(self.tools.normalize_evidence(case["case_id"]))

    def test_no_label_or_editorial_summary_in_runtime_payloads(self):
        for case in self.tools.list_cases():
            payload = json.dumps({"raw": self.tools.load_case(case["case_id"]), "pack": self.tools.normalize_evidence(case["case_id"]), "audit": self.tools.audit_case(case["case_id"])})
            self.assertNotIn("organizer_expected_decision", payload)
            self.assertNotIn("Expected ruling", payload)
            self.assertNotIn("Evidence Summary", payload)

    def test_normalization_does_not_mutate_original(self):
        before = copy.deepcopy(self.raw)
        normalize_evidence(self.raw)
        self.assertEqual(self.raw, before)

    def test_reordered_object_keys_do_not_change_ids_or_hash(self):
        reordered = dict(reversed(list(self.raw.items())))
        self.assertEqual(source_hash(self.raw), source_hash(reordered))
        self.assertEqual(normalize_evidence(self.raw), normalize_evidence(reordered))

    def test_source_version_changes_when_record_changes(self):
        changed = copy.deepcopy(self.raw)
        changed["chat_logs"][0]["content"] = "Changed record"
        self.assertNotEqual(source_hash(self.raw), source_hash(changed))

    def test_stale_source_reference_is_rejected(self):
        with self.assertRaises(InputError):
            self.tools.get_evidence("DISP-002", "E-001", "0" * 64)

    def test_unknown_reference_is_rejected(self):
        with self.assertRaises(InputError):
            self.tools.get_evidence("DISP-002", "E-999")
        with self.assertRaises(InputError):
            self.tools.get_policy("DISP-002", "E-001")

    def test_case_path_traversal_is_rejected(self):
        with self.assertRaises(InputError):
            self.tools.load_case("../../evaluation/official_expected")

    def test_catalog_cannot_escape_data_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "catalog.json").write_text(json.dumps({"cases": [{"case_id":"X", "path":"../outside.json", "dispute_type":"no_show_charge", "data_origin":"organizer_sample", "policy_origin":"organizer_sample"}]}))
            with self.assertRaises(InputError):
                CaseRepository(root).load_case("X")

    def test_mismatched_trip_is_rejected(self):
        self.raw["trip_data"]["trip_id"] = "OTHER"
        with self.assertRaises(InputError):
            normalize_evidence(self.raw)

    def test_mismatched_profile_is_rejected(self):
        self.raw["rider_profile"]["rider_id"] = "OTHER"
        with self.assertRaises(InputError):
            normalize_evidence(self.raw)

    def test_naive_time_is_rejected(self):
        self.raw["trip_data"]["driver_wait_start"] = "2026-09-13T08:43:00"
        with self.assertRaises(InputError):
            normalize_evidence(self.raw)

    def test_negative_duration_is_rejected(self):
        self.raw["trip_data"]["driver_wait_start"] = "2026-09-13T08:52:00+08:00"
        with self.assertRaises(InputError):
            normalize_evidence(self.raw)

    def test_timezones_are_respected(self):
        self.raw["trip_data"]["driver_wait_start"] = "2026-09-13T00:43:00+00:00"
        self.assertEqual(build_bundle(self.raw).audit["metrics"]["trip_wait"]["seconds"], 480)

    def test_invalid_coordinates_boolean_and_nan_are_rejected(self):
        for value in (91, float("nan"), True, "1.2"):
            with self.subTest(value=value):
                raw = copy.deepcopy(self.raw)
                raw["gps_telemetry"][0]["lat"] = value
                with self.assertRaises(InputError):
                    normalize_evidence(raw)

    def test_unordered_telemetry_is_rejected(self):
        self.raw["gps_telemetry"].reverse()
        with self.assertRaises(InputError):
            normalize_evidence(self.raw)

    def test_missing_gps_and_chat_are_review_issues_not_invented_evidence(self):
        del self.raw["gps_telemetry"]
        del self.raw["chat_logs"]
        bundle = build_bundle(self.raw)
        self.assertTrue({"MISSING_GPS", "MISSING_COMMUNICATION_LOGS"} <= self.codes(bundle))
        self.assertTrue(bundle.audit["requires_policy_or_data_review"])

    def test_missing_policy_is_visible(self):
        del self.raw["cancellation_policy"]
        bundle = build_bundle(self.raw)
        self.assertIn("MISSING_POLICY", self.codes(bundle))
        self.assertEqual(bundle.pack["policy"], [])

    def test_multiple_timer_starts_are_not_silently_collapsed(self):
        event = copy.deepcopy(self.raw["app_events"][5])
        event["timestamp"] = "2026-09-13T08:43:11+08:00"
        self.raw["app_events"].insert(6, event)
        bundle = build_bundle(self.raw)
        self.assertIn("MULTIPLE_WAIT_START_EVENTS", self.codes(bundle))
        self.assertEqual(bundle.audit["metrics"]["trip_wait"]["seconds"], 480)
        self.assertEqual(bundle.audit["metrics"]["app_wait_5"]["seconds"], 470)
        self.assertEqual(bundle.audit["metrics"]["app_wait_6"]["seconds"], 469)

    def test_historical_profiles_are_context_not_a_verdict(self):
        bundle = self.tools.repository.bundle("DISP-002")
        contexts = [item for item in bundle.evidence_index.values() if item["kind"] == "historical_context"]
        self.assertEqual(len(contexts), 2)

    def test_json_pointer_escaping_and_indices(self):
        self.assertEqual(pointer({"a/b":{"~key":[123]}}, "/a~1b/~0key/0"), 123)
        for ref in ("x", "/a~2b", "/list/-1", "/list/01", "/list/9"):
            with self.subTest(ref=ref), self.assertRaises(InputError):
                pointer({"list":[0]}, ref)

    def test_synthetic_route_has_explicit_provenance(self):
        raw = self.tools.load_case("SYN-ROUTE-001")
        audit = self.tools.audit_case("SYN-ROUTE-001")
        self.assertEqual(raw["dataset_metadata"]["data_origin"], "synthetic")
        self.assertEqual(audit["policy_origin"], "team_authored_synthetic")

    def test_route_distance_and_fare_are_calculations_not_refunds(self):
        audit = self.tools.audit_case("SYN-ROUTE-001")
        route = audit["metrics"]["route_comparison"]
        ratio = route["actual_sampled_length_m"] / route["reference_sampled_length_m"]
        self.assertGreater(ratio, 1.9)
        self.assertLess(ratio, 2.1)
        self.assertEqual(route["start_offset_m"], 0)
        self.assertEqual(route["end_offset_m"], 0)
        self.assertEqual(audit["metrics"]["fare_difference"]["difference_cents"], 500)
        self.assertNotIn("refund_amount", audit)

    def test_route_reference_missing_or_zero_length_is_not_a_valid_comparison(self):
        for reference in ([], [{"lat":1,"lng":1}, {"lat":1,"lng":1}]):
            raw = self.tools.load_case("SYN-ROUTE-001")
            raw["reference_route"] = reference
            self.assertIn("ROUTE_COMPARISON_UNAVAILABLE", self.codes(build_bundle(raw)))

    def test_route_endpoint_difference_is_flagged(self):
        raw = self.tools.load_case("SYN-ROUTE-001")
        raw["reference_route"][-1]["lat"] += 0.01
        self.assertIn("ROUTE_ENDPOINT_MISMATCH", self.codes(build_bundle(raw)))

    def test_money_minor_units_must_be_integer(self):
        raw = self.tools.load_case("SYN-ROUTE-001")
        raw["fare_breakdown"]["charged_total_cents"] = 1500.5
        with self.assertRaises(InputError):
            normalize_evidence(raw)

    def test_no_show_cannot_be_mislabeled_as_route_comparison(self):
        with self.assertRaises(InputError):
            self.tools.compare_route("DISP-002")


class OutputValidationTests(unittest.TestCase):
    def setUp(self):
        self.tools = EvidenceTools()
        self.advocate = {"case_id":"DISP-002", "side":"rider", "claims":[{"claim":"The rider states that the driver could not be found.", "evidence_refs":["E-002"]}], "counterpoints":[]}
        self.judge = {"case_id":"DISP-002", "decision":"insufficient_evidence", "findings":[{"finding":"The source timestamps require clarification.", "evidence_refs":["E-001"], "policy_refs":["P-001"]}], "escalate_to_human":True}

    def result(self):
        return self.tools.validate_outputs("DISP-002", self.advocate, self.judge)

    def test_examples_match_schemas_and_resolve(self):
        for name, value in (("advocate",self.advocate),("judge",self.judge)):
            schema=read_json(ROOT / f"ryderesolve_evidence/contracts/{name}.schema.json")
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(value)
        self.assertTrue(self.result()["structurally_valid"])
        self.assertTrue(self.result()["requires_policy_or_data_review"])

    def test_unknown_citations_fail(self):
        self.advocate["claims"][0]["evidence_refs"] = ["E-999"]
        self.assertFalse(self.result()["structurally_valid"])

    def test_unknown_policy_fails(self):
        self.judge["findings"][0]["policy_refs"] = ["P-999"]
        self.assertFalse(self.result()["structurally_valid"])

    def test_cross_case_output_fails(self):
        self.advocate["case_id"] = "SYN-ROUTE-001"
        self.assertFalse(self.result()["structurally_valid"])

    def test_empty_references_remain_visible_as_unsupported(self):
        self.advocate["claims"][0]["evidence_refs"] = []
        result = self.result()
        self.assertTrue(result["structurally_valid"])
        self.assertTrue(any(w["code"] == "UNSUPPORTED_STATEMENT" for w in result["warnings"]))

    def test_references_must_be_arrays_without_duplicates(self):
        for value in ("E-001", ["E-001", "E-001"], [True]):
            self.advocate["claims"][0]["evidence_refs"] = value
            self.assertFalse(self.result()["structurally_valid"])

    def test_confidence_nan_boolean_or_out_of_range_fails(self):
        for value in (float("nan"), True, -0.1, 1.1):
            self.judge["confidence"] = value
            self.assertFalse(self.result()["structurally_valid"])

    def test_placeholder_confidence_is_flagged(self):
        self.judge.update(confidence=0.0, escalate_to_human=False)
        self.assertTrue(any(w["code"] == "ZERO_CONFIDENCE_WITHOUT_REVIEW" for w in self.result()["warnings"]))

    def test_refund_cannot_be_negative(self):
        self.judge["refund_amount"] = -1
        self.assertFalse(self.result()["structurally_valid"])

    def test_missing_text_or_side_fails(self):
        self.advocate["side"] = "unknown"
        self.advocate["claims"][0]["claim"] = ""
        self.assertFalse(self.result()["structurally_valid"])

    def test_no_outputs_is_not_a_pass(self):
        self.assertFalse(self.tools.validate_outputs("DISP-002")["structurally_valid"])

    def test_future_decision_string_is_not_silently_rewritten(self):
        self.judge["decision"] = "team_defined_review_result"
        self.assertTrue(self.result()["structurally_valid"])

    def test_tool_dispatch_rejects_unknown_tool_or_arguments(self):
        for name, args in (("send_refund",{}),("load_case",{"case_id":"DISP-002","path":"secret"}),("load_case",{}),("load_case",{"case_id":1})):
            with self.subTest(name=name), self.assertRaises(InputError):
                self.tools.call(name,args)

    def test_tool_dispatch_and_source_version_guard(self):
        self.assertEqual(self.tools.call("load_case", {"case_id":"DISP-002"}), self.tools.load_case("DISP-002"))
        with self.assertRaises(InputError):
            self.tools.validate_outputs("DISP-002", self.advocate, expected_source_sha256="0"*64)
