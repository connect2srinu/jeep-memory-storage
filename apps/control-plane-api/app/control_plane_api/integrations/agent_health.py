from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class AgentHealthResult:
    health_status: str
    provider_status: str
    request_count: int | None = None
    error_rate: float | None = None
    p95_latency_ms: float | None = None
    last_success_at: datetime | None = None
    details: dict[str, Any] | None = None


class AgentHealthProvider:
    """Collect health without coupling the control plane to a single agent runtime."""

    async def collect(self, binding: Any) -> AgentHealthResult:
        if binding.provider == "GOOGLE_AGENT_RUNTIME":
            return await asyncio.to_thread(self._google_agent_runtime, binding)
        if binding.endpoint_url:
            return await asyncio.to_thread(self._http_health, binding.endpoint_url)
        return AgentHealthResult(
            health_status="UNKNOWN",
            provider_status="NO_HEALTH_ENDPOINT",
            details={"message": "Configure an endpoint URL or Google Agent Runtime resource."},
        )

    def _http_health(self, endpoint_url: str) -> AgentHealthResult:
        observed = datetime.now(UTC)
        url = f"{endpoint_url.rstrip('/')}/healthz"
        try:
            with urlopen(Request(url, method="GET"), timeout=5) as response:
                status = response.status
            healthy = 200 <= status < 400
            return AgentHealthResult(
                health_status="HEALTHY" if healthy else "UNHEALTHY",
                provider_status=f"HTTP_{status}",
                last_success_at=observed if healthy else None,
                details={"healthUrl": url},
            )
        except Exception as error:  # noqa: BLE001 - provider outage becomes health data
            return AgentHealthResult(
                health_status="UNKNOWN",
                provider_status="ENDPOINT_UNREACHABLE",
                details={"healthUrl": url, "error": str(error)},
            )

    def _google_agent_runtime(self, binding: Any) -> AgentHealthResult:
        if not binding.gcp_project_id or not binding.resource_name:
            return AgentHealthResult(
                health_status="UNKNOWN",
                provider_status="INCOMPLETE_BINDING",
                details={"message": "gcpProjectId and resourceName are required."},
            )
        try:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/monitoring.read"]
            )
            session = AuthorizedSession(credentials)
            end = datetime.now(UTC)
            start = end - timedelta(minutes=5)
            engine_id = binding.resource_name.rstrip("/").split("/")[-1]
            metric = "aiplatform.googleapis.com/reasoning_engine/request_count"
            response = session.get(
                f"https://monitoring.googleapis.com/v3/projects/{binding.gcp_project_id}/timeSeries",
                params={
                    "filter": (
                        'resource.type="aiplatform.googleapis.com/ReasoningEngine" '
                        f'AND resource.labels.reasoning_engine_id="{engine_id}" '
                        f'AND metric.type="{metric}"'
                    ),
                    "interval.startTime": start.isoformat(),
                    "interval.endTime": end.isoformat(),
                    "view": "FULL",
                },
                timeout=10,
            )
            response.raise_for_status()
            series = response.json().get("timeSeries", [])
            count = 0
            for item in series:
                for point in item.get("points", []):
                    value = point.get("value", {})
                    count += int(value.get("int64Value", value.get("doubleValue", 0)))
            return AgentHealthResult(
                health_status="HEALTHY",
                provider_status="MONITORING_OK",
                request_count=count,
                last_success_at=end,
                details={"resourceName": binding.resource_name, "windowMinutes": 5},
            )
        except Exception as error:  # noqa: BLE001 - provider outage becomes health data
            return AgentHealthResult(
                health_status="UNKNOWN",
                provider_status="MONITORING_ERROR",
                details={"error": str(error)},
            )
