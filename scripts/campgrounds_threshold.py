#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


# --------------------------------------------------
# Function to calculate row-level and scenario-level exposure
# --------------------------------------------------

def calculate_summary(df):
    """
    Calculate:
    1. row-level affected portion
    2. row-level affected percentage
    3. scenario-level total affected percentage
    """

    df = df.copy()
    df.columns = df.columns.str.strip()

    required_cols = [
        "group",
        "level",
        "count",
        "scenario",
        "mobile_total",
        "non_mobile_total",
    ]

    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    df["group"] = df["group"].astype(str).str.strip()

    df["portion_affected"] = np.where(
        df["group"].eq("mobile"),
        df["count"] / df["mobile_total"],
        df["count"] / df["non_mobile_total"],
    )

    df["percentage_affected"] = df["portion_affected"] * 100
    df["percentage_affected_round"] = df["percentage_affected"].round(2)

    summary_df = (
        df.groupby("scenario", as_index=False)
        .agg(
            total_affected=("count", "sum"),
            mobile_total=("mobile_total", "first"),
            non_mobile_total=("non_mobile_total", "first"),
        )
    )

    summary_df["total_exposed"] = (
        summary_df["mobile_total"] + summary_df["non_mobile_total"]
    )

    summary_df["portion_affected_total"] = (
        summary_df["total_affected"] / summary_df["total_exposed"]
    )

    summary_df["percentage_affected_total"] = (
        summary_df["portion_affected_total"] * 100
    )

    summary_df["percentage_affected_total_round"] = (
        summary_df["percentage_affected_total"].round(2)
    )

    summary_df = summary_df.sort_values("scenario").reset_index(drop=True)

    return df, summary_df


# --------------------------------------------------
# Helper function: find mathematical elbow
# --------------------------------------------------

def find_elbow_index(df, start_idx, end_idx, x_col, y_col):
    """
    Finds the point with maximum perpendicular distance from the line
    connecting start_idx and end_idx.

    If several points have almost the same maximum distance,
    the later point is selected.
    """

    candidate_df = df.loc[start_idx:end_idx].copy()

    x = candidate_df[x_col].values
    y = candidate_df[y_col].values

    x1 = df.loc[start_idx, x_col]
    y1 = df.loc[start_idx, y_col]

    x3 = df.loc[end_idx, x_col]
    y3 = df.loc[end_idx, y_col]

    denominator = np.sqrt((y3 - y1) ** 2 + (x3 - x1) ** 2)

    if denominator == 0:
        candidate_df["elbow_distance"] = 0.0
    else:
        candidate_df["elbow_distance"] = np.abs(
            (y3 - y1) * x
            - (x3 - x1) * y
            + x3 * y1
            - y3 * x1
        ) / denominator

    candidate_df["is_endpoint"] = (
        (candidate_df.index == start_idx)
        | (candidate_df.index == end_idx)
    )

    candidate_df["is_internal_candidate"] = ~candidate_df["is_endpoint"]

    internal_candidates = candidate_df.loc[
        candidate_df["is_internal_candidate"]
    ].copy()

    if len(internal_candidates) == 0:
        candidate_df["is_selected_elbow"] = False
        return None, candidate_df

    max_distance = internal_candidates["elbow_distance"].max()

    elbow_idx = internal_candidates.loc[
        np.isclose(internal_candidates["elbow_distance"], max_distance)
    ].index.max()

    candidate_df["is_selected_elbow"] = candidate_df.index == elbow_idx

    return elbow_idx, candidate_df


# --------------------------------------------------
# Function to define impact levels using corrected preventive nested-elbow method
# --------------------------------------------------

