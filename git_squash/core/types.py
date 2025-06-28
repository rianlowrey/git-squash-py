"""Type definitions for the git squash tool."""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict
from enum import Enum


@dataclass
class CommitInfo:
    """Information about a single commit."""
    hash: str
    date: str  # ISO format string
    subject: str
    author_name: str
    author_email: str
    datetime: datetime
    
    @property
    def short_hash(self) -> str:
        """Get short version of commit hash."""
        return self.hash[:8]


@dataclass  
class CommitCategories:
    """Categorized commit information."""
    features: List[str]
    fixes: List[str]
    tests: List[str]
    docs: List[str]
    dependencies: List[str]
    refactoring: List[str]
    performance: List[str]
    other: List[str]
    
    @property
    def total_count(self) -> int:
        """Total number of categorized commits."""
        return sum(len(getattr(self, field.name)) for field in self.__dataclass_fields__.values())


@dataclass
class ChangeAnalysis:
    """Analysis of changes in a set of commits."""
    categories: CommitCategories
    diff_stats: str
    has_critical_changes: bool
    has_mocked_dependencies: bool
    has_incomplete_features: bool
    file_changes: Dict[str, int]  # filename -> change count
    
    @property
    def needs_review_notes(self) -> bool:
        """Whether this change needs special review notes."""
        return (self.has_critical_changes or 
                self.has_mocked_dependencies or 
                self.has_incomplete_features)


@dataclass
class SquashPlanItem:
    """Single item in a squash plan."""
    date: str
    commits: List[CommitInfo]
    summary: str
    part: Optional[int] = None
    analysis: Optional[ChangeAnalysis] = None
    
    @property
    def start_hash(self) -> str:
        """Hash of first commit in this item."""
        return self.commits[0].hash if self.commits else ""
    
    @property 
    def end_hash(self) -> str:
        """Hash of last commit in this item.""" 
        return self.commits[-1].hash if self.commits else ""
    
    @property
    def author_info(self) -> tuple[str, str, str]:
        """Author info from first commit (name, email, date)."""
        if not self.commits:
            return ("", "", "")
        first = self.commits[0]
        return (first.author_name, first.author_email, first.date)
    
    @property
    def display_name(self) -> str:
        """Display name for this squash item."""
        part_suffix = f" (part {self.part})" if self.part else ""
        return f"{self.date}{part_suffix}"


@dataclass
class SquashPlan:
    """Complete plan for squashing commits."""
    items: List[SquashPlanItem]
    total_original_commits: int
    config: 'GitSquashConfig'
    
    @property
    def total_squashed_commits(self) -> int:
        """Number of commits after squashing."""
        return len(self.items)
    
    def summary_stats(self) -> str:
        """Get summary statistics as string."""
        return f"{self.total_original_commits} commits → {self.total_squashed_commits} squashed commits"


class GitSquashError(Exception):
    """Base exception for git squash operations."""
    pass


class InvalidDateRangeError(GitSquashError):
    """Raised when date range contains no commits."""
    pass


class NoCommitsFoundError(GitSquashError):
    """Raised when no commits are found to squash."""
    pass


class CommitAnalysisError(GitSquashError):
    """Raised when commit analysis fails.""" 
    pass


class GitOperationError(GitSquashError):
    """Raised when git operations fail."""
    pass