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
    
    async def generate_summary(self, 
                        date: str,
                        analysis: ChangeAnalysis, 
                        commit_subjects: List[str],
                        diff_content: str = None,
                        attempt: int = 1,
                        previous_summary: str = None) -> str:
        """Generate mock summary based on analysis and diff content."""
        logger.debug("Generating mock summary for %s (attempt %d)", date, attempt)
        
        cats = analysis.categories
        
        # Analyze the diff content to create meaningful subject
        subject = self._generate_meaningful_subject(cats, commit_subjects, diff_content, date)
        
        # Ensure subject fits in limit
        if len(subject) > self.config.subject_line_limit:
            subject = subject[:self.config.subject_line_limit-3] + "..."
        
        # Build body with realistic descriptions based on diff analysis
        body_lines = self._generate_body_from_diff(cats, commit_subjects, diff_content, analysis)
        
        # Create full message
        if body_lines:
            raw_message = subject + "\n\n" + "\n".join(body_lines)
        else:
            raw_message = subject
        
        # Apply formatting
        formatted = self.formatter.format_commit_message(raw_message)
        
        # Handle retry attempts by shortening if needed
        if attempt > 1 and len(formatted) > self.config.total_message_limit:
            # Trim body lines more aggressively
            while len(formatted) > self.config.total_message_limit and len(body_lines) > 1:
                body_lines.pop()
                raw_message = subject + "\n\n" + "\n".join(body_lines) if body_lines else subject
                formatted = self.formatter.format_commit_message(raw_message)
        
        logger.debug("Generated mock summary (%d chars)", len(formatted))
        return formatted
    
    async def suggest_branch_name(self, summaries: List[str]) -> str:
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
    
    def _generate_meaningful_subject(self, cats, commit_subjects, diff_content, date) -> str:
        """Generate a meaningful subject line based on actual changes."""
        # Analyze commit subjects first for context
        all_subjects = ' '.join(commit_subjects).lower()
        
        # Look for key changes in diff content
        if diff_content and len(diff_content.strip()) > 0:
            diff_lower = diff_content.lower()
            lines = diff_content.split('\n')
            
            # Count new files
            new_files = [line for line in lines if line.startswith('+++') and '/dev/null' not in line]
            rust_files = [line for line in new_files if '.rs' in line]
            
            # Detect major functionality from subjects and diff
            if 'metrics' in all_subjects or 'metrics' in diff_lower:
                if 'dashboard' in all_subjects or 'dashboard' in diff_lower:
                    return "Implement metrics dashboard and visualization"
                elif 'collector' in all_subjects or 'collector' in diff_lower:
                    return "Add metrics collection and monitoring"
                else:
                    return "Implement metrics collection system"
            
            elif 'buffer' in all_subjects or 'buffer' in diff_lower:
                return "Implement buffer management system"
            
            elif 'cache' in all_subjects or 'cache' in diff_lower:
                return "Add cache layer and optimization"
            
            elif any(word in all_subjects for word in ['fix', 'bug', 'issue']):
                if len(rust_files) > 5:
                    return "Fix critical issues and improve stability"
                else:
                    return "Fix bugs and resolve issues"
            
            elif 'test' in all_subjects and len(new_files) > 3:
                return "Add comprehensive test coverage"
            
            elif any(word in all_subjects for word in ['performance', 'optimize']):
                return "Optimize performance and efficiency"
            
            elif 'dashboard' in all_subjects or 'dashboard' in diff_lower:
                return "Add web dashboard functionality"
            
            elif len(rust_files) > 10:
                return "Implement core functionality and features"
            
            elif len(new_files) > 0:
                return "Add new implementation modules"
        
        # Fallback analysis based on commit subjects only
        if 'metrics' in all_subjects:
            return "Update metrics implementation"
        elif 'dashboard' in all_subjects:
            return "Improve dashboard functionality"
        elif 'fix' in all_subjects:
            return "Fix bugs and resolve issues"
        elif 'test' in all_subjects:
            return "Update test suite"
        elif 'buffer' in all_subjects:
            return "Update buffer implementation"
        else:
            # Use first meaningful word from subjects
            words = all_subjects.split()
            for word in words:
                if word not in ['add', 'update', 'fix', 'the', 'and', 'or', 'to', 'of', 'in', 'for']:
                    return f"Update {word} implementation"
            return f"Update implementation for {date}"
    
    def _generate_body_from_diff(self, cats, commit_subjects, diff_content, analysis) -> List[str]:
        """Generate body content based on actual diff analysis."""
        body_lines = []
        
        if diff_content and len(diff_content.strip()) > 0:
            # Analyze what actually changed
            diff_lower = diff_content.lower()
            lines = diff_content.split('\n')
            
            # Look for new files or major additions
            new_files = [line for line in lines if line.startswith('+++') and '/dev/null' not in line]
            modified_files = [line for line in lines if line.startswith('+++') and '/dev/null' in line]
            
            # Look for specific file types and functionality
            rust_files = [line for line in new_files if '.rs' in line]
            test_files = [line for line in new_files if 'test' in line]
            config_files = [line for line in new_files if any(ext in line for ext in ['toml', 'json', 'yaml', 'yml'])]
            
            # Analyze commit subjects for context
            subjects_text = ' '.join(commit_subjects).lower()
            
            # Generate specific descriptions based on what we find
            if rust_files:
                if 'metrics' in subjects_text or 'metrics' in diff_lower:
                    body_lines.append("- implement metrics collection and monitoring system")
                elif 'dashboard' in subjects_text or 'dashboard' in diff_lower:
                    body_lines.append("- add web-based dashboard for system visualization")
                elif 'buffer' in subjects_text or 'buffer' in diff_lower:
                    body_lines.append("- implement efficient buffer management system")
                else:
                    body_lines.append(f"- add {len(rust_files)} new implementation modules")
            
            if test_files:
                body_lines.append("- add comprehensive test coverage for new features")
            
            if config_files:
                body_lines.append("- update configuration and build system")
            
            # Look for specific functionality in the diff
            if '+' in diff_content:
                # Count significant additions
                added_lines = [line for line in lines if line.startswith('+') and not line.startswith('+++')]
                if len(added_lines) > 20:
                    if 'struct' in diff_content or 'impl' in diff_content:
                        body_lines.append("- implement core data structures and algorithms")
                    elif 'fn ' in diff_content:
                        body_lines.append("- add essential functionality and methods")
            
            # Look for bug fixes
            if any(word in subjects_text for word in ['fix', 'bug', 'issue']) and '-' in diff_content:
                body_lines.append("- fix: resolve critical bugs and stability issues")
            
            # Look for performance improvements
            if any(word in subjects_text for word in ['performance', 'optimize', 'speed']):
                body_lines.append("- optimize performance and resource usage")
        
        # Fallback to category-based generation if no diff insights
        if not body_lines:
            if cats.features:
                # Use first feature as context
                first_feature = cats.features[0].lower()
                if 'metrics' in first_feature:
                    body_lines.append("- implement metrics collection features")
                elif 'buffer' in first_feature:
                    body_lines.append("- add buffer management functionality")
                else:
                    body_lines.append("- implement new functionality")
            if cats.fixes:
                body_lines.append("- fix: address reported issues")
            if cats.tests:
                body_lines.append("- add test coverage")
            if cats.performance:
                body_lines.append("- optimize system performance")
        
        # Add notes based on analysis
        notes = self._generate_notes(analysis, commit_subjects)
        body_lines.extend(notes)
        
        return body_lines
    
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
            notes.append("- note: Implementation uses mocked upstream dependencies")
        
        # Check for critical changes
        if analysis.has_critical_changes:
            notes.append("- note: Contains critical stability fixes")
        
        # Check for incomplete features
        if analysis.has_incomplete_features:
            notes.append("- note: Contains temporary implementation pending review")
        
        # Check commit subjects for other patterns
        all_subjects = ' '.join(commit_subjects).lower()
        
        if 'todo' in all_subjects or 'fixme' in all_subjects:
            notes.append("- note: Contains TODO items requiring follow-up")
        
        if 'experimental' in all_subjects:
            notes.append("- note: Includes experimental features for testing")
        
        if 'breaking' in all_subjects:
            notes.append("- note: Contains breaking changes to public API")
        
        return notes