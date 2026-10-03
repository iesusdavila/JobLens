from abc import ABC, abstractmethod
from app.domain.cv_models import TailoredCv
from app.services.cv_templates.cv_blocks import CvBlockBuilder

class CvTemplate(ABC):
    def __init__(self, block_builder: CvBlockBuilder) -> None:
        self._block_builder = block_builder

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def render_docx(self, cv: TailoredCv) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def render_pdf(self, cv: TailoredCv) -> bytes:
        raise NotImplementedError
