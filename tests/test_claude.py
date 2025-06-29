"""Comprehensive tests for the Claude AI client using anthropic library."""
import pytest
import os
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime

# Import the modules we're testing
from git_squash.ai.claude import ClaudeClient, HAS_ANTHROPIC
from git_squash.core.types import ChangeAnalysis, CommitCategories
from git_squash.core.config import GitSquashConfig


class TestClaudeClientInitialization:
    """Test Claude client initialization and configuration."""
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('git_squash.ai.claude.AsyncAnthropic')
    def test_init_with_env_api_key(self, mock_anthropic_class):
        """Test initialization with API key from environment."""
        if not HAS_ANTHROPIC:
            pytest.skip("anthropic library not installed")
            
        client = ClaudeClient()
        
        assert client.api_key == 'test-key'
        mock_anthropic_class.assert_called_once_with(
            api_key='test-key',
            max_retries=3,
            timeout=30.0
        )
    
    @patch('git_squash.ai.claude.AsyncAnthropic')
    def test_init_with_provided_api_key(self, mock_anthropic_class):
        """Test initialization with provided API key."""
        if not HAS_ANTHROPIC:
            pytest.skip("anthropic library not installed")
            
        client = ClaudeClient(api_key='provided-key')
        
        assert client.api_key == 'provided-key'
        mock_anthropic_class.assert_called_once_with(
            api_key='provided-key',
            max_retries=3,
            timeout=30.0
        )
    
    @patch.dict('os.environ', {}, clear=True)
    def test_init_without_api_key_raises(self):
        """Test initialization fails without API key."""
        if not HAS_ANTHROPIC:
            pytest.skip("anthropic library not installed")
            
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY must be set"):
            ClaudeClient()
    
    def test_init_without_anthropic_lib(self):
        """Test initialization fails when anthropic is not installed."""
        with patch('git_squash.ai.claude.HAS_ANTHROPIC', False):
            with pytest.raises(ImportError, match="'anthropic' package is required"):
                ClaudeClient(api_key='test')
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('git_squash.ai.claude.AsyncAnthropic')
    def test_init_with_custom_config(self, mock_anthropic_class):
        """Test initialization with custom configuration."""
        if not HAS_ANTHROPIC:
            pytest.skip("anthropic library not installed")
            
        config = GitSquashConfig(
            model="claude-3-opus-20240229",
            total_message_limit=1000
        )
        
        client = ClaudeClient(config=config)
        
        assert client.config.model == "claude-3-opus-20240229"
        assert client.config.total_message_limit == 1000


class TestClaudeClientSummaryGeneration:
    """Test commit summary generation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        if not HAS_ANTHROPIC:
            pytest.skip("anthropic library not installed")
            
        self.config = GitSquashConfig()
        
        # Create analysis fixture
        self.categories = CommitCategories(
            features=["Add cache layer", "Add error handling"],
            fixes=["Fix memory leak"],
            tests=["Add unit tests"],
            docs=[],
            dependencies=[],
            refactoring=[],
            performance=["Optimize query performance"],
            other=[]
        )
        
        self.analysis = ChangeAnalysis(
            categories=self.categories,
            diff_stats="3 files changed, 150 insertions(+), 20 deletions(-)",
            has_critical_changes=True,
            has_mocked_dependencies=False,
            has_incomplete_features=False,
            file_changes={"cache.py": 100, "main.py": 50, "test_cache.py": 20}
        )
        
        self.commit_subjects = [
            "Add cache layer",
            "Fix memory leak in cache cleanup",
            "Add error handling",
            "Add unit tests for cache",
            "Optimize query performance"
        ]
        
        self.diff_content = """diff --git a/cache.py b/cache.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/cache.py
