import json
import logging
from datetime import datetime, timezone

class JsonLogFormatter(logging.Formatter):
    RESERVED_ATTRIBUTES = set(vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys()) | {"message", "asctime", "taskName"}

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        payload.update({key: value for key, value in vars(record).items() if key not in self.RESERVED_ATTRIBUTES})
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)

class LoggingConfigurator:
    QUIET_LOGGERS = ("httpx", "httpcore", "httpx2", "typesafe_sdk", "groq", "anthropic", "urllib3", "primp")

    def __init__(self, level: str) -> None:
        self._level = level.upper()

    def configure(self) -> None:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLogFormatter())
        root_logger = logging.getLogger()
        root_logger.handlers = [handler]
        root_logger.setLevel(self._level)
        for logger_name in self.QUIET_LOGGERS:
            logging.getLogger(logger_name).setLevel(logging.WARNING)
