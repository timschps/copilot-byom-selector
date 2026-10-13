"""Actual billed cost from Azure Cost Management, to compare with the local estimate."""

from __future__ import annotations

import time

import requests

from . import usage
from .auth import ARM_SCOPE, credential
from .config import Profile

API = "2023-11-01"


def _query(profile: Profile, days: int) -> dict:
    scope = f"/subscriptions/{profile.subscription_id}"
    account_id = (
        f"{scope}/resourceGroups/{profile.resource_group}"
        f"/providers/Microsoft.CognitiveServices/accounts/{profile.account}"
    )
    body = {
        "type": "ActualCost",
        "timeframe": "Custom",
        "timePeriod": {
            "from": time.strftime("%Y-%m-%dT00:00:00Z", time.gmtime(time.time() - days * 86400)),
            "to": time.strftime("%Y-%m-%dT23:59:59Z", time.gmtime()),
        },
        "dataset": {
            "granularity": "Daily",
            "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
            "grouping": [{"type": "Dimension", "name": "Meter"}],
            "filter": {
                "dimensions": {"name": "ResourceId", "operator": "In", "values": [account_id]}
            },
        },
    }
    token = credential(profile).get_token(ARM_SCOPE).token
    r = requests.post(
        f"https://management.azure.com{scope}/providers/Microsoft.CostManagement/query",
        params={"api-version": API},
        json=body,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    if r.status_code == 403:
        raise PermissionError("Needs the Cost Management Reader role on the subscription.")
    r.raise_for_status()
    return r.json()["properties"]


def _estimated_by_day(days: int) -> dict[str, float]:
    out: dict[str, float] = {}
    since = time.time() - days * 86400
    with usage._db() as con:
        for day, cost in con.execute(
            "SELECT strftime('%Y%m%d', ts, 'unixepoch'), SUM(cost) FROM requests "
            "WHERE ts>? GROUP BY 1",
            (since,),
        ):
            out[day] = cost or 0.0
    return out


def actual_cost(profile: Profile, days: int = 30) -> dict:
    """Billed cost per day and per meter for the profile's Foundry account, plus the estimate."""
    props = _query(profile, days)
    cols = [c["name"] for c in props["columns"]]
    i_cost, i_date, i_meter = cols.index("Cost"), cols.index("UsageDate"), cols.index("Meter")
    currency = cols.index("Currency") if "Currency" in cols else None
    by_day: dict[str, float] = {}
    by_meter: dict[str, float] = {}
    cur = ""
    for row in props["rows"]:
        day = str(row[i_date])
        by_day[day] = by_day.get(day, 0.0) + row[i_cost]
        by_meter[row[i_meter]] = by_meter.get(row[i_meter], 0.0) + row[i_cost]
        if currency is not None:
            cur = row[currency]
    est = _estimated_by_day(days)
    billed_total = sum(by_day.values())
    # Billing data lags by hours to a day: compare only days Azure has already reported.
    comparable = [d for d in est if d in by_day]
    return {
        "profile": profile.name,
        "currency": cur or "USD",
        "days": days,
        "billed_total": round(billed_total, 4),
        "estimated_total": round(sum(est.values()), 4),
        "billed_on_estimated_days": round(sum(by_day[d] for d in comparable), 4),
        "estimated_on_billed_days": round(sum(est[d] for d in comparable), 4),
        "by_day": [
            {"day": d, "billed": round(by_day[d], 4), "estimated": round(est.get(d, 0.0), 4)}
            for d in sorted(by_day)
        ],
        "by_meter": sorted(
            ({"meter": m, "billed": round(c, 4)} for m, c in by_meter.items()),
            key=lambda x: -x["billed"],
        ),
    }