@@ -0,0 +1,100 @@
+class Cache:
+    def __init__(self):
+        self.data = {}
+    
+    def get(self, key):
+        return self.data.get(key)
+    
+    def set(self, key, value):
+        self.data[key] = value
"""
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('git_squash.ai.claude.AsyncAnthropic')
    @pytest.mark.asyncio
    async def test_generate_summary_success(self, mock_anthropic_class):
        """Test successful summary generation."""
        # Set up mock response
        from anthropic.types import Message, TextBlock, Usage

        mock_response = Message(
            id="msg_test_123",
            type="message",
            role="assistant",
            content=[
                TextBlock(
                    text="<commit-message>\nAdd cache layer with memory optimization\n\n- implement LRU cache with configurable size limits\n- fix: memory leak in cache cleanup logic\n- add comprehensive error handling for cache operations\n- tests: add unit tests with 95% coverage\n- performance: optimize query operations by 40%\n- note: Contains critical memory leak fix\n</commit-message>",
                    type="text"
                )
            ],
            model="claude-3-5-sonnet-20241022",
            stop_reason="end_turn",
            usage=Usage(
                input_tokens=100,
                output_tokens=50,
                total_tokens=150
            )
        )
        
        # Set up mock client
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_anthropic_class.return_value = mock_client
        
        # Create client and generate summary
        client = ClaudeClient()
        summary = await client.generate_summary(
            date="2025-01-15",
            analysis=self.analysis,
            commit_subjects=self.commit_subjects,
            diff_content=self.diff_content
        )
        
        # Verify the summary
        assert "Add cache layer with memory optimization" in summary
        assert "implement LRU cache" in summary
        assert "note: Contains critical memory leak fix" in summary
        
        # Verify API call
        mock_client.messages.create.assert_called_once()
        call_args = mock_client.messages.create.call_args
        assert call_args.kwargs['model'] == self.config.model
        assert call_args.kwargs['max_tokens'] == 1024
        assert call_args.kwargs['temperature'] == 0.3
        
        # Verify usage tracking
        assert client._request_count == 1
        assert client._total_tokens_used == 150
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('git_squash.ai.claude.AsyncAnthropic')
    @pytest.mark.asyncio
    async def test_generate_summary_retry_on_length(self, mock_anthropic_class):
        """Test retry logic when summary is too long."""
        # Set up mock response with proper anthropic types
        from anthropic.types import Message, TextBlock, Usage

        # Mock response for retry attempt with guidance to be more concise
        mock_response = Message(
            id="msg_test_123",
            type="message",
            role="assistant",
            content=[
                TextBlock(
                    text="<commit-message>Add cache layer\n\n- implement basic cache functionality</commit-message>",
                    type="text"
                )
            ],
            model="claude-3-5-sonnet-20241022",
            stop_reason="end_turn",
            usage=Usage(
                input_tokens=120,
                output_tokens=30,
                total_tokens=150
            )
        )

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_anthropic_class.return_value = mock_client
        
        # Create client with small message limit
        config = GitSquashConfig(total_message_limit=100)
        client = ClaudeClient(config=config)
        
        # Generate summary with attempt 2 (simulating retry)
        long_previous_summary = "x" * 2000
        summary = await client.generate_summary(
            date="2025-01-15",
            analysis=self.analysis,
            commit_subjects=self.commit_subjects,
            diff_content=self.diff_content,
            attempt=2,
            previous_summary=long_previous_summary
        )
        
        # Verify the summary was generated and contains expected content
        assert "Add cache layer" in summary
        assert "implement basic cache functionality" in summary

        # Verify the prompt includes length guidance for retry
        mock_client.messages.create.assert_called_once()
        call_args = mock_client.messages.create.call_args
        user_prompt = call_args.kwargs['messages'][0]['content']
        assert "Previous summary was 2000 chars" in user_prompt
        assert f"more concise version under {config.total_message_limit} chars" in user_prompt
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('git_squash.ai.claude.AsyncAnthropic')
    @pytest.mark.asyncio
    async def test_generate_summary_fallback_on_error(self, mock_anthropic_class):
        """Test fallback summary generation on API error."""
        # Import anthropic exceptions
        if HAS_ANTHROPIC:
            import anthropic
            
            # Set up mock client that raises an error
            mock_request = AsyncMock()
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=anthropic.APIConnectionError(message="Connenction failed", request=mock_request)
            )
            mock_anthropic_class.return_value = mock_client
            
            client = ClaudeClient()
            summary = await client.generate_summary(
                date="2025-01-15",
                analysis=self.analysis,
                commit_subjects=self.commit_subjects,
                diff_content=self.diff_content
            )
            
            # Should return fallback summary
            assert "Add 2 features, 1 fixes" in summary
            assert "- feature: add cache layer" in summary
            assert "- fix: fix memory leak" in summary
            assert "- note: Contains critical" in summary
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('git_squash.ai.claude.AsyncAnthropic')
    @pytest.mark.asyncio
    async def test_generate_summary_no_structured_response(self, mock_anthropic_class):
        """Test handling of non-structured response."""
        # Set up mock response with proper anthropic types
        from anthropic.types import Message, TextBlock, Usage

        mock_response = Message(
            id="msg_test_123",
            type="message",
            role="assistant",
            content=[
                TextBlock(
                    text="Add cache layer with improvements\n\nThis adds a new caching system.",
                    type="text"
                )
            ],
            model="claude-3-5-sonnet-20241022",
            stop_reason="end_turn",
            usage=Usage(
                input_tokens=80,
                output_tokens=30,
                total_tokens=110
            )
        )
        
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_anthropic_class.return_value = mock_client
        
        client = ClaudeClient()
        summary = await client.generate_summary(
            date="2025-01-15",
            analysis=self.analysis,
            commit_subjects=self.commit_subjects
        )
        
        # Should use the raw response if it looks like a commit message
        assert "Add cache layer with improvements" in summary


class TestClaudeClientBranchNameGeneration:
    """Test branch name generation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        if not HAS_ANTHROPIC:
            pytest.skip("anthropic library not installed")
            
        self.summaries = [
            "Add cache layer with memory optimization\n\n- implement LRU cache\n- fix memory leaks",
            "Optimize database queries\n\n- add query caching\n- improve index usage",
            "Fix critical performance issues\n\n- resolve N+1 queries\n- optimize cache hits"
        ]
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('git_squash.ai.claude.AsyncAnthropic')
    @pytest.mark.asyncio
    async def test_suggest_branch_name_success(self, mock_anthropic_class):
        """Test successful branch name suggestion."""
        # Set up mock response with proper anthropic types
        from anthropic.types import Message, TextBlock, Usage

        mock_response = Message(
            id="msg_test_123",
            type="message",
            role="assistant",
            content=[
                TextBlock(
                    text="<branch-name>cache-optimization</branch-name>",
                    type="text"
                )
            ],
            model="claude-3-5-sonnet-20241022",
            stop_reason="end_turn",
            usage=Usage(
                input_tokens=50,
                output_tokens=10,
                total_tokens=60
            )
        )
        
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_anthropic_class.return_value = mock_client
        
        client = ClaudeClient()
        branch_name = await client.suggest_branch_name(self.summaries)
        
        assert branch_name == "cache-optimization"
        
        # Verify API call
        mock_client.messages.create.assert_called_once()
        call_args = mock_client.messages.create.call_args
        assert call_args.kwargs['max_tokens'] == 50
        assert call_args.kwargs['temperature'] == 0.5
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('git_squash.ai.claude.AsyncAnthropic')
    @pytest.mark.asyncio
    async def test_suggest_branch_name_cleanup(self, mock_anthropic_class):
        """Test branch name cleanup and validation."""
        # Set up proper anthropic types
        from anthropic.types import Message, TextBlock, Usage

        # Test various malformed responses
        test_cases = [
            ("<branch-name>Cache Layer Updates!</branch-name>", "cache-layer-updates"),
            ("<branch-name>feature/cache_improvements</branch-name>", "featurecache-improvements"),
            ("<branch-name>UPPERCASE-NAME</branch-name>", "uppercase-name"),
            ("<branch-name>multiple---hyphens</branch-name>", "multiple-hyphens"),
            ("<branch-name>-leading-trailing-</branch-name>", "leading-trailing"),
        ]
        
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client
        
        client = ClaudeClient()
        
        for response_text, expected in test_cases:
            mock_response = Message(
                id="msg_test_123",
                type="message",
                role="assistant",
                content=[
                    TextBlock(
                        text=response_text,
                        type="text"
                    )
                ],
                model="claude-3-5-sonnet-20241022",
                stop_reason="end_turn",
                usage=Usage(
                    input_tokens=50,
                    output_tokens=10,
                    total_tokens=60
                )
            )
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            
            branch_name = await client.suggest_branch_name(self.summaries)
            assert branch_name == expected
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('git_squash.ai.claude.AsyncAnthropic')
    @pytest.mark.asyncio
    async def test_suggest_branch_name_fallback(self, mock_anthropic_class):
        """Test fallback branch name on error."""
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("API Error"))
        mock_anthropic_class.return_value = mock_client
        
        client = ClaudeClient()
        branch_name = await client.suggest_branch_name(self.summaries)
        
        assert branch_name == "updates"


