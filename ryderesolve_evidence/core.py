from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


class InputError(ValueError):
    """Invalid input, an unresolved reference, or a stale source snapshot."""


def read_json(path: Path) -> Any:
    def reject(value: str) -> None:
        raise InputError(f"Non-finite JSON number: {value}")
    return json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=reject)


def source_hash(raw: dict) -> str:
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def pointer(raw: Any, ref: str) -> Any:
    """Resolve an absolute JSON Pointer. Array indices are zero-based."""
    if ref == "":
        return copy.deepcopy(raw)
    if not isinstance(ref, str) or not ref.startswith("/"):
        raise InputError("A source reference must be an absolute JSON Pointer")
    current = raw
    try:
        for token in ref[1:].split("/"):
            # Reject invalid escapes rather than silently changing the reference.
            i = 0
            while i < len(token):
                if token[i] == "~":
                    if i + 1 >= len(token) or token[i + 1] not in "01":
                        raise InputError(f"Invalid escape in source reference: {ref}")
                    i += 1
                i += 1
            key = token.replace("~1", "/").replace("~0", "~")
            if isinstance(current, list):
                if not key.isascii() or not key.isdigit() or (len(key) > 1 and key.startswith("0")):
                    raise InputError(f"Invalid array index: {ref}")
                current = current[int(key)]
            elif isinstance(current, dict):
                current = current[key]
            else:
                raise InputError(f"Source reference enters a scalar: {ref}")
    except (KeyError, IndexError, TypeError) as exc:
        raise InputError(f"Unresolved source reference: {ref}") from exc
    return copy.deepcopy(current)


def timestamp(value: Any, ref: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise InputError(f"Invalid timestamp at {ref}") from exc
    if result.utcoffset() is None:
        raise InputError(f"Timestamp needs an explicit timezone at {ref}")
    return result


def number(value: Any, ref: str, low: float | None = None, high: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InputError(f"Expected a finite number at {ref}")
    if (low is not None and value < low) or (high is not None and value > high):
        raise InputError(f"Number outside permitted range at {ref}")
    return value


def validate_raw(raw: dict) -> None:
    if not isinstance(raw, dict):
        raise InputError("Case must be a JSON object")
    for key in ("dispute_ticket", "trip_data"):
        if not isinstance(raw.get(key), dict):
            raise InputError(f"Missing object: {key}")
    ticket, trip = raw["dispute_ticket"], raw["trip_data"]
    if not isinstance(ticket.get("dispute_id"), str) or not ticket["dispute_id"]:
        raise InputError("Missing dispute_id")
    if ticket.get("dispute_type") not in ("no_show_charge", "route_deviation"):
        raise InputError("Unsupported dispute_type")
    if not trip.get("trip_id") or ticket.get("trip_id") != trip["trip_id"]:
        raise InputError("Ticket and trip identifiers do not match")
    for name in ("rider", "driver"):
        profile = raw.get(f"{name}_profile")
        if profile is not None:
            if not isinstance(profile, dict) or profile.get(f"{name}_id") != trip.get(f"{name}_id"):
                raise InputError(f"{name} profile belongs to a different trip participant")
    for field in ("scheduled_time", "driver_arrival_time", "driver_wait_start", "cancellation_time", "trip_start_time", "trip_end_time"):
        if field in trip:
            timestamp(trip[field], f"/trip_data/{field}")
    for field in ("cancellation_fee",):
        if field in trip:
            number(trip[field], f"/trip_data/{field}", 0)
    for key in ("gps_telemetry", "reference_route", "chat_logs", "app_events"):
        items = raw.get(key, [])
        if not isinstance(items, list):
            raise InputError(f"{key} must be an array")
        previous = None
        for i, item in enumerate(items):
            ref = f"/{key}/{i}"
            if not isinstance(item, dict):
                raise InputError(f"Expected object at {ref}")
            if key in ("gps_telemetry", "reference_route"):
                number(item.get("lat"), ref + "/lat", -90, 90)
                number(item.get("lng"), ref + "/lng", -180, 180)
            if key != "reference_route" or "timestamp" in item:
                current = timestamp(item.get("timestamp"), ref + "/timestamp")
                if previous is not None and current < previous:
                    raise InputError(f"Records are not chronologically ordered at {ref}")
                previous = current
            if "speed_kmh" in item:
                number(item["speed_kmh"], ref + "/speed_kmh", 0)
    pickup = trip.get("pickup_location")
    if pickup is not None:
        if not isinstance(pickup, dict):
            raise InputError("pickup_location must be an object")
        number(pickup.get("lat"), "/trip_data/pickup_location/lat", -90, 90)
        number(pickup.get("lng"), "/trip_data/pickup_location/lng", -180, 180)
    for policy_name in ("cancellation_policy", "route_policy"):
        if policy_name in raw and not isinstance(raw[policy_name], dict):
            raise InputError(f"{policy_name} must be an object")
    for key in ("free_wait_time_min", "no_show_threshold_min", "cancellation_fee_after_wait"):
        if key in raw.get("cancellation_policy", {}):
            number(raw["cancellation_policy"][key], f"/cancellation_policy/{key}", 0)


def haversine_m(a: dict, b: dict) -> float:
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat, dlon = lat2 - lat1, math.radians(b["lng"] - a["lng"])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1, max(0, h))))


