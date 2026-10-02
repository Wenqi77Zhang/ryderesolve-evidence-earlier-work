import argparse
import json
import sys
from pathlib import Path

from .core import InputError, read_json
from .tools import EvidenceTools


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Traceable Ryde evidence tools (no adjudication)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    for name in ("pack", "audit", "raw", "route"):
        sub.add_parser(name).add_argument("case_id")
    for name in ("evidence", "policy"):
        child = sub.add_parser(name)
        child.add_argument("case_id")
        child.add_argument("reference_id")
        child.add_argument("--source-sha256")
    validate = sub.add_parser("validate")
    validate.add_argument("case_id")
    validate.add_argument("--advocate", type=Path)
    validate.add_argument("--judge", type=Path)
    validate.add_argument("--source-sha256")
    server = sub.add_parser("serve")
    server.add_argument("--port", type=int, default=8765)
    export = sub.add_parser("export")
    export.add_argument("case_id")
    export.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    tools = EvidenceTools()
    try:
        if args.command == "serve":
            from .server import serve
            return serve(args.port)
        if args.command == "list":
            result = tools.list_cases()
        elif args.command in ("pack", "audit", "raw", "route"):
            result = {"pack": tools.normalize_evidence, "audit": tools.audit_case, "raw": tools.load_case, "route": tools.compare_route}[args.command](args.case_id)
        elif args.command in ("evidence", "policy"):
            method = tools.get_evidence if args.command == "evidence" else tools.get_policy
            result = method(args.case_id, args.reference_id, args.source_sha256)
        elif args.command == "validate":
            result = tools.validate_outputs(args.case_id, read_json(args.advocate) if args.advocate else None, read_json(args.judge) if args.judge else None, args.source_sha256)
        else:
            bundle = tools.repository.bundle(args.case_id)
            args.out.mkdir(parents=True, exist_ok=True)
            files = {"evidence_pack": bundle.pack, "audit": bundle.audit, "source_index": {"case_id": args.case_id, "source_sha256": bundle.audit["source_sha256"], "evidence": bundle.evidence_index, "policy": bundle.policy_index}}
            written = []
            for suffix, value in files.items():
                path = args.out / f"{args.case_id}.{suffix}.json"
                path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
                written.append(str(path))
            result = {"written": written}
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        if args.command == "validate" and not result["structurally_valid"]:
            return 1
        return 0
    except (InputError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