class TestClaudeClientHelperMethods:
    """Test helper methods."""
    
    def setup_method(self):
        """Set up test fixtures."""
        if not HAS_ANTHROPIC:
            pytest.skip("anthropic library not installed")
            
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('git_squash.ai.claude.AsyncAnthropic'):
                self.client = ClaudeClient()
    
    def test_smart_truncate_diff(self):
        """Test intelligent diff truncation."""
        # Create a large diff
        diff_lines = [
            "diff --git a/file1.py b/file1.py",
            "index 123..456 100644",
            "--- a/file1.py",
            "+++ b/file1.py",
            "@@ -1,10 +1,15 @@",
        ]
        
        # Add many lines
        for i in range(1000):
            diff_lines.append(f"+line {i}")
        
        diff_lines.extend([
            "diff --git a/file2.py b/file2.py",
            "index 789..abc 100644",
            "--- a/file2.py",
            "+++ b/file2.py",
            "@@ -1,5 +1,8 @@",
            "+another change"
        ])
        
        diff_content = '\n'.join(diff_lines)
        
        # Truncate to small size
        truncated = self.client._smart_truncate_diff(diff_content, 500)
        
        # Should preserve structure
        assert "diff --git a/file1.py" in truncated
        assert "truncated" in truncated
        assert len(truncated) <= 600  # Some buffer for truncation messages
    
    def test_build_context_comprehensive(self):
        """Test comprehensive context building."""
        categories = CommitCategories(
            features=["Feature 1", "Feature 2"],
            fixes=["Fix 1"],
            tests=["Test 1"],
            docs=["Doc update"],
            dependencies=["Update deps"],
            refactoring=["Refactor module"],
            performance=["Optimize algo"],
            other=["Other change"]
        )
        
        analysis = ChangeAnalysis(
            categories=categories,
            diff_stats="5 files changed, 200 insertions(+), 50 deletions(-)",
            has_critical_changes=True,
            has_mocked_dependencies=True,
            has_incomplete_features=True,
            file_changes={"file1.py": 100, "file2.py": 100}
        )
        
        commit_subjects = ["Subject " + str(i) for i in range(20)]
        diff_content = "Sample diff content"
        
        context = self.client._build_context(analysis, commit_subjects, diff_content)
        
        # Verify all elements are included
        assert "Commits being summarized: 20" in context
        assert "Subject 0" in context
        assert "Subject 14" in context
        assert "... and 5 more" in context
        assert "5 files changed" in context
        assert "Sample diff content" in context
        assert "2 feature additions" in context
        assert "1 bug fixes" in context
        assert "WARNING: Contains critical/security changes" in context
        assert "WARNING: Uses mocked dependencies" in context
        assert "WARNING: Contains incomplete features" in context
    
    def test_create_fallback_summary_comprehensive(self):
        """Test comprehensive fallback summary generation."""
        categories = CommitCategories(
            features=["Add new API endpoint", "Add caching layer"],
            fixes=["Fix authentication bug", "Fix memory leak"],
            tests=["Add integration tests"],
            docs=[],
            dependencies=[],
            refactoring=[],
            performance=["Optimize database queries"],
            other=[]
        )
        
        analysis = ChangeAnalysis(
            categories=categories,
            diff_stats="",
            has_critical_changes=True,
            has_mocked_dependencies=True,
            has_incomplete_features=True,
            file_changes={}
        )
        
        summary = self.client._create_fallback_summary("2025-01-15", analysis)
        
        lines = summary.split('\n')
        assert lines[0] == "Add 2 features, 2 fixes, performance improvements"
        assert "- feature: add new api endpoint" in summary
        assert "- fix: fix authentication bug" in summary
        assert "- performance: optimize implementation" in summary
        assert "- note: Contains critical security or stability fixes" in summary
        assert "- note: Uses mocked dependencies" in summary
        assert "- note: Contains incomplete features" in summary
    
    def test_get_usage_stats(self):
        """Test usage statistics tracking."""
        stats = self.client.get_usage_stats()
        
        assert stats['total_requests'] == 0
        assert stats['total_tokens'] == 0
        assert stats['average_tokens_per_request'] == 0
        
        # Simulate some usage
        self.client._request_count = 5
        self.client._total_tokens_used = 1000
        
        stats = self.client.get_usage_stats()
        assert stats['total_requests'] == 5
        assert stats['total_tokens'] == 1000
        assert stats['average_tokens_per_request'] == 200


