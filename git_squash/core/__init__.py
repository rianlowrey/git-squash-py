"""Core functionality for git squash tool."""

from .cache import GitSquashCache
from .config import GitSquashConfig
from .types import (
    CommitInfo, SquashPlan, SquashPlanItem, ChangeAnalysis, CommitCategories,
    GitSquashError, NoCommitsFoundError, InvalidDateRangeError, 
    CommitAnalysisError, GitOperationError
)
from .analyzer import DiffAnalyzer, MessageFormatter

__all__ = [
    "GitSquashConfig",
    "CommitInfo", "SquashPlan", "SquashPlanItem", "ChangeAnalysis", "CommitCategories",
    "GitSquashError", "NoCommitsFoundError", "InvalidDateRangeError",
    "CommitAnalysisError", "GitOperationError", 
    "DiffAnalyzer", "MessageFormatter"
]