def define_impact_levels(summary_df):
    """
    Preparedness-oriented levels using corrected preventive nested-elbow method.

    Level 1:
        First scenario with at least one affected exposed unit.

    Level 3:
        Normally the scenario immediately before the main mathematical elbow.
        However, if this makes Level 3 equal to Level 2, Level 3 is set to the
        real main mathematical elbow.

    Level 2:
        Scenario immediately before the intermediate mathematical elbow between
        Level 1 and Level 3.
    """

    summary_df = summary_df.copy().sort_values("scenario").reset_index(drop=True)

    summary_df["increase_fraction"] = summary_df["portion_affected_total"].diff()
    summary_df["increase_percentage_points"] = (
        summary_df["percentage_affected_total"].diff()
    )
    summary_df["acceleration_pp"] = summary_df["increase_percentage_points"].diff()
    summary_df["previous_increase_pp"] = (
        summary_df["increase_percentage_points"].shift(1)
    )

    # --------------------------------------------------
    # Level 1
    # --------------------------------------------------

    affected_rows = summary_df.loc[summary_df["total_affected"] > 0]

    if affected_rows.empty:
        levels_df = pd.DataFrame(
            {
                "impact_level": [1, 2, 3],
                "scenario": [np.nan, np.nan, np.nan],
                "percentage_affected": [np.nan, np.nan, np.nan],
                "percentage_affected_round": [np.nan, np.nan, np.nan],
                "increase_from_previous_pp": [np.nan, np.nan, np.nan],
                "criterion": [
                    "No affected exposed unit in any scenario",
                    "No affected exposed unit in any scenario",
                    "No affected exposed unit in any scenario",
                ],
                "reference_elbow_scenario": [np.nan, np.nan, np.nan],
                "reference_elbow_percentage_affected": [np.nan, np.nan, np.nan],
                "reference_elbow_percentage_affected_round": [np.nan, np.nan, np.nan],
            }
        )

        empty_distance_df = pd.DataFrame()
        return summary_df, levels_df, empty_distance_df, empty_distance_df

    level_1_row = affected_rows.iloc[0]
    idx_level_1 = level_1_row.name

    if len(summary_df) < 3:
        levels_df = pd.DataFrame(
            {
                "impact_level": [1, 2, 3],
                "scenario": [level_1_row["scenario"], np.nan, np.nan],
                "percentage_affected": [
                    level_1_row["percentage_affected_total"],
                    np.nan,
                    np.nan,
                ],
                "percentage_affected_round": [
                    level_1_row["percentage_affected_total_round"],
                    np.nan,
                    np.nan,
                ],
                "increase_from_previous_pp": [
                    level_1_row["increase_percentage_points"],
                    np.nan,
                    np.nan,
                ],
                "criterion": [
                    "Onset of impact: first scenario with at least one affected exposed unit",
                    "Not enough scenarios to define Level 2",
                    "Not enough scenarios to define Level 3",
                ],
                "reference_elbow_scenario": [np.nan, np.nan, np.nan],
                "reference_elbow_percentage_affected": [np.nan, np.nan, np.nan],
                "reference_elbow_percentage_affected_round": [np.nan, np.nan, np.nan],
            }
        )

        empty_distance_df = pd.DataFrame()
        return summary_df, levels_df, empty_distance_df, empty_distance_df

    # --------------------------------------------------
    # Main mathematical elbow for Level 3
    # --------------------------------------------------

    idx_last = summary_df.index.max()

    idx_main_elbow, main_elbow_df = find_elbow_index(
        df=summary_df,
        start_idx=idx_level_1,
        end_idx=idx_last,
        x_col="scenario",
        y_col="percentage_affected_total",
    )

    if idx_main_elbow is None:
        idx_level_3 = min(idx_level_1 + 2, idx_last)

        main_elbow_row = pd.Series(
            {
                "scenario": np.nan,
                "percentage_affected_total": np.nan,
                "percentage_affected_total_round": np.nan,
            }
        )

        level_3_rule = (
            "Fallback high threshold: not enough internal points for main elbow; "
            "selected a later available scenario"
        )

    else:
        main_elbow_row = summary_df.loc[idx_main_elbow]

        idx_level_3 = max(idx_main_elbow - 1, idx_level_1 + 1)

        level_3_rule = (
            "Preventive high threshold: scenario immediately before the main mathematical elbow"
        )

    level_3_row = summary_df.loc[idx_level_3]

    # --------------------------------------------------
    # Intermediate mathematical elbow for Level 2
    # --------------------------------------------------

    idx_intermediate_elbow, intermediate_elbow_df = find_elbow_index(
        df=summary_df,
        start_idx=idx_level_1,
        end_idx=idx_level_3,
        x_col="scenario",
        y_col="percentage_affected_total",
    )

    if idx_intermediate_elbow is None:
        idx_level_2 = min(idx_level_1 + 1, idx_level_3)

        intermediate_elbow_row = pd.Series(
            {
                "scenario": np.nan,
                "percentage_affected_total": np.nan,
                "percentage_affected_total_round": np.nan,
            }
        )

        level_2_rule = (
            "Fallback intermediate threshold: first scenario after Level 1 because "
            "no internal point was available for the intermediate elbow"
        )

    else:
        intermediate_elbow_row = summary_df.loc[idx_intermediate_elbow]

        idx_level_2 = max(idx_intermediate_elbow - 1, idx_level_1 + 1)

        level_2_rule = (
            "Preventive intermediate threshold: scenario immediately before the "
            "intermediate mathematical elbow between Level 1 and Level 3"
        )

    # --------------------------------------------------
    # Correction: avoid Level 2 and Level 3 being identical
    # --------------------------------------------------

    if idx_level_3 <= idx_level_2 and idx_main_elbow is not None:
        idx_level_3 = idx_main_elbow
        level_3_row = summary_df.loc[idx_level_3]

        level_3_rule = (
            "Main mathematical elbow selected as Level 3 because the preventive shift "
            "would make Level 3 equal to Level 2"
        )

        idx_intermediate_elbow, intermediate_elbow_df = find_elbow_index(
            df=summary_df,
            start_idx=idx_level_1,
            end_idx=idx_level_3,
            x_col="scenario",
            y_col="percentage_affected_total",
        )

        if idx_intermediate_elbow is None:
            idx_level_2 = min(idx_level_1 + 1, idx_level_3 - 1)

            intermediate_elbow_row = pd.Series(
                {
                    "scenario": np.nan,
                    "percentage_affected_total": np.nan,
                    "percentage_affected_total_round": np.nan,
                }
            )

            level_2_rule = (
                "Fallback intermediate threshold: first scenario after Level 1 because "
                "no internal point was available after correcting Level 3"
            )

        else:
            intermediate_elbow_row = summary_df.loc[idx_intermediate_elbow]
            idx_level_2 = max(idx_intermediate_elbow - 1, idx_level_1 + 1)

            if idx_level_2 >= idx_level_3:
                idx_level_2 = max(idx_level_3 - 1, idx_level_1 + 1)

            level_2_rule = (
                "Preventive intermediate threshold recalculated after selecting the "
                "main elbow as Level 3"
            )

    level_2_row = summary_df.loc[idx_level_2]
    level_3_row = summary_df.loc[idx_level_3]

    # --------------------------------------------------
    # Add elbow distances to summary_df
    # --------------------------------------------------

    summary_df["main_elbow_distance"] = np.nan
    summary_df.loc[main_elbow_df.index, "main_elbow_distance"] = (
        main_elbow_df["elbow_distance"]
    )
    summary_df["main_elbow_distance_round"] = (
        summary_df["main_elbow_distance"].round(4)
    )

    summary_df["intermediate_elbow_distance"] = np.nan
    summary_df.loc[intermediate_elbow_df.index, "intermediate_elbow_distance"] = (
        intermediate_elbow_df["elbow_distance"]
    )
    summary_df["intermediate_elbow_distance_round"] = (
        summary_df["intermediate_elbow_distance"].round(4)
    )

    # --------------------------------------------------
    # Distance table for L3
    # --------------------------------------------------

    main_elbow_distances_df = main_elbow_df[
        [
            "scenario",
            "percentage_affected_total",
            "percentage_affected_total_round",
            "elbow_distance",
            "is_endpoint",
            "is_internal_candidate",
            "is_selected_elbow",
        ]
    ].copy()

    main_elbow_distances_df["distance_value"] = (
        main_elbow_distances_df["elbow_distance"]
    )
    main_elbow_distances_df["distance_value_round"] = (
        main_elbow_distances_df["elbow_distance"].round(4)
    )

    main_elbow_distances_df["purpose"] = (
        "Main elbow used as reference for preventive Level 3"
    )

    main_elbow_distances_df["reference_line"] = (
        f"L1 to maximum scenario: "
        f"({level_1_row['scenario']}, {level_1_row['percentage_affected_total_round']}) "
        f"to "
        f"({summary_df.iloc[-1]['scenario']}, {summary_df.iloc[-1]['percentage_affected_total_round']})"
    )

    main_elbow_distances_df["reference_endpoint_start_scenario"] = (
        level_1_row["scenario"]
    )
    main_elbow_distances_df["reference_endpoint_start_percentage"] = (
        level_1_row["percentage_affected_total"]
    )
    main_elbow_distances_df["reference_endpoint_end_scenario"] = (
        summary_df.iloc[-1]["scenario"]
    )
    main_elbow_distances_df["reference_endpoint_end_percentage"] = (
        summary_df.iloc[-1]["percentage_affected_total"]
    )

    main_elbow_distances_df["preventive_level_selected"] = (
        main_elbow_distances_df["scenario"] == level_3_row["scenario"]
    )

    main_elbow_distances_df = main_elbow_distances_df.rename(
        columns={"elbow_distance": "distance_to_L1_max_line"}
    )

    # --------------------------------------------------
    # Distance table for L2
    # --------------------------------------------------

    intermediate_elbow_distances_df = intermediate_elbow_df[
        [
            "scenario",
            "percentage_affected_total",
            "percentage_affected_total_round",
            "elbow_distance",
            "is_endpoint",
            "is_internal_candidate",
            "is_selected_elbow",
        ]
    ].copy()

    intermediate_elbow_distances_df["distance_value"] = (
        intermediate_elbow_distances_df["elbow_distance"]
    )
    intermediate_elbow_distances_df["distance_value_round"] = (
        intermediate_elbow_distances_df["elbow_distance"].round(4)
    )

    intermediate_elbow_distances_df["purpose"] = (
        "Intermediate elbow used as reference for preventive Level 2"
    )

    intermediate_elbow_distances_df["reference_line"] = (
        f"L1 to Level 3: "
        f"({level_1_row['scenario']}, {level_1_row['percentage_affected_total_round']}) "
        f"to "
        f"({level_3_row['scenario']}, {level_3_row['percentage_affected_total_round']})"
    )

    intermediate_elbow_distances_df["reference_endpoint_start_scenario"] = (
        level_1_row["scenario"]
    )
    intermediate_elbow_distances_df["reference_endpoint_start_percentage"] = (
        level_1_row["percentage_affected_total"]
    )
    intermediate_elbow_distances_df["reference_endpoint_end_scenario"] = (
        level_3_row["scenario"]
    )
    intermediate_elbow_distances_df["reference_endpoint_end_percentage"] = (
        level_3_row["percentage_affected_total"]
    )

    intermediate_elbow_distances_df["preventive_level_selected"] = (
        intermediate_elbow_distances_df["scenario"] == level_2_row["scenario"]
    )

    intermediate_elbow_distances_df = intermediate_elbow_distances_df.rename(
        columns={"elbow_distance": "distance_to_L1_L3_line"}
    )

    # --------------------------------------------------
    # Levels dataframe
    # --------------------------------------------------

    levels_df = pd.DataFrame(
        {
            "impact_level": [1, 2, 3],
            "scenario": [
                level_1_row["scenario"],
                level_2_row["scenario"],
                level_3_row["scenario"],
            ],
            "percentage_affected": [
                level_1_row["percentage_affected_total"],
                level_2_row["percentage_affected_total"],
                level_3_row["percentage_affected_total"],
            ],
            "percentage_affected_round": [
                level_1_row["percentage_affected_total_round"],
                level_2_row["percentage_affected_total_round"],
                level_3_row["percentage_affected_total_round"],
            ],
            "increase_from_previous_pp": [
                level_1_row["increase_percentage_points"],
                level_2_row["increase_percentage_points"],
                level_3_row["increase_percentage_points"],
            ],
            "criterion": [
                "Onset of impact: first scenario with at least one affected exposed unit",
                level_2_rule,
                level_3_rule,
            ],
            "reference_elbow_scenario": [
                np.nan,
                intermediate_elbow_row["scenario"],
                main_elbow_row["scenario"],
            ],
            "reference_elbow_percentage_affected": [
                np.nan,
                intermediate_elbow_row["percentage_affected_total"],
                main_elbow_row["percentage_affected_total"],
            ],
            "reference_elbow_percentage_affected_round": [
                np.nan,
                intermediate_elbow_row["percentage_affected_total_round"],
                main_elbow_row["percentage_affected_total_round"],
            ],
        }
    )

    return (
        summary_df,
        levels_df,
        main_elbow_distances_df,
        intermediate_elbow_distances_df,
    )


