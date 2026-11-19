"""python -m agent run --request <file> --id <request_id>
python -m agent serve [--host 127.0.0.1] [--port 8000]   the web platform"""
from __future__ import annotations

import argparse

from agent.intake.request_parser import read_request
from agent.services import store
from agent.services.audit import process
from agent.services.pack import build_pack


def run(request_path: str, request_id: str) -> None:
    request = read_request(request_path, request_id)
    run_id = store.start_run(request)
    print(f"run {run_id}")
    process(run_id, request)
    print(f"pack written to {build_pack(run_id)}")
    print(f"score it: python -m eval.score --run {run_id} --gap-key eval/gap_keys/<key>.csv")


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m agent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="process one audit request")
    r.add_argument("--request", required=True)
    r.add_argument("--id", required=True, dest="request_id")
    s = sub.add_parser("serve", help="start the web platform")
    s.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to let coworkers on your network connect")
    s.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    if args.cmd == "run":
        run(args.request, args.request_id)
    else:
        import uvicorn

        uvicorn.run("agent.web.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
