"""Claude AI client implementation."""

import os
import logging
from typing import List, Optional
from .interface import AIClient
from ..core.types import ChangeAnalysis
from ..core.config import GitSquashConfig

logger = logging.getLogger(__name__)

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    anthropic = None
    HAS_ANTHROPIC = False


class ClaudeClient(AIClient):
    """Claude AI client for generating commit summaries."""
    
    def __init__(self, api_key: Optional[str] = None, config: Optional[GitSquashConfig] = None):
        if not HAS_ANTHROPIC:
            raise ImportError("anthropic package is required. Install with: pip install anthropic")
        
        self.api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable must be set")
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.config = config or GitSquashConfig()
    
    def generate_summary(self, 
                        date: str,
                        analysis: ChangeAnalysis, 
                        commit_subjects: List[str],
                        attempt: int = 1,
                        previous_summary: str = None) -> str:
        """Generate commit summary using Claude."""
        logger.debug("Generating summary for %s (attempt %d)", date, attempt)
        
        # Build context about the changes
        context = self._build_context(analysis, commit_subjects)
        
        # Adjust prompt based on attempt
        if attempt == 1:
            length_guidance = f"Keep total message under {self.config.total_message_limit} characters."
        else:
            prev_length = len(previous_summary) if previous_summary else 0
            length_guidance = f"Previous summary was {prev_length} chars. Create more concise version under {self.config.total_message_limit} chars."
        
        prompt = f"""Analyze these git changes and create a focused commit message for {date}.

{context}

Create a commit message following the 50/72 rule:
1. Subject line (max {self.config.subject_line_limit} chars):
   - Use imperative mood (e.g., "Add feature" not "Added feature")
   - Capitalize first letter only
   - No period at the end
   - Summarize the most important change

2. Blank line separating subject from body

3. Body text wrapped at {self.config.body_line_width} characters:
   - Explain WHAT changed and WHY (not how - code shows that)
   - Use bullet points for multiple changes:
     - features (use "add X to Y" or "Y: add X")
     - bug fixes (prefix with "fix:")
     - tests (only if significant)
     - IMPORTANT: NOTE entries for warnings about:
       - Incomplete implementations
       - Mocked/stubbed dependencies
       - Areas needing review
       - Breaking changes

Guidelines:
- Focus on the problem being solved and its impact
- Each body line must wrap at {self.config.body_line_width} chars
- {length_guidance}

Example format:
Add cache layer with performance optimizations

- add LRU cache with 10k entry capacity to improve
  response times for frequently accessed data
- add cache warming on startup for critical user paths
- fix: memory leak in previous buffer implementation that
  caused gradual performance degradation
- tests: add comprehensive cache behavior validation
- NOTE: cache persistence not implemented, data memory-only
- NOTE: performance gains require --use-cache flag"""

        try:
            response = self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=800,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            raw_message = response.content[0].text.strip()
            logger.debug("Generated summary (%d chars)", len(raw_message))
            return raw_message
            
        except Exception as e:
            logger.error("Claude API error: %s", e)
            # Fallback to basic summary
            return self._create_fallback_summary(date, analysis)
    
    def suggest_branch_name(self, summaries: List[str]) -> str:
        """Suggest branch name using Claude."""
        logger.debug("Generating branch name from %d summaries", len(summaries))
        
        # Get first few summaries for context
        sample_summaries = [s.split('\n')[0] for s in summaries[:3]]
        
        prompt = f"""Based on these commit summaries, suggest a short branch name (2-3 words max):

{chr(10).join(sample_summaries)}

Reply with ONLY the branch suffix (e.g., "cache-layer" or "api-fixes")"""

        try:
            response = self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=20,
                temperature=0.5,
                messages=[{"role": "user", "content": prompt}]
            )
            
            suffix = response.content[0].text.strip().lower()
            # Clean up the response
            suffix = suffix.replace(' ', '-').replace('_', '-')
            suffix = ''.join(c for c in suffix if c.isalnum() or c == '-')
            logger.debug("Generated branch suffix: %s", suffix)
            return suffix
        except Exception as e:
            logger.warning("Branch name generation failed: %s", e)
            return "updates"
    
    def _build_context(self, analysis: ChangeAnalysis, commit_subjects: List[str]) -> str:
        """Build context string for the prompt."""
        lines = [
            f"Commits being summarized: {len(commit_subjects)}",
            "",
            "Original commit messages:"
        ]
        
        # Add commit subjects (limit to prevent huge context)
        for subject in commit_subjects[:20]:
            lines.append(f"- {subject}")
        
        if len(commit_subjects) > 20:
            lines.append(f"... and {len(commit_subjects) - 20} more")
        
        lines.append("")
        
        # Add analysis insights
        cats = analysis.categories
        if cats.features:
            lines.append(f"features added: {len(cats.features)}")
        if cats.fixes:
            lines.append(f"bugs fixed: {len(cats.fixes)}")
        if cats.performance:
            lines.append(f"performance improvements: {len(cats.performance)}")
        if cats.refactoring:
            lines.append(f"refactoring changes: {len(cats.refactoring)}")
        if cats.tests:
            lines.append(f"test changes: {len(cats.tests)}")
        
        # Add special conditions
        if analysis.has_critical_changes:
            lines.append("WARNING: Contains critical/security changes")
        if analysis.has_mocked_dependencies:
            lines.append("WARNING: Uses mocked dependencies")
        if analysis.has_incomplete_features:
            lines.append("WARNING: Contains incomplete features")
        
        # Add file stats if available
        if analysis.diff_stats:
            lines.extend(["", "File changes:", analysis.diff_stats])
        
        return '\n'.join(lines)
    
    def _create_fallback_summary(self, date: str, analysis: ChangeAnalysis) -> str:
        """Create basic summary when API fails."""
        cats = analysis.categories
        
        # Build subject
        parts = []
        if cats.features:
            parts.append(f"{len(cats.features)} features")
        if cats.fixes:
            parts.append(f"{len(cats.fixes)} fixes")
        
        if parts:
            subject = f"Add {', '.join(parts)}"
        else:
            subject = f"Updates for {date}"
        
        # Ensure subject fits
        if len(subject) > self.config.subject_line_limit:
            subject = subject[:self.config.subject_line_limit-3] + "..."
        
        # Build body
        body = []
        if cats.features:
            body.append(f"- feature: {cats.features[0].lower()}")
        if cats.fixes:
            body.append(f"- fix: {cats.fixes[0].lower()}")
        
        if analysis.needs_review_notes:
            body.append("- NOTE: Contains changes requiring review")
        
        return subject + "\n\n" + "\n".join(body)