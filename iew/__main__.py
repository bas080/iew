"""iew - Simple AI code review tool."""
import argparse
import sys
import os

from .agent import Agent


def main():
    """Entry point - CLI mode by default."""
    parser = argparse.ArgumentParser(description='iew - AI code review tool')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Print debug statements')
    parser.add_argument('filepath', nargs='?', help='File to review')
    args = parser.parse_args()

    if not args.filepath:
        print("Usage: iew <filepath>", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"[DEBUG] Reviewing file: {args.filepath}", file=sys.stderr)

    agent = Agent()
    feedback = agent.review_file(args.filepath)

    if args.verbose:
        print(f"[DEBUG] Feedback generated: {bool(feedback)}", file=sys.stderr)

    if feedback:
        print(feedback)
    else:
        print("No feedback.")


if __name__ == "__main__":
    main()