def route_metrics(raw: dict) -> dict:
    actual, reference = raw.get("gps_telemetry", []), raw.get("reference_route", [])
    if len(actual) < 2 or len(reference) < 2:
        raise InputError("Route comparison needs at least two actual and reference coordinates")
    actual_m = sum(haversine_m(a, b) for a, b in zip(actual, actual[1:]))
    reference_m = sum(haversine_m(a, b) for a, b in zip(reference, reference[1:]))
    if reference_m <= 0:
        raise InputError("Reference route has zero length")
    # Ratios use unrounded distances. These are sampled polylines, not road-network distances.
    return {
        "actual_sampled_length_m": round(actual_m, 3),
        "reference_sampled_length_m": round(reference_m, 3),
        "sampled_excess_m": round(actual_m - reference_m, 3),
        "sampled_excess_ratio": round((actual_m - reference_m) / reference_m, 6),
        "start_offset_m": round(haversine_m(actual[0], reference[0]), 3),
        "end_offset_m": round(haversine_m(actual[-1], reference[-1]), 3),
        "method": "sum_of_haversine_segments; Earth radius 6371008.8 m",
        "limitation": "Sampled polyline lengths, not a map-provider optimal route or proof of driver fault.",
        "source_refs": ["/gps_telemetry", "/reference_route"],
    }


@dataclass
class EvidenceBundle:
    pack: dict
    evidence_index: dict
    policy_index: dict
    audit: dict
    raw: dict


