"""
Reproducible Benchmark Script for DevListen Core & Vault Subsystems.
Runs against an isolated temporary SQLite database and reports
mean, median, and p95 latencies alongside system hardware details.
"""
import os
import sys
import uuid
import time
import platform
import statistics
import tempfile
from typing import Callable, List

from core.hardware_profiler import probe_hardware
from core.question_detector import QuestionDetector
from vault.database import VaultDatabase
from vault.temporal_graph import TemporalDecisionGraph
from vault.decision_extractor import DecisionExtractor
from vault.commitment_extractor import CommitmentExtractor
from vault.crypto import VaultCrypto


def _measure(fn: Callable[[], None], iterations: int = 100) -> dict:
    samples_ms: List[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        samples_ms.append((time.perf_counter() - t0) * 1000.0)
    samples_ms.sort()
    p95_idx = min(len(samples_ms) - 1, int(len(samples_ms) * 0.95))
    return {
        "iterations": iterations,
        "mean_ms": round(statistics.mean(samples_ms), 4),
        "median_ms": round(statistics.median(samples_ms), 4),
        "p95_ms": round(samples_ms[p95_idx], 4),
        "mean_us": round(statistics.mean(samples_ms) * 1000.0, 2),
        "median_us": round(statistics.median(samples_ms) * 1000.0, 2),
        "p95_us": round(samples_ms[p95_idx] * 1000.0, 2),
    }


def main():
    hw = probe_hardware()
    print("=== DevListen Reproducible Benchmark ===")
    print(f"OS: {platform.platform()}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"CPU Threads: {hw.cpu_cores} | RAM: {hw.total_ram_gb} GB | GPU: {hw.gpu_name}")
    print("-" * 55)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        os.environ["LOCALAPPDATA"] = tmpdir
        VaultCrypto._master_key = None

        db = VaultDatabase(db_path=os.path.join(tmpdir, "bench.db"))
        graph = TemporalDecisionGraph(db)
        dec_ext = DecisionExtractor(graph)
        com_ext = CommitmentExtractor(db)

        m_uuid = str(uuid.uuid4())
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO meetings (uuid, title, platform) VALUES (?, ?, ?)",
                (m_uuid, "Benchmark Sync", "Local"),
            )
            conn.commit()

        sample_q = "What did we decide about Redis caching for GraphQL?"
        q_stats = _measure(lambda: QuestionDetector.is_question(sample_q), iterations=500)
        print(f"QuestionDetector.is_question : {q_stats}")

        sample_dec = "We deployed the Kubernetes cluster with an NGINX ingress controller."
        dec_stats = _measure(lambda: dec_ext.analyze_utterance(sample_dec, "USER", m_uuid), iterations=50)
        print(f"DecisionExtractor (+SQLite)  : {dec_stats}")

        sample_act = "I will update the ADR documentation before the v2 release."
        act_stats = _measure(lambda: com_ext.analyze_utterance(sample_act, "USER", m_uuid), iterations=50)
        print(f"CommitmentExtractor (+SQLite): {act_stats}")

        if sys.platform == "win32":
            # Warm DPAPI key once, then benchmark AES-256-GCM encrypt/decrypt
            VaultCrypto.get_master_key()
            enc_stats = _measure(
                lambda: VaultCrypto.decrypt_data(VaultCrypto.encrypt_data(sample_dec)),
                iterations=200,
            )
            print(f"VaultCrypto AES-256-GCM RT   : {enc_stats}")

        # Optional: SemanticSearchEngine benchmark (uses local ONNX fastembed model)
        try:
            from vault.semantic_search import SemanticSearchEngine

            sem = SemanticSearchEngine(db)
            for i in range(25):
                d_id = graph.record_decision(
                    m_uuid,
                    f"Service-{i}",
                    f"Adopt microservice pattern {i} with PostgreSQL and Redis caching",
                )
                sem.index_decision(d_id, f"Service-{i}: Adopt microservice pattern {i} with PostgreSQL")
            # Warm ONNX embedder once
            sem.search("database caching plan", top_k=3)
            sem_stats = _measure(lambda: sem.search("What is our caching plan?", top_k=3), iterations=20)
            print(f"SemanticSearch (25 docs ONNX): {sem_stats}")
        except Exception as e:
            print(f"SemanticSearch benchmark skipped: {e}")


if __name__ == "__main__":
    main()
