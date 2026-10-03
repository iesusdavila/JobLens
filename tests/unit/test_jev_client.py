import json
from typesafe_sdk import SystemOneResponse
from app.clients.jev_client import JevResponseTranslator

def test_translator_accepts_integer_level_keys_from_the_sdk() -> None:
    response = SystemOneResponse.model_validate_json(json.dumps({
        "model": "jev-1.13.0",
        "usage": {"input_tokens": 10, "output_tokens": 2},
        "answers": {
            "fit": {"type": "score", "score": 2.5, "confidence": 0.8, "legend": {"0": "low", "1": "mid", "2": "high", "3": "top"}, "probabilities": {"0": 0.0, "1": 0.1, "2": 0.3, "3": 0.6}},
            "tone": {"type": "choice", "choice": "calm", "confidence": 0.9, "probabilities": {"calm": 0.95, "angry": 0.05}},
            "billing": {"type": "noul", "noul": 0.9},
        },
    }))
    evaluation = JevResponseTranslator().to_evaluation(response, {"fit": 4})
    assert evaluation.scores["fit"].normalized == 2.5 / 3
    assert set(evaluation.scores["fit"].probabilities) == {"0", "1", "2", "3"}
    assert evaluation.scores["fit"].most_likely_level == "top"
    assert evaluation.nouls["billing"].confidence == 0.8
