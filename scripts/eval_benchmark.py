"""
eval_benchmark.py
-----------------
Runs a predefined test dataset through the RAG pipeline and reports:
  - p95 latency (ms)
  - Average cost per query (USD)
  - Keyword hit-rate accuracy (%)

Run from the project root:
    python -m scripts.eval_benchmark
"""

import sys
import os
import numpy as np

# Allow imports from app/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from main import generate_answer_with_metrics  # noqa: E402

# ---------------------------------------------------------------------------
# Test dataset
# Each entry has a Swedish query and a keyword we expect in the answer.
# Keep this in sync with README.md > Test Questions table.
# ---------------------------------------------------------------------------
TEST_DATASET = [
    {
        "query": "Vad kostar det att slänga skrotfordon?",
        "expected_keyword": "250",
        "description": "Scrap vehicle flat fee (private + business identical)",
    },
    {
        "query": "Vad kostar det att lämna in ett kylskåp som privatperson utan Misekort?",
        "expected_keyword": "6",
        "description": "Refrigerator drop-off, private, in Mise municipality",
    },
    {
        "query": "Jag bor inte i en Mise-kommun, vad kostar ett besök på återvinningscentralen?",
        "expected_keyword": "20",
        "description": "Non-Mise municipality resident visit fee",
    },
    {
        "query": "Hur sorterar jag mitt avfall?",
        "expected_keyword": "bio",
        "description": "Waste sorting guide (out-of-domain: no fee)",
    },
    {
        "query": "Vad är öppettiderna för biblioteket i Mariehamn?",
        "expected_keyword": "vet inte",
        "description": "Out-of-scope guardrail: library hours",
    },
]


def run_benchmark():
    latencies: list[float] = []
    costs: list[float] = []
    hits = 0
    results = []

    print("\n>>> Running RAG benchmark...\n")
    print(f"{'#':<3} {'Query':<55} {'Hit':<5} {'Latency':>10} {'Cost':>12}")
    print("-" * 90)

    for i, item in enumerate(TEST_DATASET, start=1):
        res = generate_answer_with_metrics(item["query"])

        latencies.append(res["latency_ms"])
        costs.append(res["cost_usd"])

        hit = item["expected_keyword"].lower() in res["answer"].lower()
        if hit:
            hits += 1

        status = "PASS" if hit else "FAIL"
        print(
            f"{i:<3} {item['query'][:54]:<55} {status:<5} "
            f"{res['latency_ms']:>8.0f}ms  ${res['cost_usd']:>10.6f}"
        )

        results.append(
            {
                "query": item["query"],
                "expected_keyword": item["expected_keyword"],
                "hit": hit,
                "latency_ms": res["latency_ms"],
                "cost_usd": res["cost_usd"],
                "answer_preview": res["answer"][:120],
            }
        )

    # ---------------------------------------------------------------------------
    # Summary metrics
    # ---------------------------------------------------------------------------
    p95_latency = float(np.percentile(latencies, 95))
    avg_latency = float(np.mean(latencies))
    avg_cost = float(np.mean(costs))
    total_cost = float(np.sum(costs))
    accuracy = (hits / len(TEST_DATASET)) * 100

    print("=" * 90)
    print("BENCHMARK RESULTS")
    print("=" * 90)
    print(f"  Queries run          : {len(TEST_DATASET)}")
    print(f"  Keyword Hit Rate     : {accuracy:.1f}%  ({hits}/{len(TEST_DATASET)} correct)")
    print(f"  p95 Latency          : {p95_latency:.0f} ms")
    print(f"  Avg Latency          : {avg_latency:.0f} ms")
    print(f"  Avg Cost / Query     : ${avg_cost:.6f}")
    print(f"  Total Cost (this run): ${total_cost:.6f}")
    print("=" * 90)

    # Print any misses with their actual answers for manual review
    misses = [r for r in results if not r["hit"]]
    if misses:
        print("\n[FAIL] Failed Cases (answer preview):")
        for m in misses:
            print(f"  Q: {m['query']}")
            print(f"     Expected keyword: '{m['expected_keyword']}'")
            print(f"     Answer preview  : {m['answer_preview']}...")
            print()

    return {
        "hit_rate_pct": accuracy,
        "p95_latency_ms": p95_latency,
        "avg_latency_ms": avg_latency,
        "avg_cost_usd": avg_cost,
        "results": results,
    }


if __name__ == "__main__":
    run_benchmark()
