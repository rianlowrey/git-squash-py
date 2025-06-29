"""
A mock package for the Claude SDK, designed for testing and development.

This package provides mock implementations of the primary types, errors,
and functions from the Claude SDK, allowing for isolated unit testing
without needing to interact with the actual CLI tool.
"""

# Import and re-export key components from the submodules
# to make them available at the top level of the package.
# e.g., `from claude_mocks import Message, ClaudeSDKError`
from ._errors import (
    ClaudeSDKError,
    CLIConnectionError,
    CLINotFoundError,
    ProcessError,
    CLIJSONDecodeError,
)
from .types import (
    Message,
    AssistantMessage,
    SystemMessage,
    UserMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    ClaudeCodeOptions,
    query,
)

# This defines what `from claude_mocks import *` will import.
__all__ = [
    # From types.py
    "Message",
    "AssistantMessage",
    "SystemMessage",
    "UserMessage",
    "ResultMessage",
    "TextBlock",
    "ToolUseBlock",
    "ToolResultBlock",
    "ClaudeCodeOptions",
    "query",
    # From _errors.py
    "ClaudeSDKError",
    "CLIConnectionError",
    "CLINotFoundError",
    "ProcessError",
    "CLIJSONDecodeError",
]

import types
import sys

types_module = types.ModuleType('claude_code_sdk.types', 'Module created to provide a context for tests')

setattr(types_module, 'TextBlock', TextBlock)
setattr(types_module, 'Message', Message)
setattr(types_module, 'AssistantMessage', AssistantMessage)
setattr(types_module, 'SystemMessage', SystemMessage)

errors_module = types.ModuleType('claude_code_sdk._errors', 'Module created to provide a context for tests')

setattr(errors_module, 'ClaudeSDKError', ClaudeSDKError)
setattr(errors_module, 'CLIConnectionError', CLIConnectionError)
setattr(errors_module, 'CLIJSONDecodeError', CLIJSONDecodeError)
setattr(errors_module, 'CLINotFoundError', CLINotFoundError)
setattr(errors_module, 'ProcessError', ProcessError)


sys.modules["claude_code_sdk.types"] = types_module
setattr(sys.modules['claude_code_sdk'], 'types', types_module)

sys.modules["claude_code_sdk._errors"] = errors_module
setattr(sys.modules['claude_code_sdk'], '_errors', errors_module)
