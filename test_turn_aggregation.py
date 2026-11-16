"""
Unit test for ConversationalTurnAggregator:
1. Verifies that natural 4-6s presentation pauses keep speech in ONE continuous paragraph.
2. Verifies that mid-sentence clauses are not broken by artificial periods.
3. Verifies that speaker transitions immediately finalize the previous turn.
4. Verifies suppression of isolated hallucinated words.
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.turn_aggregator import ConversationalTurnAggregator, merge_turn_segments
from core.local_transcriber import clean_clause_text

def test_turn_aggregation():
    print("==================================================")
    print("Testing Conversational Turn Aggregation...")
    print("==================================================")

    # 1. Test clean_clause_text hallucination filter
    assert clean_clause_text("You.") == "", "Isolated 'You.' must be dropped"
    assert clean_clause_text("Thank you.") == "", "Isolated 'Thank you.' must be dropped"
    assert clean_clause_text("You have a good point.") == "You have a good point.", "Real sentence starting with 'You' must be kept"
    print("✓ Hallucination filter passed!")

    # 2. Test merge_turn_segments
    merged = merge_turn_segments("to break up this meeting", "into four departments")
    assert merged == "to break up this meeting into four departments", f"Expected smooth join without artificial period, got '{merged}'"
    print("✓ Mid-sentence smooth join passed!")

    merged_period = merge_turn_segments("This is Eric Johnson.", "so I've got number four.")
    assert merged_period == "This is Eric Johnson. So I've got number four.", f"Expected capitalized sentence, got '{merged_period}'"
    print("✓ Sentence boundary capitalization passed!")

    # 3. Test multi-pause paragraph aggregation
    finalized_turns = []
    live_updates = []

    def on_update(text, spk):
        live_updates.append((spk, text))

    def on_finalize(text, spk):
        finalized_turns.append((spk, text))

    aggregator = ConversationalTurnAggregator(
        silence_timeout=0.6,  # Accelerated for unit test
        on_turn_update=on_update,
        on_turn_finalize=on_finalize
    )

    # Simulate Eric speaking with 0.25s pauses (less than silence_timeout 0.6s)
    aggregator.feed("Hi, this is Eric Johnson. It's February 8th.", "Eric Johnson")
    time.sleep(0.25)
    aggregator.feed("So I've got number four in the agenda which is a proposal", "Eric Johnson")
    time.sleep(0.25)
    aggregator.feed("to break up this meeting into four department key reviews.", "Eric Johnson")
    time.sleep(0.25)
    aggregator.feed("Increased visibility allows us to go deeper.", "Eric Johnson")

    # Now simulate speaker handoff to Sid Sijbrandij
    aggregator.feed("And this is the key review.", "Sid Sijbrandij")

    # Eric's turn must be finalized immediately upon Sid speaking!
    assert len(finalized_turns) == 1, f"Expected 1 finalized turn for Eric, got {len(finalized_turns)}"
    eric_spk, eric_text = finalized_turns[0]
    assert eric_spk == "Eric Johnson", f"Expected Eric Johnson, got {eric_spk}"
    assert "February 8th" in eric_text and "proposal to break up" in eric_text and "Increased visibility" in eric_text
    print(f"\n[Aggregated Paragraph]:\n'{eric_text}'\n")
    print("✓ Continuous paragraph aggregation across multiple pauses PASSED! 🚀")

    # Let Sid finalize
    time.sleep(0.7)
    assert len(finalized_turns) == 2
    assert finalized_turns[1][0] == "Sid Sijbrandij"
    print("✓ Speaker transition finalization PASSED! 🚀")

if __name__ == "__main__":
    test_turn_aggregation()
