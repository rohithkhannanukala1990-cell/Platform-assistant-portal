import logging
import json
from datetime import datetime, timezone

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": "aiops-portal",
            "component": record.name,
            "message": record.getMessage(),
        }
        # Attach structured extras if provided
        for key in ["incident_id", "severity", "provider", "user", "source", "confidence", "task_id"]:
            if hasattr(record, key):
                log_data[key] = getattr(record, key)
        return json.dumps(log_data)

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

