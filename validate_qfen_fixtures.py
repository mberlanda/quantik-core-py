#!/usr/bin/env python3
"""
QFEN Validation Script for Quantik Test Fixtures

Validates all QFEN strings in the test fixture catalog using
bb_from_qfen(qfen, validate=True) and reports pass/fail per entry.

By default the script reads directly from UnifiedTestCases (no external
file required).  Pass --csv-file to validate a custom CSV instead.

Usage:
    # validate from built-in fixtures (default)
    PYTHONPATH=src:. python validate_qfen_fixtures.py

    # validate from a CSV file
    PYTHONPATH=src:. python validate_qfen_fixtures.py --csv-file my_cases.csv

    # write detailed results to a file
    PYTHONPATH=src:. python validate_qfen_fixtures.py --output results.txt

CSV columns (when --csv-file is used):
    qfen, name, description, category, source_file
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass, field
from quantik_core.qfen import bb_from_qfen
from quantik_core.commons import ValidationError


@dataclass
class QFENValidationResult:
    """Result of validating a single QFEN string."""

    qfen: str
    name: str
    description: str
    category: str
    source_file: str
    is_valid: bool
    error_message: str = ""


def _load_from_unified_test_cases() -> List[Dict[str, Any]]:
    """Load fixtures directly from UnifiedTestCases (no CSV needed)."""
    # tests/ is not on sys.path by default when run from the project root
    tests_dir = Path(__file__).parent / "tests"
    if str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))

    from fixtures import UnifiedTestCases  # type: ignore[import]

    return [
        {
            "qfen": case.qfen,
            "name": case.name,
            "description": case.description,
            "category": case.category,
            "source_file": "tests/fixtures.py",
        }
        for case in UnifiedTestCases.all_cases()
    ]


def load_test_fixtures(csv_file: Optional[Path]) -> List[Dict[str, Any]]:
    """Load test fixtures from a CSV file or from UnifiedTestCases."""
    if csv_file is None:
        return _load_from_unified_test_cases()

    fixtures = []
    try:
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                fixtures.append(row)
    except FileNotFoundError:
        print(f"Error: CSV file '{csv_file}' not found")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        sys.exit(1)

    return fixtures


def validate_qfen(qfen: str) -> Tuple[bool, str]:
    """Validate a single QFEN string; returns (is_valid, error_message)."""
    try:
        bb_from_qfen(qfen, validate=True)
        return True, ""
    except ValueError as e:
        return False, f"ValueError: {str(e)}"
    except ValidationError as e:
        return False, f"ValidationError: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


def validate_all_fixtures(
    fixtures: List[Dict[str, Any]],
) -> List[QFENValidationResult]:
    """Validate all QFEN strings in the fixtures."""
    results = []

    print(f"Validating {len(fixtures)} QFEN strings...")
    print("-" * 80)

    for i, fixture in enumerate(fixtures, 1):
        qfen = fixture["qfen"].strip('"')
        name = fixture["name"]
        description = fixture["description"]
        category = fixture["category"]
        source_file = fixture["source_file"]

        print(f"[{i:2d}/{len(fixtures):2d}] {name}: ", end="")

        is_valid, error_msg = validate_qfen(qfen)

        results.append(
            QFENValidationResult(
                qfen=qfen,
                name=name,
                description=description,
                category=category,
                source_file=source_file,
                is_valid=is_valid,
                error_message=error_msg,
            )
        )

        if is_valid:
            print("VALID")
        else:
            print("INVALID")
            print(f"     Error: {error_msg}")

    return results


def print_summary(results: List[QFENValidationResult]) -> None:
    """Print validation summary statistics."""
    total = len(results)
    valid = sum(1 for r in results if r.is_valid)
    invalid = total - valid

    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)
    print(f"Total test cases: {total}")
    print(f"Valid QFEN strings: {valid} ({valid / total * 100:.1f}%)")
    print(f"Invalid QFEN strings: {invalid} ({invalid / total * 100:.1f}%)")

    if invalid > 0:
        print("\nINVALID CASES:")
        print("-" * 40)
        for result in results:
            if not result.is_valid:
                print(f"* {result.name} ({result.category})")
                print(f"  QFEN: {result.qfen}")
                print(f"  Error: {result.error_message}")
                print()

    categories: Dict[str, Dict[str, int]] = {}
    for result in results:
        cat = result.category
        if cat not in categories:
            categories[cat] = {"total": 0, "valid": 0}
        categories[cat]["total"] += 1
        if result.is_valid:
            categories[cat]["valid"] += 1

    print("\nBY CATEGORY:")
    print("-" * 40)
    for category, stats in sorted(categories.items()):
        valid_pct = stats["valid"] / stats["total"] * 100
        print(
            f"{category:15s}: {stats['valid']:2d}/{stats['total']:2d}"
            f" valid ({valid_pct:5.1f}%)"
        )


def save_results(results: List[QFENValidationResult], output_file: Path) -> None:
    """Save validation results to a file."""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("QFEN Validation Results\n")
        f.write("=" * 80 + "\n\n")

        for result in results:
            status = "VALID" if result.is_valid else "INVALID"
            f.write(f"[{status}] {result.name}\n")
            f.write(f"  QFEN: {result.qfen}\n")
            f.write(f"  Description: {result.description}\n")
            f.write(f"  Category: {result.category}\n")
            f.write(f"  Source: {result.source_file}\n")
            if not result.is_valid:
                f.write(f"  Error: {result.error_message}\n")
            f.write("\n")

        total = len(results)
        valid = sum(1 for r in results if r.is_valid)
        invalid = total - valid

        f.write("-" * 80 + "\n")
        f.write("SUMMARY\n")
        f.write("-" * 80 + "\n")
        f.write(f"Total test cases: {total}\n")
        f.write(f"Valid QFEN strings: {valid} ({valid / total * 100:.1f}%)\n")
        f.write(f"Invalid QFEN strings: {invalid} ({invalid / total * 100:.1f}%)\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate QFEN strings from Quantik test fixtures"
    )
    parser.add_argument(
        "--csv-file",
        type=Path,
        default=None,
        help=(
            "Path to a CSV file with columns: qfen, name, description, "
            "category, source_file. Defaults to reading from UnifiedTestCases."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write detailed results to this file (optional).",
    )

    args = parser.parse_args()

    fixtures = load_test_fixtures(args.csv_file)
    results = validate_all_fixtures(fixtures)
    print_summary(results)

    if args.output:
        save_results(results, args.output)
        print(f"\nDetailed results saved to: {args.output}")


if __name__ == "__main__":
    main()
