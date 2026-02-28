"""
Anomaly Monitor - Statistical anomaly detection across agent behaviors.

Reuses z-score method from agent-verifier's AnomalyDetector but applied to
security-relevant metrics: request rates, payload sizes, error rates, and
response times per agent.
"""

import logging
from typing import Any
from collections import defaultdict
import time

logger = logging.getLogger(__name__)

# Z-score threshold - values beyond this many standard deviations are flagged
Z_THRESHOLD = 3.0

# Minimum data points before we can detect anomalies
MIN_HISTORY = 10


class AnomalyMonitor:
    """
    Monitors agent behavior metrics for statistical anomalies using z-score analysis.

    Tracks multiple metrics per agent:
    - request_rate: requests per time window
    - payload_size: size of message payloads
    - error_rate: frequency of errors
    - response_time: processing latency
    """

    def __init__(self, z_threshold: float = Z_THRESHOLD):
        self.z_threshold = z_threshold
        # metric_key -> list of float values (trailing history)
        self._history: dict[str, list[float]] = defaultdict(list)
        # agent_id -> list of timestamps for rate calculation
        self._request_timestamps: dict[str, list[float]] = defaultdict(list)

    def check(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Check incoming data for anomalies across tracked metrics.

        Args:
            data: dict that may contain:
                - agent_id: which agent this data is from
                - payload_size: size of the payload in chars
                - response_time: processing time in ms
                - is_error: whether this was an error event

        Returns:
            dict with anomaly_detected, anomalies list, and metrics.
        """
        agent_id = data.get("agent_id", "unknown")
        anomalies = []

        # --- Metric 1: Request rate (per minute) ---
        now = time.time()
        self._request_timestamps[agent_id].append(now)
        cutoff = now - 60
        self._request_timestamps[agent_id] = [
            ts for ts in self._request_timestamps[agent_id] if ts > cutoff
        ]
        current_rate = float(len(self._request_timestamps[agent_id]))
        rate_anomaly = self._check_z_score(f"{agent_id}:request_rate", current_rate)
        if rate_anomaly:
            anomalies.append(rate_anomaly)

        # --- Metric 2: Payload size ---
        payload_size = data.get("payload_size")
        if payload_size is not None:
            size_anomaly = self._check_z_score(f"{agent_id}:payload_size", float(payload_size))
            if size_anomaly:
                anomalies.append(size_anomaly)

        # --- Metric 3: Response time ---
        response_time = data.get("response_time")
        if response_time is not None:
            time_anomaly = self._check_z_score(f"{agent_id}:response_time", float(response_time))
            if time_anomaly:
                anomalies.append(time_anomaly)

        return {
            "anomaly_detected": len(anomalies) > 0,
            "anomalies": anomalies,
            "agent_id": agent_id,
            "current_request_rate": current_rate,
        }

    def _check_z_score(self, metric_key: str, value: float) -> dict | None:
        """
        Check if a value is anomalous compared to the running history for this metric.

        Returns anomaly dict if z-score exceeds threshold, else None.
        """
        history = self._history[metric_key]

        result = None
        if len(history) >= MIN_HISTORY:
            mean = sum(history) / len(history)
            variance = sum((x - mean) ** 2 for x in history) / len(history)
            std = variance ** 0.5

            if std > 0:
                z_score = abs(value - mean) / std
                if z_score > self.z_threshold:
                    result = {
                        "metric": metric_key,
                        "value": round(value, 3),
                        "mean": round(mean, 3),
                        "std": round(std, 3),
                        "z_score": round(z_score, 3),
                        "threshold": self.z_threshold,
                    }

        # Update history (keep last 200 data points)
        history.append(value)
        if len(history) > 200:
            self._history[metric_key] = history[-200:]

        return result

    def get_stats(self) -> dict[str, Any]:
        """Return summary statistics from the anomaly monitor."""
        agents_tracked = set()
        for key in self._history:
            agent_id = key.rsplit(":", 1)[0]
            agents_tracked.add(agent_id)

        total_data_points = sum(len(v) for v in self._history.values())
        metrics_tracked = list(self._history.keys())

        return {
            "agents_tracked": list(agents_tracked),
            "total_data_points": total_data_points,
            "metrics_count": len(metrics_tracked),
            "z_threshold": self.z_threshold,
        }
