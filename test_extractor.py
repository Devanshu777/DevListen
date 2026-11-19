"""
Test DecisionExtractor against the real transcribed sentences.
"""
from vault.database import VaultDatabase
from vault.temporal_graph import TemporalDecisionGraph
from vault.decision_extractor import DecisionExtractor

def main():
    print("=== Testing DecisionExtractor on Spoken Transcripts ===")
    db = VaultDatabase()
    graph = TemporalDecisionGraph(db)
    extractor = DecisionExtractor(graph)

    test_sentences = [
        "Alex proposed using MongoDB, but the architect rejected because we need ACID transactions.",
        "We deployed the Kubernetes cluster with an NGINX ingress controller and hooked it up with PostgreSQL and Redis.",
        "We should deprecate the rest endpoints and migrate our gRPC services to OAuth2 with JWT pair of tokens.",
        "I think that will cost us $10 or something." # Casual chatter, should be ignored
    ]

    meeting_uuid = "test-session-001"
    for s in test_sentences:
        res = extractor.analyze_utterance(s, speaker="USER", meeting_uuid=meeting_uuid)
        if res:
            print(f"\n[DECISION DETECTED]")
            print(f"• Entity: {res['entity']}")
            print(f"• Status: {res['status']}")
            print(f"• Summary: {res['summary']}")
            print(f"• Proposed by: {res['proposed_by']} | Agreed by: {res['agreed_by']}")
        else:
            print(f"\n[IGNORED AS NON-DECISION]: '{s}'")

    # Now verify query from graph
    print("\n--- Verifying Retrieval from Knowledge Graph ---")
    mongo_ctx = graph.get_entity_context("Mongodb")
    print("Query 'Mongodb':", mongo_ctx["current_decision"]["summary"])
    assert mongo_ctx["current_decision"]["status"] == "REJECTED"
    print("=== Extractor Verified Successfully! ===")

if __name__ == "__main__":
    main()
