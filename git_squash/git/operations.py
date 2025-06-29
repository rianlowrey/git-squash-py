"""Git operations for the squash tool."""

import os
import subprocess
import logging
from datetime import datetime
from typing import List, Dict, Optional
from ..core.types import CommitInfo, GitOperationError, SquashPlanItem
from ..core.config import GitSquashConfig

logger = logging.getLogger(__name__)


class GitOperations:
    """Handles all git operations for the squash tool."""
    
    def __init__(self, config: Optional[GitSquashConfig] = None):
        self.config = config or GitSquashConfig()
        self._validate_git_repository()
    
    def _run_git_command(self, cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command and return the result."""
        full_cmd = ["git"] + cmd
        logger.debug("Running git command: %s", " ".join(full_cmd))
        
        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                check=check
            )
            return result
        except subprocess.CalledProcessError as e:
            logger.error("Git command failed: %s\nStderr: %s", " ".join(full_cmd), e.stderr)
            raise GitOperationError(f"Git command failed: {e.stderr}")
    
    def _validate_git_repository(self) -> None:
        """Validate that we're in a git repository."""
        try:
            result = self._run_git_command(["rev-parse", "--git-dir"], check=True)
            logger.debug("Git repository found at: %s", result.stdout.strip())
        except GitOperationError:
            raise GitOperationError(
                "Not in a git repository. Please run this command from within a git repository."
            )
    
    def get_commits_by_date(self, start_commit: Optional[str] = None, end_commit: str = "HEAD") -> Dict[str, List[CommitInfo]]:
        """Get commits grouped by date."""
        logger.info("Fetching commits from %s to %s", start_commit or "beginning", end_commit)
        
        # Use ASCII unit separator (0x1F) as delimiter - very unlikely to appear in commit messages
        cmd = ["log", "--reverse", "--pretty=format:%H\x1F%ad\x1F%s\x1F%an\x1F%ae", "--date=iso-strict-local"]
        
        if start_commit:
            cmd.append(f"{start_commit}..{end_commit}")
        else:
            cmd.append(end_commit)
            
        result = self._run_git_command(cmd)
        
        commits_by_date = {}
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
                
            try:
                parts = line.split('\x1F', 4)
                if len(parts) != 5:
                    logger.warning("Skipping malformed commit line: %s", repr(line))
                    continue
                    
                hash_id, date_str, subject, author_name, author_email = parts
                
                # Parse date with proper error handling
                try:
                    # Handle different timezone formats
                    normalized_date = date_str.replace('+00:00', '+0000')
                    date_obj = datetime.fromisoformat(normalized_date)
                except ValueError as e:
                    logger.warning("Failed to parse date '%s' for commit %s: %s", date_str, hash_id[:8], e)
                    # Use current date as fallback
                    date_obj = datetime.now()
                
                date_key = date_obj.strftime('%Y-%m-%d')
                
                commit = CommitInfo(
                    hash=hash_id,
                    date=date_str,
                    subject=subject,
                    author_name=author_name,
                    author_email=author_email,
                    datetime=date_obj
                )
                
                if date_key not in commits_by_date:
                    commits_by_date[date_key] = []
                commits_by_date[date_key].append(commit)
                
            except Exception as e:
                logger.warning("Error parsing commit line '%s': %s", line, e)
                continue
        
        logger.info("Found %d days with commits", len(commits_by_date))
        return commits_by_date
    
    def get_diff(self, start_commit: str, end_commit: str) -> str:
        """Get diff between two commits."""
        logger.debug("Getting diff from %s to %s", start_commit[:8], end_commit[:8])
        
        # Try with parent first
        result = self._run_git_command(
            ["diff", f"{start_commit}^..{end_commit}"], 
            check=False
        )
        
        if result.returncode != 0:
            # Handle first commit case
            if start_commit == end_commit:
                result = self._run_git_command(["show", "--pretty=", start_commit])
            else:
                result = self._run_git_command(["diff", start_commit, end_commit])
        
        return result.stdout
    
    def get_diff_stats(self, start_commit: str, end_commit: str) -> str:
        """Get diff statistics between commits."""
        logger.debug("Getting diff stats from %s to %s", start_commit[:8], end_commit[:8])
        
        result = self._run_git_command(
            ["diff", f"{start_commit}^..{end_commit}", "--stat"],
            check=False
        )
        
        if result.returncode != 0:
            if start_commit == end_commit:
                result = self._run_git_command(["show", "--stat", "--pretty=", start_commit])
            else:
                result = self._run_git_command(["diff", start_commit, end_commit, "--stat"])
        
        return result.stdout
    
    def get_current_branch(self) -> str:
        """Get the name of the current branch."""
        result = self._run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
        return result.stdout.strip()
    
    def create_backup_branch(self, backup_name: Optional[str] = None) -> str:
        """Create a backup branch pointing to current HEAD."""
        if backup_name is None:
            backup_name = f"{self.config.backup_branch_prefix}pre-squash"
        
        logger.info("Creating backup branch: %s", backup_name)
        self._run_git_command(["branch", "-f", backup_name, "HEAD"])
        return backup_name
    
    def create_branch(self, branch_name: str, start_point: str = "HEAD") -> None:
        """Create a new branch."""
        logger.info("Creating branch: %s from %s", branch_name, start_point)
        self._run_git_command(["checkout", "-b", branch_name, start_point])
    
    def checkout_branch(self, branch_name: str) -> None:
        """Checkout an existing branch."""
        logger.info("Checking out branch: %s", branch_name)
        self._run_git_command(["checkout", branch_name])
    
    def reset_to_commit(self, commit_hash: str, hard: bool = True) -> None:
        """Reset current branch to a specific commit."""
        reset_type = "--hard" if hard else "--soft"
        logger.info("Resetting to commit %s (%s)", commit_hash[:8], reset_type)
        self._run_git_command(["reset", reset_type, commit_hash])
    
    def create_commit(self, message: str, tree_hash: str, parent_hash: str, 
                     author_name: str, author_email: str, author_date: str) -> str:
        """Create a new commit with specific metadata."""
        logger.debug("Creating commit with tree %s, parent %s", tree_hash[:8], parent_hash[:8])
        
        # Set environment variables for author info
        env = os.environ.copy()
        env.update({
            'GIT_AUTHOR_NAME': author_name,
            'GIT_AUTHOR_EMAIL': author_email,
            'GIT_AUTHOR_DATE': author_date
        })
        
        # Create the commit
        cmd = ["commit-tree", tree_hash, "-p", parent_hash, "-m", message]
        result = subprocess.run(
            ["git"] + cmd,
            env=env,
            capture_output=True,
            text=True,
            check=True
        )
        
        return result.stdout.strip()
    
    def get_tree_hash(self, commit_hash: str) -> str:
        """Get the tree hash for a commit."""
        result = self._run_git_command(["rev-parse", f"{commit_hash}^{{tree}}"])
        return result.stdout.strip()
    
    def update_head(self, commit_hash: str) -> None:
        """Update HEAD to point to a specific commit."""
        logger.debug("Updating HEAD to %s", commit_hash[:8])
        self._run_git_command(["reset", "--hard", commit_hash])
    
    def get_commit_count(self, ref: str = "HEAD") -> int:
        """Get the number of commits in a ref."""
        result = self._run_git_command(["rev-list", "--count", ref])
        return int(result.stdout.strip())
    
    def branch_exists(self, branch_name: str) -> bool:
        """Check if a branch exists."""
        result = self._run_git_command(["show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"], check=False)
        return result.returncode == 0