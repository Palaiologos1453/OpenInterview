from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / "apps" / "api"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from openinterview_api.services.evaluation import (  # noqa: E402
    DEFAULT_EVAL_SEED_PATH,
    evaluate_scoring_cases,
    expand_seed_cases,
    write_evaluation_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate OpenInterview rule scoring against labeled cases.")
    parser.add_argument("--seed", type=Path, default=DEFAULT_EVAL_SEED_PATH)
    parser.add_argument("--output", type=Path, default=ROOT / "apps" / "api" / "eval" / "scoring-report.md")
    parser.add_argument("--json-output", type=Path, default=None)
    parser.add_argument("--max-mae", type=float, default=10.0)
    parser.add_argument("--min-gap-recall", type=float, default=0.9)
    args = parser.parse_args()

    cases = expand_seed_cases(args.seed)
    result = evaluate_scoring_cases(cases)
    write_evaluation_report(args.output, result)
    if args.json_output:
        write_evaluation_report(args.json_output, result)

    print(f"cases={result['case_count']}")
    print(f"score_mae={result['score_mae']}")
    print(f"within_tolerance_rate={result['within_tolerance_rate']}")
    print(f"gap_precision={result['gap_precision']}")
    print(f"gap_recall={result['gap_recall']}")
    print(f"misjudgment_count={result['misjudgment_count']}")

    if result["score_mae"] > args.max_mae:
        print(f"score_mae exceeds threshold: {result['score_mae']} > {args.max_mae}", file=sys.stderr)
        return 1
    if result["gap_recall"] < args.min_gap_recall:
        print(f"gap_recall below threshold: {result['gap_recall']} < {args.min_gap_recall}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
