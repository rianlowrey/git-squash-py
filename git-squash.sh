#!/bin/bash
# Git Squash Wrapper - Easy to use interface for the squash tool

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check for ANTHROPIC_API_KEY (unless using test backend)
if [ "$USE_TEST_BACKEND" != "1" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "${RED}Error: ANTHROPIC_API_KEY not set${NC}"
    echo "Please run: export ANTHROPIC_API_KEY='your-key-here'"
    echo "Or use: USE_TEST_BACKEND=1 ./git-squash"
    exit 1
fi

# Default to dry-run for safety
DRY_RUN="--dry-run"
ARGS=""

# Parse arguments
while [ $# -gt 0 ]; do
    case $1 in
        --execute|-e)
            DRY_RUN=""
            shift
            ;;
        --help|-h)
            echo "Git Squash Tool - Intelligent commit summarization"
            echo ""
            echo "Usage: ./git-squash [options]"
            echo ""
            echo "Options:"
            echo "  --execute, -e     Execute the squash (default is dry-run)"
            echo "  --from DATE       Start from specific date (YYYY-MM-DD)"
            echo "  --limit CHARS     Message character limit (default: 800)"
            echo "  --help, -h        Show this help"
            echo ""
            echo "Examples:"
            echo "  ./git-squash                  # Dry run, show plan"
            echo "  ./git-squash --execute        # Execute squashing"
            echo "  ./git-squash --from 2024-01-01 --execute"
            echo ""
            exit 0
            ;;
        --from)
            if [ -z "$2" ] || [[ "$2" =~ ^- ]]; then
                echo -e "${RED}Error: --from requires a date argument${NC}" >&2
                exit 1
            fi
            # Validate date format (basic YYYY-MM-DD check)
            if [[ ! "$2" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
                echo -e "${RED}Error: Date must be in YYYY-MM-DD format${NC}" >&2
                exit 1
            fi
            ARGS="$ARGS --start-date $(printf '%q' "$2")"
            shift 2
            ;;
        --limit)
            if [ -z "$2" ] || [[ "$2" =~ ^- ]]; then
                echo -e "${RED}Error: --limit requires a number argument${NC}" >&2
                exit 1
            fi
            # Validate it's a positive integer
            if [[ ! "$2" =~ ^[0-9]+$ ]] || [ "$2" -lt 1 ] || [ "$2" -gt 10000 ]; then
                echo -e "${RED}Error: --limit must be a number between 1 and 10000${NC}" >&2
                exit 1
            fi
            ARGS="$ARGS --message-limit $(printf '%q' "$2")"
            shift 2
            ;;
        --*)
            echo -e "${RED}Error: Unknown option $1${NC}" >&2
            echo "Use --help for usage information" >&2
            exit 1
            ;;
        *)
            echo -e "${RED}Error: Unexpected argument $1${NC}" >&2
            echo "Use --help for usage information" >&2
            exit 1
            ;;
    esac
done

# Show current status
echo -e "${GREEN}Git Squash Tool - Focused Summaries${NC}"
echo "Current branch: $(git branch --show-current)"
echo "Total commits: $(git rev-list --count HEAD)"

if [ -z "$DRY_RUN" ]; then
    echo -e "${YELLOW}Mode: EXECUTE${NC}"
    echo -e "${YELLOW}Warning: This will create a new branch with squashed commits${NC}"
    read -p "Continue? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 1
    fi
else
    echo -e "${GREEN}Mode: DRY RUN (use --execute to apply)${NC}"
fi

echo ""

# Determine which backend to use
SCRIPT_DIR="$(dirname "$0")"

# Check if we should use test backend
if [ "$USE_TEST_BACKEND" = "1" ] || [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "${YELLOW}Using test backend (no API key required)${NC}"
    python3 -m git_squash.cli --test-mode $DRY_RUN $ARGS
else
    # Use real backend
    python3 -m git_squash.cli $DRY_RUN $ARGS
fi