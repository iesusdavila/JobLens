from app.domain.document_models import DocumentSection

class EvidenceChunker:
    def __init__(self, max_chars: int) -> None:
        self._max_chars = max_chars

    def chunk_sections(self, sections: list[DocumentSection]) -> list[str]:
        blocks = [self._section_block(section) for section in sections if section.text.strip()]
        return self._pack(blocks)

    def chunk_text(self, text: str) -> list[str]:
        return self._pack([text]) if text.strip() else []

    def truncate(self, text: str) -> str:
        return text if len(text) <= self._max_chars else text[: self._max_chars]

    def _pack(self, blocks: list[str]) -> list[str]:
        chunks: list[str] = []
        current = ""
        for piece in self._split_oversized(blocks):
            candidate = f"{current}\n\n{piece}" if current else piece
            if len(candidate) <= self._max_chars:
                current = candidate
                continue
            if current:
                chunks.append(current)
            current = piece
        if current:
            chunks.append(current)
        return chunks

    def _split_oversized(self, blocks: list[str]) -> list[str]:
        pieces: list[str] = []
        for block in blocks:
            if len(block) <= self._max_chars:
                pieces.append(block)
                continue
            pieces.extend(self._split_block(block))
        return pieces

    def _split_block(self, block: str) -> list[str]:
        pieces: list[str] = []
        current = ""
        for line in block.splitlines():
            for segment in self._hard_split(line):
                candidate = f"{current}\n{segment}" if current else segment
                if len(candidate) > self._max_chars and current:
                    pieces.append(current)
                    current = segment
                else:
                    current = candidate
        if current:
            pieces.append(current)
        return pieces

    def _hard_split(self, line: str) -> list[str]:
        return [line[index:index + self._max_chars] for index in range(0, max(len(line), 1), self._max_chars)]

    @staticmethod
    def _section_block(section: DocumentSection) -> str:
        return f"[{section.id} | {section.source.value} | {section.heading}]\n{section.text}"
