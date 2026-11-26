"""
Isolated unit tests for ConversationalTurnAggregator, merge_turn_segments, and dev_terms.
"""
import re
import time
from core.turn_aggregator import ConversationalTurnAggregator, merge_turn_segments
from core.dev_terms import DEV_TERMS_REPLACEMENTS


def test_merge_turn_segments_overlap_and_casing():
    assert merge_turn_segments("", "hello world") == "Hello world"
    assert merge_turn_segments("deployed GitLab 14", "GitLab 14 yesterday") == "deployed GitLab 14 yesterday"
    assert merge_turn_segments("to break up this meeting", "into four departments") == (
        "to break up this meeting into four departments"
    )
    assert merge_turn_segments("First sentence.", "second sentence.") == "First sentence. Second sentence."
    assert merge_turn_segments("Existing text.", "   ") == "Existing text."


def test_conversational_turn_aggregator_handoff_and_flush():
    finalized = []
    updates = []

    agg = ConversationalTurnAggregator(
        silence_timeout=0.5,
        on_turn_update=lambda txt, spk: updates.append((spk, txt)),
        on_turn_finalize=lambda txt, spk: finalized.append((spk, txt)),
    )

    agg.feed("We should hold off on Redis", "ATTENDEES")
    time.sleep(0.15)
    agg.feed("until Schema v2 lands", "ATTENDEES")

    # Speaker switch must immediately finalize ATTENDEES turn
    agg.feed("Agreed, let's document that.", "YOU")
    assert len(finalized) == 1
    assert finalized[0][0] == "ATTENDEES"
    assert "hold off on Redis until Schema v2 lands." in finalized[0][1]

    agg.flush()
    assert len(finalized) == 2
    assert finalized[1][0] == "YOU"


def test_dev_terms_normalization_no_personal_names():
    joined = " ".join(rep for _, rep in DEV_TERMS_REPLACEMENTS)
    for name in ("Devanshu", "Bikram", "Pankaj", "Supriya", "Krishna", "Sanchit", "Prem", "Gaurav"):
        assert name not in joined

    sample = "We deployed kubernet is with enginex and post gresql"
    for pat, rep in DEV_TERMS_REPLACEMENTS:
        sample = re.sub(pat, rep, sample, flags=re.IGNORECASE)
    assert "Kubernetes" in sample
    assert "NGINX" in sample
    assert "PostgreSQL" in sample
