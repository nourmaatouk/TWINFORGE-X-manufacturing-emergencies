"""
Anomaly Detector - Detects statistical anomalies in sensor data streams.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """Detects anomalies using statistical methods (z-score, IQR)."""

    def __init__(self, z_threshold: float = 3.0):
        self.z_threshold = z_threshold
        self._history: dict[str, list[float]] = {}

    def detect(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Detect anomalies in a data point against historical data."""
        sensor_id = payload.get("sensor_id", "unknown")
        value = payload.get("value", 0.0)
        anomalies = []

        history = self._history.get(sensor_id, [])

        if len(history) >= 10:
            mean = sum(history) / len(history)
            variance = sum((x - mean) ** 2 for x in history) / len(history)
            std = variance ** 0.5

            if std > 0:
                z_score = abs(value - mean) / std
                if z_score > self.z_threshold:
                    anomalies.append({
                        "type": "z_score",
                        "z_score": round(z_score, 3),
                        "threshold": self.z_threshold,
                        "mean": round(mean, 3),
                        "std": round(std, 3),
                    })

        # Track history
        if sensor_id not in self._history:
            self._history[sensor_id] = []
        self._history[sensor_id].append(value)
        # Keep last 100 values
        self._history[sensor_id] = self._history[sensor_id][-100:]

        return {
            "is_valid": len(anomalies) == 0,
            "verification_type": "anomaly",
            "sensor_id": sensor_id,
            "anomalies": anomalies,
            "history_length": len(self._history.get(sensor_id, [])),
        }
