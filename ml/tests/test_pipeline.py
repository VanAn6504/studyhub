"""Small independent oracle for feature timelines and person-disjoint splitting."""
import sys
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from train_oulad import build_features, choose_threshold, coverage, group_split


def test_oulad_cutoff_missing_clicks_scores_and_labels(tmp_path):
    path = tmp_path / 'fixture.zip'
    files = {
        'studentInfo.csv': 'code_module,code_presentation,id_student,final_result\nAAA,2020J,1,Fail\nAAA,2020J,2,Pass\nAAA,2020J,3,Withdrawn\nAAA,2020J,4,Distinction\n',
        'assessments.csv': 'id_assessment,code_module,code_presentation\n10,AAA,2020J\n11,AAA,2020J\n12,AAA,2020J\n',
        'studentAssessment.csv': 'id_assessment,id_student,date_submitted,is_banked,score\n10,1,10,0,40\n10,1,11,0,100\n11,1,42,0,75\n12,1,43,0,100\n10,2,2,1,100\n11,2,3,0,\n',
        'studentVle.csv': 'code_module,code_presentation,id_student,date,sum_click\nAAA,2020J,1,0,2\nAAA,2020J,1,2,3\nAAA,2020J,1,2,4\nAAA,2020J,1,42,5\nAAA,2020J,1,43,50\nAAA,2020J,1,-1,100\nAAA,2020J,2,0,0\n',
    }
    with ZipFile(path, 'w') as archive:
        for name, contents in files.items():
            archive.writestr(name, contents)
    frames, report = build_features(path, chunksize=2)
    assert report['excluded_withdrawn'] == 1 and report['eligible_rows'] == 3
    day42 = frames[42].set_index('id_student')
    assert list(day42.index) == [1, 2, 4]
    assert list(day42.label) == [1, 0, 0]
    row = day42.loc[1]
    assert row.active_days == 3 and row.material_interactions == 14 and row.days_since_last_activity == 0
    assert row.assessment_count == 2 and row.mean_assessment_score == 57.5 and row.has_assessment == 1
    assert day42.loc[2].active_days == 0 and day42.loc[2].days_since_last_activity == 43
    assert day42.loc[2].assessment_count == 0 and np.isnan(day42.loc[2].mean_assessment_score)
    row28 = frames[28].set_index('id_student').loc[1]
    assert row28.active_days == 2 and row28.material_interactions == 9
    assert row28.assessment_count == 1 and row28.mean_assessment_score == 40
    assert coverage(frames[42]) == {'rows': 3, 'active_fraction': 1 / 3, 'assessment_fraction': 1 / 3}


def test_group_split_is_reproducible_and_threshold_uses_validation_only():
    frame = pd.DataFrame({'id_student': np.repeat(np.arange(80), 2), 'label': np.repeat(np.arange(80) % 2, 2)})
    splits = group_split(frame)
    repeated = group_split(frame)
    for name in splits:
        assert np.array_equal(splits[name], repeated[name])
    groups = {name: set(frame.iloc[index].id_student) for name, index in splits.items()}
    assert not groups['train'] & groups['validation'] and not groups['train'] & groups['test'] and not groups['validation'] & groups['test']
    assert set(np.concatenate(list(splits.values()))) == set(range(len(frame)))
    assert choose_threshold(np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.3, 0.4])) == 0.3
