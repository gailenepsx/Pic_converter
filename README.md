#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Compare P2E classification vs manual classification from a semicolon-separated CSV
and generate a full KPI report.

Expected columns:
- beneficiary_name
- class_p2e
- class_manual

Expected classes:
- business
- individual

Usage:
    python compare_p2e_vs_manual.py input.csv

Optional:
    python compare_p2e_vs_manual.py input.csv --output-dir report_output
"""

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd


def normalize_class(value):
    if pd.isna(value):
        return np.nan

    v = str(value).strip().lower()

    mapping = {
        "business": "business",
        "company": "business",
        "corporate": "business",
        "organisation": "business",
        "organization": "business",
        "entreprise": "business",
        "societe": "business",
        "société": "business",
        "pro": "business",
        "individual": "individual",
        "person": "individual",
        "private": "individual",
        "particular": "individual",
        "individu": "individual",
        "particulier": "individual",
        "natural person": "individual",
    }

    return mapping.get(v, v)


def safe_div(num, den):
    return round((num / den) * 100, 2) if den else 0.0


def compute_binary_metrics(tp, tn, fp, fn):
    total = tp + tn + fp + fn

    accuracy = safe_div(tp + tn, total)
    precision_business = safe_div(tp, tp + fp)
    recall_business = safe_div(tp, tp + fn)
    specificity_business = safe_div(tn, tn + fp)
    f1_business = round(
        2 * precision_business * recall_business / (precision_business + recall_business), 2
    ) if (precision_business + recall_business) else 0.0

    precision_individual = safe_div(tn, tn + fn)
    recall_individual = safe_div(tn, tn + fp)
    f1_individual = round(
        2 * precision_individual * recall_individual / (precision_individual + recall_individual), 2
    ) if (precision_individual + recall_individual) else 0.0

    balanced_accuracy = round((recall_business + recall_individual) / 2, 2)

    return {
        "total_observations": total,
        "accuracy_pct": accuracy,
        "precision_business_pct": precision_business,
        "recall_business_pct": recall_business,
        "specificity_business_pct": specificity_business,
        "f1_business_pct": f1_business,
        "precision_individual_pct": precision_individual,
        "recall_individual_pct": recall_individual,
        "f1_individual_pct": f1_individual,
        "balanced_accuracy_pct": balanced_accuracy,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", help="Path to the semicolon-separated CSV file")
    parser.add_argument("--output-dir", default="report_output", help="Directory for output files")
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_path, sep=";", dtype=str, keep_default_na=False)

    expected_cols = ["beneficiary_name", "class_p2e", "class_manual"]
    missing = [c for c in expected_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df[expected_cols].copy()

    df["beneficiary_name"] = df["beneficiary_name"].astype(str).str.strip()
    df["class_p2e_raw"] = df["class_p2e"]
    df["class_manual_raw"] = df["class_manual"]

    df["class_p2e"] = df["class_p2e"].apply(normalize_class)
    df["class_manual"] = df["class_manual"].apply(normalize_class)

    valid_classes = {"business", "individual"}

    df["p2e_valid"] = df["class_p2e"].isin(valid_classes)
    df["manual_valid"] = df["class_manual"].isin(valid_classes)
    df["comparison_possible"] = df["p2e_valid"] & df["manual_valid"]

    total_rows = len(df)
    comparable_df = df[df["comparison_possible"]].copy()
    invalid_df = df[~df["comparison_possible"]].copy()

    comparable_count = len(comparable_df)
    invalid_count = len(invalid_df)

    comparable_df["match"] = comparable_df["class_p2e"] == comparable_df["class_manual"]

    confusion = pd.crosstab(
        comparable_df["class_manual"],
        comparable_df["class_p2e"],
        rownames=["manual"],
        colnames=["p2e"],
        dropna=False
    )

    for row in ["business", "individual"]:
        if row not in confusion.index:
            confusion.loc[row] = 0
    for col in ["business", "individual"]:
        if col not in confusion.columns:
            confusion[col] = 0

    confusion = confusion.sort_index().sort_index(axis=1)

    tp = int(confusion.loc["business", "business"])
    fn = int(confusion.loc["business", "individual"])
    fp = int(confusion.loc["individual", "business"])
    tn = int(confusion.loc["individual", "individual"])

    metrics = compute_binary_metrics(tp, tn, fp, fn)

    agreement_count = int(comparable_df["match"].sum())
    disagreement_count = comparable_count - agreement_count

    p2e_distribution = comparable_df["class_p2e"].value_counts(dropna=False).rename_axis("class").reset_index(name="count")
    manual_distribution = comparable_df["class_manual"].value_counts(dropna=False).rename_axis("class").reset_index(name="count")

    mismatch_details = comparable_df.loc[~comparable_df["match"], [
        "beneficiary_name", "class_p2e_raw", "class_manual_raw", "class_p2e", "class_manual"
    ]].copy()

    invalid_details = invalid_df.loc[:, [
        "beneficiary_name", "class_p2e_raw", "class_manual_raw", "class_p2e", "class_manual", "p2e_valid", "manual_valid"
    ]].copy()

    summary = {
        "input_file": str(input_path),
        "total_rows": total_rows,
        "comparable_rows": comparable_count,
        "non_comparable_rows": invalid_count,
        "agreement_count": agreement_count,
        "disagreement_count": disagreement_count,
        "agreement_rate_pct": safe_div(agreement_count, comparable_count),
        "disagreement_rate_pct": safe_div(disagreement_count, comparable_count),
        "business_business_tp": tp,
        "business_individual_fn": fn,
        "individual_business_fp": fp,
        "individual_individual_tn": tn,
        **metrics
    }

    summary_df = pd.DataFrame([summary])
    confusion_reset = confusion.reset_index()

    summary_df.to_csv(output_dir / "kpi_summary.csv", index=False)
    confusion_reset.to_csv(output_dir / "confusion_matrix.csv", index=False)
    p2e_distribution.to_csv(output_dir / "p2e_distribution.csv", index=False)
    manual_distribution.to_csv(output_dir / "manual_distribution.csv", index=False)
    mismatch_details.to_csv(output_dir / "mismatch_details.csv", index=False)
    invalid_details.to_csv(output_dir / "invalid_rows.csv", index=False)

    report_lines = []

    report_lines.append("# P2E Classification Performance Report
")
    report_lines.append(f"Input file: {input_path}
")
    report_lines.append("## 1. Scope
")
    report_lines.append("This report compares the classification produced by P2E against the manual classification considered as ground truth.
")
    report_lines.append("The comparison is performed on the two expected classes: `business` and `individual`.
")

    report_lines.append("
## 2. Data Quality
")
    report_lines.append(f"- Total rows in source file: {total_rows}
")
    report_lines.append(f"- Comparable rows used for KPI calculation: {comparable_count}
")
    report_lines.append(f"- Non-comparable rows excluded from KPI calculation: {invalid_count}
")

    report_lines.append("
## 3. Main KPIs
")
    report_lines.append(f"- Performance rate / Accuracy: {summary['accuracy_pct']}%
")
    report_lines.append(f"- Agreement rate: {summary['agreement_rate_pct']}%
")
    report_lines.append(f"- Disagreement rate: {summary['disagreement_rate_pct']}%
")
    report_lines.append(f"- Balanced accuracy: {summary['balanced_accuracy_pct']}%
")
    report_lines.append(f"- Precision on `business`: {summary['precision_business_pct']}%
")
    report_lines.append(f"- Recall on `business`: {summary['recall_business_pct']}%
")
    report_lines.append(f"- Specificity on `business`: {summary['specificity_business_pct']}%
")
    report_lines.append(f"- F1-score on `business`: {summary['f1_business_pct']}%
")
    report_lines.append(f"- Precision on `individual`: {summary['precision_individual_pct']}%
")
    report_lines.append(f"- Recall on `individual`: {summary['recall_individual_pct']}%
")
    report_lines.append(f"- F1-score on `individual`: {summary['f1_individual_pct']}%
")

    report_lines.append("
## 4. Confusion Matrix
")
    report_lines.append("Manual classification is the reference. P2E is the prediction.
")
    report_lines.append(f"- True Positives  (manual=business,   p2e=business): {tp}
")
    report_lines.append(f"- False Negatives (manual=business,   p2e=individual): {fn}
")
    report_lines.append(f"- False Positives (manual=individual, p2e=business): {fp}
")
    report_lines.append(f"- True Negatives  (manual=individual, p2e=individual): {tn}
")

    report_lines.append("
## 5. Interpretation
")
    report_lines.append("Accuracy measures the overall share of correct P2E classifications among comparable rows.
")
    report_lines.append("Precision on `business` measures how often P2E is correct when it predicts `business`.
")
    report_lines.append("Recall on `business` measures how many real `business` beneficiaries are correctly identified by P2E.
")
    report_lines.append("Balanced accuracy is useful when the dataset is imbalanced between `business` and `individual`.
")

    report_lines.append("
## 6. Output Files
")
    report_lines.append("- `kpi_summary.csv`: one-line summary of all main KPIs.
")
    report_lines.append("- `confusion_matrix.csv`: matrix of manual vs P2E classifications.
")
    report_lines.append("- `p2e_distribution.csv`: class distribution predicted by P2E.
")
    report_lines.append("- `manual_distribution.csv`: class distribution in manual ground truth.
")
    report_lines.append("- `mismatch_details.csv`: row-level mismatches between P2E and manual classification.
")
    report_lines.append("- `invalid_rows.csv`: excluded rows with invalid or missing labels.
")

    with open(output_dir / "detailed_report.md", "w", encoding="utf-8") as f:
        f.write("".join(report_lines))

    with open(output_dir / "kpi_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"Report generated in: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