class TestClaudeClientEdgeCases:
    """Test edge cases and error conditions."""
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('git_squash.ai.claude.AsyncAnthropic')
    @pytest.mark.asyncio
    async def test_empty_response_handling(self, mock_anthropic_class):
        """Test handling of empty responses."""
        if not HAS_ANTHROPIC:
            pytest.skip("anthropic library not installed")
            
        # Empty content
        mock_response = Mock()
        mock_response.content = []
        
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_anthropic_class.return_value = mock_client
        
        client = ClaudeClient()
        
        # Create minimal analysis
        analysis = ChangeAnalysis(
            categories=CommitCategories([], [], [], [], [], [], [], []),
            diff_stats="",
            has_critical_changes=False,
            has_mocked_dependencies=False,
            has_incomplete_features=False,
            file_changes={}
        )
        
        summary = await client.generate_summary(
            date="2025-01-15",
            analysis=analysis,
            commit_subjects=["Test commit"]
        )
        
        # Should return fallback
        assert "Update implementation for 2025-01-15" in summary
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('git_squash.ai.claude.AsyncAnthropic')
    @pytest.mark.asyncio
    async def test_malformed_response_handling(self, mock_anthropic_class):
        """Test handling of malformed responses."""
        if not HAS_ANTHROPIC:
            pytest.skip("anthropic library not installed")
            
        # Response with dict-style content blocks
        mock_response = Mock()
        mock_response.content = [
            {'type': 'text', 'text': 'Some response without proper tags'},
            {'type': 'not-text', 'data': 'ignored'}
        ]
        
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_anthropic_class.return_value = mock_client
        
        client = ClaudeClient()
        
        analysis = ChangeAnalysis(
            categories=CommitCategories(["Add feature"], [], [], [], [], [], [], []),
            diff_stats="",
            has_critical_changes=False,
            has_mocked_dependencies=False,
            has_incomplete_features=False,
            file_changes={}
        )
        
        summary = await client.generate_summary(
            date="2025-01-15",
            analysis=analysis,
            commit_subjects=["Add feature"]
        )
        
        # Should handle dict-style blocks
        assert len(summary) > 0


