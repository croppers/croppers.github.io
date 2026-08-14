#!/usr/bin/env python3
"""Refresh the market snapshot used by the static world-split page."""

import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).parent
OUTPUT = ROOT / "data.json"
VANGUARD_HEADERS = {"Accept": "application/json"}
NASDAQ_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/126 Safari/537.36"
    ),
}


def get_json(url, headers):
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def money(value):
    return float(re.sub(r"[^0-9.-]", "", value or ""))


def iso_day(value):
    return value[:10]


def quote(ticker):
    payload = get_json(
        f"https://api.nasdaq.com/api/quote/{ticker}/info?assetclass=etf",
        NASDAQ_HEADERS,
    )
    data = payload["data"]
    primary = data["primaryData"]
    return {
        "price": money(primary["lastSalePrice"]),
        "timestamp": primary["lastTradeTimestamp"],
        "marketStatus": data.get("marketStatus", "Unknown"),
    }


def market_leg(ticker, fund_id, anchor_date):
    from_date = urllib.parse.quote(anchor_date)
    history = get_json(
        f"https://api.nasdaq.com/api/quote/{ticker}/historical"
        f"?assetclass=etf&fromdate={from_date}&limit=500",
        NASDAQ_HEADERS,
    )
    distributions = get_json(
        f"https://investor.vanguard.com/vmf/api/{fund_id}/distribution",
        VANGUARD_HEADERS,
    )
    current = quote(ticker)

    year, month, day = anchor_date.split("-")
    target = f"{month}/{day}/{year}"
    rows = history["data"]["tradesTable"]["rows"]
    anchor_row = next(row for row in rows if row["date"] == target)
    anchor_price = money(anchor_row["close"])

    share_factor = 1.0
    reinvested = 0
    for item in distributions.get("divCapGain", {}).get("item", []):
        reinvest_date = iso_day(item.get("reinvestmentDate", "0000-00-00"))
        if (
            item.get("type") == "Dividend"
            and anchor_date < reinvest_date <= date.today().isoformat()
        ):
            share_factor *= 1 + money(item["perShareAmount"]) / money(
                item["reinvestPrice"]
            )
            reinvested += 1

    return {
        **current,
        "anchorPrice": anchor_price,
        "totalReturnFactor": current["price"] * share_factor / anchor_price,
        "distributionsReinvested": reinvested,
    }


def build_snapshot():
    characteristic = get_json(
        "https://investor.vanguard.com/vmf/api/3141/characteristic"
        "?isInternal=true&isBfpCharacteristicsToggle=true",
        VANGUARD_HEADERS,
    )["equityCharacteristic"]
    foreign = float(characteristic["fund"]["foreignHolding"])
    anchor_us = 100 - foreign
    anchor_date = iso_day(
        characteristic["fund"].get("foreignHoldingDate")
        or characteristic["asOfDate"]
    )

    us_leg = market_leg("VTI", "0970", anchor_date)
    ex_us_leg = market_leg("VXUS", "3369", anchor_date)
    vt = quote("VT")
    avuv = quote("AVUV")
    avdv = quote("AVDV")

    rolled_us = anchor_us / 100 * us_leg["totalReturnFactor"]
    rolled_ex_us = foreign / 100 * ex_us_leg["totalReturnFactor"]
    us_weight = rolled_us / (rolled_us + rolled_ex_us) * 100

    return {
        "usWeight": us_weight,
        "exUsWeight": 100 - us_weight,
        "anchorUsWeight": anchor_us,
        "anchorExUsWeight": foreign,
        "anchorDate": anchor_date,
        "quoteTimestamp": us_leg["timestamp"],
        "marketStatus": us_leg["marketStatus"],
        "benchmark": characteristic.get(
            "benchmarkShortName", "FTSE Global All Cap Index"
        ),
        "prices": {
            "vt": vt["price"],
            "vti": us_leg["price"],
            "vxus": ex_us_leg["price"],
            "avuv": avuv["price"],
            "avdv": avdv["price"],
        },
        "returns": {
            "us": (us_leg["totalReturnFactor"] - 1) * 100,
            "exUs": (ex_us_leg["totalReturnFactor"] - 1) * 100,
        },
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
    }


def main():
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else OUTPUT
    snapshot = build_snapshot()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(
        f"Updated {output}: {snapshot['usWeight']:.2f}% US / "
        f"{snapshot['exUsWeight']:.2f}% ex-US"
    )


if __name__ == "__main__":
    main()
