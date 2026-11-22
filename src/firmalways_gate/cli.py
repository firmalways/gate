"""Command line: ``firmalways-gate scan | serve | echo-upstream | benchmark``."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys

from . import __version__
from .audit import AuditLog
from .engine import Gate
from .policy import Policy, PolicyError, load_policy


def _policy(path: str | None) -> Policy:
    return load_policy(path) if path else Policy()


def _cmd_scan(args: argparse.Namespace) -> int:
    text = args.text if args.text is not None else sys.stdin.read()
    result = Gate(_policy(args.policy)).preview(text)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["masked_text"])
        print("---", file=sys.stderr)
        if not result["entities"]:
            print("No personal data found.", file=sys.stderr)
        for item in result["entities"]:
            target = item.get("placeholder", "")
            print(f"{item['type']:<17} {item['action']:<5} score={item['score']:.2f} {target}", file=sys.stderr)
        if result["blocked_types"]:
            print("BLOCKED: " + ", ".join(result["blocked_types"]), file=sys.stderr)
    return 1 if result["blocked_types"] else 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from .server import CLIENT_KEY_ENV, create_server

    policy = _policy(args.policy)
    client_key = os.environ.get(CLIENT_KEY_ENV)
    audit = AuditLog.from_env(args.audit if args.audit is not None else policy.audit_path)
    server = create_server(policy, args.host, args.port, audit=audit, client_api_key=client_key, verbose=args.verbose)
    err = sys.stderr
    print(f"FirmAlways Gate {__version__} listening on {server.url}/v1", file=err)
    if not policy.upstreams:
        print("WARNING: no [[upstreams]] in policy; every chat request will be refused (403).", file=err)
    for upstream in policy.upstreams:
        key_note = ""
        if upstream.api_key_env and not upstream.api_key():
            key_note = f"  (WARNING: environment variable {upstream.api_key_env} is not set)"
        print(f"  upstream {upstream.name}: {upstream.base_url} models={list(upstream.models)}{key_note}", file=err)
    print(f"  audit: {audit.path or 'disabled'}", file=err)
    try:
        loopback = ipaddress.ip_address(args.host).is_loopback
    except ValueError:
        loopback = args.host == "localhost"
    for client in policy.clients:
        state = "" if client.api_key() else f"  (WARNING: environment variable {client.api_key_env} is not set)"
        print(f"  client {client.name}: key from {client.api_key_env}{state}", file=err)
    if not client_key and not policy.clients and not loopback:
        print(f"WARNING: listening on {args.host} without {CLIENT_KEY_ENV}; anyone on the network can use it.", file=err)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _cmd_echo(args: argparse.Namespace) -> int:
    from .echo_upstream import EchoUpstreamServer

    server = EchoUpstreamServer((args.host, args.port), verbose=True)
    print(f"Echo upstream (fake AI) on {server.base_url} — model name: echo", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _cmd_benchmark(args: argparse.Namespace) -> int:
    from .benchmark import format_report, run

    report = run(seed=args.seed, repeats=args.repeats, dataset=args.dataset, thai_ner=args.thai_ner)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else format_report(report))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="firmalways-gate", description="Thai PDPA AI privacy gateway")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="show what an AI would receive for a text (reads stdin if no text)")
    scan.add_argument("text", nargs="?")
    scan.add_argument("--policy")
    scan.add_argument("--json", action="store_true")
    scan.set_defaults(func=_cmd_scan)

    serve = sub.add_parser("serve", help="run the OpenAI-compatible proxy")
    serve.add_argument("--policy")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument("--audit", help='audit log path ("-" for stdout); overrides the policy')
    serve.add_argument("--verbose", action="store_true")
    serve.set_defaults(func=_cmd_serve)

    echo = sub.add_parser("echo-upstream", help="run a fake AI that echoes what it receives")
    echo.add_argument("--host", default="127.0.0.1")
    echo.add_argument("--port", type=int, default=8788)
    echo.set_defaults(func=_cmd_echo)

    bench = sub.add_parser("benchmark", help="measure detection on the synthetic Thai dataset")
    bench.add_argument("--seed", type=int, default=7)
    bench.add_argument("--repeats", type=int, default=30)
    bench.add_argument("--dataset", choices=("synthetic", "curated"), default="synthetic")
    bench.add_argument("--thai-ner", action="store_true", help="also use the optional PyThaiNLP detector")
    bench.add_argument("--json", action="store_true")
    bench.set_defaults(func=_cmd_benchmark)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except PolicyError as exc:
        print(f"Policy error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
