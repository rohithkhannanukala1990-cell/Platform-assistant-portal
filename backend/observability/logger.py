import logging
import json
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": "aiops-portal",
            "component": record.name,
            "message": record.getMessage(),
        }
        # Attach structured extras if provided
        for key in [
            "incident_id",
            "severity",
            "provider",
            "user",
            "source",
            "confidence",
            "task_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "user_id",
            "workspace_id",
        ]:
            if hasattr(record, key):
                data[key] = getattr(record, key)

        request_id = getattr(record, "request_id", None)
        if request_id:
            data["request_id"] = request_id

        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)

        return json.dumps(data, default=str)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger

logger = get_logger("aiops")

