"""Unit tests for ContradictionDetector."""
import pytest

from app.core.enums import EntailmentResult, SourceTier
from app.models.schemas import EvidenceChunk, SourceMetadata
from app.services.contradiction_detector import ContradictionDetector

cd = ContradictionDetector()


def _chunk(url: str, text: str, entailment: EntailmentResult, domain: str = "example.com") -> EvidenceChunk:
    source = SourceMetadata(url=url, domain=domain, tier=SourceTier.TIER2_SECONDARY)
    chunk = EvidenceChunk(source=source, text=text)
    chunk.entailment = entailment
    return chunk


class TestContradictionDetector:
    def test_no_contradiction_when_only_support(self):
        supporting = [_chunk("https://a.com", "Feature was released in March.", EntailmentResult.SUPPORTS)]
        report = cd.detect(supporting, contradicting=[])
        assert not report.conflict_detected

    def test_contradiction_detected(self):
        supporting = [_chunk("https://a.com", "Feature released in March.", EntailmentResult.SUPPORTS)]
        contradicting = [_chunk("https://b.com", "Feature released in April.", EntailmentResult.CONTRADICTS)]
        report = cd.detect(supporting, contradicting)
        assert report.conflict_detected

    def test_duplicate_source_detection(self):
        a = _chunk("https://a.com", "Python was created by Guido.", EntailmentResult.SUPPORTS, "a.com")
        b = _chunk("https://b.com", "Python was created by Guido.", EntailmentResult.SUPPORTS, "a.com")
        assert cd.is_duplicate_source(a, b) is True

    def test_non_duplicate_different_domains(self):
        a = _chunk("https://a.com", "Python is a programming language used for web development.", EntailmentResult.SUPPORTS, "a.com")
        b = _chunk("https://b.com", "React is a JavaScript library built by Meta for UI components.", EntailmentResult.SUPPORTS, "b.com")
        # Different domains, different content → not duplicate
        assert cd.is_duplicate_source(a, b) is False
