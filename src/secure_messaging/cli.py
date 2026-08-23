from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .artifacts import ArtifactReference
from .envelope import Envelope
from .helper import handle_stdio_request

_MAX_STDIO_REQUEST = 128 * 1024


def _run_stdio_once() -> int:
    line = sys.stdin.readline(_MAX_STDIO_REQUEST + 1)
    if not line or len(line.encode("utf-8")) > _MAX_STDIO_REQUEST:
        response = {"request_id": "", "accepted": False, "message_id": None, "error_code": "invalid_request"}
        print(json.dumps(response, separators=(",", ":")))
        return 2
    try:
        request = json.loads(line)
        if not isinstance(request, dict):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        response = {"request_id": "", "accepted": False, "message_id": None, "error_code": "invalid_request"}
        print(json.dumps(response, separators=(",", ":")))
        return 2

    response = asyncio.run(handle_stdio_request(request))
    print(json.dumps(response, separators=(",", ":"), sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="secure-messaging")
    parser.add_argument("--stdio-once", action="store_true", help="process one newline-delimited JSON request")
    sub = parser.add_subparsers(dest="command")

    validate = sub.add_parser("validate-envelope", help="validate a JSON envelope")
    validate.add_argument("path")

    artifact = sub.add_parser("hash-artifact", help="emit a generic artifact reference")
    artifact.add_argument("path")
    artifact.add_argument("--media-type")

    args = parser.parse_args()
    if args.stdio_once:
        return _run_stdio_once()
    if args.command == "validate-envelope":
        data = json.loads(Path(args.path).read_text(encoding="utf-8"))
        env = Envelope.from_dict(data)
        print(json.dumps(env.to_dict(), indent=2, sort_keys=True))
        return 0
    if args.command == "hash-artifact":
        ref = ArtifactReference.from_file(args.path, media_type=args.media_type)
        print(json.dumps(ref.to_dict(), indent=2, sort_keys=True))
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
