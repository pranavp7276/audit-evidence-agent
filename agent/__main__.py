"""python -m agent run --request <file> --id <request_id>"""
from __future__ import annotations

import argparse

from agent import store
from agent.checks import REGISTRY
from agent.parser.request_parser import parse_checks, read_request


def run(request_path: str, request_id: str) -> None:
    request = read_request(request_path, request_id)
    checks, scale = parse_checks(request)
    request.severity_scale = scale
    run_id = store.start_run(request)
    print(f"run {run_id}")
    try:
        samples: dict[str, list[str]] = {}  # TODO(owner): resolve each check's sample to account ids
        store.save_checks(run_id, checks, samples)
        for spec in checks:
            check_cls = REGISTRY.get(spec.check_type)
            if check_cls is None:
                continue  # OTHER: reported in the letter as not tested
            findings = check_cls(spec, scale).run(samples.get(spec.check_id, []))
            store.save_findings(run_id, findings)
        store.finish_run(run_id, "completed")
    except Exception as exc:
        store.finish_run(run_id, "failed", notes=repr(exc))
        raise


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
