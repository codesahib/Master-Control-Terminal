#!/usr/bin/env python3
"""Smoke-test every Master Terminal API endpoint.

Read-only by default: every GET with valid and invalid params, plus invalid-body
probes for write endpoints (expect 4xx, never 5xx). With --disposable it also runs
create/read/update/delete cycles and an export -> import-backup round trip.
ONLY pass --disposable against a throwaway database.

  python3 scripts/audit/smoke_endpoints.py --api http://127.0.0.1:18005 [--token T] [--disposable] [--skip-network]

Exit code 1 on any 5xx or unexpected status. Stdlib only.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import date

RESULTS = []
WARNINGS = []


class Api:
    def __init__(self, base, token):
        self.base = base.rstrip("/")
        self.headers = {"X-Requested-With": "master-terminal", "X-API-Token": token or ""}

    def call(self, method, path, params=None, body=None, files=None, expect=(200,), timeout=60, label=None):
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = dict(self.headers)
        data = None
        if files:
            boundary = uuid.uuid4().hex
            name, filename, content = files
            data = (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
                f"Content-Type: application/octet-stream\r\n\r\n"
            ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read()
        except Exception as exc:  # connection refused, timeout
            status, raw = 0, str(exc).encode()
        ms = (time.perf_counter() - started) * 1000
        ok = status in expect
        shown = label or (path + ("?" + urllib.parse.urlencode(params) if params else ""))
        RESULTS.append({"method": method, "path": shown, "status": status, "expect": list(expect), "ms": round(ms), "ok": ok,
                        "detail": "" if ok else raw[:200].decode(errors="replace")})
        try:
            payload = json.loads(raw) if raw else None
        except ValueError:
            payload = None
        return status, payload


def sample_value(name, schema, ctx):
    schema = schema or {}
    options = schema.get("anyOf") or [schema]
    for option in options:
        if "$ref" in option:
            return ctx["enums"].get(option["$ref"].rsplit("/", 1)[-1], [None])[0]
        if option.get("enum"):
            return option["enum"][0]
    pattern = schema.get("pattern", "")
    if pattern.startswith("^(") and pattern.endswith(")$"):
        return pattern[2:-2].split("|")[0]
    known = {"q": "VFV", "account": "RRSP", "platform": ctx["platform"], "symbol": "VFV", "status": "ok",
             "currency": "CAD", "year": date.today().year, "page": 1, "page_size": 25, "limit": 5, "days": 30,
             "tax_year": str(date.today().year)}
    return known.get(name)


def run_gets(api, spec, ctx):
    for path, ops in spec["paths"].items():
        op = ops.get("get")
        if not op:
            continue
        params = op.get("parameters", [])
        path_values = {p["name"]: sample_value(p["name"], p.get("schema"), ctx) for p in params if p["in"] == "path"}
        concrete = path.format(**path_values)
        required = {p["name"]: sample_value(p["name"], p.get("schema"), ctx) for p in params if p["in"] == "query" and p.get("required")}
        optional = {p["name"]: sample_value(p["name"], p.get("schema"), ctx) for p in params if p["in"] == "query" and not p.get("required")}
        optional = {k: v for k, v in optional.items() if v is not None and k != "exclude_transaction_id"}
        if "symbols/search" in path and ctx["skip_network"]:
            continue
        api.call("GET", concrete, required or None)
        if optional:
            api.call("GET", concrete, {**required, **optional})
        for p in params:  # every enum/pattern alternative once
            schema = p.get("schema") or {}
            pattern = schema.get("pattern", "")
            values = schema.get("enum") or (pattern[2:-2].split("|") if pattern.startswith("^(") else [])
            for value in values[1:]:
                api.call("GET", concrete, {**required, p["name"]: value})


def run_bad_params(api, spec, ctx):
    paths = spec["paths"]
    probes = [
        ("/transactions", {"page": 0}), ("/transactions", {"year": "abc"}), ("/transactions", {"sort_direction": "sideways"}),
        ("/transactions", {"transaction_type": "bogus"}), ("/account-transactions", {"page": 0}),
        ("/analytics/distribution", {"group_by": "bogus"}), ("/analytics/distribution", None),
        ("/analytics/distribution", {"group_by": "sector", "currency": "cad"}), ("/portfolio/pl", {"page_size": 0}),
        ("/available-contributions", None), ("/symbols/search", {"q": ""}), ("/limits/abcd", None),
        ("/portfolio/pl", {"sort_by": "bogus"}), ("/transactions", {"page_size": 0}), ("/portfolio/history", {"days": -1}),
    ]
    for path, params in probes:
        base = path if path in paths else ("/limits/{year}" if path.startswith("/limits/") else None)
        if not base:
            continue
        if params and any(k not in [p["name"] for p in paths[base]["get"].get("parameters", [])] for k in params):
            continue  # parameter not supported by this API version
        api.call("GET", path, params, expect=(400, 404, 422))


def run_invalid_writes(api, spec):
    """Reachability probes for write endpoints that must not mutate data: invalid bodies -> 4xx."""
    paths = spec["paths"]
    for path, ops in paths.items():
        for method in ("post", "put", "delete"):
            if method not in ops:
                continue
            concrete = re.sub(r"\{[^}]+\}", "999999999", path.replace("{account}", "RRSP").replace("{tax_year}", "20x6"))
            content = ops[method].get("requestBody", {}).get("content", {})
            if "multipart/form-data" in content:
                api.call(method.upper(), concrete, files=("file", "not-a-backup.txt", b"hello"), expect=(400, 415, 422),
                         label=f"{concrete} [non-json/xlsx upload]")
            elif "application/json" in content:
                api.call(method.upper(), concrete, body={"bogus": True}, expect=(400, 404, 422), label=f"{concrete} [invalid body]")
            elif method == "delete":
                api.call("DELETE", concrete, expect=(404,), label=f"{concrete} [missing id]")


def counts(export_payload):
    return {table: len(rows) for table, rows in (export_payload or {}).get("data", {}).items()}


def run_write_cycles(api, spec, ctx):
    paths = spec["paths"]
    today = date.today().isoformat()
    platform = ctx["platform"]

    def item_url(prefix, method, item_id):
        """URL for /prefix/{any_param_name} when the API exposes that method, else None."""
        template = next((p for p in paths if re.fullmatch(re.escape(prefix) + r"/\{[^}]+\}", p) and method in paths[p]), None)
        return template and re.sub(r"\{[^}]+\}", str(item_id), template)

    status, before_export = api.call("GET", "/export")

    # Contribution cycle
    status, created = api.call("POST", "/contributions", body={"transaction_date": today, "account_name": "RRSP",
                                "platform_name": platform, "amount": 123.45, "notes": "qa-audit"})
    if status == 200:
        cid = created["id"]
        _, listed = api.call("GET", "/contributions", {"account": "RRSP"})
        if not any(row["id"] == cid for row in listed or []):
            WARNINGS.append(f"contribution {cid} missing from GET /contributions")
        api.call("PUT", f"/contributions/{cid}", body={"transaction_date": today, "account_name": "RRSP",
                 "platform_name": platform, "amount": 150, "notes": "qa-audit edit"})
        if item_url("/contributions", "delete", cid):
            api.call("DELETE", item_url("/contributions", "delete", cid), expect=(204,))
            api.call("DELETE", item_url("/contributions", "delete", cid), expect=(404,), label="/contributions/{id} [deleted twice]")
    api.call("POST", "/contributions", body={"transaction_date": today, "account_name": "RRSP", "amount": -1},
             expect=(422,), label="/contributions [negative amount]")
    api.call("PUT", "/contributions/999999999", body={"transaction_date": today, "account_name": "RRSP", "amount": 1},
             expect=(404,), label="/contributions/{id} [missing]")

    # Account transaction cycle (custom symbol so no real instrument is touched)
    symbol = "QA" + uuid.uuid4().hex[:6].upper()
    buy = {"transaction_type": "investment_buy", "transaction_date": today, "account_name": "RRSP", "platform_name": platform,
           "symbol": symbol, "is_custom_symbol": True, "instrument_name": "QA audit", "quantity": 2, "amount": 50, "fees": 0}
    status, created = api.call("POST", "/account-transactions", body=buy)
    if status == 200:
        tid = created["id"]
        _, page = api.call("GET", "/account-transactions", {"account": "RRSP", "symbol": symbol})
        if not any(row["id"] == tid for row in (page or {}).get("items", [])):
            WARNINGS.append(f"account transaction {tid} missing from GET /account-transactions")
        api.call("PUT", f"/account-transactions/{tid}", body={**buy, "quantity": 3, "amount": 75})
        if item_url("/account-transactions", "delete", tid):
            api.call("DELETE", item_url("/account-transactions", "delete", tid), expect=(204,))
    api.call("POST", "/account-transactions", body={**buy, "transaction_type": "contribution"}, expect=(400, 422),
             label="/account-transactions [contribution type]")
    api.call("PUT", "/account-transactions/999999999", body=buy, expect=(404,), label="/account-transactions/{id} [missing]")

    if "withdrawal" in ctx["enums"].get("TransactionType", []):
        status, created = api.call("POST", "/account-transactions", label="/account-transactions [withdrawal]", body={
            "transaction_type": "withdrawal", "transaction_date": today, "account_name": "TFSA", "platform_name": platform,
            "amount": 1, "notes": "qa-audit"})
        if status == 200 and item_url("/account-transactions", "delete", created["id"]):
            api.call("DELETE", item_url("/account-transactions", "delete", created["id"]), expect=(204,))

    # Manual valuation
    api.call("POST", "/manual-valuations", body={"account_name": "RRSP", "platform_name": platform, "symbol": symbol,
             "is_custom_symbol": True, "market_value": 60, "snapshot_date": today})
    api.call("POST", "/manual-valuations", body={"account_name": "RRSP", "market_value": -5, "snapshot_date": today},
             expect=(422,), label="/manual-valuations [negative value]")

    # Contribution limit edit, then restore the original
    _, limits = api.call("GET", "/contribution-limits")
    year = str(date.today().year)
    row = next((r for r in limits or [] if r["account"] == "RRSP" and r["tax_year"] == year), None)
    if row:
        original = row["new_room"]
        _, saved = api.call("PUT", f"/contribution-limits/RRSP/{year}", body={"new_room": original + 1})
        if saved and saved.get("new_room") != original + 1:
            WARNINGS.append("contribution limit PUT did not return the new value")
        api.call("PUT", f"/contribution-limits/RRSP/{year}", body={"new_room": original}, label="/contribution-limits [restore]")
    api.call("PUT", f"/contribution-limits/RRSP/{year}", body={"new_room": -5}, expect=(422,), label="/contribution-limits [negative]")
    api.call("PUT", "/contribution-limits/RRSP/20x6", body={"new_room": 1}, expect=(400, 422), label="/contribution-limits [bad year]")
    api.call("PUT", f"/contribution-limits/NOTANACCOUNT/{year}", body={"new_room": 1}, expect=(400, 404, 422),
             label="/contribution-limits [unknown account]")

    # Export -> import round trip must not change row counts
    status, export = api.call("GET", "/export")
    if status == 200:
        api.call("POST", "/import-backup", files=("file", "roundtrip.json", json.dumps(export).encode()), timeout=120)
        _, after = api.call("GET", "/export")
        if counts(after) != counts(export):
            WARNINGS.append(f"import round trip changed row counts: {counts(export)} -> {counts(after)}")
        api.call("POST", "/import-backup", files=("file", "bad.json", b"{not json"), expect=(400, 422), label="/import-backup [bad json]")
        api.call("POST", "/import-backup", files=("file", "other.json", b'{"meta": {"format": "x"}, "data": {}}'),
                 expect=(400, 422), label="/import-backup [wrong format]")
    if counts(before_export) and counts(export):
        ctx["delta"] = {k: counts(export)[k] - v for k, v in counts(before_export).items() if counts(export).get(k) != v}


def check_negative_cash(api):
    status, holdings = api.call("GET", "/holdings")
    for row in holdings or []:
        for leaf in row.get("children") or [row]:
            if leaf.get("record_type") == "cash" and leaf.get("book_value", 0) < 0:
                WARNINGS.append(f"negative cash: {leaf['account_name']} / {leaf.get('platform_name')} / {leaf['currency']} = {leaf['book_value']}")


def check_auth(api, spec):
    """When the API declares auth, requests without the headers (or with a wrong token) must be rejected."""
    if not spec.get("components", {}).get("securitySchemes"):
        return
    saved = api.headers
    api.headers = {}
    api.call("GET", "/years", expect=(401, 403), label="/years [no auth headers]")
    api.headers = {**saved, "X-API-Token": "wrong-token"}
    if saved.get("X-API-Token"):
        api.call("GET", "/years", expect=(401,), label="/years [wrong token]")
    api.headers = saved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=os.environ.get("API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--token", default=os.environ.get("API_TOKEN", ""))
    parser.add_argument("--disposable", action="store_true", help="allow writes; ONLY for throwaway databases")
    parser.add_argument("--skip-network", action="store_true", help="skip endpoints that call Yahoo Finance")
    parser.add_argument("--json", help="write results to this file")
    args = parser.parse_args()

    api = Api(args.api, args.token)
    status, spec = api.call("GET", "/openapi.json")
    if status != 200:
        sys.exit(f"cannot read {args.api}/openapi.json (status {status})")
    _, platforms = api.call("GET", "/platforms")
    ctx = {"enums": {name: s["enum"] for name, s in spec["components"]["schemas"].items() if "enum" in s},
           "platform": (platforms or ["Wealthsimple"])[0], "skip_network": args.skip_network}

    check_auth(api, spec)
    run_gets(api, spec, ctx)
    run_bad_params(api, spec, ctx)
    run_invalid_writes(api, spec)
    check_negative_cash(api)
    if args.disposable:
        run_write_cycles(api, spec, ctx)
    if not args.skip_network and "/market-prices/refresh" in spec["paths"]:
        if args.disposable:
            _, refreshed = api.call("POST", "/market-prices/refresh", timeout=600)
            errors = [r["symbol"] for r in refreshed or [] if r.get("status") != "ok"]
            if errors:
                WARNINGS.append(f"price refresh: {len(errors)}/{len(refreshed)} symbols failed: {', '.join(errors[:10])}")
        else:
            WARNINGS.append("skipped POST /market-prices/refresh (writes prices; needs --disposable)")

    width = max(len(r["path"]) for r in RESULTS)
    for r in RESULTS:
        mark = "ok " if r["ok"] else "FAIL"
        print(f"{mark} {r['method']:6} {r['path']:<{width}} {r['status']:>3} (want {'/'.join(map(str, r['expect']))}) {r['ms']:>6} ms {r['detail']}")
    slow = sorted(RESULTS, key=lambda r: r["ms"], reverse=True)[:5]
    print("\nslowest:", ", ".join(f"{r['method']} {r['path']} {r['ms']} ms" for r in slow))
    for warning in WARNINGS:
        print("WARN", warning)
    if ctx.get("delta"):
        print("row-count delta from write cycles:", ctx["delta"])
    failures = [r for r in RESULTS if not r["ok"]]
    print(f"\n{len(RESULTS)} calls, {len(failures)} unexpected, {sum(r['status'] >= 500 for r in RESULTS)} 5xx")
    if args.json:
        with open(args.json, "w") as handle:
            json.dump({"results": RESULTS, "warnings": WARNINGS}, handle, indent=2)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
