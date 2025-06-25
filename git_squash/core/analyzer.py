"""Core analysis logic for commits and diffs."""

import re
import logging
from typing import List, Dict
from .types import CommitInfo, CommitCategories, ChangeAnalysis
from .config import GitSquashConfig

logger = logging.getLogger(__name__)


class DiffAnalyzer:
    """Analyzes git diffs and commits without external dependencies."""
    
    def __init__(self, config: GitSquashConfig):
        self.config = config
    
    def categorize_commits(self, commits: List[CommitInfo]) -> CommitCategories:
        """Categorize commits based on their subjects."""
        categories = CommitCategories(
            features=[], fixes=[], tests=[], docs=[], 
            dependencies=[], refactoring=[], performance=[], other=[]
        )
        
        for commit in commits:
            subject_lower = commit.subject.lower()
            
            if any(kw in subject_lower for kw in ['add', 'implement', 'create', 'new', 'feature']):
                categories.features.append(commit.subject)
            elif any(kw in subject_lower for kw in ['fix', 'bug', 'issue', 'resolve', 'patch']):
                categories.fixes.append(commit.subject)
            elif any(kw in subject_lower for kw in ['test', 'spec', 'coverage']):
                categories.tests.append(commit.subject)
            elif any(kw in subject_lower for kw in ['doc', 'readme', 'comment']):
                categories.docs.append(commit.subject)
            elif any(kw in subject_lower for kw in ['update', 'bump', 'dependency', 'dependencies']):
                categories.dependencies.append(commit.subject)
            elif any(kw in subject_lower for kw in ['refactor', 'cleanup', 'reorganize', 'restructure']):
                categories.refactoring.append(commit.subject)
            elif any(kw in subject_lower for kw in ['optimize', 'performance', 'speed', 'faster']):
                categories.performance.append(commit.subject)
            else:
                categories.other.append(commit.subject)
        
        return categories
    
    def analyze_diff_content(self, diff_text: str) -> Dict[str, int]:
        """Extract file change information from diff."""
        file_changes = {}
        
        for line in diff_text.split('\n'):
            if line.startswith('diff --git'):
                # Extract filename from git diff header
                match = re.search(r'b/(.+)$', line)
                if match:
                    filename = match.group(1)
                    file_changes[filename] = file_changes.get(filename, 0) + 1
        
        return file_changes
    
    def detect_special_conditions(self, commits: List[CommitInfo], diff_text: str) -> tuple[bool, bool, bool]:
        """Detect special conditions that need notes."""
        all_subjects = ' '.join(c.subject.lower() for c in commits)
        
        has_critical = any(kw in all_subjects for kw in [
            'critical', 'security', 'vulnerability', 'urgent', 'hotfix'
        ])
        
        has_mocked = any(kw in all_subjects for kw in [
            'mock', 'stub', 'fake', 'temporary', 'todo'
        ])
        
        has_incomplete = any(kw in all_subjects for kw in [
            'wip', 'incomplete', 'partial', 'draft', 'placeholder'
        ])
        
        return has_critical, has_mocked, has_incomplete
    
    def analyze_changes(self, commits: List[CommitInfo], diff_text: str, diff_stats: str) -> ChangeAnalysis:
        """Perform complete analysis of a set of commits and their changes."""
        logger.debug("Analyzing %d commits", len(commits))
        
        categories = self.categorize_commits(commits)
        file_changes = self.analyze_diff_content(diff_text)
        has_critical, has_mocked, has_incomplete = self.detect_special_conditions(commits, diff_text)
        
        analysis = ChangeAnalysis(
            categories=categories,
            diff_stats=diff_stats,
            has_critical_changes=has_critical,
            has_mocked_dependencies=has_mocked,
            has_incomplete_features=has_incomplete,
            file_changes=file_changes
        )
        
        logger.debug("Analysis complete: %d features, %d fixes, needs_review=%s", 
                    len(categories.features), len(categories.fixes), analysis.needs_review_notes)
        
        return analysis


class MessageFormatter:
    """Formats commit messages according to Git best practices."""
    
    def __init__(self, config: GitSquashConfig):
        self.config = config
    
    def wrap_text(self, text: str, width: int, indent: str = "") -> List[str]:
        """Wrap text to specified width, preserving bullet points."""
        lines = []
        
        for line in text.split('\n'):
            if not line.strip():
                lines.append("")
                continue
                
            # Handle bullet points specially
            if line.strip().startswith(('- ', '* ', '• ')):
                stripped = line.strip()
                bullet = stripped[:2]
                content = stripped[2:].strip()
                
                # First line with bullet
                first_line = indent + bullet + ' ' + content
                if len(first_line) <= width:
                    lines.append(first_line)
                else:
                    # Need to wrap - split content
                    words = content.split()
                    if words:
                        current = indent + bullet + ' ' + words[0]
                        for word in words[1:]:
                            if len(current + ' ' + word) <= width:
                                current += ' ' + word
                            else:
                                lines.append(current)
                                current = indent + '  ' + word  # Indent continuation
                        if current:
                            lines.append(current)
            else:
                # Regular text
                line_content = indent + line.strip()
                if len(line_content) <= width:
                    lines.append(line_content)
                else:
                    # Need to wrap
                    words = line.strip().split()
                    if words:
                        current = indent + words[0]
                        for word in words[1:]:
                            if len(current + ' ' + word) <= width:
                                current += ' ' + word
                            else:
                                lines.append(current)
                                current = indent + word
                        if current:
                            lines.append(current)
        
        return lines
    
    def format_commit_message(self, raw_message: str) -> str:
        """Format commit message to follow Git best practices."""
        lines = raw_message.split('\n')
        
        if not lines:
            return raw_message
            
        # Process subject line
        subject = lines[0].strip()
        
        # Apply subject line rules
        if subject:
            # Capitalize first letter
            subject = subject[0].upper() + subject[1:] if len(subject) > 1 else subject.upper()
            # Remove trailing period
            if subject.endswith('.'):
                subject = subject[:-1]
            # Enforce length limit
            if len(subject) > self.config.subject_line_limit:
                subject = subject[:self.config.subject_line_limit-3] + "..."
        
        # Process body
        if len(lines) < 3:
            return subject
            
        # Ensure blank line after subject
        body_lines = lines[2:] if len(lines) > 2 and not lines[1].strip() else lines[1:]
        
        # Wrap body text
        formatted_body = []
        for line in body_lines:
            if not line.strip():
                formatted_body.append("")
            else:
                wrapped = self.wrap_text(line, self.config.body_line_width)
                formatted_body.extend(wrapped)
        
        # Combine and clean up
        result = [subject, ""] + formatted_body
        
        # Remove trailing empty lines
        while result and not result[-1]:
            result.pop()
            
        return '\n'.join(result)