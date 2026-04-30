"""Experiment 16: strategy recommendation match analysis."""

from __future__ import annotations

from collections import defaultdict
from statistics import median

from common_v4 import RESULT_DIR_V4, read_csv, strategy_score, write_csv, write_report_v4


FIELDNAMES = [
    "workload",
    "family",
    "seed",
    "n",
    "C",
    "B",
    "regime_label",
    "recommended_strategy",
    "empirical_best_strategy",
    "match",
    "score_recommended",
    "score_best",
    "regret",
]

SUMMARY_FIELDNAMES = [
    "strategy_match_rate",
    "mean_regret",
    "median_regret",
    "regime_label",
    "match_rate_by_regime",
    "count",
]


RECOMMENDED_TO_CANDIDATE = {
    "none": "none/static",
    "smooth": "smooth",
    "increase_buffer": "increase_B",
    "increase_capacity": "increase_C",
    "robust_scheduling": "robust_smooth",
    "architecture_provisioning": "increase_C",
}


def main() -> None:
    exp12 = read_csv(RESULT_DIR_V4 / "exp12_strategy_validation.csv")
    grouped: dict[tuple[str, str, str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in exp12:
        key = (row["workload"], row["family"], row["seed"], row["n"], row["C"], row["B"])
        grouped[key].append(row)

    rows = []
    for key, group in grouped.items():
        scores = {
            row["candidate_strategy"]: strategy_score(
                float(row["candidate_T_exe"]) / float(row["T_ref_asap"]),
                float(row["candidate_BacklogArea"]),
            )
            for row in group
        }
        best_strategy, best_score = min(scores.items(), key=lambda item: (item[1], item[0]))
        first = group[0]
        recommended_candidate = RECOMMENDED_TO_CANDIDATE.get(
            first["recommended_strategy"],
            first["recommended_strategy"],
        )
        score_recommended = scores.get(recommended_candidate, best_score)
        if score_recommended <= best_score + 1e-9:
            match = 1
            empirical_best = recommended_candidate
        else:
            match = 0
            empirical_best = best_strategy
        rows.append(
            {
                "workload": key[0],
                "family": key[1],
                "seed": key[2],
                "n": key[3],
                "C": key[4],
                "B": key[5],
                "regime_label": first["regime_label"],
                "recommended_strategy": first["recommended_strategy"],
                "empirical_best_strategy": empirical_best,
                "match": match,
                "score_recommended": score_recommended,
                "score_best": best_score,
                "regret": score_recommended - best_score,
            }
        )

    out_path = RESULT_DIR_V4 / "exp16_strategy_match_analysis.csv"
    write_csv(out_path, rows, FIELDNAMES)
    _write_summary(rows)
    write_report_v4()
    print(f"Wrote {len(rows)} rows to {out_path}")


def _write_summary(rows: list[dict[str, object]]) -> None:
    regrets = [float(row["regret"]) for row in rows]
    summary = [
        {
            "strategy_match_rate": sum(int(row["match"]) for row in rows) / len(rows) if rows else 0.0,
            "mean_regret": sum(regrets) / len(regrets) if regrets else 0.0,
            "median_regret": median(regrets) if regrets else 0.0,
            "regime_label": "OVERALL",
            "match_rate_by_regime": sum(int(row["match"]) for row in rows) / len(rows)
            if rows
            else 0.0,
            "count": len(rows),
        }
    ]
    regimes = sorted({str(row["regime_label"]) for row in rows})
    for regime in regimes:
        selected = [row for row in rows if row["regime_label"] == regime]
        summary.append(
            {
                "strategy_match_rate": "",
                "mean_regret": "",
                "median_regret": "",
                "regime_label": regime,
                "match_rate_by_regime": sum(int(row["match"]) for row in selected) / len(selected)
                if selected
                else 0.0,
                "count": len(selected),
            }
        )
    write_csv(RESULT_DIR_V4 / "exp16_strategy_match_summary.csv", summary, SUMMARY_FIELDNAMES)


if __name__ == "__main__":
    main()