class TestClaudeClientIntegration:
    """Integration tests with mocked Anthropic client."""
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('git_squash.ai.claude.AsyncAnthropic')
    @pytest.mark.asyncio
    async def test_full_workflow(self, mock_anthropic_class):
        """Test complete workflow from analysis to summary."""
        if not HAS_ANTHROPIC:
            pytest.skip("anthropic library not installed")
            
        # Set up comprehensive test data
        categories = CommitCategories(
            features=[
                "Add user authentication system",
                "Add OAuth2 integration",
                "Add session management"
            ],
            fixes=[
                "Fix SQL injection vulnerability",
                "Fix password hashing algorithm"
            ],
            tests=[
                "Add authentication unit tests",
                "Add integration tests for OAuth"
            ],
            docs=["Update API documentation"],
            dependencies=["Add oauth2-client library"],
            refactoring=["Refactor user model"],
            performance=["Optimize session queries"],
            other=[]
        )
        
        analysis = ChangeAnalysis(
            categories=categories,
            diff_stats="12 files changed, 1500 insertions(+), 200 deletions(-)",
            has_critical_changes=True,  # Security fixes
            has_mocked_dependencies=False,
            has_incomplete_features=False,
            file_changes={
                "auth/models.py": 300,
                "auth/views.py": 400,
                "auth/oauth.py": 500,
                "tests/test_auth.py": 300
            }
        )
        
        commit_subjects = [
            "Add basic user model",
            "Implement password hashing",
            "Fix SQL injection in login",
            "Add OAuth2 provider support",
            "Add session management",
            "Fix password algorithm vulnerability",
            "Add comprehensive auth tests",
            "Refactor user model for OAuth",
            "Update API docs for auth endpoints",
            "Optimize session lookup queries"
        ]
        
        diff_content = """diff --git a/auth/models.py b/auth/models.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/auth/models.py
@@ -0,0 +1,50 @@
+from django.db import models
+from django.contrib.auth.models import AbstractUser
+import bcrypt
+
+class User(AbstractUser):
+    '''Enhanced user model with OAuth support'''
+    oauth_provider = models.CharField(max_length=50, blank=True)
+    oauth_id = models.CharField(max_length=255, blank=True)
+    
+    def set_password(self, raw_password):
+        # Use bcrypt for secure password hashing
+        self.password = bcrypt.hashpw(
+            raw_password.encode('utf-8'),
+            bcrypt.gensalt()
+        ).decode('utf-8')
"""
        
        # Set up mock response with proper anthropic types
        from anthropic.types import Message, TextBlock, Usage

        mock_response = Message(
            id="msg_test_123",
            type="message",
            role="assistant",
            content=[
                TextBlock(
                    text="""<commit-message>
Implement secure authentication system with OAuth2 support

- add comprehensive user authentication with bcrypt password hashing
- implement OAuth2 integration for third-party authentication
- add session management with optimized database queries
- fix: critical SQL injection vulnerability in login endpoint
- fix: upgrade password hashing from MD5 to bcrypt
- tests: add full test coverage for authentication flows
- refactor: restructure user model to support OAuth providers
- docs: update API documentation with auth endpoints
- performance: optimize session queries with proper indexing
- note: Contains critical security fixes for SQL injection and weak hashing
</commit-message>""",
                    type="text"
                )
            ],
            model="claude-3-5-sonnet-20241022",
            stop_reason="end_turn",
            usage=Usage(
                input_tokens=200,
                output_tokens=50,
                total_tokens=250
            )
        )
        
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        mock_anthropic_class.return_value = mock_client
        
        # Test summary generation
        client = ClaudeClient()
        summary = await client.generate_summary(
            date="2025-01-15",
            analysis=analysis,
            commit_subjects=commit_subjects,
            diff_content=diff_content
        )
        
        # Verify comprehensive summary
        assert "Implement secure authentication system with OAuth2 support" in summary
        assert "bcrypt password hashing" in summary
        assert "SQL injection vulnerability" in summary
        assert "note: Contains critical security fixes" in summary
        
        # Test branch name suggestion
        mock_branch_response = Message(
            id="msg_test_456",
            type="message",
            role="assistant",
            content=[
                TextBlock(
                    text="<branch-name>auth-security-fixes</branch-name>",
                    type="text"
                )
            ],
            model="claude-3-5-sonnet-20241022",
            stop_reason="end_turn",
            usage=Usage(
                input_tokens=30,
                output_tokens=10,
                total_tokens=40
            )
        )
        mock_client.messages.create = AsyncMock(return_value=mock_branch_response)
        
        branch_name = await client.suggest_branch_name([summary])
        assert branch_name == "auth-security-fixes"
        
        # Verify usage stats
        stats = client.get_usage_stats()
        assert stats['total_requests'] == 2
        assert stats['total_tokens'] == 290  # 250 + 40 from both calls
        assert stats['average_tokens_per_request'] == 145  # 290 / 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])