def build_bundle(raw: dict, metadata: dict | None = None) -> EvidenceBundle:
    raw = copy.deepcopy(raw)
    validate_raw(raw)
    metadata = copy.deepcopy(metadata or {"data_origin": "unverified_input", "policy_origin": "unverified_input"})
    case_id = raw["dispute_ticket"]["dispute_id"]
    dispute_type = raw["dispute_ticket"]["dispute_type"]
    digest = source_hash(raw)
    pack = {"case_id": case_id, "dispute_type": dispute_type, "facts": [], "policy": []}
    evidence_index, policy_index, issues, metrics = {}, {}, [], {}

    def add(fact: str, source: str, refs: list[str], kind: str = "record") -> str:
        eid = f"E-{len(pack['facts']) + 1:03d}"
        for ref in refs:
            pointer(raw, ref)
        pack["facts"].append({"evidence_id": eid, "fact": fact, "source": source})
        evidence_index[eid] = {"kind": kind, "source_refs": refs}
        return eid

    def issue(code: str, message: str, refs: list[str], severity: str = "review") -> None:
        issues.append({"code": code, "severity": severity, "message": message, "source_refs": refs})

    trip = raw["trip_data"]
    gps = raw.get("gps_telemetry", [])
    pickup = trip.get("pickup_location", {})
    stationary = [(i, g) for i, g in enumerate(gps) if pickup and g["lat"] == pickup["lat"] and g["lng"] == pickup["lng"] and g.get("speed_kmh") == 0]
    if stationary:
        times = ", ".join(g["timestamp"] for _, g in stationary)
        add(f"{len(stationary)} GPS samples ({times}) match the recorded pickup coordinates and report speed 0 km/h. Samples do not establish uninterrupted observation between timestamps.", "gps_telemetry", [f"/gps_telemetry/{i}" for i, _ in stationary] + ["/trip_data/pickup_location"], "derived_observation")
    else:
        add(f"The supplied GPS collection contains {len(gps)} samples; no sample establishes both an exact pickup-coordinate match and speed 0 km/h.", "gps_telemetry", ["/gps_telemetry"] if "gps_telemetry" in raw else ["/trip_data"], "data_availability")
    ticket = raw["dispute_ticket"]
    if "description" in ticket:
        add(f"{ticket.get('filed_by', 'Unspecified party')}'s statement (not independently verified): {ticket['description']}", "dispute_ticket.description", ["/dispute_ticket/description"], "party_statement")
    for field in ("scheduled_time", "driver_arrival_time", "driver_wait_start", "cancellation_time", "trip_start_time", "trip_end_time", "cancellation_reason", "cancellation_fee"):
        if field in trip:
            add(f"Trip record {field}: {trip[field]}.", "trip_data", [f"/trip_data/{field}"])
    for i, item in enumerate(gps):
        add(f"GPS record at {item['timestamp']}: lat={item['lat']}, lng={item['lng']}, speed_kmh={item.get('speed_kmh', 'not supplied')}, status={item.get('status', 'not supplied')}.", "gps_telemetry", [f"/gps_telemetry/{i}"])
    for i, item in enumerate(raw.get("chat_logs", [])):
        add(f"Communication log at {item['timestamp']}, sender={item.get('sender', 'unspecified')}, type={item.get('type', 'unspecified')}: {item.get('content', '')}", "chat_logs", [f"/chat_logs/{i}"], "communication_record")
    for i, item in enumerate(raw.get("app_events", [])):
        add(f"App event at {item['timestamp']}, type={item.get('event_type', 'unspecified')}, reports: {item.get('details', '')}", "app_events", [f"/app_events/{i}"], "event_record")
    for role in ("rider", "driver"):
        key = f"{role}_profile"
        if key in raw:
            context = {k: v for k, v in raw[key].items() if k not in ("name", "vehicle", "payment_method")}
            add(f"Historical {role} profile metadata: {json.dumps(context, ensure_ascii=False, sort_keys=True)}. Historical metadata alone does not establish responsibility for this dispute.", key, [f"/{key}"], "historical_context")
    for key in ("reference_route", "fare_breakdown", "dataset_metadata"):
        if key in raw:
            add(f"Provided {key}: {json.dumps(raw[key], ensure_ascii=False, sort_keys=True)}", key, [f"/{key}"], "provenance" if key == "dataset_metadata" else "record")
    policy_name = "cancellation_policy" if dispute_type == "no_show_charge" else "route_policy"
    policy = raw.get(policy_name, {})
    for key in sorted(policy):
        pid = f"P-{len(pack['policy']) + 1:03d}"
        escaped = key.replace("~", "~0").replace("/", "~1")
        ref = f"/{policy_name}/{escaped}"
        pack["policy"].append({"policy_id": pid, "rule": f"{key} = {json.dumps(policy[key], ensure_ascii=False, sort_keys=True)}", "source": policy_name})
        policy_index[pid] = {"source_refs": [ref], "policy_origin": metadata.get("policy_origin", "unverified_input")}
    if not policy:
        issue("MISSING_POLICY", "No applicable policy object was supplied.", [])
    if not gps:
        issue("MISSING_GPS", "No GPS evidence was supplied; absence is not proof of absence at pickup.", [])
    if not raw.get("chat_logs"):
        issue("MISSING_COMMUNICATION_LOGS", "No communication logs were supplied; do not infer that no contact occurred.", [])
    if dispute_type == "no_show_charge":
        end = trip.get("cancellation_time")
        starts = [("trip_wait", trip.get("driver_wait_start"), "/trip_data/driver_wait_start")]
        app_starts = [(i, e) for i, e in enumerate(raw.get("app_events", [])) if e.get("event_type") == "wait_timer_started"]
        for i, event in app_starts:
            starts.append((f"app_wait_{i}", event["timestamp"], f"/app_events/{i}/timestamp"))
        if len(app_starts) > 1:
            issue("MULTIPLE_WAIT_START_EVENTS", "Multiple app timer starts were supplied; no event was silently selected.", [f"/app_events/{i}" for i, _ in app_starts])
        if not end or not trip.get("driver_wait_start") or not app_starts:
            issue("INCOMPLETE_WAIT_TIMING", "At least one cancellation/order/app wait timestamp is missing.", ["/trip_data"])
        for key, start, ref in starts:
            if start and end:
                elapsed = (timestamp(end, "/trip_data/cancellation_time") - timestamp(start, ref)).total_seconds()
                if elapsed < 0:
                    raise InputError("Wait starts after cancellation")
                metrics[key] = {"seconds": elapsed, "source_refs": [ref, "/trip_data/cancellation_time"], "method": "timezone-aware timestamp subtraction"}
                add(f"Computed elapsed time from {ref} to the recorded cancellation is {elapsed:g} seconds. This calculation does not determine the applicable policy clock.", "derived.wait_duration", metrics[key]["source_refs"], "derived_metric")
        if len({m["seconds"] for m in metrics.values()}) > 1:
            issue("WAIT_START_DISAGREEMENT", "Order and app timer start records produce different elapsed times. Preserve both calculations.", [ref for _, start, ref in starts if start])
        if "wait_clock_basis" not in policy:
            issue("POLICY_CLOCK_BASIS_UNSPECIFIED", "The policy does not specify which recorded event starts the no-show clock. Do not silently choose a basis.", [f"/{policy_name}"] if policy_name in raw else [])
        for key in ("free_wait_time_min", "no_show_threshold_min", "cancellation_fee_after_wait"):
            if key not in policy:
                issue("INCOMPLETE_NO_SHOW_POLICY", f"Policy field {key} is not supplied.", [f"/{policy_name}"] if policy_name in raw else [])
    else:
        if metadata.get("data_origin") == "synthetic":
            issue("SYNTHETIC_SCENARIO", "Team-authored synthetic case and policy, not official Ryde trip records or rules.", ["/dataset_metadata"] if "dataset_metadata" in raw else [], "info")
        try:
            comparison = route_metrics(raw)
            metrics["route_comparison"] = comparison
            add(f"Sampled actual polyline length is {comparison['actual_sampled_length_m']} m; provided reference is {comparison['reference_sampled_length_m']} m; excess ratio is {comparison['sampled_excess_ratio']}. Neither distance alone nor this reference establishes an unauthorized detour.", "derived.route_comparison", comparison["source_refs"], "derived_metric")
            if comparison["start_offset_m"] > 1 or comparison["end_offset_m"] > 1:
                issue("ROUTE_ENDPOINT_MISMATCH", "Actual and reference routes do not share endpoints within 1 m; comparison is not like-for-like. This is a data check, not a Ryde policy threshold.", comparison["source_refs"])
        except InputError as exc:
            issue("ROUTE_COMPARISON_UNAVAILABLE", str(exc), [])
        fare = raw.get("fare_breakdown", {})
        if isinstance(fare, dict) and all(k in fare for k in ("charged_total_cents", "reference_quote_cents", "currency")):
            for key in ("charged_total_cents", "reference_quote_cents"):
                if type(fare[key]) is not int or fare[key] < 0:
                    raise InputError(f"{key} must be a non-negative integer in minor currency units")
            metrics["fare_difference"] = {"currency": fare["currency"], "difference_cents": fare["charged_total_cents"] - fare["reference_quote_cents"], "source_refs": ["/fare_breakdown/charged_total_cents", "/fare_breakdown/reference_quote_cents"], "limitation": "Arithmetic difference, not an awarded refund."}
        else:
            issue("INCOMPLETE_FARE_COMPARISON", "Charged and reference fares with a currency were not both supplied.", [])
    audit = {"case_id": case_id, "source_sha256": digest, "data_origin": metadata.get("data_origin", "unverified_input"), "policy_origin": metadata.get("policy_origin", "unverified_input"), "source_url": metadata.get("source_url"), "issues": issues, "requires_policy_or_data_review": any(i["severity"] == "review" for i in issues), "metrics": metrics, "notes": ["This report does not decide the dispute or supply model confidence.", "Party statements and app-event conclusions are attributed records, not automatically established facts.", "Evidence IDs are scoped to case_id and source_sha256; do not reuse references after a source update."]}
    return EvidenceBundle(pack, evidence_index, policy_index, audit, raw)


