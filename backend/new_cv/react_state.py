from typing import TypedDict

class ImproveCVState(TypedDict):
    cv_content: str
    feedback: str
    cv_file_path: str
    improved_cv: str
    cv_sections: dict