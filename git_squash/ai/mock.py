"""Mock AI client for testing."""

import logging
from typing import List
from .interface import AIClient
from ..core.types import ChangeAnalysis
from ..core.config import GitSquashConfig
from ..core.analyzer import MessageFormatter

logger = logging.getLogger(__name__)


class MockAIClient(AIClient):
    """Mock AI client that generates realistic summaries for testing."""
    
    def __init__(self, config: GitSquashConfig = None):
        self.config = config or GitSquashConfig()
        self.formatter = MessageFormatter(self.config)
    
    def generate_summary(self, 
                        date: str,
                        analysis: ChangeAnalysis, 
                        commit_subjects: List[str],
                        attempt: int = 1,
                        previous_summary: str = None) -> str:
        """Generate mock summary based on analysis."""
        logger.debug("Generating mock summary for %s (attempt %d)", date, attempt)
        
        cats = analysis.categories
        
        # Build subject line following Git conventions
        subject_parts = []
        if cats.features:
            subject_parts.append(f"{len(cats.features)} features")
        if cats.fixes:
            subject_parts.append(f"{len(cats.fixes)} fixes")
        if cats.performance:
            subject_parts.append("performance improvements")
        
        if subject_parts:
            subject = f"Add {', '.join(subject_parts[:2])}"  # Limit to avoid length issues
        else:
            subject = f"Update code for {date.split('-')[1]}/{date.split('-')[2]}"
        
        # Ensure subject fits in limit
        if len(subject) > self.config.subject_line_limit:
            subject = subject[:self.config.subject_line_limit-3] + "..."
        
        # Build body with realistic descriptions
        body_lines = []
        
        # Features section
        if cats.features:
            for feat in cats.features[:3]:  # Limit to avoid length issues
                body_lines.append(self._enhance_feature_description(feat))
        
        # Fixes section
        if cats.fixes:
            for fix in cats.fixes[:2]:
                body_lines.append(f"- fix: {self._enhance_fix_description(fix)}")
        
        # Performance section
        if cats.performance:
            body_lines.append(f"- performance: {len(cats.performance)} optimizations applied")
        
        # Tests section
        if cats.tests:
            body_lines.append(f"- tests: add {len(cats.tests)} comprehensive test cases")
        
        # Add notes based on analysis
        notes = self._generate_notes(analysis, commit_subjects)
        body_lines.extend(notes)
        
        # Create full message
        raw_message = subject + "\n\n" + "\n".join(body_lines)
        
        # Apply formatting
        formatted = self.formatter.format_commit_message(raw_message)
        
        # Handle retry attempts by shortening if needed
        if attempt > 1 and len(formatted) > self.config.total_message_limit:
            # Trim body lines more aggressively
            while len(formatted) > self.config.total_message_limit and len(body_lines) > 2:
                body_lines.pop()
                raw_message = subject + "\n\n" + "\n".join(body_lines)
                formatted = self.formatter.format_commit_message(raw_message)
        
        logger.debug("Generated mock summary (%d chars)", len(formatted))
        return formatted
    
    def suggest_branch_name(self, summaries: List[str]) -> str:
        """Generate branch name based on summaries."""
        logger.debug("Generating mock branch name from %d summaries", len(summaries))
        
        # Extract key words from first few summaries
        keywords = []
        for summary in summaries[:3]:
            first_line = summary.split('\n')[0].lower()
            # Look for significant words
            if 'cache' in first_line:
                keywords.append('cache')
            elif 'buffer' in first_line:
                keywords.append('buffer')
            elif 'api' in first_line:
                keywords.append('api')
            elif 'performance' in first_line or 'optimize' in first_line:
                keywords.append('performance')
            elif 'fix' in first_line:
                keywords.append('fixes')
            elif 'feature' in first_line:
                keywords.append('features')
        
        # Generate name
        if keywords:
            if len(keywords) == 1:
                return keywords[0] + "-improvements"
            else:
                return keywords[0] + "-" + keywords[1]
        else:
            return "general-updates"
    
    def _enhance_feature_description(self, original: str) -> str:
        """Enhance feature description with realistic details."""
        lower = original.lower()
        
        if 'buffer' in lower:
            return "- implement efficient buffer management with memory pooling"
        elif 'cache' in lower:
            return "- add LRU cache layer for improved performance"
        elif 'error' in lower:
            return "- add comprehensive error handling and recovery"
        elif 'test' in lower:
            return "- implement comprehensive test coverage"
        elif 'config' in lower:
            return "- add flexible configuration system"
        else:
            # Fallback to making it more descriptive
            clean_desc = original.replace('Add ', '').replace('add ', '')
            return f"- implement {clean_desc.lower()}"
    
    def _enhance_fix_description(self, original: str) -> str:
        """Enhance fix description with realistic details."""
        lower = original.lower()
        
        if 'critical' in lower or 'bug' in lower:
            return original.replace('Fix ', '').replace('fix ', '')
        elif 'memory' in lower or 'leak' in lower:
            return "Memory leak in buffer cleanup logic"
        elif 'race' in lower or 'concurrent' in lower:
            return "Race condition in concurrent access paths"
        else:
            return original.replace('Fix ', '').replace('fix ', '')
    
    def _generate_notes(self, analysis: ChangeAnalysis, commit_subjects: List[str]) -> List[str]:
        """Generate realistic NOTE entries based on analysis."""
        notes = []
        
        # Check for mocked dependencies
        if analysis.has_mocked_dependencies:
            notes.append("- NOTE: Implementation uses mocked upstream dependencies")
        
        # Check for critical changes
        if analysis.has_critical_changes:
            notes.append("- NOTE: Contains critical stability fixes")
        
        # Check for incomplete features
        if analysis.has_incomplete_features:
            notes.append("- NOTE: Contains temporary implementation pending review")
        
        # Check commit subjects for other patterns
        all_subjects = ' '.join(commit_subjects).lower()
        
        if 'todo' in all_subjects or 'fixme' in all_subjects:
            notes.append("- NOTE: Contains TODO items requiring follow-up")
        
        if 'experimental' in all_subjects:
            notes.append("- NOTE: Includes experimental features for testing")
        
        if 'breaking' in all_subjects:
            notes.append("- NOTE: Contains breaking changes to public API")
        
        return notes