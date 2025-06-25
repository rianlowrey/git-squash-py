"""Configuration management for git squash tool."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class GitSquashConfig:
    """Configuration for git squash operations."""
    
    # Message formatting
    subject_line_limit: int = 50
    body_line_width: int = 72 
    total_message_limit: int = 800
    
    # Splitting thresholds
    split_threshold_commits: int = 20
    split_threshold_hours: int = 8
    time_gap_hours: int = 2
    
    # Retry behavior
    max_retry_attempts: int = 3
    
    # Branch settings
    default_branch_prefix: str = "feature/"
    backup_branch_prefix: str = "backup/"
    
    @classmethod
    def from_cli_args(cls, args) -> 'GitSquashConfig':
        """Create config from command line arguments."""
        return cls(
            total_message_limit=getattr(args, 'message_limit', cls.total_message_limit),
            default_branch_prefix=getattr(args, 'branch_prefix', cls.default_branch_prefix)
        )
    
    def with_overrides(self, **kwargs) -> 'GitSquashConfig':
        """Create a new config with specific overrides."""
        # Create a copy with modifications
        fields = {field.name: getattr(self, field.name) for field in self.__dataclass_fields__.values()}
        fields.update(kwargs)
        return GitSquashConfig(**fields)