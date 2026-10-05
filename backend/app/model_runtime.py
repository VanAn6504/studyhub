"""Load only administrator-managed, hash-checked artifacts; exact empirical SHAP.

The joblib file is trusted executable material produced locally by the training CLI.
It must never be loaded from an upload or a client-supplied path.
"""
import hashlib
import io
import json
import math
import platform
from functools import lru_cache
from itertools import combinations
from pathlib import Path

import joblib
import numpy as np
import sklearn
import xgboost

from app.features import CUTOFF_DAY, FEATURES_A, FEATURES_B, SCHEMA_VERSION


class ArtifactUnavailable(Exception):
    pass


def load_artifact(directory: Path):
    try:
        manifest_bytes = (directory / 'manifest.json').read_bytes()
        metadata = json.loads(manifest_bytes)
        names = FEATURES_A if metadata['feature_set'] == 'A' else FEATURES_B
        if (metadata['artifact_version'] != 1 or metadata['feature_schema_version'] != SCHEMA_VERSION
                or metadata['cutoff_day'] != CUTOFF_DAY or metadata['feature_set'] not in ('A', 'B')
                or metadata['feature_order'] != names or metadata['class_mapping'] != {'0': 'Pass/Distinction', '1': 'Fail'}
                or metadata['output_space'] != 'raw_probability' or metadata['calibration_status'] != 'uncalibrated'
                or metadata['threshold_source'] != 'validation_max_fail_f1'
                or not isinstance(metadata['code'], str) or not metadata['code']
                or not math.isfinite(metadata['threshold']) or not 0 <= metadata['threshold'] <= 1):
            raise ArtifactUnavailable()
        versions = metadata['libraries']
        if (versions['python'].split('.')[:2] != platform.python_version().split('.')[:2]
                or versions['numpy'] != np.__version__ or versions['sklearn'] != sklearn.__version__
                or versions['xgboost'] != xgboost.__version__ or versions['joblib'] != joblib.__version__):
            raise ArtifactUnavailable()
        content = (directory / 'model.joblib').read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest != metadata['artifact_sha256']:
            raise ArtifactUnavailable()
        bundle = _deserialize(hashlib.sha256(manifest_bytes).hexdigest(), digest, content)
        model = bundle['model']
        background = np.array(bundle['background'], dtype=float)
        if list(model.classes_) != [0, 1] or model.n_features_in_ != len(names) or background.ndim != 2 or background.shape[1] != len(names) or not 1 <= len(background) <= 16:
            raise ArtifactUnavailable()
        preprocessing = metadata['preprocessing']
        if (preprocessing['strategy'] != 'train_only_median'
                or not np.array_equal(np.asarray(preprocessing['statistics']), model.named_steps['imputer'].statistics_)):
            raise ArtifactUnavailable()
        metadata['manifest_sha256'] = hashlib.sha256(manifest_bytes).hexdigest()
        return metadata, model, background
    except ArtifactUnavailable:
        raise
    except Exception as error:
        raise ArtifactUnavailable() from error


@lru_cache(maxsize=2)
def _deserialize(manifest_hash, model_hash, content):
    return joblib.load(io.BytesIO(content))


def predict_explain(model, background, features, names):
    """Exact interventional SHAP over <=6 raw features and fixed train backgrounds.

    Missing score is a feature value (NaN); imputation runs inside the pipeline for
    every coalition. Additivity is in raw probability units, not log odds/causality.
    """
    x = np.array([np.nan if features[name] is None else features[name] for name in names], dtype=float)
    size = len(names)
    rows = []
    for mask in range(1 << size):
        mixed = background.copy()
        for index in range(size):
            if mask & (1 << index):
                mixed[:, index] = x[index]
        rows.append(mixed)
    values = model.predict_proba(np.concatenate(rows))[:, 1].reshape(1 << size, len(background)).mean(axis=1)
    contributions = []
    for index, name in enumerate(names):
        phi = 0.0
        others = [j for j in range(size) if j != index]
        for count in range(size):
            weight = math.factorial(count) * math.factorial(size - count - 1) / math.factorial(size)
            for subset in combinations(others, count):
                mask = sum(1 << j for j in subset)
                phi += weight * (values[mask | (1 << index)] - values[mask])
        contributions.append({'feature': name, 'value': features[name], 'contribution': float(phi)})
    score = float(values[-1])
    if not math.isfinite(score) or not 0 <= score <= 1 or not math.isclose(float(values[0]) + sum(c['contribution'] for c in contributions), score, abs_tol=1e-6):
        raise ArtifactUnavailable()
    return score, {'method': 'exact_interventional_shap', 'output_space': 'raw_probability',
        'background_source': 'fixed_training_sample', 'background_size': len(background),
        'base_value': float(values[0]), 'output_value': score,
        'contributions': sorted(contributions, key=lambda c: -abs(c['contribution']))}
