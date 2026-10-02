from __future__ import annotations

import copy
import math

from .core import CaseRepository, InputError, pointer


TOOL_SPECS = [
    {"name": "list_cases", "description": "List allowed case IDs and official/synthetic provenance.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
]
for name, description, extra in [
    ("load_case", "Read the original case JSON only; never returns answer keys or editorial evidence summaries.", {}),
    ("normalize_evidence", "Get the agreed Evidence Pack: case_id, dispute_type, facts, policy.", {}),
    ("get_evidence", "Resolve a case-scoped evidence ID to its fact and original excerpts.", {"evidence_id": {"type": "string"}}),
    ("get_policy", "Resolve a case-scoped policy ID to its rule and original excerpts.", {"policy_id": {"type": "string"}}),
    ("audit_case", "Read source provenance, calculation methods, missing data and conflicts; not a verdict.", {}),
    ("compare_route", "Compare actual and provided reference sampled polylines; not navigation-optimal routes or a ruling.", {}),
]:
    properties = {"case_id": {"type": "string"}, **extra}
    required = list(properties)
    if name in ("get_evidence", "get_policy"):
        properties["expected_source_sha256"] = {"type": "string", "pattern": "^[a-f0-9]{64}$"}
    TOOL_SPECS.append({"name": name, "description": description, "parameters": {"type": "object", "properties": properties, "required": required, "additionalProperties": False}})
TOOL_SPECS.append({"name": "validate_outputs", "description": "Check case IDs, output structure and evidence/policy references. Does not grade correctness against an answer key.", "parameters": {"type": "object", "properties": {"case_id": {"type": "string"}, "advocate": {"type": "object"}, "judge": {"type": "object"}, "expected_source_sha256": {"type": "string"}}, "required": ["case_id"], "additionalProperties": False}})


def validate_agent_outputs(bundle, advocate: dict | None = None, judge: dict | None = None) -> dict:
    errors, warnings = [], []
    known_evidence, known_policy = bundle.evidence_index, bundle.policy_index

    def error(code, path, message):
        errors.append({"code": code, "path": path, "message": message})

    def refs(item, key, allowed, path):
        values = item.get(key)
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            error("INVALID_REFERENCE_LIST", path + "/" + key, "Expected an array of reference IDs")
            return
        if len(values) != len(set(values)):
            error("DUPLICATE_REFERENCE", path + "/" + key, "Reference IDs must not repeat")
        for value in values:
            if value not in allowed:
                error("UNKNOWN_REFERENCE", path + "/" + key, f"Unknown case-scoped reference: {value}")
        if not values:
            warnings.append({"code": "UNSUPPORTED_STATEMENT", "path": path + "/" + key, "message": "No support cited; do not treat this statement as established fact"})

    def items(value, array_key, text_key, allowed_policy=False):
        records = value.get(array_key)
        if not isinstance(records, list):
            error("INVALID_ITEMS", "/" + array_key, "Expected an array")
            return
        for i, item in enumerate(records):
            path = f"/{array_key}/{i}"
            if not isinstance(item, dict):
                error("INVALID_ITEM", path, "Expected an object")
                continue
            if not isinstance(item.get(text_key), str) or not item[text_key].strip():
                error("MISSING_TEXT", path + "/" + text_key, "Expected non-empty text")
            refs(item, "evidence_refs", known_evidence, path)
            if allowed_policy or "policy_refs" in item:
                refs(item, "policy_refs", known_policy, path)

    if advocate is None and judge is None:
        error("NO_OUTPUT", "/", "Provide at least one advocate or judge output")
    for label, value in (("advocate", advocate), ("judge", judge)):
        if value is None:
            continue
        if not isinstance(value, dict):
            error("INVALID_OUTPUT", label, "Expected a JSON object")
            continue
        if value.get("case_id") != bundle.pack["case_id"]:
            error("CASE_MISMATCH", label + "/case_id", "Output belongs to another case")
        if label == "advocate":
            if value.get("side") not in ("rider", "driver"):
                error("INVALID_SIDE", "/side", "Use rider or driver")
            items(value, "claims", "claim")
            if "counterpoints" in value:
                items(value, "counterpoints", "claim")
        else:
            if not isinstance(value.get("decision"), str) or not value["decision"].strip():
                error("MISSING_DECISION", "/decision", "Expected a non-empty decision string")
            # Names are locked; the team has not yet frozen the complete decision vocabulary.
            items(value, "findings", "finding", True)
            if not value.get("findings"):
                warnings.append({"code": "NO_FINDINGS", "path": "/findings", "message": "The decision has no findings to inspect"})
            if "confidence" in value:
                confidence = value["confidence"]
                if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                    error("INVALID_CONFIDENCE", "/confidence", "Expected a finite number between 0 and 1")
                elif confidence == 0 and value.get("escalate_to_human") is False:
                    warnings.append({"code": "ZERO_CONFIDENCE_WITHOUT_REVIEW", "path": "/confidence", "message": "A zero-confidence result marked no-review needs checking; confidence is not calibrated accuracy"})
            if "escalate_to_human" in value and type(value["escalate_to_human"]) is not bool:
                error("INVALID_REVIEW_FLAG", "/escalate_to_human", "Expected a boolean")
            if "refund_amount" in value and value["refund_amount"] is not None:
                amount = value["refund_amount"]
                if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
                    error("INVALID_AMOUNT", "/refund_amount", "Expected a non-negative finite amount or null")
    return {"case_id": bundle.pack["case_id"], "source_sha256": bundle.audit["source_sha256"], "structurally_valid": not errors, "errors": errors, "warnings": warnings, "requires_policy_or_data_review": bundle.audit["requires_policy_or_data_review"], "limitation": "Valid references do not prove that a claim follows from its sources or that a ruling is correct."}


class EvidenceTools:
    def __init__(self, repository: CaseRepository | None = None):
        self.repository = repository or CaseRepository()

    def list_cases(self):
        return self.repository.list_cases()

    def load_case(self, case_id):
        return self.repository.load_case(case_id)

    def normalize_evidence(self, case_id):
        return self.repository.bundle(case_id).pack

    def audit_case(self, case_id):
        return self.repository.bundle(case_id).audit

    def _resolve(self, case_id, ref_id, is_policy, expected_source_sha256):
        bundle = self.repository.bundle(case_id)
        if expected_source_sha256 is not None and expected_source_sha256 != bundle.audit["source_sha256"]:
            raise InputError("Source snapshot changed; re-normalize and do not reuse stale references")
        index = bundle.policy_index if is_policy else bundle.evidence_index
        if not isinstance(ref_id, str) or ref_id not in index:
            raise InputError(f"Unknown {'policy' if is_policy else 'evidence'} reference: {ref_id}")
        key = "policy_id" if is_policy else "evidence_id"
        record = next(item for item in bundle.pack["policy" if is_policy else "facts"] if item[key] == ref_id)
        meta = index[ref_id]
        return {"case_id": case_id, "source_sha256": bundle.audit["source_sha256"], **copy.deepcopy(record), **copy.deepcopy(meta), "excerpts": [{"source_ref": ref, "value": pointer(bundle.raw, ref)} for ref in meta["source_refs"]]}

    def get_evidence(self, case_id, evidence_id, expected_source_sha256=None):
        return self._resolve(case_id, evidence_id, False, expected_source_sha256)

    def get_policy(self, case_id, policy_id, expected_source_sha256=None):
        return self._resolve(case_id, policy_id, True, expected_source_sha256)

    def compare_route(self, case_id):
        bundle = self.repository.bundle(case_id)
        if bundle.pack["dispute_type"] != "route_deviation":
            raise InputError("compare_route requires a route_deviation case")
        result = bundle.audit["metrics"].get("route_comparison")
        if result is None:
            raise InputError("Route evidence is insufficient for comparison")
        return {"case_id": case_id, "source_sha256": bundle.audit["source_sha256"], "data_origin": bundle.audit["data_origin"], **copy.deepcopy(result)}

    def validate_outputs(self, case_id, advocate=None, judge=None, expected_source_sha256=None):
        bundle = self.repository.bundle(case_id)
        if expected_source_sha256 is not None and expected_source_sha256 != bundle.audit["source_sha256"]:
            raise InputError("Output references an outdated source snapshot")
        return validate_agent_outputs(bundle, advocate, judge)

    def call(self, name: str, arguments: dict):
        spec = next((item for item in TOOL_SPECS if item["name"] == name), None)
        if spec is None:
            raise InputError(f"Unknown tool: {name}")
        if not isinstance(arguments, dict):
            raise InputError("Tool arguments must be an object")
        schema = spec["parameters"]
        if any(key not in schema["properties"] for key in arguments):
            raise InputError("Unknown tool argument")
        if any(key not in arguments for key in schema.get("required", [])):
            raise InputError("Missing required tool argument")
        for key, value in arguments.items():
            if schema["properties"][key]["type"] == "string" and not isinstance(value, str):
                raise InputError(f"{key} must be a string")
            if schema["properties"][key]["type"] == "object" and not isinstance(value, dict):
                raise InputError(f"{key} must be an object")
        return getattr(self, name)(**arguments)
