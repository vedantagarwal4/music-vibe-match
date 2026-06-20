"""
STEP 5 - Full Pipeline Dry Run
================================
Runs the complete pipeline end-to-end using your REAL Shazam and YouTube Music data,
but prints results to the terminal instead of sending an email.

Use this to:
  - Confirm all steps work together
  - See what songs would be scored and emailed
  - Tune the SCORE_THRESHOLD before going live

Flags:
  --limit N     Only process N songs (default: 10, good for first test)
  --all         Process your full Shazam library (slow)

Run:
  python tests/step5_full_dry_run.py           # processes last 10 Shazam songs
  python tests/step5_full_dry_run.py --limit 5  # faster, just 5 songs
  python tests/step5_full_dry_run.py --all      # your full library
"""

import sys
import os
import argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
load_dotenv()

# Bypass state file for testing - always process songs
# (state.json tracks "since last run" for production use)
import main as pipeline

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    limit = None if args.all else args.limit

    print("\nStep 5: Full pipeline dry run")
    print("=" * 50)
    if limit:
        print(f"Processing up to {limit} Shazam songs (pass --all to process your full library)")
    else:
        print("Processing your FULL Shazam library (this may take a while)")
    print()

    # Ignore state.json so we always fetch the N most recent songs regardless of last run
    pipeline.load_state = lambda: {"last_run": ""}

    try:
        pipeline.run(dry_run=True, debug=True, limit=limit)
    except SystemExit as e:
        print(f"\nExited with code {e.code}")
        sys.exit(e.code)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\nStep 5 passed. Review the songs printed above.")
    print("If the scores look right, you're ready for production deployment.")
    print("\nNext: let Claude know you're happy, and we'll deploy to GitHub Actions.")


if __name__ == "__main__":
    main()
