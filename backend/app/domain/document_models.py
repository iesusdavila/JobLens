from pydantic import BaseModel
from app.domain.enums import DocumentKind

class DocumentSection(BaseModel):
    id: str
    source: DocumentKind
    heading: str
    text: str

class ParsedDocument(BaseModel):
    kind: DocumentKind
    filename: str
    text: str
    sections: list[DocumentSection]

    @property
    def word_count(self) -> int:
        return len(self.text.split())
