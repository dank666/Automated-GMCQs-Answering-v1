#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Run sensitivity analysis for the 3WCA rule filtering parameters.

This script intentionally uses the non-DCR evaluation path. It varies only:
  - RULE_CONF_PERCENTILE
  - RULE_SUPP_PERCENTILE
  - RULE_STRENGTH_PERCENTILE
  - RULE_RELAX_FACTOR
"""

import argparse
import contextlib
import csv
import os
from datetime import datetime
from pathlib import Path

from batch_evaluate import evaluate_json


DATASETS = {
    "Climatology": {
        "single": ("single_questions/Climatology.json", "dict_single/Climatology.csv"),
        "multiple": ("multiple_questions/Climatology.json", "dict_multiple/Climatology.csv"),
    },
    "GPP": {
        "single": ("single_questions/GPP.json", "dict_single/GPP.csv"),
        "multiple": ("multiple_questions/GPP.json", "dict_multiple/GPP.csv"),
    },
    "HEG": {
        "single": ("single_questions/HEG.json", "dict_single/HEG.csv"),
        "multiple": ("multiple_questions/HEG.json", "dict_multiple/HEG.csv"),
    },
    "Hydrology": {
        "single": ("single_questions/Hydrology.json", "dict_single/Hydrology.csv"),
        "multiple": ("multiple_questions/Hydrology.json", "dict_multiple/Hydrology.csv"),
    },
    "SV": {
        "single": ("single_questions/SV.json", "dict_single/SV.csv"),
        "multiple": ("multiple_questions/SV.json", "dict_multiple/SV.csv"),
    },
    "TG": {
        "single": ("single_questions/TG.json", "dict_single/TG.csv"),
        "multiple": ("multiple_questions/TG.json", "dict_multiple/TG.csv"),
    },
}


EXPERIMENTS_A = [
    {"experiment_id": "A1", "conf": 0.70, "supp": 0.70, "strength": 0.80, "relax": 0.70},
    {"experiment_id": "A2", "conf": 0.75, "supp": 0.75, "strength": 0.85, "relax": 0.70},
    {"experiment_id": "A3", "conf": 0.80, "supp": 0.80, "strength": 0.90, "relax": 0.70},
    {"experiment_id": "A4", "conf": 0.85, "supp": 0.85, "strength": 0.95, "relax": 0.70},
]


EXPERIMENTS_B = [
    {"experiment_id": "B1", "conf": 0.80, "supp": 0.80, "strength": 0.90, "relax": 0.60},
    {"experiment_id": "B2", "conf": 0.80, "supp": 0.80, "strength": 0.90, "relax": 0.70},
    {"experiment_id": "B3", "conf": 0.80, "supp": 0.80, "strength": 0.90, "relax": 0.80},
    {"experiment_id": "B4", "conf": 0.80, "supp": 0.80, "strength": 0.90, "relax": 0.90},
]


FIELDNAMES = [
    "run_time",
    "experiment_id",
    "question_type",
    "domain",
    "question_file",
    "dict_file",
    "conf_percentile",
    "supp_percentile",
    "strength_percentile",
    "relax_factor",
    "accuracy",
    "accuracy_percent",
    "correct_count",
    "total_count",
    "avg_rule_count",
    "total_rule_count",
    "avg_confidence",
    "avg_support",
    "avg_strength",
    "relax_trigger_count",
    "log_file",
]


def _set_rule_env(exp):
    os.environ["RULE_CONF_PERCENTILE"] = str(exp["conf"])
    os.environ["RULE_SUPP_PERCENTILE"] = str(exp["supp"])
    os.environ["RULE_STRENGTH_PERCENTILE"] = str(exp["strength"])
    os.environ["RULE_RELAX_FACTOR"] = str(exp["relax"])


def _selected_experiments(suite):
    if suite == "A":
        return EXPERIMENTS_A
    if suite == "B":
        return EXPERIMENTS_B
    return EXPERIMENTS_A + EXPERIMENTS_B


def _selected_question_types(question_type):
    if question_type == "both":
        return ["single", "multiple"]
    return [question_type]


def _summarize_rules(result):
    results = (result or {}).get("results", [])
    rule_counts = [item.get("extracted_rules_count", 0) for item in results]
    all_rules = []
    relaxed_questions = 0

    for item in results:
        rules = item.get("rules") or []
        all_rules.extend(rules)
        if any(rule.get("_threshold_relaxed") for rule in rules):
            relaxed_questions += 1

    def avg(key):
        values = [float(rule.get(key, 0.0) or 0.0) for rule in all_rules]
        return sum(values) / len(values) if values else 0.0

    return {
        "avg_rule_count": sum(rule_counts) / len(rule_counts) if rule_counts else 0.0,
        "total_rule_count": sum(rule_counts),
        "avg_confidence": avg("confidence"),
        "avg_support": avg("support"),
        "avg_strength": avg("rule_strength"),
        "relax_trigger_count": relaxed_questions,
    }


def _resolve_dict_file(dict_file, use_backup_dicts):
    if not use_backup_dicts:
        return dict_file
    backup_file = Path("dict_backup") / dict_file
    if backup_file.exists():
        return str(backup_file)
    print(f"警告：未找到备份词典 {backup_file}，改用当前词典 {dict_file}")
    return dict_file


def _run_one(exp, domain, question_type, output_dir, use_backup_dicts=False):
    question_file, dict_file = DATASETS[domain][question_type]
    dict_file = _resolve_dict_file(dict_file, use_backup_dicts)
    _set_rule_env(exp)

    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{exp['experiment_id']}_{question_type}_{domain}.log"

    print(
        f">>> {exp['experiment_id']} | {question_type} | {domain} "
        f"(conf={exp['conf']}, supp={exp['supp']}, strength={exp['strength']}, relax={exp['relax']})"
    )

    with open(log_file, "w", encoding="utf-8") as log, contextlib.redirect_stdout(log):
        result = evaluate_json(question_file, custom_dict=dict_file)

    rule_summary = _summarize_rules(result)
    accuracy = (result or {}).get("accuracy", 0.0)
    row = {
        "run_time": datetime.now().isoformat(timespec="seconds"),
        "experiment_id": exp["experiment_id"],
        "question_type": question_type,
        "domain": domain,
        "question_file": question_file,
        "dict_file": dict_file,
        "conf_percentile": exp["conf"],
        "supp_percentile": exp["supp"],
        "strength_percentile": exp["strength"],
        "relax_factor": exp["relax"],
        "accuracy": round(accuracy, 6),
        "accuracy_percent": round(accuracy * 100, 2),
        "correct_count": (result or {}).get("correct_count", 0),
        "total_count": (result or {}).get("total_count", 0),
        "log_file": str(log_file),
    }
    row.update({key: round(value, 6) for key, value in rule_summary.items()})
    return row


def _append_rows(csv_path, rows):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def parse_args():
    parser = argparse.ArgumentParser(description="Run 3WCA parameter sensitivity analysis.")
    parser.add_argument("--suite", choices=["A", "B", "all"], default="all", help="Experiment suite to run.")
    parser.add_argument(
        "--question-type",
        choices=["single", "multiple", "both"],
        default="both",
        help="Question type to evaluate.",
    )
    parser.add_argument(
        "--domains",
        nargs="*",
        default=list(DATASETS.keys()),
        choices=list(DATASETS.keys()),
        help="Domains to evaluate.",
    )
    parser.add_argument(
        "--output-dir",
        default="test_results/sensitivity_analysis",
        help="Directory for CSV results and logs.",
    )
    parser.add_argument(
        "--limit-runs",
        type=int,
        default=None,
        help="Optional smoke-test limit for the number of runs.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite sensitivity_results.csv before writing new results.",
    )
    parser.add_argument(
        "--use-backup-dicts",
        action="store_true",
        help="Use dictionaries from dict_backup/ for a clean fixed experimental baseline.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    csv_path = output_dir / "sensitivity_results.csv"
    if args.overwrite and csv_path.exists():
        csv_path.unlink()

    experiments = _selected_experiments(args.suite)
    question_types = _selected_question_types(args.question_type)
    rows = []
    run_count = 0

    for exp in experiments:
        for question_type in question_types:
            for domain in args.domains:
                if args.limit_runs is not None and run_count >= args.limit_runs:
                    break
                rows.append(_run_one(exp, domain, question_type, output_dir, args.use_backup_dicts))
                run_count += 1
            if args.limit_runs is not None and run_count >= args.limit_runs:
                break
        if args.limit_runs is not None and run_count >= args.limit_runs:
            break

    _append_rows(csv_path, rows)
    print(f"\n完成：写入 {len(rows)} 条实验结果 -> {csv_path}")
    print("注意：本脚本未启用 DCR，结果只反映 3WCA 规则筛选参数敏感性。")


if __name__ == "__main__":
    main()
