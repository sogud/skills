#!/usr/bin/env python3
"""Filter structured screener output down to tradable Shanghai/Shenzhen mainboard A shares."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


MAINBOARD_PREFIXES = {
    "SH": ("600", "601", "603", "605"),
    "SZ": ("000", "001", "002", "003"),
}
CODE_PATTERN = re.compile(r"(?:(SH|SZ)[._-]?)?(\d{6})(?:[._-]?(SH|SZ))?", re.IGNORECASE)
NAME_FIELDS = ("name", "display_name", "security_name", "name_cn")
SYMBOL_FIELDS = ("symbol", "ticker", "code", "security_code")


def normalize_symbol(item: dict[str, Any]) -> tuple[str, str] | None:
    for field in SYMBOL_FIELDS:
        value = item.get(field)
        if value is None:
            continue
        match = CODE_PATTERN.fullmatch(str(value).strip())
        if not match:
            continue
        market = (match.group(1) or match.group(3) or "").upper()
        code = match.group(2)
        if not market:
            if code.startswith(MAINBOARD_PREFIXES["SH"]):
                market = "SH"
            elif code.startswith(MAINBOARD_PREFIXES["SZ"]):
                market = "SZ"
        if market:
            return market, code
    return None


def has_name_risk(item: dict[str, Any]) -> bool:
    for field in NAME_FIELDS:
        value = item.get(field)
        if not isinstance(value, str):
            continue
        name = value.strip().upper()
        if name.startswith(("ST", "*ST")) or "退" in name:
            return True
    return False


def is_mainboard(item: Any) -> bool:
    if not isinstance(item, dict) or has_name_risk(item):
        return False
    normalized = normalize_symbol(item)
    if normalized is None:
        return False
    market, code = normalized
    return code.startswith(MAINBOARD_PREFIXES.get(market, ()))


def filter_payload(payload: Any) -> Any:
    if isinstance(payload, list):
        return [item for item in payload if is_mainboard(item)]

    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON list or object")

    output = dict(payload)
    if isinstance(payload.get("items"), list):
        output["items"] = filter_payload(payload["items"])
        for key in ("total", "count"):
            if key in output:
                output[key] = len(output["items"])
        return output

    if isinstance(payload.get("data"), list):
        output["data"] = filter_payload(payload["data"])
        for key in ("total", "count"):
            if key in output:
                output[key] = len(output["data"])
        return output

    if isinstance(payload.get("data"), dict):
        output["data"] = filter_payload(payload["data"])
        return output

    raise ValueError("input object must contain an items or data collection")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="JSON file; omit to read stdin")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        raw = args.input.read_text(encoding="utf-8") if args.input else sys.stdin.read()
        payload = json.loads(raw)
        filtered = filter_payload(payload)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"mainboard filter error: {error}", file=sys.stderr)
        return 2

    json.dump(filtered, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
