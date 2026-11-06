"""Train a daily, activity-only OULAD classifier in a separate artifact directory."""
import argparse
import hashlib
import json
import platform
from pathlib import Path
from zipfile import ZipFile

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from train_oulad import KEY, ROOT, SEED, choose_threshold, csv, group_split, metrics
from app.engagement_features import FEATURES, MAX_DAY, MIN_DAY, SCHEMA, STAGES, feature_values


def snapshots(archive_path):
    with ZipFile(archive_path) as archive:
        eligible = csv(archive, 'studentInfo.csv')
        eligible = eligible[eligible.final_result.isin(['Fail', 'Pass', 'Distinction'])][KEY + ['final_result']].copy()
        eligible['label'] = (eligible.final_result == 'Fail').astype(int)
        eligible = eligible.merge(csv(archive, 'studentRegistration.csv')[KEY + ['date_registration']],
                                  on=KEY, validate='one_to_one')
        eligible['date_registration'] = pd.to_numeric(eligible.date_registration, errors='coerce')
        eligible = eligible.merge(csv(archive, 'courses.csv'), on=KEY[:2], validate='many_to_one')
        eligible = eligible.sort_values(KEY).reset_index(drop=True)
        active, first = [], []
        with archive.open('studentVle.csv') as handle:
            for chunk in pd.read_csv(handle, chunksize=500_000):
                valid = chunk[chunk.date.between(MIN_DAY, MAX_DAY) & (chunk.sum_click > 0)]
                active.append(valid[KEY + ['date']].drop_duplicates())
                first.append(valid.groupby(KEY + ['id_site'], as_index=False).date.min())
    index = pd.MultiIndex.from_frame(eligible[KEY])
    days = np.arange(MIN_DAY, MAX_DAY + 1)
    active = pd.concat(active).drop_duplicates()
    resources = pd.concat(first).groupby(KEY + ['id_site'], as_index=False).date.min()
    resources = resources.groupby(KEY + ['date'], as_index=False).size()
    activity = active.assign(count=1).pivot(index=KEY, columns='date', values='count')
    activity = activity.reindex(index=index, columns=days).fillna(0).to_numpy(dtype=int)
    resource_counts = resources.pivot(index=KEY, columns='date', values='size')
    resource_counts = resource_counts.reindex(index=index, columns=days).fillna(0).to_numpy(dtype=int)
    cumulative = activity.cumsum(axis=1)
    last = np.maximum.accumulate(np.where(activity > 0, days, -1), axis=1)
    distinct = resource_counts.cumsum(axis=1)
    frames = []
    for day in days:
        current = eligible[KEY + ['label']].assign(day=day)
        current = current.assign(**feature_values(day, cumulative[:, day],
            activity[:, max(0, day - 6):day + 1].sum(axis=1), last[:, day], distinct[:, day]))
        observed = eligible.date_registration.le(day) & eligible.module_presentation_length.gt(day)
        frames.append(current[observed])
    return pd.concat(frames, ignore_index=True)


def stage_report(frame, probabilities, threshold):
    result = {}
    for lower, upper in STAGES:
        mask = frame.day.between(lower, upper).to_numpy()
        part = frame[mask]
        report = metrics(part.label, probabilities[mask], threshold)
        report.update(students=int(part.id_student.nunique()), active_fraction=float((part.active_days > 0).mean()))
        result[f'{lower}-{upper}'] = report
    return result


def train(dataset, output):
    frame = snapshots(dataset)
    splits = group_split(frame)
    x, y = frame[FEATURES].to_numpy(dtype=float), frame.label.to_numpy()
    training, validation, test = (splits[name] for name in ('train', 'validation', 'test'))
    candidates = []
    for name, pipeline in [
        ('logistic', Pipeline([('scale', StandardScaler()), ('classifier', LogisticRegression(max_iter=500))])),
        ('xgboost', Pipeline([('classifier', xgboost.XGBClassifier(n_estimators=150, max_depth=3,
            learning_rate=.05, random_state=SEED, n_jobs=4, tree_method='hist'))])),
    ]:
        pipeline.fit(x[training], y[training])
        probabilities = pipeline.predict_proba(x[validation])[:, 1]
        threshold = choose_threshold(y[validation], probabilities)
        report = metrics(y[validation], probabilities, threshold)
        stages = stage_report(frame.iloc[validation], probabilities, threshold)
        candidates.append((name, pipeline, threshold, report, stages))
    name, model, threshold, validation_report, validation_stages = max(candidates,
        key=lambda candidate: (candidate[3]['f1'], -candidate[3]['brier']))
    # Freeze support using validation alone. Require discrimination above chance and both classes.
    ranges = [[lower, upper] for lower, upper in STAGES
              if (validation_stages[f'{lower}-{upper}']['roc_auc'] or 0) >= .55]
    probabilities = model.predict_proba(x[test])[:, 1]
    test_stages = stage_report(frame.iloc[test], probabilities, threshold)
    for lower, upper in STAGES:
        test_stages[f'{lower}-{upper}']['served_fraction'] = int([lower, upper] in ranges)
    output.mkdir(parents=True, exist_ok=True)
    background = x[np.random.default_rng(SEED).choice(training, size=8, replace=False)]
    artifact = output / 'model.joblib'
    joblib.dump({'model': model, 'background': background}, artifact, compress=3)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest = dict(artifact_version=1, code=f'oulad_{name}_daily_{digest[:12]}', artifact_sha256=digest,
        feature_schema_version=SCHEMA, feature_order=FEATURES, feature_set='activity_daily',
        supported_ranges=ranges, class_mapping={'0': 'Pass/Distinction', '1': 'Fail'},
        threshold=threshold, threshold_source='validation_max_fail_f1', calibration_status='uncalibrated',
        output_space='raw_probability', transport_status='unvalidated',
        libraries={'python': platform.python_version(), 'numpy': np.__version__, 'sklearn': sklearn.__version__,
                   'xgboost': xgboost.__version__, 'joblib': joblib.__version__})
    report = dict(dataset_sha256=hashlib.sha256(dataset.read_bytes()).hexdigest(), seed=SEED,
        model=name, threshold=threshold, supported_ranges=ranges,
        support_policy='validation ROC-AUC >= 0.55 per stage',
        split={name: dict(snapshots=len(rows), students=int(frame.iloc[rows].id_student.nunique()))
               for name, rows in splits.items()},
        validation=validation_report, validation_stages=validation_stages,
        test=metrics(y[test], probabilities, threshold), test_stages=test_stages,
        test_served_fraction=float(np.logical_or.reduce([frame.iloc[test].day.between(lo, hi).to_numpy()
                                                        for lo, hi in ranges]).mean()) if ranges else 0,
        candidates={candidate[0]: candidate[3] for candidate in candidates})
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (output / 'evaluation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('model', 'supported_ranges', 'split', 'test_stages')}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'ml/data/oulad.zip')
    parser.add_argument('--output', type=Path, default=ROOT / 'ml/artifacts/engagement')
    args = parser.parse_args()
    if args.output.resolve() == (ROOT / 'ml/artifacts/current').resolve():
        parser.error('Choose an output directory separate from the day-42 artifact.')
    train(args.dataset, args.output)
