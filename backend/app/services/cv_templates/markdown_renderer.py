from app.domain.cv_models import CvChange, TailoredCv
from app.services.cv_templates.cv_blocks import CvBlockBuilder, CvBlockKind

class MarkdownCvRenderer:
    PREFIXES = {
        CvBlockKind.NAME: "# ",
        CvBlockKind.HEADING: "## ",
        CvBlockKind.ENTRY: "### ",
        CvBlockKind.BULLET: "- ",
    }

    def __init__(self, block_builder: CvBlockBuilder) -> None:
        self._block_builder = block_builder

    def render(self, cv: TailoredCv) -> str:
        lines: list[str] = []
        for block in self._block_builder.build(cv):
            if block.kind == CvBlockKind.ENTRY_META:
                lines.append(f"*{block.text}*")
            elif block.kind == CvBlockKind.HEADLINE:
                lines.append(f"**{block.text}**")
            else:
                lines.append(f"{self.PREFIXES.get(block.kind, '')}{block.text}")
            if block.kind in (CvBlockKind.NAME, CvBlockKind.HEADING, CvBlockKind.PARAGRAPH, CvBlockKind.CONTACT):
                lines.append("")
        return "\n".join(lines).strip() + "\n"

class ChangeLogRenderer:
    def render(self, changes: list[CvChange]) -> str:
        if not changes:
            return "No changes were recorded.\n"
        return "\n".join(self._render_change(index, change) for index, change in enumerate(changes, start=1))

    @staticmethod
    def _render_change(index: int, change: CvChange) -> str:
        diff_lines = []
        if change.original:
            diff_lines.append(f"- {change.original}")
        if change.tailored:
            diff_lines.append(f"+ {change.tailored}")
        diff = "\n".join(diff_lines) or "  (reordered)"
        return f"### {index}. {change.section}\n```diff\n{diff}\n```\n**Why:** {change.reason}\n"
