"""python -m agent run --request <file> --id <request_id>"""
from __future__ import annotations

import argparse

from agent import store
from agent.checks import REGISTRY
from agent.pack.writer import build_pack
from agent.parser.request_parser import extract_sample_accounts, parse_checks, read_request


def run(request_path: str, request_id: str) -> None:
    request = read_request(request_path, request_id)
    checks, scale = parse_checks(request)
    request.severity_scale = scale
    run_id = store.start_run(request)
    print(f"run {run_id}")
    try:
        accounts = extract_sample_accounts(request.text)
        samples = {c.check_id: accounts for c in checks}  # every check shares the request's sample
        store.save_checks(run_id, checks, samples)
        for spec in checks:
            check_cls = REGISTRY.get(spec.check_type)
            if check_cls is None:
                print(f"  {spec.check_id}: no test for check type '{spec.check_type.value}'; reported as not tested")
                continue
            findings = check_cls(spec, scale).run(samples.get(spec.check_id, []))
            store.save_findings(run_id, findings)
            n = {s: sum(f.status.value == s for f in findings) for s in ("evidenced", "gap", "cannot_determine")}
            print(f"  {spec.check_id} {spec.check_type.value}: {len(accounts)} accounts, {n}")
        store.finish_run(run_id, "completed")
    except Exception as exc:
        store.finish_run(run_id, "failed", notes=repr(exc))
        raise
    print(f"pack written to {build_pack(run_id)}")
    print(f"score it: python -m eval.score --run {run_id} --gap-key eval/gap_keys/<key>.csv")


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m agent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="process one audit request")
    r.add_argument("--request", required=True)
    r.add_argument("--id", required=True, dest="request_id")
    args = ap.parse_args()
    if args.cmd == "run":
        run(args.request, args.request_id)


if __name__ == "__main__":
    main()
