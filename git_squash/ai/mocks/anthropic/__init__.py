"""
Mock package for the Anthropic SDK, designed for testing and development.

This package provides mock implementations of the primary types, errors,
and classes from the Anthropic SDK, allowing for isolated unit testing
without needing to interact with the actual API.
"""

import types as python_types
import sys
from typing import Dict, Any, Optional, List, AsyncIterator
from dataclasses import dataclass, field
import asyncio

# Import submodules
from . import exceptions
from . import types as anthropic_types

# Re-export main exceptions
from .exceptions import (
    APIError,
    APIConnectionError,
    APIStatusError,
    RateLimitError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    InternalServerError
)

# Re-export types
from .types import Message, TextBlock, ContentBlock, Usage, BetaMessage, BetaTextBlock


class AsyncAnthropic:
    """Mock AsyncAnthropic client for testing."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: int = 2,
        default_headers: Optional[Dict[str, str]] = None,
        default_query: Optional[Dict[str, Any]] = None,
        http_client: Optional[Any] = None,
    ):
        """Initialize mock Anthropic client."""
        self.api_key = api_key
        self.base_url = base_url or "https://api.anthropic.com"
        self.timeout = timeout or 30.0
        self.max_retries = max_retries
        self.default_headers = default_headers or {}
        self.default_query = default_query or {}
        self.http_client = http_client
        
        # Add messages attribute
        self.messages = MockMessages()
    
    async def close(self):
        """Mock close method."""
        pass
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


class MockMessages:
    """Mock messages endpoint."""
    
    async def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        max_tokens: int,
        metadata: Optional[Dict[str, Any]] = None,
        stop_sequences: Optional[List[str]] = None,
        stream: bool = False,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        top_k: Optional[int] = None,
        top_p: Optional[float] = None,
        **kwargs
    ) -> Message:
        """Mock message creation."""
        # Simulate some API delay
        await asyncio.sleep(0.1)
        
        # Create mock response
        content = [
            TextBlock(
                text="This is a mock response from the Anthropic API.",
                type="text"
            )
        ]
        
        return Message(
            id="msg_mock_12345",
            type="message",
            role="assistant",
            content=content,
            model=model,
            stop_reason="end_turn",
            stop_sequence=None,
            usage=Usage(
                input_tokens=100,
                output_tokens=50,
                total_tokens=150
            )
        )


# Create a more complete Anthropic class for backwards compatibility
Anthropic = AsyncAnthropic


# Mock override functionality
_anthropic_overridden = False
_original_modules = {}

def enable_anthropic_mock():
    """
    Explicitly override the real anthropic library with our mock.

    This replaces sys.modules['anthropic'] with our mock implementation,
    allowing tests to use mock behavior even when the real library is installed.

    Call disable_anthropic_mock() to restore the original library.
    """
    global _anthropic_overridden, _original_modules

    if _anthropic_overridden:
        return  # Already overridden

    # Store original modules
    anthropic_modules = [m for m in sys.modules.keys() if m.startswith('anthropic')]
    for module_name in anthropic_modules:
        _original_modules[module_name] = sys.modules.get(module_name)
    
    # Create mock types module
    types_module = python_types.ModuleType('anthropic.types', 'Mock types module')
    setattr(types_module, 'Message', Message)
    setattr(types_module, 'TextBlock', TextBlock)
    setattr(types_module, 'ContentBlock', ContentBlock)
    setattr(types_module, 'Usage', Usage)
    
    # Create beta submodule
    beta_module = python_types.ModuleType('anthropic.types.beta', 'Mock beta types module')
    setattr(beta_module, 'BetaMessage', BetaMessage)
    setattr(beta_module, 'BetaTextBlock', BetaTextBlock)
    setattr(types_module, 'beta', beta_module)
    
    # Create main anthropic module
    anthropic_module = python_types.ModuleType('anthropic', 'Mock anthropic module')
    setattr(anthropic_module, 'AsyncAnthropic', AsyncAnthropic)
    setattr(anthropic_module, 'Anthropic', Anthropic)
    setattr(anthropic_module, 'types', types_module)

    # Add exceptions
    for exc_name in ['APIError', 'APIConnectionError', 'APIStatusError', 'RateLimitError',
                     'APITimeoutError', 'AuthenticationError', 'BadRequestError',
                     'NotFoundError', 'InternalServerError']:
        setattr(anthropic_module, exc_name, globals()[exc_name])

    # Override sys.modules
    sys.modules['anthropic'] = anthropic_module
    sys.modules['anthropic.types'] = types_module
    sys.modules['anthropic.types.beta'] = beta_module
    
    _anthropic_overridden = True


def disable_anthropic_mock():
    """
    Restore the original anthropic library.

    This undoes the override from enable_anthropic_mock() and restores
    the real anthropic library in sys.modules.
    """
    global _anthropic_overridden, _original_modules

    if not _anthropic_overridden:
        return  # Not overridden

    # Remove mock modules
    mock_modules = [m for m in sys.modules.keys() if m.startswith('anthropic')]
    for module_name in mock_modules:
        if module_name in sys.modules:
            del sys.modules[module_name]

    # Restore original modules
    for module_name, original_module in _original_modules.items():
        if original_module is not None:
            sys.modules[module_name] = original_module

    _original_modules.clear()
    _anthropic_overridden = False


def is_anthropic_mocked() -> bool:
    """Check if anthropic is currently being mocked."""
    return _anthropic_overridden


# Create types module structure for this mock (but don't override sys.modules)
types_module = python_types.ModuleType('types', 'Mock types module')
setattr(types_module, 'Message', Message)
setattr(types_module, 'TextBlock', TextBlock)
setattr(types_module, 'ContentBlock', ContentBlock)
setattr(types_module, 'Usage', Usage)

# Create beta submodule
beta_module = python_types.ModuleType('beta', 'Mock beta types module')
setattr(beta_module, 'BetaMessage', BetaMessage)
setattr(beta_module, 'BetaTextBlock', BetaTextBlock)
setattr(types_module, 'beta', beta_module)

# Add types to this module
sys.modules[__name__].types = types_module


__all__ = [
    # Client
    "AsyncAnthropic",
    "Anthropic",
    
    # Exceptions
    "APIError",
    "APIConnectionError", 
    "APIStatusError",
    "RateLimitError",
    "APITimeoutError",
    "AuthenticationError",
    "BadRequestError",
    "NotFoundError",
    "InternalServerError",
    
    # Types
    "Message",
    "TextBlock",
    "ContentBlock",
    "Usage",
    "BetaMessage",
    "BetaTextBlock",
]