#!/usr/bin/env python3
"""
QFEN Validation Script for Quantik Test Fixtures

This script validates all QFEN strings from the test fixtures CSV file using
bb_from_qfen(qfen, validate=True) and reports which ones pass or fail validation.

Usage:
    python validate_qfen_fixtures.py [--csv-file quantik_test_fixtures.csv] [--output results.txt]
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import List, Tuple, Dict, Any
from dataclasses import dataclass
from quantik_core.qfen import bb_from_qfen
from quantik_core.commons import ValidationError


@dataclass
class ValidationResult:
    """Result of validating a single QFEN string."""

    qfen: str
    name: str
    description: str
    category: str
    source_file: str
    is_valid: bool
    error_message: str = ""


def load_test_fixtures(csv_file: Path) -> List[Dict[str, Any]]:
    """Load test fixtures from CSV file."""
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
    """
    Validate a single QFEN string.

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        bb_from_qfen(qfen, validate=True)
        return True, ""
    except ValueError as e:
        return False, f"ValueError: {str(e)}"
    except ValidationError as e:
        return False, f"ValidationError: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


def validate_all_fixtures(fixtures: List[Dict[str, Any]]) -> List[ValidationResult]:
    """Validate all QFEN strings in the fixtures."""
    results = []

    print(f"Validating {len(fixtures)} QFEN strings...")
    print("-" * 80)

    for i, fixture in enumerate(fixtures, 1):
        qfen = fixture["qfen"].strip('"')  # Remove quotes if present
        name = fixture["name"]
        description = fixture["description"]
        category = fixture["category"]
        source_file = fixture["source_file"]

        print(f"[{i:2d}/{len(fixtures):2d}] {name}: ", end="")

        is_valid, error_msg = validate_qfen(qfen)

        result = ValidationResult(
            qfen=qfen,
            name=name,
            description=description,
            category=category,
            source_file=source_file,
            is_valid=is_valid,
            error_message=error_msg,
        )
        results.append(result)

        if is_valid:
            print("✅ VALID")
        else:
            print("❌ INVALID")
            print(f"     Error: {error_msg}")

    return results


def print_summary(results: List[ValidationResult]) -> None:
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
                print(f"• {result.name} ({result.category})")
                print(f"  QFEN: {result.qfen}")
                print(f"  Error: {result.error_message}")
                print()

    # Summary by category
    categories = {}
    for result in results:
        category = result.category
        if category not in categories:
            categories[category] = {"total": 0, "valid": 0}
        categories[category]["total"] += 1
        if result.is_valid:
            categories[category]["valid"] += 1

    print("\nBY CATEGORY:")
    print("-" * 40)
    for category, stats in sorted(categories.items()):
        valid_pct = stats["valid"] / stats["total"] * 100
        print(
            f"{category:15s}: {stats['valid']:2d}/{stats['total']:2d} valid ({valid_pct:5.1f}%)"
        )


def save_results(results: List[ValidationResult], output_file: Path) -> None:
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

        # Add summary at the end
        total = len(results)
        valid = sum(1 for r in results if r.is_valid)
        invalid = total - valid

        f.write("-" * 80 + "\n")
        f.write("SUMMARY\n")
        f.write("-" * 80 + "\n")
        f.write(f"Total test cases: {total}\n")
        f.write(f"Valid QFEN strings: {valid} ({valid / total * 100:.1f}%)\n")
        f.write(f"Invalid QFEN strings: {invalid} ({invalid / total * 100:.1f}%)\n")


def main():
    parser = argparse.ArgumentParser(
        description="Validate QFEN strings from Quantik test fixtures"
    )
    parser.add_argument(
        "--csv-file",
        type=Path,
        default="quantik_test_fixtures.csv",
        help="Path to the CSV file containing test fixtures (default: quantik_test_fixtures.csv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default="qfen_validation_results.txt",
        help="Output file for detailed results (default: qfen_validation_results.txt)",
    )

    args = parser.parse_args()

    print("Quantik QFEN Validation Script")
    print(f"CSV file: {args.csv_file}")
    print(f"Output file: {args.output}")
    print()

    # Load fixtures
    fixtures = load_test_fixtures(args.csv_file)

    # Validate all QFEN strings
    results = validate_all_fixtures(fixtures)

    # Print summary
    print_summary(results)

    # Save detailed results
    save_results(results, args.output)
    print(f"\nDetailed results saved to: {args.output}")


if __name__ == "__main__":
    main()
