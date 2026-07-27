
from app.schemas import ResearchAnswer


def test_confidence_range():
    answer = ResearchAnswer(answer="ok", confidence=0.8)
    assert answer.confidence == 0.8