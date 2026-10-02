"""Read Gemini token usage for one model from Cloud Monitoring.

Memory Bank doesn't report the tokens its extraction uses, but the calls run on a Gemini model in
our project, so they show in the project's publisher-model metrics. The POC extracts with a model
nothing else uses, so that model's usage in a time window is the extraction usage.

    python model_usage.py MODEL START END     (times as 2026-10-02T11:30:00Z)
"""

from __future__ import annotations

import json
import os
import sys

import google.auth
from google.auth.transport.requests import AuthorizedSession

METRIC = "aiplatform.googleapis.com/publisher/online_serving/token_count"


def token_usage(project: str, model: str, start: str, end: str) -> dict[str, int]:
    """Total tokens by type ("input", "output", ...) for the model between start and end."""
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    response = AuthorizedSession(credentials).get(
        f"https://monitoring.googleapis.com/v3/projects/{project}/timeSeries",
        params={
            "filter": f'metric.type="{METRIC}" AND resource.labels.model_user_id="{model}"',
            "interval.startTime": start,
            "interval.endTime": end,
        },
    )
    response.raise_for_status()
    totals: dict[str, int] = {}
    for series in response.json().get("timeSeries", []):
        kind = series["metric"]["labels"].get("type", "unknown")
        for point in series["points"]:
            totals[kind] = totals.get(kind, 0) + int(point["value"].get("int64Value", 0))
    return totals


if __name__ == "__main__":
    model, start, end = sys.argv[1:4]
    print(json.dumps(token_usage(os.environ["GOOGLE_CLOUD_PROJECT"], model, start, end)))
