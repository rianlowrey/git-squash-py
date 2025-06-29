"""Claude AI client implementation."""
import os
import logging
from typing import List, Optional
from .interface import AIClient
from ..core.types import ChangeAnalysis, can_import
from ..core.config import GitSquashConfig

logger = logging.getLogger(__name__)

HAS_CLAUDE_SDK = True

if not can_import('claude_code_sdk'):
    import mocks.claude_code_sdk
    HAS_CLAUDE_SDK = False

# needs to be forced after dependency check
# fmt: off
from claude_code_sdk import query, ClaudeCodeOptions
from claude_code_sdk.types import Message, AssistantMessage, SystemMessage, TextBlock
from claude_code_sdk._errors import (
    ClaudeSDKError,
    CLIConnectionError,
    CLIJSONDecodeError,
    CLINotFoundError,
    ProcessError
)
# fmt: on


class ClaudeClient(AIClient):
    """Claude AI client for generating commit summaries."""

    def __init__(self, api_key: Optional[str] = None, config: Optional[GitSquashConfig] = None):
        if not HAS_CLAUDE_SDK:
            raise ImportError(
                "claude-code-sdk package is required. Install with: pip install claude-code-sdk")

        self.api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable must be set")

        self.config = config or GitSquashConfig()

    async def generate_summary(self,
                               date: str,
                               analysis: ChangeAnalysis,
                               commit_subjects: List[str],
                               diff_content: Optional[str] = None,
                               attempt: int = 1,
                               previous_summary: Optional[str] = None) -> str:
        """Generate commit summary using Claude."""
        logger.debug("Generating summary for %s (attempt %d)", date, attempt)

        # Build context about the changes
        context = self._build_context(analysis, commit_subjects, diff_content)

        # Adjust prompt based on attempt
        if attempt == 1:
            length_guidance = f"Keep total message under {self.config.total_message_limit} characters."
        else:
            prev_length = len(previous_summary) if previous_summary else 0
            length_guidance = f"Previous summary was {prev_length} chars. Create more concise version under {self.config.total_message_limit} chars."

        prompt = f"""Analyze these git changes and create a focused commit message for {date}.

{context}

Based on the actual code changes shown above, create a commit message following the 50/72 rule:
1. Subject line (max {self.config.subject_line_limit} chars):
   - Use imperative mood (e.g., "Add feature" not "Added feature")
   - Capitalize first letter only
   - No period at the end
   - Summarize the most important change

2. Blank line separating subject from body

3. Body text wrapped at {self.config.body_line_width} characters:
   - Focus on WHAT changed and WHY based on the actual diff content
   - Use bullet points to describe the key changes:
     - new functionality: describe what was added
     - bug fixes: describe what was fixed
     - improvements: describe what was enhanced
     - refactoring: describe structural changes
   - Add NOTE entries if needed for:
     - Incomplete implementations
     - Areas needing review
     - Breaking changes

Guidelines:
- Analyze the actual code changes from the diff to understand what was done
- Focus on the problem being solved and its impact
- Be specific about what changed based on the diff content
- Each body line must wrap at {self.config.body_line_width} chars
- {length_guidance}

Format your response exactly as:
<commit-message>
Your subject line here

Your body content here with proper wrapping
</commit-message>

Example:
<commit-message>
Implement metrics collection and dashboard system
w
- add MetricsCollector with configurable backends for
  tracking system performance and usage statistics
- implement web dashboard with real-time visualization
  of collected metrics using charts and graphs
- add comprehensive test suite covering collector
  functionality and dashboard rendering
- fix: resolve memory allocation issues in previous
  monitoring implementation
- NOTE: dashboard requires enabling metrics collection
</commit-message>"""

        try:
            messages: List[Message] = []
            async for message in query(
                    prompt=prompt,
                    options=ClaudeCodeOptions(
                        max_turns=1,
                        model=self.config.model,
                        system_prompt="You are an AI assistant that generates focused, high-quality git commit messages following the 50/72 rule.")
            ):
                messages.append(message)

            if messages:
                # Process messages looking for actual response
                for msg in messages:
                    raw_message = None

                    # Debug log message type and content
                    logger.debug("Message type: %s", type(msg).__name__)

                    if isinstance(msg, AssistantMessage) and msg.content:
                        # Extract text from content blocks
                        text_parts = []
                        for block in msg.content:
                            logger.debug("Content block type: %s",
                                         type(block).__name__)
                            if isinstance(block, TextBlock) and hasattr(block, 'text'):
                                text_parts.append(block.text)
                                logger.debug(
                                    "Block text: %s", block.text[:100] if block.text else "None")
                        response_text = ' '.join(text_parts).strip()
                        logger.debug(
                            "Full response text: %s", response_text[:200] if response_text else "Empty")

                        # Look for structured response
                        import re
                        match = re.search(
                            r'<commit-message>\s*(.*?)\s*</commit-message>', response_text, re.DOTALL)
                        if match:
                            raw_message = match.group(1).strip()
                            logger.debug(
                                "Generated summary (%d chars)", len(raw_message))
                            return raw_message
                        else:
                            logger.debug(
                                "No <commit-message> tags found in response")
                    elif isinstance(msg, SystemMessage) and msg.data:
                        # Skip system messages with metadata - these are not responses
                        if isinstance(msg.data, dict) and 'type' in msg.data:
                            logger.debug("Skipping system metadata message")
                            continue

                # No valid response found
                logger.warning("No valid commit message in Claude response")
                return self._create_fallback_summary(date, analysis)
            else:
                logger.warning("No response from Claude")
                return self._create_fallback_summary(date, analysis)

        except CLINotFoundError as e:
            logger.error("Claude Code CLI not found: %s", e)
            return self._create_fallback_summary(date, analysis)
        except CLIConnectionError as e:
            logger.error("Cannot connect to Claude Code: %s", e)
            return self._create_fallback_summary(date, analysis)
        except CLIJSONDecodeError as e:
            logger.debug("Claude SDK JSON decode error (expected): %s", e)
            return self._create_fallback_summary(date, analysis)
        except ProcessError as e:
            logger.error("Claude Code process error: %s", e)
            return self._create_fallback_summary(date, analysis)
        except ClaudeSDKError as e:
            logger.error("Claude SDK error: %s", e)
            return self._create_fallback_summary(date, analysis)
        except Exception as e:
            logger.error("Unexpected error during summary generation: %s", e)
            return self._create_fallback_summary(date, analysis)

    async def suggest_branch_name(self, summaries: List[str]) -> str:
        """Suggest branch name using Claude."""
        logger.debug("Generating branch name from %d summaries",
                     len(summaries))

        # Extract key information from summaries
        sample_summaries = []
        for summary in summaries[:3]:
            # Get subject line and key bullet points
            lines = summary.split('\n')
            subject = lines[0].strip()
            sample_summaries.append(subject)

            # Add key feature/fix lines for context
            for line in lines[1:5]:  # First few body lines
                if line.strip().startswith('- ') and ('feature:' in line or 'fix:' in line or 'add' in line.lower()):
                    sample_summaries.append(line.strip())

        context = '\n'.join(sample_summaries)

        prompt = f"""Based on these git commit details, suggest a concise branch name (2-3 words max):

{context}

Guidelines:
- Focus on the main feature/fix being implemented
- Use kebab-case (e.g., "cache-layer", "user-auth", "api-fixes")
- Be descriptive but brief
- Common patterns: feature-name, fix-type, component-update

Format your response exactly as: <branch-name>your-suggestion-here</branch-name>

Example: <branch-name>cache-layer</branch-name>"""

        try:
            messages: List[Message] = []

            # Collect all messages from the async generator
            try:
                async for message in query(
                    prompt=prompt,
                    options=ClaudeCodeOptions(
                        max_turns=1,
                        model=self.config.model,
                        system_prompt="You are an AI assistant that suggests concise git branch names."
                    )
                ):
                    messages.append(message)
            except Exception as e:
                # Handle any errors from the query
                logger.debug("Query error: %s", str(e))
                # Continue processing any collected messages

            if messages:
                # Process messages looking for actual response
                for msg in messages:
                    suffix = None

                    if isinstance(msg, AssistantMessage) and msg.content:
                        # Extract text from content blocks
                        text_parts = []
                        for block in msg.content:
                            if isinstance(block, TextBlock) and hasattr(block, 'text'):
                                text_parts.append(block.text)
                        response_text = ' '.join(text_parts).strip()

                        # Look for structured response
                        import re
                        match = re.search(
                            r'<branch-name>([^<]+)</branch-name>', response_text)
                        if match:
                            suffix = match.group(1).strip().lower()
                            # Clean up the response
                            suffix = suffix.replace(' ', '-').replace('_', '-')
                            suffix = ''.join(
                                c for c in suffix if c.isalnum() or c == '-')
                            logger.debug("Generated branch suffix: %s", suffix)
                            return suffix
                    elif isinstance(msg, SystemMessage) and msg.data:
                        # Skip system messages with metadata - these are not responses
                        if isinstance(msg.data, dict) and 'type' in msg.data:
                            logger.debug("Skipping system metadata message")
                            continue

                # No valid response found
                logger.warning("No valid branch name suggestion in messages")
                return "updates"
            else:
                logger.warning("No response from Claude")
                return "updates"
        except CLINotFoundError as e:
            logger.error("Claude Code CLI not found for branch name: %s", e)
            return "updates"
        except CLIConnectionError as e:
            logger.error(
                "Cannot connect to Claude Code for branch name: %s", e)
            return "updates"
        except CLIJSONDecodeError as e:
            logger.debug(
                "Claude SDK JSON decode error for branch name (expected): %s", e)
            return "updates"
        except ProcessError as e:
            logger.error("Claude Code process error for branch name: %s", e)
            return "updates"
        except ClaudeSDKError as e:
            logger.error("Claude SDK error for branch name: %s", e)
            return "updates"
        except Exception as e:
            logger.error(
                "Unexpected error during branch name generation: %s", e)
            return "updates"

    def _build_context(self, analysis: ChangeAnalysis, commit_subjects: List[str], diff_content: Optional[str] = None) -> str:
        """Build context string for the prompt."""
        lines = [
            f"Commits being summarized: {len(commit_subjects)}",
            "",
            "Original commit messages:"
        ]

        # Add commit subjects (limit to prevent huge context)
        for subject in commit_subjects[:10]:
            lines.append(f"- {subject}")

        if len(commit_subjects) > 10:
            lines.append(f"... and {len(commit_subjects) - 10} more")

        lines.append("")

        # Add file stats if available
        if analysis.diff_stats:
            lines.extend(["File changes:", analysis.diff_stats, ""])

        # Add the actual diff content (truncated for context window)
        if diff_content:
            lines.append("Code changes (diff):")
            lines.append("---")
            # Limit diff size to prevent context overflow
            if len(diff_content) > 8000:
                lines.append(diff_content[:8000] +
                             "\n... (diff truncated for length)")
            else:
                lines.append(diff_content)
            lines.append("---")
            lines.append("")

        # Add analysis insights
        cats = analysis.categories
        if cats.features:
            lines.append(f"Detected {len(cats.features)} feature additions")
        if cats.fixes:
            lines.append(f"Detected {len(cats.fixes)} bug fixes")
        if cats.performance:
            lines.append(
                f"Detected {len(cats.performance)} performance improvements")
        if cats.refactoring:
            lines.append(
                f"Detected {len(cats.refactoring)} refactoring changes")
        if cats.tests:
            lines.append(f"Detected {len(cats.tests)} test changes")

        # Add special conditions
        if analysis.has_critical_changes:
            lines.append("WARNING: Contains critical/security changes")
        if analysis.has_mocked_dependencies:
            lines.append("WARNING: Uses mocked dependencies")
        if analysis.has_incomplete_features:
            lines.append("WARNING: Contains incomplete features")

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
