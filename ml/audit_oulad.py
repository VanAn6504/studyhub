"""Audit early prediction feasibility in the original OULAD CSV archive.

Run: python ml/audit_oulad.py
Requires pandas. The downloaded archive stays in ml/data/ and is gitignored.
"""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pandas as pd


ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT / "data" / "oulad.zip"
OUTPUT = ROOT / "oulad_audit.json"
KEY = ["code_module", "code_presentation", "id_student"]
CUTOFFS = (28, 42)


def read_csv(archive: ZipFile, name: str) -> pd.DataFrame:
    with archive.open(name) as handle:
        return pd.read_csv(handle)


def as_percent(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 1) if denominator else 0.0


with ZipFile(ARCHIVE) as archive:
    students = read_csv(archive, "studentInfo.csv")
    assessments = read_csv(archive, "assessments.csv")
    submissions = read_csv(archive, "studentAssessment.csv")
    registration = read_csv(archive, "studentRegistration.csv")
    vle = read_csv(archive, "vle.csv")

    labels = students["final_result"].value_counts(dropna=False).to_dict()
    eligible = students.loc[students.final_result.isin(["Fail", "Pass", "Distinction"]), KEY + ["final_result"]].copy()

    scored = submissions.merge(
        assessments[["id_assessment", "code_module", "code_presentation", "assessment_type", "date"]],
        on="id_assessment",
        how="left",
        validate="many_to_one",
    )
    scored["score"] = pd.to_numeric(scored["score"], errors="coerce")
    scored = scored.loc[(scored.is_banked == 0) & scored.score.notna() & (scored.date_submitted >= 0)].copy()
    scored = scored.merge(eligible[KEY], on=KEY, how="inner", validate="many_to_one")

    result = {
        "source": "UCI OULAD dataset 349, CC BY 4.0",
        "student_course_rows": len(students),
        "unique_students": int(students.id_student.nunique()),
        "labels": {str(k): int(v) for k, v in labels.items()},
        "eligible_fail_vs_pass_distinction": len(eligible),
        "assessment_types": {str(k): int(v) for k, v in assessments.assessment_type.value_counts().items()},
        "vle_activity_types": {str(k): int(v) for k, v in vle.activity_type.value_counts().items()},
        "cutoffs": {},
    }

    for day in CUTOFFS:
        before = scored.loc[scored.date_submitted <= day]
        per_student = before.groupby(KEY, observed=True).agg(
            scored_assessments=("score", "count"),
            mean_score=("score", "mean"),
        )
        one = int((per_student.scored_assessments >= 1).sum())
        two = int((per_student.scored_assessments >= 2).sum())
        cma_students = int(before.loc[before.assessment_type == "CMA", KEY].drop_duplicates().shape[0])
        by_course = (
            eligible.groupby(["code_module", "code_presentation"], observed=True)
            .size()
            .rename("eligible")
            .to_frame()
            .join(per_student.groupby(level=[0, 1]).size().rename("with_score"), how="left")
            .fillna({"with_score": 0})
        )
        result["cutoffs"][str(day)] = {
            "eligible_rows": len(eligible),
            "with_at_least_one_score": one,
            "with_at_least_one_score_pct": as_percent(one, len(eligible)),
            "with_at_least_two_scores": two,
            "with_at_least_two_scores_pct": as_percent(two, len(eligible)),
            "with_cma_score": cma_students,
            "with_cma_score_pct": as_percent(cma_students, len(eligible)),
            "course_presentations_with_no_scores": int((by_course.with_score == 0).sum()),
            "course_presentations": len(by_course),
            "score_coverage_by_presentation": {
                f"{module}-{presentation}": as_percent(int(row.with_score), int(row.eligible))
                for (module, presentation), row in by_course.iterrows()
            },
        }

    result["registration_columns"] = registration.columns.tolist()
    result["student_info_columns"] = students.columns.tolist()
    result["student_assessment_columns"] = submissions.columns.tolist()
    result["student_vle_columns"] = ["code_module", "code_presentation", "id_student", "id_site", "date", "sum_click"]

    eligible_keys = set(eligible[KEY].itertuples(index=False, name=None))
    active_keys = {day: set() for day in CUTOFFS}
    event_counts = {day: 0 for day in CUTOFFS}
    with archive.open("studentVle.csv") as handle:
        for chunk in pd.read_csv(handle, chunksize=500_000):
            early = chunk.loc[(chunk.date >= 0) & (chunk.date <= max(CUTOFFS))]
            for day in CUTOFFS:
                period = early.loc[early.date <= day]
                event_counts[day] += len(period)
                active_keys[day].update(period[KEY].drop_duplicates().itertuples(index=False, name=None))
    for day in CUTOFFS:
        active_eligible = len(active_keys[day] & eligible_keys)
        result["cutoffs"][str(day)]["with_vle_activity"] = active_eligible
        result["cutoffs"][str(day)]["with_vle_activity_pct"] = as_percent(active_eligible, len(eligible))
        result["cutoffs"][str(day)]["vle_event_rows"] = event_counts[day]

OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: result[k] for k in ("student_course_rows", "unique_students", "labels", "eligible_fail_vs_pass_distinction", "cutoffs")}, ensure_ascii=False, indent=2))
