"""Comprehensive tests for the refactored git squash tool."""

import pytest
from git_squash import (GitSquashConfig, GitSquashTool,
                        GitOperations, MockAIClient)


class TestMergeableFeatureBranchWorkflow:
    """Integration test for the complete mergeable feature branch workflow."""

    @pytest.mark.asyncio
    async def test_complete_mergeable_workflow(self):
        """Test the complete workflow: dev commits → squash → merge to main."""
        import tempfile
        import subprocess
        import os
        from pathlib import Path

        # Create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Initialize git repository
            def run_git(*args, cwd=repo_path):
                cmd = ["git"] + list(args)
                result = subprocess.run(
                    cmd,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    check=True
                )
                return result

            # Set up repository
            run_git("init")
            run_git("config", "user.name", "Test User")
            run_git("config", "user.email", "test@example.com")
            run_git("branch", "-m", "main")

            # Create initial commit on main
            (repo_path / "README.md").write_text("# Test Project\n")
            run_git("add", "README.md")
            run_git("commit", "-m", "Initial commit")

            # Create and switch to dev branch
            run_git("checkout", "-b", "dev")

            # Create multiple commits on dev branch
            commits_data = [
                ("app.js", "console.log('hello');\n", "Add initial app.js file"),
                ("app.js", "console.log('hello');\nconsole.log('world');\n",
                 "Add world to app.js"),
                ("app.js",
                 "console.log('hello');\nconsole.log('world');\nfunction greet() { console.log('Hi!'); }\n", "Add greet function"),
                ("CHANGELOG.md", "# Bug fixes\n", "Fix critical bug in logging"),
            ]

            for filename, content, message in commits_data:
                (repo_path / filename).write_text(content)
                run_git("add", filename)
                run_git("commit", "-m", message)

            # Verify we have the expected commits
            log_result = run_git("log", "--oneline", "--no-decorate")
            commit_lines = log_result.stdout.strip().split('\n')
            assert len(commit_lines) == 5  # 4 dev commits + 1 initial

            # Get today's date for filtering
            from datetime import date
            today = date.today().strftime('%Y-%m-%d')

            # Create components for the tool
            original_cwd = os.getcwd()
            try:
                os.chdir(repo_path)

                # Create git operations and tool
                config = GitSquashConfig()
                git_ops = GitOperations(config)
                ai_client = MockAIClient(config)
                tool = GitSquashTool(git_ops, ai_client, config)

                # Prepare squash plan for today's commits
                plan = await tool.prepare_squash_plan(start_date=today)

                # Verify plan looks correct
                assert len(plan.items) >= 1  # Should have at least one day
                assert plan.total_original_commits >= 4  # Should include our dev commits

                # Execute squash plan with base branch
                target_branch = "feature/test-squash"
                tool.execute_squash_plan(plan, target_branch, "main")

                # Verify the feature branch was created
                branches_result = run_git("branch", "--list", target_branch)
                assert target_branch in branches_result.stdout

                # Verify the feature branch has commits
                run_git("checkout", target_branch)
                log_result = run_git("log", "--oneline", "--no-decorate")
                feature_commits = log_result.stdout.strip().split('\n')

                # Should have fewer commits than original (squashed)
                assert len(feature_commits) < len(commit_lines)
                assert len(feature_commits) >= 2  # At least initial + squashed

                # Verify files exist and have correct content
                assert (repo_path / "app.js").exists()
                assert (repo_path / "CHANGELOG.md").exists()

                app_content = (repo_path / "app.js").read_text()
                assert "console.log('hello');" in app_content
                assert "console.log('world');" in app_content
                assert "function greet()" in app_content

                changelog_content = (repo_path / "CHANGELOG.md").read_text()
                assert "# Bug fixes" in changelog_content

                # CRITICAL TEST: Verify the branch can be merged back to main
                run_git("checkout", "main")

                # Before merge, main should only have README
                assert (repo_path / "README.md").exists()
                assert not (repo_path / "app.js").exists()
                assert not (repo_path / "CHANGELOG.md").exists()

                # Perform the merge - this is the key test!
                merge_result = run_git(
                    "merge", "--no-ff", target_branch, "-m", "Merge squashed feature")
                assert merge_result.returncode == 0

                # After merge, main should have all files
                assert (repo_path / "README.md").exists()
                assert (repo_path / "app.js").exists()
                assert (repo_path / "CHANGELOG.md").exists()

                # Verify final file content is correct
                final_app_content = (repo_path / "app.js").read_text()
                assert "console.log('hello');" in final_app_content
                assert "console.log('world');" in final_app_content
                assert "function greet()" in final_app_content

                final_changelog_content = (
                    repo_path / "CHANGELOG.md").read_text()
                assert "# Bug fixes" in final_changelog_content

                # Verify clean merge history
                log_result = run_git("log", "--oneline",
                                     "--graph", "--no-decorate")
                history = log_result.stdout

                # Should show merge commit structure
                assert "Merge squashed feature" in history

                # Test passes if we get here without exceptions!

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