# --------------------------------------------------
# Function to process one campground
# --------------------------------------------------

def process_campground(base_dir, campground_name):
    """
    Example:
    campground_name = 'Aaregg'

    Expected file:
    /storage/homefs/ge24z347/exposure_results_campgrounds/
    Aaregg_2m_v2/Aaregg_2m_v2_exposure.xlsx
    """

    folder_name = f"{campground_name}_2m_v2"
    file_name = f"{campground_name}_2m_v2_exposure.xlsx"

    file_path = base_dir / folder_name / file_name

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    print(f"Processing: {campground_name}")
    print(f"Reading: {file_path}")

    df = pd.read_excel(file_path, sheet_name=0)

    row_df, summary_df = calculate_summary(df)

    (
        summary_df,
        levels_df,
        main_elbow_distances_df,
        intermediate_elbow_distances_df,
    ) = define_impact_levels(summary_df)

    row_df.insert(0, "campground", campground_name)
    summary_df.insert(0, "campground", campground_name)
    levels_df.insert(0, "campground", campground_name)

    if not main_elbow_distances_df.empty:
        main_elbow_distances_df.insert(0, "campground", campground_name)

    if not intermediate_elbow_distances_df.empty:
        intermediate_elbow_distances_df.insert(0, "campground", campground_name)

    wide_levels = {
        "campground": campground_name,
    }

    for _, row in levels_df.iterrows():
        level = int(row["impact_level"])

        wide_levels[f"L{level}_scenario"] = row["scenario"]
        wide_levels[f"L{level}_percentage_affected"] = row["percentage_affected"]
        wide_levels[f"L{level}_percentage_affected_round"] = row[
            "percentage_affected_round"
        ]
        wide_levels[f"L{level}_increase_from_previous_pp"] = row[
            "increase_from_previous_pp"
        ]
        wide_levels[f"L{level}_criterion"] = row["criterion"]
        wide_levels[f"L{level}_reference_elbow_scenario"] = row[
            "reference_elbow_scenario"
        ]
        wide_levels[f"L{level}_reference_elbow_percentage_affected"] = row[
            "reference_elbow_percentage_affected"
        ]
        wide_levels[f"L{level}_reference_elbow_percentage_affected_round"] = row[
            "reference_elbow_percentage_affected_round"
        ]

    wide_levels_df = pd.DataFrame([wide_levels])

    return (
        row_df,
        summary_df,
        levels_df,
        wide_levels_df,
        main_elbow_distances_df,
        intermediate_elbow_distances_df,
    )


