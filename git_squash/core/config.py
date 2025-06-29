"""Configuration management for git squash tool."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class GitSquashConfig:
    """Configuration for git squash operations."""

    # Message formatting
    subject_line_limit: int = 96
    body_line_width: int = 96
    total_message_limit: int = 1500

    # Splitting thresholds
    split_threshold_commits: int = 20
    split_threshold_hours: int = 23
    time_gap_hours: int = 2

    # Retry behavior
    max_retry_attempts: int = 3

    # Branch settings
    branch_prefix: str = "feature/"
    backup_branch_prefix: str = "backup/"

    # ai settings
    model: str = "claude-3-7-sonnet-20250219"

    def __post_init__(self):
        """Validate configuration parameters after initialization."""
        # Validate message limits
        if self.total_message_limit <= 0:
            raise ValueError(
                f"total_message_limit must be positive, got {self.total_message_limit}")
        if self.subject_line_limit <= 0:
            raise ValueError(
                f"subject_line_limit must be positive, got {self.subject_line_limit}")
        if self.body_line_width <= 0:
            raise ValueError(
                f"body_line_width must be positive, got {self.body_line_width}")

        # Validate subject line limit is reasonable
        if self.subject_line_limit > self.total_message_limit:
            raise ValueError(
                f"subject_line_limit ({self.subject_line_limit}) cannot exceed total_message_limit ({self.total_message_limit})")

        # Validate splitting thresholds
        if self.split_threshold_commits <= 0:
            raise ValueError(
                f"split_threshold_commits must be positive, got {self.split_threshold_commits}")
        if self.split_threshold_hours <= 0:
            raise ValueError(
                f"split_threshold_hours must be positive, got {self.split_threshold_hours}")
        if self.time_gap_hours < 0:
            raise ValueError(
                f"time_gap_hours cannot be negative, got {self.time_gap_hours}")

        # Validate retry attempts
        if self.max_retry_attempts <= 0:
            raise ValueError(
                f"max_retry_attempts must be positive, got {self.max_retry_attempts}")
        if self.max_retry_attempts > 10:
            raise ValueError(
                f"max_retry_attempts should not exceed 10 for reasonable performance, got {self.max_retry_attempts}")

        # Validate branch prefixes
        if not isinstance(self.branch_prefix, str):
            raise ValueError(
                f"branch_prefix must be a string, got {type(self.branch_prefix)}")
        if not isinstance(self.backup_branch_prefix, str):
            raise ValueError(
                f"backup_branch_prefix must be a string, got {type(self.backup_branch_prefix)}")

        # Validate branch prefixes don't contain invalid characters
        invalid_chars = [' ', '\n', '\t', '..',
                         '~', '^', ':', '?', '*', '[', '\\']
        for char in invalid_chars:
            if char in self.branch_prefix:
                raise ValueError(
                    f"branch_prefix contains invalid character '{char}': {self.branch_prefix}")
            if char in self.backup_branch_prefix:
                raise ValueError(
                    f"backup_branch_prefix contains invalid character '{char}': {self.backup_branch_prefix}")

        # Validate ai options
        if not isinstance(self.model, str):
            raise ValueError(f"model must be a string, got {type(self.model)}")

    @classmethod
    def from_cli_args(cls, args) -> 'GitSquashConfig':
        """Create config from command line arguments."""
        try:
            return cls(
                total_message_limit=getattr(
                    args, 'message_limit', cls.total_message_limit),
                model=getattr(args, 'model', cls.branch_prefix),
                branch_prefix=getattr(args, 'branch_prefix', cls.branch_prefix)
            )
        except ValueError as e:
            raise ValueError(
                f"Invalid configuration from command line arguments: {e}") from e

    def with_overrides(self, **kwargs) -> 'GitSquashConfig':
        """Create a new config with specific overrides."""
        # Create a copy with modifications
        fields = {field.name: getattr(self, field.name)
                  for field in self.__dataclass_fields__.values()}
        fields.update(kwargs)
        return GitSquashConfig(**fields)
