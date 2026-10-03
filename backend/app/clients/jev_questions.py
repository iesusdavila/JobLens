from typing import Any
from pydantic import BaseModel, Field

JevInstructions = str | dict[str, Any]
JevState = str | dict[str, Any] | list[Any]

class NoulQuestion(BaseModel):
    key: str
    instructions: JevInstructions
    true_criteria: str | None = None
    false_criteria: str | None = None

class ChoiceQuestion(BaseModel):
    key: str
    instructions: JevInstructions
    options: dict[str, str | None] = Field(min_length=2)

class ScoreQuestion(BaseModel):
    key: str
    instructions: JevInstructions
    levels: list[str] = Field(min_length=2, max_length=10)

JevQuestion = NoulQuestion | ChoiceQuestion | ScoreQuestion
