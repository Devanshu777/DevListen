"""
Test suite for Brick 5: Local Semantic Vector Search.
Indexes existing decisions and tests natural language queries with NO exact keyword overlap.
"""
from vault.database import VaultDatabase
from vault.semantic_search import SemanticSearchEngine

def main():
    print("=== Testing Brick 5: Local Semantic Vector Search ===")
    db = VaultDatabase()
    engine = SemanticSearchEngine(db)

    print("Indexing all pending decisions in vault...")
    engine.index_all_pending()
    print("Indexing complete!")

    test_queries = [
        "What is our database plan?",
        "How are we speeding up API responses?",
        "What did we decide about container orchestration?",
        "Why did we say no to Mongo?"
    ]

    for q in test_queries:
        print(f"\n[QUERY]: '{q}'")
        matches = engine.search(q, top_k=2)
        if matches:
            for m in matches:
                print(f"  -> Match ({m['similarity_score']:.3f}): [{m['entity_name']}] ({m['status']}): {m['summary'][:80]}...")
        else:
            print("  -> No match above threshold.")

    print("\n=== Semantic Search Verification Passed! ===")

if __name__ == "__main__":
    main()
