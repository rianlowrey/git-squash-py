"""Command line interface for the git squash tool."""

from pathlib import Path
from typing import Optional
import argparse
import asyncio
import logging
import os
import sys

from .core.config import GitSquashConfig
from .core.types import GitSquashError, NoCommitsFoundError, InvalidDateRangeError
from .git.operations import GitOperations
from .ai.claude import ClaudeClient
from .ai.mock import MockAIClient
from .tool import GitSquashTool

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    
    # Configure root logger
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Reduce noise from external libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)


def create_argument_parser() -> argparse.ArgumentParser:
    """Create the command line argument parser."""
    parser = argparse.ArgumentParser(
        description='Git Squash Tool - Intelligent commit summarization with Claude',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run                    # Show plan without executing
  %(prog)s --execute                    # Execute squashing  
  %(prog)s --start-date 2024-01-15      # Squash from specific date
  %(prog)s --start-date 2024-01-15 --end-date 2024-01-20  # Squash date range
  %(prog)s --message-limit 600          # Custom message length limit
  %(prog)s --test-mode                  # Use mock AI for testing

Environment Variables:
  ANTHROPIC_API_KEY    Required for Claude integration (unless --test-mode)
  GIT_SQUASH_VERBOSE   Set to enable debug logging
        """
    )
    
    parser.add_argument(
        '--start-date', '--from',
        help='Start date for squashing (YYYY-MM-DD)',
        metavar='DATE'
    )
    
    parser.add_argument(
        '--end-date', '--to',
        help='End date for squashing (YYYY-MM-DD, defaults to HEAD)',
        metavar='DATE'
    )
    
    parser.add_argument(
        '--combine',
        action='store_true',
        help='Combine all commits in the date range into a single commit (default: group by date)'
    )

    parser.add_argument(
        '--message-limit',
        type=int,
        default=800,
        help='Maximum commit message length in characters (default: %(default)s)',
        metavar='CHARS'
    )
    
    parser.add_argument(
        '--branch-prefix',
        default='feature/',
        help='Prefix for new branch name (default: %(default)s)',
        metavar='PREFIX'
    )
    
    # Add cache management group
    cache_group = parser.add_argument_group('cache management')
    
    cache_group.add_argument(
        '--clear-cache',
        action='store_true',
        help='Clear all cached summaries and plans'
    )
    
    cache_group.add_argument(
        '--cleanup-cache',
        action='store_true',
        help='Remove expired cache entries'
    )
    
    cache_group.add_argument(
        '--cache-stats',
        action='store_true',
        help='Display cache statistics'
    )
    
    cache_group.add_argument(
        '--cache-dir',
        type=Path,
        help='Custom cache directory (default: ~/.cache/git-squash)',
        metavar='DIR'
    )
    
    cache_group.add_argument(
        '--no-cache',
        action='store_true',
        help='Disable caching for this run'
    )

    # Execution control
    execution_group = parser.add_mutually_exclusive_group()
    execution_group.add_argument(
        '--dry-run',
        action='store_true',
        help='Show plan without executing (default behavior)'
    )
    
    execution_group.add_argument(
        '--execute',
        action='store_true',
        help='Execute the squashing operation'
    )
    
    # AI client selection
    ai_group = parser.add_mutually_exclusive_group()
    ai_group.add_argument(
        '--test-mode',
        action='store_true',
        help='Use mock AI client instead of Claude (no API key required)'
    )
    
    ai_group.add_argument(
        '--model',
        default='claude-3-7-sonnet-20250219',
        help='Claude model to use (default: %(default)s)',
        metavar='MODEL'
    )
    
    # Output control
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--save-plan',
        help='Save execution plan to JSON file',
        metavar='FILE'
    )
    
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip creating backup branch'
    )
    
    parser.add_argument(
        '--base-branch',
        default='main',
        help='Base branch to create mergeable commits from (default: %(default)s)',
        metavar='BRANCH'
    )

    return parser


def validate_environment(use_test_mode: bool) -> None:
    """Validate required environment variables."""
    if not use_test_mode and not os.environ.get('ANTHROPIC_API_KEY'):
        print("Error: ANTHROPIC_API_KEY environment variable not set", file=sys.stderr)
        print("Either set the API key or use --test-mode for testing", file=sys.stderr)
        sys.exit(1)


def create_ai_client(args, config: GitSquashConfig, cache_dir: Optional[Path] = None):
    """Create appropriate AI client based on arguments."""
    if args.test_mode:
        logger.info("Using mock AI client")
        return MockAIClient(config)
    else:
        logger.info("Using Claude AI client with caching")
        return ClaudeClient(config=config, cache_dir=cache_dir)


def save_plan_to_file(plan, filename: str) -> None:
    """Save execution plan to JSON file."""
    import json
    
    plan_data = {
        'total_original_commits': plan.total_original_commits,
        'total_squashed_commits': plan.total_squashed_commits,
        'items': []
    }
    
    for item in plan.items:
        item_data = {
            'date': item.date,
            'part': item.part,
            'commit_count': len(item.commits),
            'start_hash': item.start_hash,
            'end_hash': item.end_hash,
            'summary': item.summary,
            'author_name': item.author_info[0],
            'author_email': item.author_info[1],
            'author_date': item.author_info[2]
        }
        plan_data['items'].append(item_data)
    
    with open(filename, 'w') as f:
        json.dump(plan_data, f, indent=2)
    
    logger.info("Plan saved to %s", filename)


def display_plan(plan) -> None:
    """Display the squash plan to the user."""
    print("\n" + "=" * 80)
    print("SQUASH PLAN")
    print("=" * 80)
    
    for item in plan.items:
        part_str = f" (part {item.part})" if item.part else ""
        print(f"\n{item.date}{part_str}: {len(item.commits)} commits")
        print(f"Range: {item.start_hash[:8]}..{item.end_hash[:8]}")
        print(f"Message length: {len(item.summary)} chars")
        
        print("\nCommit message:")
        print("-" * 40)
        for line in item.summary.split('\n'):
            print(line)
        print("-" * 40)
    
    print(f"\nSummary: {plan.summary_stats()}")


def confirm_execution() -> bool:
    """Ask user to confirm execution."""
    while True:
        response = input("\nProceed with squashing? (y/n): ").lower().strip()
        if response in ('y', 'yes'):
            return True
        elif response in ('n', 'no'):
            return False
        else:
            print("Please enter 'y' or 'n'")


async def async_main(args: Optional[list] = None) -> int:
    """Async main entry point for the CLI."""
    parser = create_argument_parser()
    parsed_args = parser.parse_args(args)
    
    # Setup logging
    env_verbose = bool(os.environ.get('GIT_SQUASH_VERBOSE', ""))
    verbose = parsed_args.verbose or env_verbose
    setup_logging(verbose)
    
    try:
        # Handle cache management commands
        if parsed_args.clear_cache:
            from git_squash.core.cache import GitSquashCache
            cache = GitSquashCache(cache_dir=parsed_args.cache_dir)
            cache.clear_all()
            print("Cache cleared successfully.")
            return 0
        
        if parsed_args.cleanup_cache:
            from git_squash.core.cache import GitSquashCache
            cache = GitSquashCache(cache_dir=parsed_args.cache_dir)
            cache.clear_expired()
            stats = cache.get_stats()
            print(f"Cleaned up expired entries. Current cache size: {stats['total_size_bytes']} bytes")
            return 0
        
        if parsed_args.cache_stats:
            from git_squash.core.cache import GitSquashCache
            cache = GitSquashCache(cache_dir=parsed_args.cache_dir)
            stats = cache.get_stats()
            
            print("\nCache Statistics")
            print("=" * 40)
            print(f"Cache directory: {stats['cache_dir']}")
            print(f"Total summaries: {stats['total_summaries']}")
            print(f"Total plans: {stats['total_plans']}")
            print(f"Summary cache size: {stats['summary_cache_size_bytes']:,} bytes")
            print(f"Plan cache size: {stats['plan_cache_size_bytes']:,} bytes")
            print(f"Total size: {stats['total_size_bytes']:,} bytes")
            print(f"TTL: {stats['ttl_days']} days")
            
            # If using Claude client, show hit rate
            if not parsed_args.test_mode:
                # This would need the client instance, simplified here
                print("\nAPI Statistics")
                print("=" * 40)
                print("Run with --dry-run to see cache hit rates")
            
            return 0

        # Validate environment
        validate_environment(parsed_args.test_mode)
        
        # Create configuration
        config = GitSquashConfig.from_cli_args(parsed_args)
        logger.debug("Configuration: %s", config)
        

        # Create AI client with cache options
        if parsed_args.no_cache:
            # Create a temporary cache directory that will be cleared
            import tempfile
            cache_dir = Path(tempfile.mkdtemp(prefix="git-squash-temp-"))
        else:
            cache_dir = parsed_args.cache_dir

        # Create components
        git_ops = GitOperations(config=config)
        ai_client = create_ai_client(parsed_args, config, cache_dir=cache_dir)
        tool = GitSquashTool(git_ops, ai_client, config)
        
        # Prepare plan
        logger.info("Analyzing commits...")
        plan = await tool.prepare_squash_plan(parsed_args.start_date, parsed_args.end_date, parsed_args.combine, parsed_args.base_branch)
        
        # Display plan
        display_plan(plan)
        
        # Save plan if requested
        if parsed_args.save_plan:
            save_plan_to_file(plan, parsed_args.save_plan)
        
        # Execute if requested
        if parsed_args.execute:
            if not confirm_execution():
                print("Aborted.")
                return 0
            
            # Generate branch name
            branch_name = await tool.suggest_branch_name(plan)
            logger.info("Creating branch: %s", branch_name)
            
            # Create backup unless disabled
            if not parsed_args.no_backup:
                logger.info("Creating backup branch...")
            
            # Execute squashing
            logger.info("Executing squash plan...")
            tool.execute_squash_plan(plan, branch_name, parsed_args.base_branch)
            
            print(f"\nSuccess! Created branch: {branch_name}")
            print(f"To review: git log --oneline {branch_name}")
            print(f"To merge: git checkout main && git merge --no-ff {branch_name}")
            
        else:
            print("\nDry run complete. Use --execute to apply changes.")
        
        # At the end, show cache statistics if available
        if hasattr(ai_client, 'get_usage_stats') and not parsed_args.execute:
            stats = ai_client.get_usage_stats()
            if stats.get('cache_hits', 0) + stats.get('cache_misses', 0) > 0:
                print(f"\nCache Statistics:")
                print(f"  Hits: {stats['cache_hits']}")
                print(f"  Misses: {stats['cache_misses']}")
                print(f"  Hit rate: {stats['cache_hit_rate']:.1%}")
                print(f"  API requests saved: {stats['cache_hits']}")

        return 0
        
    except NoCommitsFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
        
    except InvalidDateRangeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
        
    except GitSquashError as e:
        logger.error("Git squash error: %s", e)
        print(f"Error: {e}", file=sys.stderr)
        return 1
        
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        return 1
        
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


def main(args: Optional[list] = None) -> int:
    """Main entry point for the CLI."""
    return asyncio.run(async_main(args))


if __name__ == '__main__':
    sys.exit(main())