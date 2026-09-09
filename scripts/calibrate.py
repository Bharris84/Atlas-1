"""Run Atlas calibration and print the comparison.

    python scripts/calibrate.py                        # uses the example deals
    python scripts/calibrate.py calibration/deals.json # your real deals
    python scripts/calibrate.py --json                 # machine-readable

For each deal it reports what Atlas predicted, what actually happened, the
difference, and which assumption caused it — by re-running the engine with each
known actual substituted in, one at a time.

The most important line in the output is the unexplained residual: what remains
after every known input is corrected. That is not an estimate being wrong, it is
the cost model being wrong, and it is the one thing this exercise can tell you
that staring at a spreadsheet cannot.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "financial-engine" / "src"))

from atlas_financial_engine.calibration import (  # noqa: E402
    CalibrationReport,
    CalibrationResult,
    calibrate_from_dicts,
)

DEFAULT_DEALS = ROOT / "calibration" / "deals.example.json"
RULE = "=" * 78


def money(value: Optional[Decimal]) -> str:
    if value is None:
        return "—"
    return f"${value:,.0f}"


def signed(value: Optional[Decimal]) -> str:
    if value is None:
        return "—"
    return f"{'+' if value >= 0 else '-'}${abs(value):,.0f}"


def load(path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(path.read_text())
    if isinstance(payload, list):
        return payload
    return payload["deals"]


def print_deal(result: CalibrationResult) -> None:
    print(RULE)
    print(result.name)
    print(f"  Strategy executed : {result.strategy.value}")
    print(f"  Profit measured as: {result.profit_basis}")

    if result.predicted_profit is None:
        print("  " + (result.notes[0] if result.notes else "No prediction available."))
        return

    print()
    print(f"  Atlas prediction  : {money(result.predicted_profit)}")
    print(f"  Actual outcome    : {money(result.actual_profit)}")
    pct = (
        f"  ({result.difference_percent * 100:+.1f}%)"
        if result.difference_percent is not None
        else ""
    )
    print(f"  Difference        : {signed(result.difference)}{pct}")

    if result.attributions:
        print()
        print("  Which assumption caused the difference:")
        width = max(len(a.label) for a in result.attributions)
        for attribution in result.attributions:
            print(
                f"    {attribution.label:<{width}}  "
                f"{attribution.predicted_value or '—':>10} -> "
                f"{attribution.actual_value or '—':<10}  "
                f"{signed(attribution.profit_impact):>10}"
            )

    if result.explained_by_inputs is not None:
        print()
        print(f"  Explained by wrong inputs : {signed(result.explained_by_inputs)}")
        if result.interaction_effect:
            print(f"  Factor interaction        : {signed(result.interaction_effect)}")
        print(
            f"  Unexplained residual      : {signed(result.unexplained_residual)}"
            "   <- cost model, not estimates"
        )

    for note in result.notes:
        print(f"\n  ! {note}")


def print_report(report: CalibrationReport) -> None:
    print()
    print(RULE)
    print("SUMMARY")
    print(RULE)
    print(f"  Deals compared            : {len(report.results)}")
    print(f"  Mean absolute error       : {money(report.mean_absolute_error)}")
    print(
        f"  Mean signed error         : {signed(report.mean_signed_error)}"
        "   (negative = Atlas is optimistic)"
    )
    print(f"  Mean unexplained residual : {signed(report.mean_unexplained_residual)}")

    if report.dominant_factor_counts:
        print()
        print("  Most often the largest cause:")
        for factor, count in sorted(
            report.dominant_factor_counts.items(), key=lambda kv: kv[1], reverse=True
        ):
            print(f"    {factor:<24} {count} deal(s)")

    if report.factor_totals:
        print()
        print("  Total absolute impact by factor:")
        for factor, total in sorted(
            report.factor_totals.items(), key=lambda kv: kv[1], reverse=True
        ):
            print(f"    {factor:<24} {money(total)}")

    if report.notes:
        print()
        for note in report.notes:
            print(f"  ! {note}")
    print(RULE)


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--json"]
    as_json = "--json" in sys.argv[1:]
    path = Path(args[0]) if args else DEFAULT_DEALS

    if not path.exists():
        print(f"No such file: {path}", file=sys.stderr)
        return 1

    report = calibrate_from_dicts(load(path))

    if as_json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0

    if path == DEFAULT_DEALS:
        print()
        print("*** Running the HYPOTHETICAL example deals. ***")
        print("*** These figures are invented. Nothing here says anything about  ***")
        print("*** Atlas's real accuracy. Copy the file and use real outcomes.   ***")

    for result in report.results:
        print_deal(result)
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
