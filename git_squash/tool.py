"""Main git squash tool implementation."""

import logging
from typing import List, Optional
from .core.config import GitSquashConfig
from .core.types import (
    CommitInfo, SquashPlan, SquashPlanItem, 
    NoCommitsFoundError, InvalidDateRangeError
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
    
    def prepare_squash_plan(self, start_date: Optional[str] = None) -> SquashPlan:
        """Prepare a complete squash plan."""
        logger.info("Preparing squash plan (start_date=%s)", start_date)
        
        # Get commits grouped by date
        commits_by_date = self.git_ops.get_commits_by_date()
        
        # Filter by start date if provided
        if start_date:
            commits_by_date = {
                date: commits for date, commits in commits_by_date.items()
                if date >= start_date
            }
            
            if not commits_by_date:
                raise InvalidDateRangeError(f"No commits found after {start_date}")
        
        if not commits_by_date:
            raise NoCommitsFoundError("No commits found to squash")
        
        # Process each day
        plan_items = []
        total_commits = 0
        
        for date in sorted(commits_by_date.keys()):
            commits = commits_by_date[date]
            total_commits += len(commits)
            
            logger.info("Processing %s: %d commits", date, len(commits))
            
            # Try to create summary for all commits in the day
            day_items = self._process_day_commits(date, commits)
            plan_items.extend(day_items)
        
        plan = SquashPlan(
            items=plan_items,
            total_original_commits=total_commits,
            config=self.config
        )
        
        logger.info("Plan complete: %s", plan.summary_stats())
        return plan
    
    def execute_squash_plan(self, plan: SquashPlan, target_branch: str) -> None:
        """Execute a squash plan."""
        logger.info("Executing squash plan on branch: %s", target_branch)
        
        # Create backup
        backup_branch = self.git_ops.create_backup_branch()
        logger.info("Created backup: %s", backup_branch)
        
        # Create target branch
        self.git_ops.create_branch(target_branch)
        
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
        
        # Apply each squashed commit
        current_parent = None
        for i, item in enumerate(plan.items):
            logger.info("Creating commit %d/%d: %s", i+1, len(plan.items), item.display_name)
            
            # Get tree from the end commit of this item
            tree_hash = self.git_ops.get_tree_hash(item.end_hash)
            
            # Get parent for this commit
            if current_parent is None:
                # First commit - try to get parent of original first commit
                try:
                    parent_result = self.git_ops._run_git_command(
                        ["rev-parse", f"{first_commit}^"],
                        check=False
                    )
                    if parent_result.returncode == 0:
                        current_parent = parent_result.stdout.strip()
                    else:
                        # No parent - this will be root commit
                        current_parent = None
                except:
                    current_parent = None
            
            # Create the commit
            if current_parent:
                author_name, author_email, author_date = item.author_info
                new_commit = self.git_ops.create_commit(
                    message=item.summary,
                    tree_hash=tree_hash,
                    parent_hash=current_parent,
                    author_name=author_name,
                    author_email=author_email,
                    author_date=author_date
                )
            else:
                # Root commit case - handle differently
                logger.info("Creating root commit")
                # For root commits, we need to use commit-tree without parent
                import os
                env = os.environ.copy()
                author_name, author_email, author_date = item.author_info
                env.update({
                    'GIT_AUTHOR_NAME': author_name,
                    'GIT_AUTHOR_EMAIL': author_email,
                    'GIT_AUTHOR_DATE': author_date
                })
                
                result = self.git_ops._run_git_command([
                    "commit-tree", tree_hash, "-m", item.summary
                ])
                new_commit = result.stdout.strip()
            
            # Update HEAD and set up for next iteration
            self.git_ops.update_head(new_commit)
            current_parent = new_commit
            
            logger.debug("Created commit %s", new_commit[:8])
        
        logger.info("Squash execution complete!")
    
    def suggest_branch_name(self, plan: SquashPlan) -> str:
        """Suggest a branch name based on the squash plan."""
        summaries = [item.summary for item in plan.items]
        suffix = self.ai_client.suggest_branch_name(summaries)
        return f"{self.config.default_branch_prefix}{suffix}"
    
    def _process_day_commits(self, date: str, commits: List[CommitInfo]) -> List[SquashPlanItem]:
        """Process commits for a single day, splitting if necessary."""
        # Try to create a single summary for all commits
        summary = self._generate_summary_with_retry(date, commits)
        
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
        return self._split_day_commits(date, commits)
    
    def _split_day_commits(self, date: str, commits: List[CommitInfo]) -> List[SquashPlanItem]:
        """Split day's commits into multiple groups."""
        if len(commits) == 1:
            # Can't split further - use truncated summary
            analysis = self._analyze_commits(commits)
            summary = self._generate_summary_with_retry(date, commits)
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
        result.extend(self._process_day_commits(date, first_half))
        result.extend(self._process_day_commits(date, second_half))
        
        # Add part numbers
        for i, item in enumerate(result, 1):
            if item.date == date:  # Only update items from this date
                item.part = i
        
        return result
    
    def _generate_summary_with_retry(self, date: str, commits: List[CommitInfo]) -> str:
        """Generate summary with retry logic."""
        analysis = self._analyze_commits(commits)
        subjects = [c.subject for c in commits]
        
        summary = None
        for attempt in range(1, self.config.max_retry_attempts + 1):
            summary = self.ai_client.generate_summary(
                date=date,
                analysis=analysis,
                commit_subjects=subjects,
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