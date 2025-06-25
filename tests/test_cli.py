"""Tests for CLI functionality."""

import pytest
import sys
from io import StringIO
from unittest.mock import Mock, patch, MagicMock
from git_squash.cli import (
    create_argument_parser, validate_environment, create_ai_client,
    display_plan, confirm_execution, main
)
from git_squash.core.config import GitSquashConfig
from git_squash.core.types import SquashPlan, SquashPlanItem, CommitInfo
from datetime import datetime


class TestArgumentParser:
    """Test CLI argument parsing."""
    
    def test_default_arguments(self):
        """Test default argument values."""
        parser = create_argument_parser()
        args = parser.parse_args([])
        
        assert args.message_limit == 800
        assert args.branch_prefix == "feature/"
        assert args.claude_model == "claude-3-haiku-20240307"
        assert args.dry_run is False
        assert args.execute is False
        assert args.test_mode is False
        assert args.verbose is False
    
    def test_execute_argument(self):
        """Test --execute argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--execute"])
        
        assert args.execute is True
        assert args.dry_run is False
    
    def test_dry_run_argument(self):
        """Test --dry-run argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--dry-run"])
        
        assert args.dry_run is True
        assert args.execute is False
    
    def test_mutually_exclusive_execution(self):
        """Test that --execute and --dry-run are mutually exclusive."""
        parser = create_argument_parser()
        
        with pytest.raises(SystemExit):
            parser.parse_args(["--execute", "--dry-run"])
    
    def test_date_and_limit_arguments(self):
        """Test date and limit arguments."""
        parser = create_argument_parser()
        args = parser.parse_args([
            "--start-date", "2024-01-01",
            "--message-limit", "600"
        ])
        
        assert args.start_date == "2024-01-01"
        assert args.message_limit == 600
    
    def test_test_mode_argument(self):
        """Test --test-mode argument."""
        parser = create_argument_parser()
        args = parser.parse_args(["--test-mode"])
        
        assert args.test_mode is True


class TestEnvironmentValidation:
    """Test environment validation."""
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_valid_environment_with_api_key(self):
        """Test validation passes with API key."""
        # Should not raise
        validate_environment(use_test_mode=False)
    
    def test_valid_environment_test_mode(self):
        """Test validation passes in test mode."""
        # Should not raise
        validate_environment(use_test_mode=True)
    
    @patch.dict('os.environ', {}, clear=True)
    def test_invalid_environment_no_api_key(self):
        """Test validation fails without API key."""
        with pytest.raises(SystemExit):
            validate_environment(use_test_mode=False)


class TestAIClientCreation:
    """Test AI client creation."""
    
    def test_create_mock_client(self):
        """Test creating mock AI client."""
        args = Mock()
        args.test_mode = True
        config = GitSquashConfig()
        
        client = create_ai_client(args, config)
        
        from git_squash.ai.mock import MockAIClient
        assert isinstance(client, MockAIClient)
    
    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    @patch('git_squash.cli.ClaudeClient')
    def test_create_claude_client(self, mock_claude_class):
        """Test creating Claude AI client."""
        args = Mock()
        args.test_mode = False
        config = GitSquashConfig()
        
        mock_instance = Mock()
        mock_claude_class.return_value = mock_instance
        
        client = create_ai_client(args, config)
        
        mock_claude_class.assert_called_once_with(config=config)
        assert client == mock_instance


class TestPlanDisplay:
    """Test plan display functionality."""
    
    def test_display_plan(self, capsys):
        """Test plan display output."""
        # Create mock plan
        commit = CommitInfo(
            hash="abc123def456",
            date="2024-01-01T10:00:00",
            subject="Test commit",
            author_name="Test User",
            author_email="test@example.com",
            datetime=datetime(2024, 1, 1, 10, 0, 0)
        )
        
        item = SquashPlanItem(
            date="2024-01-01",
            commits=[commit],
            summary="Test summary\n\nThis is a test commit summary"
        )
        
        plan = Mock()
        plan.items = [item]
        plan.summary_stats.return_value = "1 commit → 1 squashed commit"
        
        display_plan(plan)
        
        captured = capsys.readouterr()
        assert "SQUASH PLAN" in captured.out
        assert "2024-01-01: 1 commits" in captured.out
        assert "abc123de..abc123de" in captured.out
        assert "Test summary" in captured.out