def normalize_evidence(raw: dict) -> dict:
    """Public pipeline step: raw JSON in, the agreed Evidence Pack dictionary out."""
    return build_bundle(raw).pack


class CaseRepository:
    def __init__(self, data_dir: str | Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).parent / "data"
        manifest = read_json(self.data_dir / "catalog.json")
        entries = manifest["cases"]
        self._entries = {entry["case_id"]: entry for entry in entries}
        if len(self._entries) != len(entries):
            raise InputError("Duplicate case IDs in catalog")

    def list_cases(self) -> list[dict]:
        return [{k: v for k, v in entry.items() if k != "path"} for entry in self._entries.values()]

    def _entry(self, case_id: str) -> dict:
        if not isinstance(case_id, str) or case_id not in self._entries:
            raise InputError(f"Unknown case_id: {case_id}")
        return self._entries[case_id]

    def load_case(self, case_id: str) -> dict:
        entry = self._entry(case_id)
        path = (self.data_dir / entry["path"]).resolve()
        if not path.is_relative_to(self.data_dir.resolve()):
            raise InputError("Catalog path escapes the data directory")
        raw = read_json(path)
        validate_raw(raw)
        if raw["dispute_ticket"]["dispute_id"] != case_id or raw["dispute_ticket"]["dispute_type"] != entry["dispute_type"]:
            raise InputError("Catalog identity differs from raw case")
        if entry["data_origin"] == "synthetic" and raw.get("dataset_metadata", {}).get("data_origin") != "synthetic":
            raise InputError("Synthetic case must label its origin inside the raw data")
        return raw

    def bundle(self, case_id: str) -> EvidenceBundle:
        return build_bundle(self.load_case(case_id), self._entry(case_id))
