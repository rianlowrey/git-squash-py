"""Mock types for the Anthropic SDK."""

from dataclasses import dataclass, field
from typing import List, Optional, Union, Literal, Dict, Any
from datetime import datetime


@dataclass
class Usage:
    """Token usage information."""
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass
class TextBlock:
    """Text content block."""
    text: str
    type: Literal["text"] = "text"
    
    def __post_init__(self):
        """Ensure type is set correctly."""
        self.type = "text"


@dataclass
class ToolUseBlock:
    """Tool use content block."""
    id: str
    name: str
    input: Dict[str, Any]
    type: Literal["tool_use"] = "tool_use"
    
    def __post_init__(self):
        """Ensure type is set correctly."""
        self.type = "tool_use"


@dataclass
class ToolResultBlock:
    """Tool result content block."""
    tool_use_id: str
    content: Union[str, List[Dict[str, Any]]]
    is_error: Optional[bool] = None
    type: Literal["tool_result"] = "tool_result"
    
    def __post_init__(self):
        """Ensure type is set correctly."""
        self.type = "tool_result"


# ContentBlock is a union type
ContentBlock = Union[TextBlock, ToolUseBlock, ToolResultBlock]


@dataclass
class Message:
    """Message response from the API."""
    id: str
    type: Literal["message"]
    role: Literal["assistant"]
    content: List[ContentBlock]
    model: str
    stop_reason: Optional[Literal["end_turn", "max_tokens", "stop_sequence"]] = None
    stop_sequence: Optional[str] = None
    usage: Optional[Usage] = None
    
    def __post_init__(self):
        """Ensure types are set correctly."""
        self.type = "message"
        self.role = "assistant"
        
        # Ensure content blocks have correct types
        for i, block in enumerate(self.content):
            if isinstance(block, dict):
                # Convert dict to appropriate block type
                block_type = block.get('type', 'text')
                if block_type == 'text':
                    self.content[i] = TextBlock(**block)
                elif block_type == 'tool_use':
                    self.content[i] = ToolUseBlock(**block)
                elif block_type == 'tool_result':
                    self.content[i] = ToolResultBlock(**block)


# Beta types submodule
class beta:
    """Beta types submodule."""
    
    @dataclass
    class BetaTextBlock:
        """Beta version of TextBlock with additional features."""
        text: str
        type: Literal["text"] = "text"
        annotations: List[Dict[str, Any]] = field(default_factory=list)
        
        def __post_init__(self):
            """Ensure type is set correctly."""
            self.type = "text"
    
    @dataclass 
    class BetaMessage:
        """Beta version of Message with additional features."""
        id: str
        type: Literal["message"]
        role: Literal["assistant", "user", "system"]
        content: Union[str, List[Union['BetaTextBlock', ContentBlock]]]
        model: str
        created_at: Optional[datetime] = None
        stop_reason: Optional[str] = None
        stop_sequence: Optional[str] = None
        usage: Optional[Usage] = None
        metadata: Optional[Dict[str, Any]] = None
        
        def __post_init__(self):
            """Ensure types are set correctly."""
            self.type = "message"
            if self.created_at is None:
                self.created_at = datetime.now()
            
            # Convert string content to list of blocks
            if isinstance(self.content, str):
                self.content = [BetaTextBlock(text=self.content)]


# Make beta types available at module level for cleaner imports
BetaMessage = beta.BetaMessage
BetaTextBlock = beta.BetaTextBlock


__all__ = [
    "Usage",
    "TextBlock",
    "ToolUseBlock", 
    "ToolResultBlock",
    "ContentBlock",
    "Message",
    "beta",
    "BetaMessage",
    "BetaTextBlock",
]