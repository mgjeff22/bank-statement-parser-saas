"""
Structured Test Reporter and Coverage Tracker for E2E Suite.
Tracks pass/fail metrics across Tiers 1-4 and verifies all 35 features.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional
import time


@dataclass
class TestResult:
    test_id: str
    feature_id: Optional[int]
    tier: int
    name: str
    status: str  # "PASS" | "FAIL" | "ERROR"
    duration_ms: float
    error_message: Optional[str] = None


class E2ETestReporter:
    def __init__(self):
        self.results: List[TestResult] = []
        self.start_time: float = time.time()
        self.features_covered: Dict[int, int] = {i: 0 for i in range(1, 36)}

    def record_test(
        self,
        test_id: str,
        tier: int,
        name: str,
        status: str,
        duration_ms: float,
        feature_id: Optional[int] = None,
        error_message: Optional[str] = None,
    ):
        result = TestResult(
            test_id=test_id,
            feature_id=feature_id,
            tier=tier,
            name=name,
            status=status,
            duration_ms=duration_ms,
            error_message=error_message,
        )
        self.results.append(result)
        if feature_id and status == "PASS":
            self.features_covered[feature_id] = self.features_covered.get(feature_id, 0) + 1

    def print_summary(self):
        total_time = time.time() - self.start_time
        total_tests = len(self.results)
        passed = sum(1 for r in self.results if r.status == "PASS")
        failed = sum(1 for r in self.results if r.status == "FAIL")
        errors = sum(1 for r in self.results if r.status == "ERROR")

        tier_counts = {1: {"pass": 0, "fail": 0}, 2: {"pass": 0, "fail": 0}, 3: {"pass": 0, "fail": 0}, 4: {"pass": 0, "fail": 0}}
        for r in self.results:
            t = r.tier if r.tier in tier_counts else 1
            if r.status == "PASS":
                tier_counts[t]["pass"] += 1
            else:
                tier_counts[t]["fail"] += 1

        print("=" * 78)
        print("          AI BANK STATEMENT PARSER MICRO-SAAS -- E2E TEST SUMMARY")
        print("=" * 78)
        print(f"Total Tests Run: {total_tests} | Passed: {passed} | Failed: {failed} | Errors: {errors}")
        print(f"Execution Duration: {total_time:.2f}s\n")
        print("Coverage by Test Tier:")
        for t in sorted(tier_counts.keys()):
            p = tier_counts[t]["pass"]
            f = tier_counts[t]["fail"]
            tot = p + f
            rate = (p / tot * 100) if tot > 0 else 0
            print(f"  Tier {t}: {p}/{tot} passed ({rate:.1f}%)")

        print("\nFeature Coverage Matrix (Features 1 to 35):")
        uncovered = []
        for fid in range(1, 36):
            cnt = self.features_covered.get(fid, 0)
            if cnt == 0:
                uncovered.append(fid)
        if not uncovered:
            print("  [OK] 100% of all 35 features in PROJECT.md have passing test verification!")
        else:
            print(f"  [WARNING] Missing test coverage for features: {uncovered}")

        if failed > 0 or errors > 0:
            print("\nFailures:")
            for r in self.results:
                if r.status != "PASS":
                    print(f"  - [{r.status}] {r.test_id} ({r.name}): {r.error_message}")
        print("=" * 78)
        return failed == 0 and errors == 0 and len(uncovered) == 0
