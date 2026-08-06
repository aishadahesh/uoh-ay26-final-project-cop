"""Validate the email-ready Police-Thief JSON artifact set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from police_thief.services.submission_artifacts import validate_submission_directory


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate all mandatory JSON files before submission email",
    )
    parser.add_argument("--directory", type=Path, default=Path("results/network"))
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--json", action="store_true", help="emit machine-readable errors")
    args = parser.parse_args()
    errors, paths = validate_submission_directory(args.directory, args.game_id)
    if errors:
        if args.json:
            print(json.dumps([error.to_dict() for error in errors], indent=2, ensure_ascii=False))
        else:
            print(f"SUBMISSION INVALID: {len(errors)} error(s)")
            for error in errors:
                print(f"- {error}")
        return 1
    print(f"SUBMISSION VALID: {len(paths)} required JSON attachment(s)")
    for path in paths:
        print(f"- {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
