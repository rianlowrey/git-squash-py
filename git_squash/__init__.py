"""
Git Squash Tool - Clean Architecture Implementation

A tool for intelligently squashing git commits with AI-powered summaries.
"""

__version__ = "2.0.0"

from .core.config import GitSquashConfig
from .core.types import CommitInfo, SquashPlan, ChangeAnalysis
from .git.operations import GitOperations
from .ai.interface import AIClient
from .ai.claude import ClaudeClient
from .ai.mock import MockAIClient
from .tool import GitSquashTool

__all__ = [
    "GitSquashConfig",
    "CommitInfo", 
    "SquashPlan",
    "ChangeAnalysis",
    "GitOperations",
    "AIClient",
    "ClaudeClient", 
    "MockAIClient",
    "GitSquashTool"
]