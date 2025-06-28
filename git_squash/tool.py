"""Main git squash tool implementation."""

import logging
import asyncio
from typing import Any, Dict, List, Optional
from .core.config import GitSquashConfig
from .core.types import (
    CommitInfo, SquashPlan, SquashPlanItem, 
    NoCommitsFoundError, InvalidDateRangeError, GitOperationError
)
from .core.analyzer import DiffAnalyzer, MessageFormatter
from .git.operations import GitOperations
from .ai.interface import AIClient

logger = logging.getLogger(__name__)


class GitSquashTool:
    """Main tool for intelligently squashing git commits."""
    
    def __init__(self, 
                 git_ops: GitOperations,
                 ai_client: AIClient,
                 config: GitSquashConfig):
        self.git_ops = git_ops
        self.ai_client = ai_client
        self.config = config
        self.analyzer = DiffAnalyzer(config)
        self.formatter = MessageFormatter(config)
    
    async def prepare_squash_plan(self, start_date: Optional[str] = None, end_date: Optional[str] = None, combine: bool = False, base_branch: str = "main") -> SquashPlan:
        """Prepare a complete squash plan."""
        logger.info("Preparing squash plan (start_date=%s, end_date=%s, combine=%s, base_branch=%s)", start_date, end_date, combine, base_branch)
        
        # Get commits grouped by date, only including commits not in base branch
        commits_by_date = self.git_ops.get_commits_by_date(start_commit=base_branch)
        
        # Filter by date range if provided
        if start_date or end_date:
            filtered_commits = {}
            for date, commits in commits_by_date.items():
                include_date = True
                if start_date and date < start_date:
                    include_date = False
                if end_date and date > end_date:
                    include_date = False
                if include_date:
                    filtered_commits[date] = commits
            commits_by_date = filtered_commits
            
            if not commits_by_date:
                date_range = f"between {start_date or 'beginning'} and {end_date or 'HEAD'}"
                raise InvalidDateRangeError(f"No commits found {date_range}")
        
        if not commits_by_date:
            raise NoCommitsFoundError("No commits found to squash")
        
        # Collect all commits for cache key
        all_commits = []
        for commits in commits_by_date.values():
            all_commits.extend(commits)
        
        # Sort all commits chronologically when combining
        if combine:
            all_commits.sort(key=lambda c: c.datetime)

        # Check if we have a cached plan (if AI client supports caching)
        if hasattr(self.ai_client, 'cache'):
            cached_plan_data = self.ai_client.cache.get_plan(
                start_date, end_date, all_commits, self.config
            )
            
            if cached_plan_data:
                logger.info("Using cached squash plan")
                # Reconstruct plan from cached data
                plan = self._reconstruct_plan_from_cache(cached_plan_data, commits_by_date)
                if plan:
                    return plan
        
        # Process commits based on combine flag
        plan_items = []
        total_commits = sum(len(commits) for commits in commits_by_date.values())
        
        if combine:
            # Combine all commits (filtered or unfiltered) into a single squash
            logger.info("Combining %d commits into a single commit", total_commits)
            
            # Determine date description for the combined commit
            dates = sorted(commits_by_date.keys())
            if len(dates) == 1:
                combined_date = dates[0]
            else:
                combined_date = f"{dates[0]} to {dates[-1]}"
            
            # Process all commits together
            combined_items = await self._process_commits(combined_date, all_commits)
            plan_items.extend(combined_items)
        else:
            # Process each day separately (default behavior)
            for date in sorted(commits_by_date.keys()):
                commits = commits_by_date[date]

                logger.info("Processing %s: %d commits", date, len(commits))

                # Try to create summary for all commits in the day
                day_items = await self._process_commits(date, commits)
                plan_items.extend(day_items)
        
        plan = SquashPlan(
            items=plan_items,
            total_original_commits=total_commits,
            config=self.config
        )
        
        # Cache the plan (if AI client supports caching)
        if hasattr(self.ai_client, 'cache'):
            self.ai_client.cache.set_plan(
                start_date, end_date, all_commits, self.config, plan
            )
        
        logger.info("Plan complete: %s", plan.summary_stats())
        return plan
    
    def execute_squash_plan(self, plan: SquashPlan, target_branch: str, base_branch: str = "main") -> None:
        """Execute a squash plan and invalidate cache."""
        logger.info("Executing squash plan on branch: %s from base: %s", target_branch, base_branch)
        
        # Create backup
        backup_branch = self.git_ops.create_backup_branch()
        logger.info("Created backup: %s", backup_branch)
        
        # Create target branch from base branch to ensure mergeable commits
        self.git_ops.create_branch(target_branch, base_branch)
        
        # Get parent of first commit to reset to
        first_item = plan.items[0]
        first_commit = first_item.commits[0].hash
        
        try:
            # Try to get parent commit
            parent_result = self.git_ops._run_git_command(
                ["rev-parse", f"{first_commit}^"], 
                check=False
            )
            
            if parent_result.returncode == 0:
                # Reset to parent
                parent_hash = parent_result.stdout.strip()
                self.git_ops.reset_to_commit(parent_hash)
            else:
                # First commit in repo - start from empty
                logger.info("First commit in repository, starting from empty state")
                # We'll handle this in the commit creation loop
                
        except Exception as e:
            logger.warning("Could not determine parent commit: %s", e)
        
        # Get the base branch HEAD to use as parent for first commit
        try:
            base_head_result = self.git_ops._run_git_command(["rev-parse", base_branch])
            base_head = base_head_result.stdout.strip()
            logger.debug("Base branch %s is at commit %s", base_branch, base_head[:8])
        except Exception as e:
            logger.error("Cannot resolve base branch %s: %s", base_branch, e)
            raise GitOperationError(f"Cannot resolve base branch '{base_branch}': {e}")

        # Apply each squashed commit
        current_parent = None  # Will be determined based on original ancestry
        for i, item in enumerate(plan.items):
            logger.info("Creating commit %d/%d: %s", i+1, len(plan.items), item.display_name)
            
            # Get tree from the end commit of this item
            tree_hash = self.git_ops.get_tree_hash(item.end_hash)
            
            # Get parent for this commit
            if current_parent is None:
                # First commit - check if original had a parent
                try:
                    parent_result = self.git_ops._run_git_command(
                        ["rev-parse", f"{first_commit}^"],
                        check=False
                    )
                    if parent_result.returncode == 0:
                        original_parent = parent_result.stdout.strip()

                        # Check if the original parent is reachable from base branch
                        # This prevents issues with incremental squashing where the parent was squashed away
                        merge_base_result = self.git_ops._run_git_command(
                            ["merge-base", "--is-ancestor", original_parent, base_head],
                            check=False
                        )

                        if merge_base_result.returncode == 0:
                            # Original parent is an ancestor of base branch - safe to preserve ancestry
                            current_parent = original_parent
                            logger.debug("Preserving original ancestry, parent: %s", current_parent[:8])
                        else:
                            # Original parent is not in base branch history (likely squashed) - use base head
                            current_parent = base_head
                            logger.info("Original parent not in base branch, using base branch %s at %s", base_branch, base_head[:8])
                    else:
                        # Original was root commit - graft onto base branch instead of creating orphan
                        current_parent = base_head
                        logger.info("Grafting root commit onto base branch %s at %s", base_branch, base_head[:8])
                except Exception as e:
                    # Fallback to base branch HEAD to ensure mergeability
                    current_parent = base_head
                    logger.warning("Could not determine original parent, using base branch: %s", e)
            
            # Create the commit (we always have a valid parent now)
            author_name, author_email, author_date = item.author_info
            new_commit = self.git_ops.create_commit(
                message=item.summary,
                tree_hash=tree_hash,
                parent_hash=current_parent,
                author_name=author_name,
                author_email=author_email,
                author_date=author_date
            )
            
            # Update HEAD and set up for next iteration
            self.git_ops.update_head(new_commit)
            current_parent = new_commit
            
            logger.debug("Created commit %s", new_commit[:8])
        
        # Invalidate plan cache after successful execution
        if hasattr(self.ai_client, 'invalidate_plan_cache'):
            self.ai_client.invalidate_plan_cache(plan)
        
        logger.info("Squash execution complete!")
    
    async def suggest_branch_name(self, plan: SquashPlan) -> str:
        """Suggest a branch name based on the squash plan."""
        summaries = [item.summary for item in plan.items]
        suffix = await self.ai_client.suggest_branch_name(summaries)
        return f"{self.config.branch_prefix}{suffix}"
    
    async def _process_commits(self, date: str, commits: List[CommitInfo], depth: int = 0) -> List[SquashPlanItem]:
        """Process commits for a given date or date range, splitting if necessary."""
        # Prevent infinite recursion
        MAX_RECURSION_DEPTH = 10
        if depth > MAX_RECURSION_DEPTH:
            logger.warning("Maximum recursion depth reached for date %s with %d commits", date, len(commits))
            # Create basic summary without AI generation to avoid further recursion
            analysis = self._analyze_commits(commits)
            return [SquashPlanItem(
                date=date,
                commits=commits,
                summary=f"Update {date} ({len(commits)} commits)",
                analysis=analysis
            )]
        
        # For single commits, still generate summary to improve the message
        if len(commits) <= 1:
            logger.debug("Processing single commit for date %s", date)
            # Still generate a summary to improve the original commit message
            summary = await self._generate_summary_with_retry(date, commits)
            analysis = self._analyze_commits(commits)
            return [SquashPlanItem(
                date=date,
                commits=commits,
                summary=summary,
                analysis=analysis
            )]
        
        # Try to create a single summary for all commits
        summary = await self._generate_summary_with_retry(date, commits)
        
        # Check if summary fits within limits
        if len(summary) <= self.config.total_message_limit:
            # Single item for the day
            analysis = self._analyze_commits(commits)
            return [SquashPlanItem(
                date=date,
                commits=commits,
                summary=summary,
                analysis=analysis
            )]
        
        # Need to split the day
        logger.info("Summary too long (%d chars), splitting day", len(summary))
        return await self._split_day_commits(date, commits)
    
    async def _split_day_commits(self, date: str, commits: List[CommitInfo]) -> List[SquashPlanItem]:
        """Split day's commits into multiple groups."""
        if len(commits) == 1:
            # Can't split further - generate the best summary possible
            summary = await self._generate_summary_with_retry(date, commits)
            analysis = self._analyze_commits(commits)
            
            # Truncate if still too long
            if len(summary) > self.config.total_message_limit:
                lines = summary.split('\n')
                truncated = [lines[0], ""] if lines else ["Update " + date, ""]
                char_count = len('\n'.join(truncated))
                
                for line in lines[2:] if len(lines) > 2 else []:
                    if char_count + len(line) + 1 > self.config.total_message_limit - 20:
                        truncated.append("- ...additional changes")
                        break
                    truncated.append(line)
                    char_count += len(line) + 1
                
                summary = '\n'.join(truncated)
            
            return [SquashPlanItem(
                date=date,
                commits=commits,
                summary=summary,
                analysis=analysis
            )]
        
        # Split commits using binary approach
        mid = len(commits) // 2
        first_half = commits[:mid]
        second_half = commits[mid:]
        
        # Recursively process each half
        result = []
        result.extend(await self._process_commits(date, first_half, depth + 1))
        result.extend(await self._process_commits(date, second_half, depth + 1))
        
        # Add part numbers
        for i, item in enumerate(result, 1):
            if item.date == date:  # Only update items from this date
                item.part = i
        
        return result
    
    async def _generate_summary_with_retry(self, date: str, commits: List[CommitInfo]) -> str:
        """Generate summary with retry logic and caching."""
        analysis = self._analyze_commits(commits)
        subjects = [c.subject for c in commits]
        
        # Get the actual diff content for this range
        start_commit = commits[0].hash
        end_commit = commits[-1].hash
        diff_content = self.git_ops.get_diff(start_commit, end_commit)
        
        summary = None
        for attempt in range(1, self.config.max_retry_attempts + 1):
            # Pass commits for caching support
            if hasattr(self.ai_client.generate_summary, '__code__') and \
               'commits' in self.ai_client.generate_summary.__code__.co_varnames:
                # New interface with commits parameter
                summary = await self.ai_client.generate_summary(
                    date=date,
                    analysis=analysis,
                    commit_subjects=subjects,
                    diff_content=diff_content,
                    attempt=attempt,
                    previous_summary=summary,
                    commits=commits  # Pass for caching
                )
            else:
                # Old interface without commits parameter
                summary = await self.ai_client.generate_summary(
                    date=date,
                    analysis=analysis,
                    commit_subjects=subjects,
                    diff_content=diff_content,
                    attempt=attempt,
                    previous_summary=summary
                )
            
            if len(summary) <= self.config.total_message_limit:
                return summary
            
            logger.debug("Summary attempt %d was %d chars (limit: %d)", 
                        attempt, len(summary), self.config.total_message_limit)
        
        # If still too long after retries, the splitting logic will handle it
        return summary
    
    def _analyze_commits(self, commits: List[CommitInfo]) -> 'ChangeAnalysis':
        """Analyze a group of commits."""
        if not commits:
            # Return minimal analysis for empty commits
            from .core.types import ChangeAnalysis, CommitCategories
            return ChangeAnalysis(
                categories=CommitCategories([], [], [], [], [], [], [], []),
                diff_stats="",
                has_critical_changes=False,
                has_mocked_dependencies=False,
                has_incomplete_features=False,
                file_changes={}
            )
        
        # Get diff for this range
        start_commit = commits[0].hash
        end_commit = commits[-1].hash
        
        diff_text = self.git_ops.get_diff(start_commit, end_commit)
        diff_stats = self.git_ops.get_diff_stats(start_commit, end_commit)
        
        # Analyze the changes
        analysis = self.analyzer.analyze_changes(commits, diff_text, diff_stats)
        return analysis
    
    def _reconstruct_plan_from_cache(
        self, 
        cached_data: Dict[str, Any], 
        commits_by_date: Dict[str, List[CommitInfo]]
    ) -> Optional[SquashPlan]:
        """Reconstruct a SquashPlan from cached data."""
        try:
            plan_items = []
            
            for item_data in cached_data.get("items", []):
                date = item_data["date"]
                
                # Find the commits for this item
                item_commits = []
                commit_hashes = set(item_data.get("commit_hashes", []))
                
                # Look through all dates to find matching commits
                for date_commits in commits_by_date.values():
                    for commit in date_commits:
                        if commit.hash in commit_hashes:
                            item_commits.append(commit)
                
                if len(item_commits) == item_data["commit_count"]:
                    # Sort commits by their order in commit_hashes
                    hash_order = {h: i for i, h in enumerate(item_data["commit_hashes"])}
                    item_commits.sort(key=lambda c: hash_order.get(c.hash, float('inf')))
                    
                    plan_item = SquashPlanItem(
                        date=date,
                        commits=item_commits,
                        summary=item_data["summary"],
                        part=item_data.get("part"),
                        analysis=self._analyze_commits(item_commits)
                    )
                    plan_items.append(plan_item)
                else:
                    logger.warning("Cache mismatch: expected %d commits, found %d",
                                 item_data["commit_count"], len(item_commits))
                    return None
            
            if len(plan_items) == len(cached_data.get("items", [])):
                return SquashPlan(
                    items=plan_items,
                    total_original_commits=cached_data["total_original_commits"],
                    config=self.config
                )
            else:
                logger.warning("Failed to reconstruct all plan items from cache")
                return None
                
        except Exception as e:
            logger.error("Error reconstructing plan from cache: %s", e)
            return None