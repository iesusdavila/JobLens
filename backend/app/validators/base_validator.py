import logging
from abc import ABC, abstractmethod
from app.clients.jev_client import JevClient
from app.config.settings import ValidationThresholds

class BaseValidator(ABC):
    STATE_MARGIN_CHARS = 4000

    def __init__(self, jev_client: JevClient, thresholds: ValidationThresholds) -> None:
        self._jev = jev_client
        self._thresholds = thresholds
        self._logger = logging.getLogger(f"app.validators.{self.name}")

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    def _evidence_budget(self) -> int:
        return max(1000, self._jev.max_state_chars - self.STATE_MARGIN_CHARS)

    def _is_low_confidence(self, confidence: float) -> bool:
        return confidence < self._thresholds.low_confidence

    def _log_summary(self, **summary: object) -> None:
        self._logger.info("validator_completed", extra={"validator": self.name, **summary})