# --------------------------------------------------
# Main script
# --------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Calculate preparedness-oriented impact levels for campground exposure files "
            "using the corrected preventive nested-elbow method."
        )
    )

    parser.add_argument(
        "--base-dir",
        type=str,
        default="/storage/homefs/ge24z347/exposure_results_campgrounds/",
        help="Base directory containing campground folders.",
    )

    parser.add_argument(
        "--campgrounds",
        nargs="+",
        required=True,
        help=(
            "Campground names without '_2m_v2'. "
            "Example: Aaregg Sempach Bern Salavaux Gordevio Muzzano"
        ),
    )

    parser.add_argument(
        "--output",
        type=str,
        default="campground_impact_levels_summary.xlsx",
        help="Output Excel file name.",
    )

    args = parser.parse_args()

    base_dir = Path(args.base_dir)

    all_row_results = []
    all_scenario_summaries = []
    all_long_levels = []
    all_wide_levels = []
    all_main_elbow_distances = []
    all_intermediate_elbow_distances = []

    failed = []

    for campground in args.campgrounds:
        try:
            (
                row_df,
                summary_df,
                levels_df,
                wide_levels_df,
                main_elbow_distances_df,
                intermediate_elbow_distances_df,
            ) = process_campground(base_dir, campground)

            all_row_results.append(row_df)
            all_scenario_summaries.append(summary_df)
            all_long_levels.append(levels_df)
            all_wide_levels.append(wide_levels_df)

            if not main_elbow_distances_df.empty:
                all_main_elbow_distances.append(main_elbow_distances_df)

            if not intermediate_elbow_distances_df.empty:
                all_intermediate_elbow_distances.append(
                    intermediate_elbow_distances_df
                )

        except Exception as e:
            print(f"FAILED: {campground}")
            print(f"Reason: {e}")
            failed.append({"campground": campground, "error": str(e)})

    if not all_wide_levels:
        raise RuntimeError("No campground was processed successfully.")

    row_results_all = pd.concat(all_row_results, ignore_index=True)
    scenario_summary_all = pd.concat(all_scenario_summaries, ignore_index=True)
    levels_long_all = pd.concat(all_long_levels, ignore_index=True)
    levels_wide_all = pd.concat(all_wide_levels, ignore_index=True)

    if all_main_elbow_distances:
        main_elbow_distances_all = pd.concat(
            all_main_elbow_distances,
            ignore_index=True,
        )
    else:
        main_elbow_distances_all = pd.DataFrame()

    if all_intermediate_elbow_distances:
        intermediate_elbow_distances_all = pd.concat(
            all_intermediate_elbow_distances,
            ignore_index=True,
        )
    else:
        intermediate_elbow_distances_all = pd.DataFrame()

    failed_df = pd.DataFrame(failed)

    output_path = base_dir / args.output

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        levels_wide_all.to_excel(writer, sheet_name="impact_levels_wide", index=False)
        levels_long_all.to_excel(writer, sheet_name="impact_levels_long", index=False)
        scenario_summary_all.to_excel(writer, sheet_name="scenario_summary", index=False)
        row_results_all.to_excel(writer, sheet_name="row_level_results", index=False)

        if not main_elbow_distances_all.empty:
            main_elbow_distances_all.to_excel(
                writer,
                sheet_name="main_elbow_distances",
                index=False,
            )

        if not intermediate_elbow_distances_all.empty:
            intermediate_elbow_distances_all.to_excel(
                writer,
                sheet_name="intermediate_distances",
                index=False,
            )

        if not failed_df.empty:
            failed_df.to_excel(writer, sheet_name="failed_files", index=False)

    print("\nDone.")
    print(f"Saved output to:\n{output_path}")

    if failed:
        print("\nSome files failed:")
        for item in failed:
            print(f"- {item['campground']}: {item['error']}")


if __name__ == "__main__":
    main()