"""Claude AI client implementation using the official anthropic library."""
import os
import logging
import re
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager
from asyncio import Semaphore
from pathlib import Path

# Local application imports
from .interface import AIClient
from ..core.types import ChangeAnalysis, CommitInfo, can_import
from ..core.config import GitSquashConfig
from ..core.cache import GitSquashCache

logger = logging.getLogger(__name__)

# Check if anthropic is available
HAS_ANTHROPIC = can_import('anthropic')

if HAS_ANTHROPIC:
    import anthropic
else:
    from .mocks import anthropic

# Import what we need from anthropic (real or mock)
from anthropic import AsyncAnthropic, APIConnectionError, APIStatusError, RateLimitError
from anthropic.types import Message, TextBlock, ContentBlock
from anthropic.types.beta import BetaMessage, BetaTextBlock


class ClaudeClient(AIClient):
    """Claude AI client for generating commit summaries using the anthropic library.

    This client provides production-ready integration with Claude AI for generating
    high-quality git commit messages. It includes:
    - Automatic retry logic with exponential backoff
    - Comprehensive error handling and fallback mechanisms
    - Structured response parsing with validation
    - Context-aware prompt engineering
    - Resource usage tracking and logging
    - File-based caching with TTL
    - Rate limiting for API requests
    """

    def __init__(self, api_key: Optional[str] = None, config: Optional[GitSquashConfig] = None,
                 cache_dir: Optional[Path] = None, max_concurrent_requests: int = 3):
        """Initialize the Claude client.

        Args:
            api_key: Anthropic API key. If not provided, reads from ANTHROPIC_API_KEY env var.
            config: GitSquashConfig instance. If not provided, uses default configuration.
            cache_dir: Directory for caching. If not provided, uses default cache location.
            max_concurrent_requests: Maximum number of concurrent API requests.

        Raises:
            ImportError: If anthropic package is not installed.
            ValueError: If no API key is provided or found in environment.
        """
        if not HAS_ANTHROPIC:
            raise ImportError(
                "The 'anthropic' package is required. Please install it with: pip install anthropic"
            )

        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY must be set in your environment or provided as parameter.")

        self.config = config or GitSquashConfig()

        # Initialize the async client with proper configuration
        self.client = AsyncAnthropic(
            api_key=self.api_key,
            max_retries=3,  # Built-in retry logic
            timeout=30.0,   # 30 second timeout per request
        )

        # Initialize cache
        self.cache = GitSquashCache(cache_dir=cache_dir)

        # Rate limiting
        self._semaphore = Semaphore(max_concurrent_requests)

        # Track usage for monitoring
        self._total_tokens_used = 0
        self._request_count = 0
        self._cache_hits = 0
        self._cache_misses = 0

    async def generate_summary(
        self,
        date: str,
        analysis: ChangeAnalysis,
        commit_subjects: List[str],
        diff_content: Optional[str] = None,
        attempt: int = 1,
        previous_summary: Optional[str] = None,
        commits: Optional[List[CommitInfo]] = None,
    ) -> str:
        """Generate commit summary using the Claude Messages API with caching.

        Args:
            date: Date string for the commits being summarized
            analysis: Analysis of the changes
            commit_subjects: List of original commit subjects
            diff_content: The actual diff content (optional but recommended)
            attempt: Current attempt number (for retry logic)
            previous_summary: Previous summary if this is a retry
            commits: List of CommitInfo objects for cache key generation

        Returns:
            Formatted commit message following Git best practices
        """
        logger.debug("Generating summary for %s (attempt %d)", date, attempt)

        # Check cache first (only on first attempt)
        if attempt == 1 and commits and diff_content:
            cached_summary = self.cache.get_summary(
                date, commits, diff_content, self.config)
            if cached_summary:
                logger.info("Using cached summary for %s", date)
                self._cache_hits += 1
                return cached_summary
            self._cache_misses += 1

        context = self._build_context(analysis, commit_subjects, diff_content)
        system_prompt = self._get_system_prompt()
        user_prompt = self._build_user_prompt(
            date, context, attempt, previous_summary)

        try:
            # Use the official anthropic client's messages.create method
            response = await self._create_message_with_retry(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=1024,  # Sufficient for commit messages
                temperature=0.3,  # Lower temperature for more consistent output
            )

            # Extract and validate the response
            response_text = self._extract_response_text(response)

            if response_text:
                # Parse structured response
                raw_message = self._parse_commit_message(response_text)
                if raw_message:
                    logger.debug("Generated summary (%d chars)",
                                 len(raw_message))

                    # Cache the successful summary
                    if attempt == 1 and commits and diff_content:
                        self.cache.set_summary(
                            date, commits, diff_content, self.config, raw_message)

                    return raw_message
                else:
                    logger.warning("No valid commit message found in response")
                    return self._create_fallback_summary(date, analysis)
            else:
                logger.warning("Empty response from Claude")
                return self._create_fallback_summary(date, analysis)

        except APIConnectionError as e:
            logger.error("Network error connecting to Anthropic API: %s", e)
            return self._create_fallback_summary(date, analysis)
        except RateLimitError as e:
            logger.error("Rate limit exceeded: %s", e)
            return self._create_fallback_summary(date, analysis)
        except APIStatusError as e:
            logger.error("Anthropic API error (status %s): %s",
                         e.status_code, e.message)
            return self._create_fallback_summary(date, analysis)
        except Exception as e:
            logger.error(
                "Unexpected error during summary generation: %s", e, exc_info=True)
            return self._create_fallback_summary(date, analysis)

    async def suggest_branch_name(self, summaries: List[str]) -> str:
        """Suggest branch name using the anthropic library.

        Args:
            summaries: List of commit summaries to analyze

        Returns:
            Suggested branch name suffix (e.g., "cache-improvements")
        """
        logger.debug("Generating branch name from %d summaries",
                     len(summaries))

        context = self._build_branch_name_context(summaries)
        system_prompt = "You are an AI assistant that suggests concise, descriptive git branch names."
        user_prompt = self._build_branch_name_prompt(context)

        try:
            response = await self._create_message_with_retry(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=50,  # Branch names should be very short
                temperature=0.5,  # Slightly higher for creativity
            )

            response_text = self._extract_response_text(response)
            if response_text:
                branch_suffix = self._parse_branch_name(response_text)
                if branch_suffix:
                    logger.debug("Generated branch suffix: %s", branch_suffix)
                    return branch_suffix

            logger.warning("No valid branch name in response")
            return "updates"

        except Exception as e:
            logger.error("Error during branch name generation: %s", e)
            return "updates"

    async def _create_message_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float = 0.3,
    ) -> Message:
        """Create a message with built-in retry logic and rate limiting.

        Args:
            system_prompt: System prompt for Claude
            user_prompt: User prompt
            max_tokens: Maximum tokens in response
            temperature: Temperature for response generation

        Returns:
            Message response from Claude
        """
        async with self._semaphore:  # Rate limiting
            try:
                response = await self.client.messages.create(
                    model=self.config.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[
                        {
                            "role": "user",
                            "content": user_prompt
                        }
                    ],
                )

                # Track usage
                self._request_count += 1
                if hasattr(response, 'usage'):
                    self._total_tokens_used += getattr(
                        response.usage, 'total_tokens', 0)
                    logger.debug("Tokens used: %s", response.usage)

                return response

            except Exception as e:
                logger.error("Failed to create message: %s", e)
                raise

    def _extract_response_text(self, response: Message) -> Optional[str]:
        """Extract text content from Claude's response.

        Args:
            response: Message response from Claude

        Returns:
            Extracted text or None if no valid content
        """
        if not response.content:
            return None

        # Combine all text blocks in the response
        text_parts = []
        for block in response.content:
            if isinstance(block, TextBlock) and hasattr(block, 'text'):
                text_parts.append(block.text)
            elif isinstance(block, dict) and block.get('type') == 'text':
                # Handle dict representation
                text_parts.append(block.get('text', ''))

        return ' '.join(text_parts).strip() if text_parts else None

    def _parse_commit_message(self, response_text: str) -> Optional[str]:
        """Parse commit message from structured response.

        Args:
            response_text: Raw response text from Claude

        Returns:
            Parsed commit message or None if not found
        """
        # Look for commit message in XML-like tags
        match = re.search(
            r'<commit-message>\s*(.*?)\s*</commit-message>',
            response_text,
            re.DOTALL | re.IGNORECASE
        )

        if match:
            return match.group(1).strip()

        # Fallback: if response looks like a commit message without tags
        lines = response_text.strip().split('\n')
        if lines and len(lines[0]) <= self.config.subject_line_limit:
            # Might be a raw commit message
            logger.debug("Using raw response as commit message")
            return response_text.strip()

        return None

    def _parse_branch_name(self, response_text: str) -> Optional[str]:
        """Parse branch name from structured response.

        Args:
            response_text: Raw response text from Claude

        Returns:
            Cleaned branch name or None if not found
        """
        # Look for branch name in XML-like tags
        match = re.search(
            r'<branch-name>([^<]+)</branch-name>',
            response_text,
            re.IGNORECASE
        )

        if match:
            suffix = match.group(1).strip().lower()
            # Clean up the branch name
            # Replace spaces/underscores
            suffix = re.sub(r'[\s_]+', '-', suffix)
            # Remove invalid characters
            suffix = re.sub(r'[^a-z0-9-]', '', suffix)
            suffix = re.sub(r'-+', '-', suffix)  # Collapse multiple hyphens
            suffix = suffix.strip('-')  # Remove leading/trailing hyphens

            if suffix and len(suffix) <= 50:  # Reasonable length limit
                return suffix

        # Fallback: extract key words from response
        words = re.findall(r'\b[a-z]+\b', response_text.lower())
        for word in words:
            if word in ['feature', 'fix', 'update', 'refactor', 'optimize']:
                return word

        return None

    def _get_system_prompt(self) -> str:
        """Get the system prompt for Claude."""
        return (
            "You are an AI assistant that generates focused, high-quality git commit messages "
            "following the 50/72 rule and Git best practices. Your commit messages should be "
            "clear, concise, and describe both what changed and why it matters."
        )

    def _build_user_prompt(
        self,
        date: str,
        context: str,
        attempt: int,
        previous_summary: Optional[str]
    ) -> str:
        """Build the user prompt for commit message generation."""
        if attempt == 1:
            length_guidance = f"Keep total message under {self.config.total_message_limit} characters."
        else:
            prev_length = len(previous_summary) if previous_summary else 0
            length_guidance = (
                f"Previous summary was {prev_length} chars. "
                f"Create a more concise version under {self.config.total_message_limit} chars."
            )

        return f"""Analyze these git changes and create a focused commit message for {date}.

{context}

Based on the actual code changes shown above, create a commit message following the 50/72 rule:

1. Subject line (max {self.config.subject_line_limit} chars):
   - Use imperative mood (e.g., "Adds feature" not "Added feature")
   - Capitalize first letter only
   - No period at the end
   - Summarize the most important changes

2. Blank line separating subject from body

3. Body text wrapped at {self.config.body_line_width} characters:
   - Focus on WHAT changed and WHY based on the actual diff content
   - Use the minus/dash "-" character to list and describe key changes
   - Add "note:" entries if needed for incomplete implementations or breaking changes

Guidelines:
- Analyze the actual code changes from the diff to understand what was done
- Be specific about what changed based on the diff content
- Order the list of changes by significance
- {length_guidance}

Format your response exactly as:
<commit-message>
Your subject line here

Your body content here with proper wrapping
</commit-message>"""

    def _build_branch_name_prompt(self, context: str) -> str:
        """Build the prompt for branch name suggestion."""
        return f"""Based on these git commit details, suggest a concise branch name (2-3 words max):

{context}

Guidelines:
- Focus on the main feature/fix being implemented
- Use kebab-case (e.g., "cache-layer", "user-auth", "api-fixes")
- Be descriptive but brief
- Common patterns: feature-name, fix-type, component-update

Format your response exactly as: <branch-name>your-suggestion-here</branch-name>

Example: <branch-name>cache-layer</branch-name>"""

    def _build_context(
        self,
        analysis: ChangeAnalysis,
        commit_subjects: List[str],
        diff_content: Optional[str] = None
    ) -> str:
        """Build context string for the prompt."""
        lines = [
            f"Commits being summarized: {len(commit_subjects)}",
            "",
            "Original commit messages:"
        ]

        # Add commit subjects (limit to prevent huge context)
        for i, subject in enumerate(commit_subjects[:15]):
            lines.append(f"- {subject}")

        if len(commit_subjects) > 15:
            lines.append(f"... and {len(commit_subjects) - 15} more")

        lines.append("")

        # Add file stats if available
        if analysis.diff_stats:
            lines.extend(["File changes:", analysis.diff_stats, ""])

        # Add the actual diff content (truncated for context window)
        if diff_content:
            lines.append("Code changes (diff):")
            lines.append("---")
            # Limit diff size to prevent context overflow
            max_diff_size = 10000  # Increased from 8000 for better context
            if len(diff_content) > max_diff_size:
                # Try to include complete file sections
                truncated_diff = self._smart_truncate_diff(
                    diff_content, max_diff_size)
                lines.append(truncated_diff)
            else:
                lines.append(diff_content)
            lines.append("---")
            lines.append("")

        # Add analysis insights
        cats = analysis.categories
        insights = []

        if cats.features:
            insights.append(f"{len(cats.features)} feature additions")
        if cats.fixes:
            insights.append(f"{len(cats.fixes)} bug fixes")
        if cats.performance:
            insights.append(
                f"{len(cats.performance)} performance improvements")
        if cats.refactoring:
            insights.append(f"{len(cats.refactoring)} refactoring changes")
        if cats.tests:
            insights.append(f"{len(cats.tests)} test changes")

        if insights:
            lines.append("Change summary: " + ", ".join(insights))

        # Add special conditions as warnings
        warnings = []
        if analysis.has_critical_changes:
            warnings.append("Contains critical/security changes")
        if analysis.has_mocked_dependencies:
            warnings.append("Uses mocked dependencies")
        if analysis.has_incomplete_features:
            warnings.append("Contains incomplete features")

        if warnings:
            lines.append("")
            for warning in warnings:
                lines.append(f"WARNING: {warning}")

        return '\n'.join(lines)

    def _smart_truncate_diff(self, diff_content: str, max_size: int) -> str:
        """Intelligently truncate diff content to preserve complete file changes."""
        if len(diff_content) <= max_size:
            return diff_content

        lines = diff_content.split('\n')
        result = []
        current_size = 0
        in_file = False

        for line in lines:
            line_size = len(line) + 1  # +1 for newline

            # Always include file headers
            if line.startswith(('diff --git', '+++', '---', '@@')):
                in_file = True
                if current_size + line_size > max_size - 100:  # Leave buffer
                    result.append("... (diff truncated for length)")
                    break

            if current_size + line_size > max_size:
                if in_file:
                    result.append("... (file changes truncated)")
                result.append("... (additional files omitted)")
                break

            result.append(line)
            current_size += line_size

        return '\n'.join(result)

    def _build_branch_name_context(self, summaries: List[str]) -> str:
        """Build context for branch name suggestion from commit summaries."""
        sample_summaries = []

        for summary in summaries[:5]:  # Analyze first 5 summaries
            lines = summary.split('\n')
            if lines:
                # Get subject line
                sample_summaries.append(f"Subject: {lines[0].strip()}")

                # Extract key feature/fix lines from body
                for line in lines[1:8]:  # First few body lines
                    line = line.strip()
                    if line.startswith('- ') and any(
                        keyword in line.lower()
                        for keyword in ['feature:', 'fix:', 'add', 'implement', 'update']
                    ):
                        sample_summaries.append(f"  {line}")

        return '\n'.join(sample_summaries)

    def _create_fallback_summary(self, date: str, analysis: ChangeAnalysis) -> str:
        """Create basic summary when API fails."""
        cats = analysis.categories

        # Build subject based on most significant changes
        parts = []
        if cats.features:
            parts.append(f"{len(cats.features)} features")
        if cats.fixes:
            parts.append(f"{len(cats.fixes)} fixes")
        if cats.performance:
            parts.append("performance improvements")

        if parts:
            subject = f"Add {', '.join(parts)}"
        else:
            subject = f"Update implementation for {date}"

        # Ensure subject fits within limit
        if len(subject) > self.config.subject_line_limit:
            subject = subject[:self.config.subject_line_limit-3] + "..."

        # Build body with specific details
        body = []

        if cats.features and cats.features[0]:
            body.append(f"- feature: {cats.features[0].lower()}")
        if cats.fixes and cats.fixes[0]:
            body.append(f"- fix: {cats.fixes[0].lower()}")
        if cats.tests:
            body.append("- tests: add test coverage")
        if cats.performance:
            body.append("- performance: optimize implementation")

        # Add notes for special conditions
        if analysis.has_critical_changes:
            body.append(
                "- note: Contains critical security or stability fixes")
        if analysis.has_mocked_dependencies:
            body.append("- note: Uses mocked dependencies")
        if analysis.has_incomplete_features:
            body.append("- note: Contains incomplete features")

        return subject + "\n\n" + "\n".join(body) if body else subject

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get usage statistics for monitoring.

        Returns:
            Dictionary with usage statistics
        """
        cache_stats = self.cache.get_stats()

        return {
            "total_requests": self._request_count,
            "total_tokens": self._total_tokens_used,
            "average_tokens_per_request": (
                self._total_tokens_used / self._request_count
                if self._request_count > 0 else 0
            ),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_hit_rate": (
                self._cache_hits / (self._cache_hits + self._cache_misses)
                if (self._cache_hits + self._cache_misses) > 0 else 0
            ),
            "cache_stats": cache_stats
        }

    def clear_cache(self):
        """Clear all cached summaries and plans."""
        self.cache.clear_all()
        logger.info("Cleared all cache entries")

    def invalidate_plan_cache(self, plan):
        """Invalidate cached plans after execution.

        Args:
            plan: SquashPlan that was executed
        """
        self.cache.invalidate_plan(plan)

    def cleanup_cache(self):
        """Remove expired cache entries."""
        self.cache.clear_expired()

    async def close(self):
        """Close the client and cleanup resources."""
        # Persist any pending cache changes
        self.cache._persist_caches()

        if hasattr(self.client, 'close'):
            await self.client.close()
