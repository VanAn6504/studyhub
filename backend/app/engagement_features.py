"""Feature contract shared by OULAD training and live StudyHub inference."""
from zoneinfo import ZoneInfo

from app.features import cutoff_bounds

SCHEMA = 'engagement_daily_v1'
FEATURES = ['elapsed_days', 'active_days', 'active_days_7', 'days_since_last_activity', 'distinct_resources']
MIN_DAY, MAX_DAY = 0, 41
STAGES = ((0, 6), (7, 13), (14, 27), (28, 41))


def feature_values(day, active_days, active_days_7, last_day, distinct_resources):
    return dict(zip(FEATURES, (day + 1, active_days, active_days_7,
                              day - last_day if last_day is not None else day + 1, distinct_resources)))


def day_bounds(run, now):
    last_day = (now.astimezone(ZoneInfo(run.timezone)).date() - run.course_run_start_date).days - 1
    start, end = cutoff_bounds(run.course_run_start_date, run.timezone, last_day)
    return last_day, start, end


def snapshot_features(run, day, activity):
    days = {(local_date - run.course_run_start_date).days for local_date, _ in activity}
    return feature_values(day, len(days), sum(value >= day - 6 for value in days),
                          max(days, default=None), len({resource for _, resource in activity}))
