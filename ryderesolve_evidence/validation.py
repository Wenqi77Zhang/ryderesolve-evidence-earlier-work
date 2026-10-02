"""Validate with the same published schemas that downstream consumers receive."""
from pathlib import Path

from jsonschema import Draft202012Validator

from .core import InputError, assert_json_value, read_json


VALIDATORS = {
    name: Draft202012Validator(read_json(Path(__file__).parent / "contracts" / f"{name}.schema.json"))
    for name in ("advocate", "judge")
}


def validate_agent_outputs(bundle, advocate=None, judge=None):
    errors, warnings = [], []

    def report(target, code, path, message):
        target.append({"code": code, "path": path, "message": message})

    def check_items(label, value, array_key):
        records = value.get(array_key)
        if not isinstance(records, list):
            return
        for i, item in enumerate(records):
            if not isinstance(item, dict):
                continue
            for key, known in (("evidence_refs", bundle.evidence_index), ("policy_refs", bundle.policy_index)):
                refs = item.get(key)
                if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
                    continue  # The published schema already reports this error.
                path = f"/{label}/{array_key}/{i}/{key}"
                for ref in refs:
                    if ref not in known:
                        report(errors, "UNKNOWN_REFERENCE", path, f"Unknown case-scoped reference: {ref}")
                if not refs:
                    report(warnings, "UNSUPPORTED_STATEMENT", path, "No support cited; do not treat this statement as established fact")
                elif key == "evidence_refs" and all(known.get(ref, {}).get("kind") == "historical_context" for ref in refs):
                    report(warnings, "ONLY_HISTORICAL_CONTEXT_CITED", path, "Historical profiles alone do not establish what happened in this dispute")

    if advocate is None and judge is None:
        report(errors, "NO_OUTPUT", "/", "Provide at least one advocate or judge output")
    for label, value in (("advocate", advocate), ("judge", judge)):
        if value is None:
            continue
        try:
            assert_json_value(value)
        except InputError as exc:
            report(errors, "INVALID_JSON_VALUE", f"/{label}", str(exc))
            continue
        for problem in VALIDATORS[label].iter_errors(value):
            segments = [str(segment).replace("~", "~0").replace("/", "~1") for segment in problem.absolute_path]
            report(errors, "SCHEMA_VIOLATION", "/" + "/".join([label, *segments]), problem.message)
        if not isinstance(value, dict):
            continue
        if value.get("case_id") != bundle.pack["case_id"]:
            report(errors, "CASE_MISMATCH", f"/{label}/case_id", "Output belongs to another case")
        if label == "advocate":
            check_items(label, value, "claims")
            check_items(label, value, "counterpoints")
        else:
            check_items(label, value, "findings")
            if value.get("findings") == []:
                report(warnings, "NO_FINDINGS", "/judge/findings", "The decision has no findings to inspect")
            if type(value.get("confidence")) in (int, float) and value["confidence"] == 0 and value.get("escalate_to_human") is False:
                report(warnings, "ZERO_CONFIDENCE_WITHOUT_REVIEW", "/judge/confidence", "A zero-confidence result marked no-review needs checking; confidence is not calibrated accuracy")
            if bundle.audit["requires_policy_or_data_review"] and value.get("escalate_to_human") is False:
                report(warnings, "UNRESOLVED_REVIEW_FLAGS", "/judge/escalate_to_human", "The case has unresolved data/policy review flags; a no-review decision needs explicit justification")
    return {
        "case_id": bundle.pack["case_id"],
        "source_sha256": bundle.audit["source_sha256"],
        "normalizer_version": bundle.audit["normalizer_version"],
        "snapshot_id": bundle.audit["snapshot_id"],
        "structurally_valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "requires_policy_or_data_review": bundle.audit["requires_policy_or_data_review"],
        "review_issue_codes": [issue["code"] for issue in bundle.audit["issues"] if issue["severity"] == "review"],
        "limitation": "Valid references do not prove that a claim follows from its sources or that a ruling is correct.",
    }
