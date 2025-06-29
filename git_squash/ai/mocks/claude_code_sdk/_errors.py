"""Custom exception types for the mock Claude SDK."""


class ClaudeSDKError(Exception):
    """Base exception for all Claude SDK errors."""
    pass


class CLIConnectionError(ClaudeSDKError):
    """Raised when unable to connect to Claude Code."""
    pass


class CLINotFoundError(CLIConnectionError):
    """Raised when Claude Code is not found or not installed."""

    def __init__(
        self, message: str = "Claude Code not found", cli_path: str | None = None
    ):
        super().__init__(message)
        self.cli_path = cli_path


class ProcessError(ClaudeSDKError):
    """Raised when the CLI process fails."""

    def __init__(
        self, message: str, exit_code: int | None = None, stderr: str | None = None
    ):
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr


class CLIJSONDecodeError(ClaudeSDKError):
    """Raised when unable to decode JSON from CLI output."""

    def __init__(self, line: str, original_error: Exception):
        super().__init__(f"Failed to decode JSON from line: {line}")
        self.line = line
        self.original_error = original_error