class TestConfirmExecution:
    """Test execution confirmation."""
    
    @patch('builtins.input', return_value='y')
    def test_confirm_yes(self, mock_input):
        """Test confirmation with 'y' response."""
        result = confirm_execution()
        assert result is True
    
    @patch('builtins.input', return_value='yes')
    def test_confirm_yes_full(self, mock_input):
        """Test confirmation with 'yes' response."""
        result = confirm_execution()
        assert result is True
    
    @patch('builtins.input', return_value='n')
    def test_confirm_no(self, mock_input):
        """Test confirmation with 'n' response."""
        result = confirm_execution()
        assert result is False
    
    @patch('builtins.input', return_value='no')
    def test_confirm_no_full(self, mock_input):
        """Test confirmation with 'no' response."""
        result = confirm_execution()
        assert result is False
    
    @patch('builtins.input', side_effect=['invalid', 'y'])
    def test_confirm_retry(self, mock_input):
        """Test confirmation retry on invalid input."""
        result = confirm_execution()
        assert result is True


class TestMainFunction:
    """Test main CLI function."""
    
    @patch('git_squash.cli.GitOperations')
    @patch('git_squash.cli.create_ai_client')
    @patch('git_squash.cli.GitSquashTool')
    @patch('git_squash.cli.validate_environment')
    def test_main_dry_run(self, mock_validate, mock_tool_class, mock_create_ai, mock_git_ops_class):
        """Test main function in dry run mode."""
        # Set up mocks
        mock_git_ops = Mock()
        mock_git_ops_class.return_value = mock_git_ops
        
        mock_ai_client = Mock()
        mock_create_ai.return_value = mock_ai_client
        
        mock_tool = Mock()
        mock_tool_class.return_value = mock_tool
        
        # Create mock plan
        mock_plan = Mock()
        mock_plan.items = []
        mock_plan.summary_stats.return_value = "0 commits → 0 squashed commits"
        mock_tool.prepare_squash_plan.return_value = mock_plan
        
        # Run main
        result = main(['--dry-run'])
        
        assert result == 0
        mock_validate.assert_called_once()
        mock_tool.prepare_squash_plan.assert_called_once()
    
    @patch('git_squash.cli.GitOperations')
    @patch('git_squash.cli.create_ai_client')
    @patch('git_squash.cli.GitSquashTool')
    @patch('git_squash.cli.validate_environment')
    @patch('git_squash.cli.confirm_execution', return_value=True)
    def test_main_execute(self, mock_confirm, mock_validate, mock_tool_class, mock_create_ai, mock_git_ops_class):
        """Test main function in execute mode."""
        # Set up mocks
        mock_git_ops = Mock()
        mock_git_ops_class.return_value = mock_git_ops
        
        mock_ai_client = Mock()
        mock_create_ai.return_value = mock_ai_client
        
        mock_tool = Mock()
        mock_tool_class.return_value = mock_tool
        
        # Create mock plan
        mock_plan = Mock()
        mock_plan.items = []
        mock_plan.summary_stats.return_value = "0 commits → 0 squashed commits"
        mock_tool.prepare_squash_plan.return_value = mock_plan
        mock_tool.suggest_branch_name.return_value = "feature/test"
        
        # Run main
        result = main(['--execute'])
        
        assert result == 0
        mock_tool.execute_squash_plan.assert_called_once()
    
    @patch('git_squash.cli.GitOperations')
    @patch('git_squash.cli.create_ai_client') 
    @patch('git_squash.cli.GitSquashTool')
    @patch('git_squash.cli.validate_environment')
    @patch('git_squash.cli.confirm_execution', return_value=False)
    def test_main_execute_aborted(self, mock_confirm, mock_validate, mock_tool_class, mock_create_ai, mock_git_ops_class):
        """Test main function when execution is aborted."""
        # Set up mocks
        mock_git_ops = Mock()
        mock_git_ops_class.return_value = mock_git_ops
        
        mock_ai_client = Mock()
        mock_create_ai.return_value = mock_ai_client
        
        mock_tool = Mock()
        mock_tool_class.return_value = mock_tool
        
        # Create mock plan
        mock_plan = Mock()
        mock_plan.items = []
        mock_plan.summary_stats.return_value = "0 commits → 0 squashed commits"
        mock_tool.prepare_squash_plan.return_value = mock_plan
        
        # Run main
        result = main(['--execute'])
        
        assert result == 0
        mock_tool.execute_squash_plan.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])