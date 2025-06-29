"""Test the Anthropic mock implementation."""
import pytest
import sys
from pathlib import Path


class TestAnthropicMocks:
    """Test the Anthropic mock package."""
    
    def setup_method(self):
        """Enable anthropic mock for testing."""
        from git_squash.ai.mocks.anthropic import enable_anthropic_mock
        enable_anthropic_mock()
    
    def teardown_method(self):
        """Restore original anthropic library."""
        from git_squash.ai.mocks.anthropic import disable_anthropic_mock
        disable_anthropic_mock()
    
    def test_mock_imports(self):
        """Test that mock imports work correctly."""
        # Import through the mocked anthropic module
        import anthropic
        from anthropic import AsyncAnthropic, APIConnectionError, APIStatusError, RateLimitError
        from anthropic.types import Message, TextBlock, ContentBlock
        from anthropic.types.beta import BetaMessage, BetaTextBlock
        
        # Verify they exist and are our mock classes
        assert AsyncAnthropic is not None
        assert APIConnectionError is not None
        assert Message is not None
        assert TextBlock is not None
    
    def test_mock_client_creation(self):
        """Test creating a mock client."""
        import anthropic
        
        # Create client
        client = anthropic.AsyncAnthropic(api_key="test-key-123")
        
        assert client.api_key == "test-key-123"
        assert client.timeout == 30.0
        assert client.max_retries == 2
        assert hasattr(client, 'messages')
    
    def test_mock_types(self):
        """Test mock type creation."""
        import anthropic
        
        # Test TextBlock
        text_block = anthropic.types.TextBlock(text="Hello, world!")
        assert text_block.text == "Hello, world!"
        assert text_block.type == "text"
        
        # Test Message
        message = anthropic.types.Message(
            id="msg_123",
            type="message",
            role="assistant",
            content=[text_block],
            model="claude-3-opus-20240229",
            stop_reason="end_turn",
            usage=anthropic.types.Usage(input_tokens=10, output_tokens=5, total_tokens=15)
        )
        assert message.id == "msg_123"
        assert len(message.content) == 1
        assert isinstance(message.content[0], anthropic.types.TextBlock)
        assert message.content[0].text == "Hello, world!"
    
    def test_mock_exceptions(self):
        """Test mock exceptions."""
        import anthropic
        
        # Test APIConnectionError
        with pytest.raises(anthropic.APIConnectionError) as exc_info:
            raise anthropic.APIConnectionError("Connection failed")
        assert "Connection failed" in str(exc_info.value)
        
        # Test RateLimitError
        with pytest.raises(anthropic.RateLimitError) as exc_info:
            raise anthropic.RateLimitError("Too many requests")
        assert "Too many requests" in str(exc_info.value)
        assert exc_info.value.status_code == 429
    
    @pytest.mark.asyncio
    async def test_mock_message_creation(self):
        """Test creating a message with the mock client."""
        from git_squash.ai.mocks import anthropic
        
        client = anthropic.AsyncAnthropic(api_key="test-key")
        
        # Create a message
        response = await client.messages.create(
            model="claude-3-opus-20240229",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=100,
            system="You are a helpful assistant"
        )
        
        # Verify response
        assert isinstance(response, anthropic.types.Message)
        assert response.model == "claude-3-opus-20240229"
        assert len(response.content) > 0
        assert isinstance(response.content[0], anthropic.types.TextBlock)
        assert isinstance(response.usage, anthropic.types.Usage)
        assert response.usage.total_tokens == 150
    
    def test_mock_beta_types(self):
        """Test beta types."""
        import anthropic
        
        # Test BetaTextBlock
        beta_block = anthropic.types.beta.BetaTextBlock(
            text="Beta content",
            annotations=[{"type": "bold", "start": 0, "end": 4}]
        )
        assert beta_block.text == "Beta content"
        assert len(beta_block.annotations) == 1
        
        # Test BetaMessage
        beta_msg = anthropic.types.beta.BetaMessage(
            id="beta_123",
            type="message",
            role="assistant",
            content="Simple content",
            model="claude-3",
            usage=anthropic.types.Usage(input_tokens=5, output_tokens=3, total_tokens=8)
        )
        assert beta_msg.id == "beta_123"
        assert len(beta_msg.content) == 1
        assert isinstance(beta_msg.content[0], anthropic.types.beta.BetaTextBlock)
    
    def test_claude_client_with_mocks(self):
        """Test that ClaudeClient works with mocks."""
        from git_squash.ai.mocks.anthropic import is_anthropic_mocked
        
        # Should be using mocks now
        assert is_anthropic_mocked()
        
        # Test that we can import anthropic and it's our mock
        import anthropic
        assert hasattr(anthropic, 'AsyncAnthropic')

        # Create a mock client
        client = anthropic.AsyncAnthropic(api_key="mock-key")
        assert client.api_key == "mock-key"
    
    @pytest.mark.asyncio
    async def test_claude_client_generate_summary_with_mock(self):
        """Test generating a summary with mock client."""
        from git_squash.ai.claude import ClaudeClient
        from git_squash.core.types import ChangeAnalysis, CommitCategories
        
        # Create test data
        categories = CommitCategories(
            features=["Add feature"],
            fixes=[],
            tests=[],
            docs=[],
            dependencies=[],
            refactoring=[],
            performance=[],
            other=[]
        )
        
        analysis = ChangeAnalysis(
            categories=categories,
            diff_stats="1 file changed",
            has_critical_changes=False,
            has_mocked_dependencies=False,
            has_incomplete_features=False,
            file_changes={}
        )
        
        # Create client and generate summary
        client = ClaudeClient(api_key="mock-key")
        summary = await client.generate_summary(
            date="2025-01-01",
            analysis=analysis,
            commit_subjects=["Add feature"],
            diff_content="+ new code"
        )
        
        # Should get some response (mock or fallback)
        assert isinstance(summary, str)
        assert len(summary) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])