"""Abstract interface for AI clients."""

from abc import ABC, abstractmethod
from typing import List
from ..core.types import ChangeAnalysis


class AIClient(ABC):
    """Abstract interface for AI providers that generate commit summaries."""
    
    @abstractmethod
    async def generate_summary(self, 
                        date: str,
                        analysis: ChangeAnalysis, 
                        commit_subjects: List[str],
                        diff_content: str = None,
                        attempt: int = 1,
                        previous_summary: str = None) -> str:
        """Generate a commit summary based on analysis and commit information.
        
        Args:
            date: The date for this summary (e.g., "2025-06-23")
            analysis: Analysis of the changes being summarized
            commit_subjects: List of original commit subjects
            diff_content: The actual diff content showing what changed
            attempt: Attempt number (for retry logic)
            previous_summary: Previous summary if this is a retry
            
        Returns:
            Formatted commit message following Git best practices
        """
        pass
    
    @abstractmethod
    async def suggest_branch_name(self, summaries: List[str]) -> str:
        """Suggest a branch name based on commit summaries.
        
        Args:
            summaries: List of commit message summaries
            
        Returns:
            Suggested branch name suffix (e.g., "cache-improvements")
        """
        pass