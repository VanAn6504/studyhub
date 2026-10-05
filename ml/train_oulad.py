"""Reproducible OULAD A/B at day28/42; grouped splits, validation-only selection.

Run from the repo: backend/.venv/Scripts/python.exe ml/train_oulad.py
Outputs are private, ignored artifacts; never load a joblib received from others.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path
from zipfile import ZipFile

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import brier_score_loss, confusion_matrix, precision_recall_curve, precision_recall_fscore_support, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.features import FEATURES_A, FEATURES_B, SCHEMA_VERSION  # noqa: E402

KEY = ['code_module', 'code_presentation', 'id_student']
SEED = 20261005


def csv(archive, name):
    with archive.open(name) as handle:
        return pd.read_csv(handle)


def build_features(archive_path, cutoffs=(28, 42), chunksize=500_000):
    """Never select by activity/score coverage; labels stay outside feature arrays."""
    with ZipFile(archive_path) as archive:
        students = csv(archive, 'studentInfo.csv')
        if students.duplicated(KEY).any():
            raise ValueError('Duplicate student-course key')
        eligible = students[students.final_result.isin(['Fail', 'Pass', 'Distinction'])][KEY + ['final_result']].copy()
        eligible['label'] = (eligible.final_result == 'Fail').astype(int)
        eligible = eligible.sort_values(KEY).reset_index(drop=True)
        assessments = csv(archive, 'assessments.csv')
        scores = csv(archive, 'studentAssessment.csv').merge(assessments[['id_assessment', 'code_module', 'code_presentation']],
            on='id_assessment', validate='many_to_one')
        scores['score'] = pd.to_numeric(scores.score, errors='coerce')
        scores = scores[(scores.is_banked == 0) & scores.score.between(0, 100) & (scores.date_submitted >= 0)]
        scores = scores.sort_values(['date_submitted', 'id_assessment', 'id_student'], kind='stable')
        scores = scores.drop_duplicates(KEY + ['id_assessment'], keep='first')
        daily_parts = []
        with archive.open('studentVle.csv') as handle:
            for chunk in pd.read_csv(handle, chunksize=chunksize):
                valid = chunk[(chunk.date >= 0) & (chunk.date <= max(cutoffs)) & (chunk.sum_click > 0)]
                daily_parts.append(valid.groupby(KEY + ['date'], observed=True).sum_click.sum())
        daily = pd.concat(daily_parts).groupby(level=[0, 1, 2, 3]).sum().rename('clicks').reset_index()
    frames = {}
    for cutoff in cutoffs:
        activity = daily[daily.date <= cutoff].groupby(KEY, observed=True).agg(
            active_days=('date', 'nunique'), material_interactions=('clicks', 'sum'), last_day=('date', 'max'))
        scored = scores[scores.date_submitted <= cutoff].groupby(KEY, observed=True).agg(
            assessment_count=('score', 'size'), mean_assessment_score=('score', 'mean'))
        frame = eligible.merge(activity, on=KEY, how='left', validate='one_to_one').merge(scored, on=KEY, how='left', validate='one_to_one')
        frame['days_since_last_activity'] = cutoff - frame.last_day.fillna(-1)
        for field in ['active_days', 'material_interactions', 'assessment_count']:
            frame[field] = frame[field].fillna(0).astype(int)
        frame['has_assessment'] = (frame.assessment_count > 0).astype(int)
        frames[cutoff] = frame[KEY + ['label'] + FEATURES_B]
    return frames, {'source': 'UCI OULAD 349, CC BY 4.0', 'rows': len(students),
        'eligible_rows': len(eligible), 'excluded_withdrawn': int((students.final_result == 'Withdrawn').sum()),
        'labels': {str(k): int(v) for k, v in students.final_result.value_counts().items()},
        'archive_sha256': hashlib.sha256(Path(archive_path).read_bytes()).hexdigest()}


def group_split(frame, seed=SEED):
    trainval, test = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed).split(frame, groups=frame.id_student))
    train_local, validation_local = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=seed + 1)
        .split(frame.iloc[trainval], groups=frame.iloc[trainval].id_student))
    splits = dict(train=trainval[train_local], validation=trainval[validation_local], test=test)
    groups = {name: set(frame.iloc[index].id_student) for name, index in splits.items()}
    assert all(not groups[a] & groups[b] for a, b in [('train', 'validation'), ('train', 'test'), ('validation', 'test')])
    if any(frame.iloc[index].label.nunique() != 2 for index in splits.values()):
        raise ValueError('Each split must contain both classes')
    return splits


def choose_threshold(labels, probabilities):
    precision, recall, thresholds = precision_recall_curve(labels, probabilities)
    f1 = 2 * precision[:-1] * recall[:-1] / np.maximum(precision[:-1] + recall[:-1], 1e-15)
    # Deterministic tie: higher precision, then higher threshold.
    best = max(range(len(thresholds)), key=lambda i: (f1[i], precision[i], thresholds[i]))
    return float(thresholds[best])


def coverage(frame):
    return {'rows': len(frame), 'active_fraction': float((frame.active_days > 0).mean()),
            'assessment_fraction': float(frame.has_assessment.mean())}


def metrics(labels, probabilities, threshold):
    predicted = probabilities >= threshold
    precision, recall, f1, _ = precision_recall_fscore_support(labels, predicted, average='binary', zero_division=0)
    bins = []
    for index in range(10):
        selected = (probabilities >= index / 10) & (probabilities < (index + 1) / 10 if index < 9 else probabilities <= 1)
        if selected.any():
            bins.append(dict(count=int(selected.sum()), mean_score=float(probabilities[selected].mean()),
                             observed_fail_rate=float(np.asarray(labels)[selected].mean())))
    return dict(n=len(labels), fail_count=int(np.asarray(labels).sum()), precision=float(precision), recall=float(recall), f1=float(f1),
        confusion_matrix=confusion_matrix(labels, predicted, labels=[0, 1]).tolist(), confusion_order=['Pass/Distinction', 'Fail'],
        roc_auc=float(roc_auc_score(labels, probabilities)) if len(set(labels)) == 2 else None,
        brier=float(brier_score_loss(labels, probabilities)), reliability_bins=bins,
        expected_calibration_error=sum(b['count'] * abs(b['mean_score'] - b['observed_fail_rate']) for b in bins) / len(labels))


def train(archive_path, output_path):
    frames, dataset = build_features(archive_path)
    splits = group_split(frames[42])
    output_path.mkdir(parents=True, exist_ok=True)
    report = dict(seed=SEED, dataset=dataset, split_strategy='group_by_id_student_60_20_20',
        splits={name: dict(rows=len(index), students=int(frames[42].iloc[index].id_student.nunique()),
                          fail_count=int(frames[42].iloc[index].label.sum())) for name, index in splits.items()},
        limitations=['Same module/presentation can appear across splits; no unseen-presentation validation.',
                     'OULAD score availability is approximated by date_submitted, not actual grading time.',
                     'Uncalibrated scores; Brier/reliability measured, no StudyHub transport validation.',
                     'OULAD clicks and StudyHub page views differ in scale/meaning.'], experiments=[])
    candidates = []
    for cutoff, frame in frames.items():
        for feature_set, names in [('A', FEATURES_A), ('B', FEATURES_B)]:
            x, y = frame[names].to_numpy(dtype=float), frame.label.to_numpy()
            estimators = [('baseline_prior', DummyClassifier(strategy='prior')),
                ('random_forest', RandomForestClassifier(n_estimators=200, max_depth=8, min_samples_leaf=10, random_state=SEED, n_jobs=2)),
                ('xgboost', xgboost.XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.05,
                    subsample=1, colsample_bytree=1, reg_lambda=1, objective='binary:logistic', eval_metric='logloss', random_state=SEED, n_jobs=2))]
            for name, estimator in estimators:
                pipeline = Pipeline([('imputer', SimpleImputer(strategy='median', keep_empty_features=True)), ('classifier', estimator)])
                pipeline.fit(x[splits['train']], y[splits['train']])
                probabilities = pipeline.predict_proba(x[splits['validation']])[:, 1]
                threshold = choose_threshold(y[splits['validation']], probabilities)
                validation = metrics(y[splits['validation']], probabilities, threshold)
                record = dict(cutoff_day=cutoff, feature_set=feature_set, model=name, threshold=threshold,
                    validation=validation, hyperparameters={k: None if isinstance(v, float) and not np.isfinite(v) else v for k, v in estimator.get_params().items()},
                    imputer_statistics=pipeline.named_steps['imputer'].statistics_.tolist())
                candidates.append((record, pipeline, x, y, names))
                print(f"day{cutoff} {feature_set} {name}: validation Fail-F1={validation['f1']:.4f}", flush=True)
    # Freeze model, feature-set and threshold BEFORE reading test predictions.
    eligible = [candidate for candidate in candidates if candidate[0]['cutoff_day'] == 42]
    selected = max(eligible, key=lambda c: (c[0]['validation']['f1'], -c[0]['validation']['brier']))
    report['selected'] = {key: selected[0][key] for key in ['cutoff_day', 'feature_set', 'model', 'threshold']}
    for record, pipeline, x, y, names in candidates:
        index = splits['test']
        probabilities = pipeline.predict_proba(x[index])[:, 1]
        record['test'] = metrics(y[index], probabilities, record['threshold'])
        record['test_by_presentation'] = {}
        groupframe = frames[record['cutoff_day']].iloc[index].reset_index(drop=True)
        for group, positions in groupframe.groupby(['code_module', 'code_presentation']).indices.items():
            record['test_by_presentation']['/'.join(group)] = metrics(y[index][positions], probabilities[positions], record['threshold'])
        record['coverage'] = coverage(frames[record['cutoff_day']])
        record['coverage_by_presentation'] = {'/'.join(group): coverage(rows)
            for group, rows in frames[record['cutoff_day']].groupby(['code_module', 'code_presentation'])}
        report['experiments'].append(record)
    record, pipeline, x, _, names = selected
    background_index = np.random.default_rng(SEED).choice(splits['train'], size=8, replace=False)
    joblib.dump({'model': pipeline, 'background': x[background_index]}, output_path / 'model.joblib', compress=3)
    digest = hashlib.sha256((output_path / 'model.joblib').read_bytes()).hexdigest()
    manifest = dict(artifact_version=1, code=f"oulad_{record['model']}_{record['feature_set'].lower()}_d42_{digest[:12]}",
        artifact_sha256=digest, feature_schema_version=SCHEMA_VERSION, feature_set=record['feature_set'], feature_order=names,
        cutoff_day=42, class_mapping={'0': 'Pass/Distinction', '1': 'Fail'}, threshold=record['threshold'],
        threshold_source='validation_max_fail_f1', calibration_status='uncalibrated', output_space='raw_probability',
        preprocessing={'strategy': 'train_only_median', 'statistics': record['imputer_statistics']},
        dataset=dataset, evaluation={'validation': record['validation'], 'test': record['test']},
        libraries={'python': platform.python_version(), 'numpy': np.__version__, 'sklearn': sklearn.__version__, 'xgboost': xgboost.__version__, 'joblib': joblib.__version__},
        transport_status='unvalidated', limitations=report['limitations'])
    (output_path / 'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding='utf-8')
    (output_path / 'evaluation.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    split_rows = frames[42][KEY].copy()
    for name, index in splits.items():
        split_rows.loc[index, 'split'] = name
    split_rows.to_csv(output_path / 'split.csv', index=False)
    for cutoff, frame in frames.items():
        frame.to_csv(output_path / f'features_d{cutoff}.csv', index=False)
    print('Selected:', report['selected'], 'test:', record['test']['f1'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=ROOT / 'ml/data/oulad.zip')
    parser.add_argument('--output', type=Path, default=ROOT / 'ml/artifacts/current')
    args = parser.parse_args()
    train(args.archive, args.output)
