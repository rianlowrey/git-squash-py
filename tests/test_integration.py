"""Comprehensive integration tests for git squash tool.

This combines the best of test_integration.py and test_integration_v2.py:
- Structured test scenarios with versioned content (from v2)
- Explicit merge testing and verification (from v1)
- Both abstracted and direct git operations
- Comprehensive date filtering and combine flag tests
"""

import pytest
import tempfile
import subprocess
import os
from pathlib import Path
from datetime import date, timedelta
from typing import List, Optional, Dict, Self, Sequence, Tuple
from dataclasses import dataclass
from enum import Enum
from git_squash import (
    GitSquashConfig, GitSquashTool,
    GitOperations, MockAIClient
)


class Version(Enum):
    """Content versions."""
    V1 = 1
    V2 = 2
    V3 = 3
    V4 = 4
    V5 = 5


# Versioned lorem ipsum content
LOREM_CONTENT = {
    Version.V1: "Lorem ipsum dolor sit amet.",

    Version.V2: (
        "Lorem ipsum dolor sit amet.\n"
        "Consectetur adipiscing elit, sed do eiusmod."
    ),

    Version.V3: (
        "Lorem ipsum dolor sit amet.\n"
        "Consectetur adipiscing elit, sed do eiusmod.\n"
        "Tempor incididunt ut labore et dolore magna aliqua."
    ),

    Version.V4: (
        "Lorem ipsum dolor sit amet.\n"
        "Consectetur adipiscing elit, sed do eiusmod.\n"
        "Tempor incididunt ut labore et dolore magna aliqua.\n"
        "Ut enim ad minim veniam, quis nostrud exercitation."
    ),

    Version.V5: (
        "Lorem ipsum dolor sit amet.\n"
        "Consectetur adipiscing elit, sed do eiusmod.\n"
        "Tempor incididunt ut labore et dolore magna aliqua.\n"
        "Ut enim ad minim veniam, quis nostrud exercitation.\n"
        "Ullamco laboris nisi ut aliquip ex ea commodo consequat."
    ),
}


@dataclass
class FileChange:
    """A file change with version."""
    path: str
    version: Version
    message: Optional[str] = None
    days_ago: Optional[int] = None  # Relative date specification

    def get_content(self) -> str:
        """Get the content for this version."""
        return LOREM_CONTENT[self.version]

    def get_message(self) -> str:
        """Get commit message."""
        if self.message:
            return self.message
        if self.version == Version.V1:
            return f"Add {Path(self.path).name}"
        return f"Update {Path(self.path).name} to v{self.version.value}"

    def get_commit_date(self, base_date: Optional[date] = None) -> Optional[str]:
        """Get commit date as ISO string."""
        if self.days_ago is None:
            return None
        base = base_date or date.today()
        commit_date = base - timedelta(days=self.days_ago)
        return f"{commit_date}T10:00:00"


def create_daily_scenario(
    name: str,
    days: int,
    files_per_day: int = 2,
    updates_per_day: int = 1
) -> List[FileChange]:
    """Create a scenario with daily commits over specified days.

    Args:
        name: Scenario name
        days: Number of days to span
        files_per_day: Number of new files to add each day
        updates_per_day: Number of file updates each day

    Returns:
        List of file changes
    """
    builder = ScenarioBuilder(name)
    all_files = []

    for day in range(days - 1, -1, -1):  # Start from oldest day
        builder.days_ago(day)

        # Add new files for this day
        day_files = []
        for i in range(files_per_day):
            file_path = f"src/day{days-day}/file{i+1}.js"
            builder.add(file_path)
            day_files.append(file_path)
            all_files.append(file_path)

        # Update some existing files
        if all_files and updates_per_day > 0:
            # Pick files to update (from previous days)
            files_to_update = [
                f for f in all_files if f not in day_files][:updates_per_day]
            for file_path in files_to_update:
                current_version = builder.file_versions[file_path]
                next_version = Version(min(current_version.value + 1, 5))
                builder.update(file_path, next_version)

    return builder.build()


class ScenarioBuilder:
    """Builder for test scenarios."""

    def __init__(self, name: str):
        self.name = name
        self.changes: List[FileChange] = []
        self.file_versions: Dict[str, Version] = {}
        # Track current date context
        self.current_days_ago: Optional[int] = None

    def on_day(self, days_ago: int) -> Self:
        """Set the date context for subsequent changes."""
        self.current_days_ago = days_ago
        return self

    def today(self) -> Self:
        """Set context to today."""
        return self.on_day(0)

    def yesterday(self) -> Self:
        """Set context to yesterday."""
        return self.on_day(1)

    def days_ago(self, n: int) -> Self:
        """Set context to n days ago."""
        return self.on_day(n)

    def add(self, path: str, message: Optional[str] = None) -> Self:
        """Add a new file."""
        self.changes.append(FileChange(
            path, Version.V1, message, self.current_days_ago))
        self.file_versions[path] = Version.V1
        return self

    def update(self, path: str, version: Version, message: Optional[str] = None) -> Self:
        """Update file to new version."""
        if path not in self.file_versions:
            raise ValueError(f"File {path} not found. Add it first.")
        self.changes.append(FileChange(
            path, version, message, self.current_days_ago))
        self.file_versions[path] = version
        return self

    def add_many(self, *paths: str, message: Optional[str] = None) -> Self:
        """Add multiple files in one commit."""
        for path in paths:
            self.add(path, message)
        return self

    def update_many(self, *updates: Tuple[str, Version], message: Optional[str] = None) -> Self:
        """Update multiple files in one commit."""
        for path, version in updates:
            self.update(path, version, message)
        return self

    def build(self) -> List[FileChange]:
        """Build the list of changes."""
        return self.changes


class GitTestRepository:
    """Helper for managing test git repositories."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.repo_path.mkdir(exist_ok=True)

    def run_git(self, *args, env=None, check=True):
        """Execute a git command."""
        cmd = ["git"] + list(args)
        result = subprocess.run(
            cmd,
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=check,
            env=env or os.environ
        )
        return result

    def init_repo(self, initial_branch="main"):
        """Initialize repository."""
        self.run_git("init")
        self.run_git("config", "user.name", "Test User")
        self.run_git("config", "user.email", "test@example.com")
        self.run_git("branch", "-m", initial_branch)

    def create_initial_commit(self):
        """Create initial commit."""
        (self.repo_path / "README.md").write_text("# Test Repository\n")
        self.run_git("add", "README.md")
        self.run_git("commit", "-m", "Initial commit")

    def switch_branch(self, branch_name: str, create: bool = True):
        """Switch to branch."""
        if create:
            self.run_git("checkout", "-b", branch_name)
        else:
            self.run_git("checkout", branch_name)

    def apply_change(self, change: FileChange, commit_date: Optional[str] = None):
        """Apply a single file change."""
        file_path = self.repo_path / change.path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(change.get_content())
        self.run_git("add", change.path)

        env = None
        if commit_date:
            env = os.environ.copy()
            env['GIT_AUTHOR_DATE'] = commit_date
            env['GIT_COMMITTER_DATE'] = commit_date

        self.run_git("commit", "-m", change.get_message(), env=env)

    def get_commit_count(self, revision_range: Optional[str] = None) -> int:
        """Get commit count."""
        args = ["log", "--oneline"]
        if revision_range:
            args.append(revision_range)
        result = self.run_git(*args)
        return len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0

    def merge_branch(self, branch_name: str, message: str):
        """Merge a branch."""
        return self.run_git("merge", "--no-ff", branch_name, "-m", message)

    def verify_file(self, path: str, version: Version) -> bool:
        """Verify file has expected content."""
        file_path = self.repo_path / path
        if not file_path.exists():
            return False
        return file_path.read_text() == LOREM_CONTENT[version]

    def get_file_content(self, path: str) -> str:
        """Get file content."""
        return (self.repo_path / path).read_text()

    def get_log_graph(self) -> str:
        """Get git log with graph."""
        result = self.run_git("log", "--oneline", "--graph", "--no-decorate")
        return result.stdout

    def file_exists(self, path: str) -> bool:
        """Check if file exists."""
        return (self.repo_path / path).exists()


# Test scenarios
SCENARIOS = {
    "simple_feature": (
        ScenarioBuilder("Simple Feature")
        .add("src/main.js")
        .update("src/main.js", Version.V2)
        .update("src/main.js", Version.V3)
        .add("docs/README.md")
        .update("docs/README.md", Version.V2)
        .build()
    ),

    "multi_file_commits": (
        ScenarioBuilder("Multi-file Commits")
        .add_many("src/app.js", "src/utils.js", "src/config.js",
                  message="Initial implementation")
        .update_many(
            ("src/app.js", Version.V2),
            ("src/utils.js", Version.V2),
            message="Add processing logic"
        )
        .update("src/config.js", Version.V2, "Update configuration")
        .add("tests/app.test.js", "Add tests")
        .update_many(
            ("src/app.js", Version.V3),
            ("tests/app.test.js", Version.V2),
            message="Enhance app with tests"
        )
        .build()
    ),

    "three_day_development": (
        ScenarioBuilder("Three Day Development")
        # Day 1 - 2 days ago
        .days_ago(2)
        .add("src/index.js")
        .add("package.json")
        .update("src/index.js", Version.V2)
        # Day 2 - yesterday
        .yesterday()
        .add("src/lib/core.js")
        .add("src/lib/utils.js")
        .update("src/lib/core.js", Version.V2, "Implement core logic")
        # Day 3 - today
        .today()
        .add("tests/core.test.js")
        .add("docs/API.md")
        .update("tests/core.test.js", Version.V2, "Expand tests")
        .update("docs/API.md", Version.V2, "Document API")
        .build()
    ),

    "multi_day_feature": (
        ScenarioBuilder("Feature Across Days")
        # Start 3 days ago
        .days_ago(3)
        .add("src/feature.js", "Initial feature stub")
        # Continue 2 days ago
        .days_ago(2)
        .update("src/feature.js", Version.V2, "Implement basic logic")
        .add("src/feature.config.js")
        # Yesterday
        .yesterday()
        .update("src/feature.js", Version.V3, "Add validation")
        .update("src/feature.config.js", Version.V2)
        .add("tests/feature.test.js")
        # Today
        .today()
        .update("src/feature.js", Version.V4, "Production ready")
        .update("tests/feature.test.js", Version.V2, "Complete test coverage")
        .build()
    ),

    # Real-world scenario similar to test_integration.py
    "real_world_dev": (
        ScenarioBuilder("Real World Development")
        .add("app.js", "Add initial app.js file")
        .update("app.js", Version.V2, "Add world to app.js")
        .update("app.js", Version.V3, "Add greet function")
        .add("CHANGELOG.md", "Fix critical bug in logging")
        .build()
    ),
}


def apply_scenario(repo: GitTestRepository, changes: List[FileChange],
                   base_date: Optional[date] = None):
    """Apply a scenario to repository."""
    for change in changes:
        commit_date = change.get_commit_date(base_date)
        repo.apply_change(change, commit_date)


def verify_final_state(repo: GitTestRepository, changes: List[FileChange]):
    """Verify all files are in their final state."""
    # Group by path to get final version (highest version number)
    final_versions = {}
    for change in changes:
        if change.path not in final_versions:
            final_versions[change.path] = change.version
        else:
            # Keep the higher version number
            if change.version.value > final_versions[change.path].value:
                final_versions[change.path] = change.version

    # Verify each file
    for path, version in final_versions.items():
        assert repo.verify_file(
            path, version), f"File {path} not at version {version}"


@pytest.fixture
def git_repo():
    """Create a temporary git repository."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo = GitTestRepository(Path(temp_dir) / "test_repo")
        repo.init_repo()
        repo.create_initial_commit()
        yield repo


@pytest.fixture
def squash_tool(git_repo: GitTestRepository):
    """Create GitSquashTool instance."""
    original_cwd = os.getcwd()
    try:
        os.chdir(git_repo.repo_path)

        config = GitSquashConfig()
        git_ops = GitOperations(config)
        ai_client = MockAIClient(config)
        tool = GitSquashTool(git_ops, ai_client, config)

        yield tool
    finally:
        os.chdir(original_cwd)


class TestGitSquashWorkflow:
    """Integration tests for git squash workflow."""

    @pytest.mark.asyncio
    async def test_simple_feature(self, git_repo: GitTestRepository, squash_tool: GitSquashTool):
        """Test squashing a simple feature branch."""
        changes = SCENARIOS["simple_feature"]

        # Create feature branch and apply changes
        git_repo.switch_branch("feature/simple")
        apply_scenario(git_repo, changes)

        # Create squash plan
        plan = await squash_tool.prepare_squash_plan()
        assert len(plan.items) >= 1

        # Execute squash
        target_branch = "feature/simple-squashed"
        squash_tool.execute_squash_plan(plan, target_branch)

        # Verify files are in final state
        git_repo.switch_branch(target_branch, create=False)
        verify_final_state(git_repo, changes)

        # Test merge to main
        git_repo.switch_branch("main", create=False)
        result = git_repo.merge_branch(target_branch, "Merge simple feature")
        assert result.returncode == 0

        # Verify files on main
        verify_final_state(git_repo, changes)

    @pytest.mark.asyncio
    async def test_real_world_workflow(self, git_repo: GitTestRepository, squash_tool: GitSquashTool):
        """Test the complete workflow matching test_integration.py test_simple_workflow."""
        changes = SCENARIOS["real_world_dev"]

        # Create dev branch and apply changes
        git_repo.switch_branch("dev")
        apply_scenario(git_repo, changes)

        # Verify we have the expected commits
        commit_count = git_repo.get_commit_count()
        assert commit_count == 5  # 4 dev commits + 1 initial

        # Get today's date for filtering
        today = date.today().strftime('%Y-%m-%d')

        # Prepare squash plan for today's commits
        plan = await squash_tool.prepare_squash_plan(start_date=today)

        # Verify plan looks correct
        assert len(plan.items) >= 1  # Should have at least one day
        assert plan.total_original_commits >= 4  # Should include our dev commits

        # Execute squash plan with base branch
        target_branch = "feature/test-squash"
        squash_tool.execute_squash_plan(plan, target_branch, "main")

        # Verify the feature branch was created
        git_repo.switch_branch(target_branch, create=False)
        feature_commits = git_repo.get_commit_count("main..")

        # Should have fewer commits than original (squashed)
        assert feature_commits < 4
        assert feature_commits >= 1  # At least 1 squashed commit

        # Verify files exist and have correct content
        assert git_repo.file_exists("app.js")
        assert git_repo.file_exists("CHANGELOG.md")

        app_content = git_repo.get_file_content("app.js")
        assert "Lorem ipsum dolor sit amet." in app_content  # V1
        assert "Consectetur adipiscing elit" in app_content  # V2
        assert "Tempor incididunt" in app_content  # V3

        changelog_content = git_repo.get_file_content("CHANGELOG.md")
        assert "Lorem ipsum" in changelog_content

        # CRITICAL TEST: Verify the branch can be merged back to main
        git_repo.switch_branch("main", create=False)

        # Before merge, main should only have README
        assert git_repo.file_exists("README.md")
        assert not git_repo.file_exists("app.js")
        assert not git_repo.file_exists("CHANGELOG.md")

        # Perform the merge - this is the key test!
        merge_result = git_repo.merge_branch(target_branch, "Merge squashed feature")
        assert merge_result.returncode == 0

        # After merge, main should have all files
        assert git_repo.file_exists("README.md")
        assert git_repo.file_exists("app.js")
        assert git_repo.file_exists("CHANGELOG.md")

        # Verify final file content is correct
        verify_final_state(git_repo, changes)

        # Verify clean merge history
        history = git_repo.get_log_graph()
        assert "Merge squashed feature" in history

    @pytest.mark.asyncio
    async def test_multi_day_incremental(self, git_repo: GitTestRepository, squash_tool: GitSquashTool):
        """Test incremental squashing over multiple days."""
        scenario = SCENARIOS["three_day_development"]

        # Apply all changes on dev branch
        git_repo.switch_branch("dev")
        apply_scenario(git_repo, scenario)

        # Process each day incrementally
        accumulated_changes = []
        base_date = date.today()

        for days_ago in [2, 1, 0]:  # Process from oldest to newest
            # Calculate date for this day
            process_date = base_date - timedelta(days=days_ago)
            date_str = process_date.strftime('%Y-%m-%d')

            # Create plan for this day only
            plan = await squash_tool.prepare_squash_plan(
                start_date=date_str,
                end_date=date_str
            )
            assert len(plan.items) == 1

            # Execute squash
            target_branch = f"feature/day{3-days_ago}"
            squash_tool.execute_squash_plan(plan, target_branch, "main")

            # Merge to main
            git_repo.switch_branch("main", create=False)
            result = git_repo.merge_branch(
                target_branch, f"Day {3-days_ago} work")
            assert result.returncode == 0

            # Accumulate changes for this day and verify
            day_changes = [c for c in scenario if c.days_ago == days_ago]
            accumulated_changes.extend(day_changes)
            verify_final_state(git_repo, accumulated_changes)

            # Back to dev for next day
            if days_ago > 0:
                git_repo.switch_branch("dev", create=False)

        # Verify clean merge history shows all merges
        history = git_repo.get_log_graph()
        assert "Day 1 work" in history
        assert "Day 2 work" in history
        assert "Day 3 work" in history

    @pytest.mark.asyncio
    async def test_date_filtering(self, git_repo: GitTestRepository, squash_tool: GitSquashTool):
        """Test date range filtering for squash plans."""
        scenario = SCENARIOS["multi_day_feature"]

        git_repo.switch_branch("feature/date-test")
        apply_scenario(git_repo, scenario)

        base_date = date.today()

        # Test: Get only yesterday's commits
        yesterday_str = (base_date - timedelta(days=1)).strftime('%Y-%m-%d')
        plan_yesterday = await squash_tool.prepare_squash_plan(
            start_date=yesterday_str,
            end_date=yesterday_str
        )

        # Should only include commits from yesterday
        yesterday_commits = [c for c in scenario if c.days_ago == 1]
        assert len(plan_yesterday.items) == 1
        assert len(plan_yesterday.items[0].commits) == len(yesterday_commits)

        # Test: Get range from 3 days ago to yesterday
        three_days_ago_str = (
            base_date - timedelta(days=3)).strftime('%Y-%m-%d')
        plan_range = await squash_tool.prepare_squash_plan(
            start_date=three_days_ago_str,
            end_date=yesterday_str
        )

        # Should exclude today's commits
        range_commits = [
            c for c in scenario if c.days_ago is not None and c.days_ago >= 1]
        total_commits_in_range = len(range_commits)
        total_commits_in_plan = sum(len(item.commits)
                                    for item in plan_range.items)
        assert total_commits_in_plan == total_commits_in_range

    @pytest.mark.asyncio
    async def test_custom_date_scenario(self, git_repo: GitTestRepository, squash_tool: GitSquashTool):
        """Test creating a custom scenario with specific date pattern."""
        # Create a scenario with a specific commit pattern
        scenario = (
            ScenarioBuilder("Custom Date Pattern")
            # Week 1 - heavy development
            .days_ago(7).add("src/core.js")
            .days_ago(6).update("src/core.js", Version.V2)
            .days_ago(6).add("src/utils.js")
            .days_ago(5).update("src/core.js", Version.V3)
            .days_ago(5).update("src/utils.js", Version.V2)
            # Week 2 - bug fixes
            .days_ago(3).update("src/core.js", Version.V4, "Fix critical bug")
            .days_ago(2).add("tests/core.test.js")
            .days_ago(1).update("tests/core.test.js", Version.V2)
            # Today - final touches
            .today().update("src/core.js", Version.V5, "Production ready")
            .build()
        )

        git_repo.switch_branch("feature/custom")
        apply_scenario(git_repo, scenario)

        # Test weekly squashing
        base_date = date.today()

        # Week 1 plan
        week1_start = (base_date - timedelta(days=7)).strftime('%Y-%m-%d')
        week1_end = (base_date - timedelta(days=5)).strftime('%Y-%m-%d')
        plan_week1 = await squash_tool.prepare_squash_plan(
            start_date=week1_start,
            end_date=week1_end
        )

        # Should have commits from days 7, 6, and 5 ago
        week1_commits = [c for c in scenario if c.days_ago in [7, 6, 5]]

    @pytest.mark.asyncio
    async def test_generated_daily_scenario(self, git_repo: GitTestRepository, squash_tool: GitSquashTool):
        """Test with a generated daily commit scenario."""
        # Generate a 5-day scenario with 3 files per day and 2 updates per day
        scenario = create_daily_scenario(
            name="Generated Daily Development",
            days=5,
            files_per_day=3,
            updates_per_day=2
        )

        git_repo.switch_branch("feature/generated")
        apply_scenario(git_repo, scenario)

        # Process with combine flag to get single commit
        plan = await squash_tool.prepare_squash_plan(combine=True)
        assert len(plan.items) == 1

        # Verify the date range
        combined_item = plan.items[0]
        assert " to " in combined_item.date

        # Execute and verify
        target_branch = "feature/generated-squashed"
        squash_tool.execute_squash_plan(plan, target_branch)

        git_repo.switch_branch(target_branch, create=False)
        verify_final_state(git_repo, scenario)

        # Verify we have the expected number of files
        # 5 days * 3 files per day = 15 unique files
        unique_files = set(change.path for change in scenario)
        assert len(unique_files) == 15

    @pytest.mark.asyncio
    async def test_combine_flag(self, git_repo: GitTestRepository, squash_tool: GitSquashTool):
        """Test combining multiple days into single commit."""
        # Use a scenario that spans multiple days
        scenario = SCENARIOS["multi_day_feature"]

        git_repo.switch_branch("feature/multi-day")
        apply_scenario(git_repo, scenario)

        # Without combine - should have multiple items (one per day)
        plan_separate = await squash_tool.prepare_squash_plan()
        assert len(plan_separate.items) > 1

        # With combine - should have 1 item
        plan_combined = await squash_tool.prepare_squash_plan(combine=True)
        assert len(plan_combined.items) == 1
        assert " to " in plan_combined.items[0].date  # Should show date range

        # Execute combined plan
        target_branch = "feature/combined"
        squash_tool.execute_squash_plan(plan_combined, target_branch)

        git_repo.switch_branch(target_branch, create=False)
        assert git_repo.get_commit_count("main..") == 1  # Single commit
        verify_final_state(git_repo, scenario)

    @pytest.mark.asyncio
    async def test_incremental_multi_day_merging_workflow(self, git_repo: GitTestRepository, squash_tool: GitSquashTool):
        """Test incremental squashing over 3 days with proper mergeability.

        This matches test_integration.py's test_incremental_multi_day_squashing_workflow.
        """
        # Define commits for each day (3 days)
        base_date = date.today() - timedelta(days=2)

        # Create scenario
        scenario = (
            ScenarioBuilder("Multi-day Incremental")
            # Day 1 commits
            .days_ago(2)
            .add("src/app.js", "Add initial app.js file")
            .update("src/app.js", Version.V2, "Add world to app.js")
            # Day 2 commits
            .days_ago(1)
            .add("src/utils.js", "Add utility functions")
            .update("src/app.js", Version.V3, "Add greet function")
            # Day 3 commits (today)
            .today()
            .add("CHANGELOG.md", "Add changelog")
            .add("package.json", "Add package.json")
            .build()
        )

        # Create and switch to dev branch
        git_repo.switch_branch("dev")
        apply_scenario(git_repo, scenario)

        # Verify we have the expected commits
        commit_count = git_repo.get_commit_count()
        assert commit_count == 7  # 6 dev commits + 1 initial

        current_base_branch = "main"

        # Process each day incrementally
        for day_idx in range(3):
            day_date = (base_date + timedelta(days=day_idx)).strftime('%Y-%m-%d')
            target_branch = f"feature/day-{day_idx + 1}-squash"

            print(f"\n--- Processing Day {day_idx + 1} ({day_date}) ---")

            # Go back to dev branch to get commits
            git_repo.switch_branch("dev", create=False)

            # Prepare squash plan for this specific day
            plan = await squash_tool.prepare_squash_plan(
                start_date=day_date,
                end_date=day_date
            )

            # Verify plan contains commits for this day
            assert len(plan.items) >= 1, f"Day {day_idx + 1} should have commits"
            assert plan.total_original_commits >= 1, f"Day {day_idx + 1} should have at least 1 commit"

            day_commit_count = plan.total_original_commits
            print(f"Day {day_idx + 1}: {day_commit_count} commits to squash")

            # Execute squash plan using current base branch
            squash_tool.execute_squash_plan(plan, target_branch, current_base_branch)

            # Verify the feature branch was created from correct base
            git_repo.switch_branch(target_branch, create=False)

            # Verify feature branch has expected structure
            feature_commits = git_repo.get_commit_count("main..")

            # Should have the squashed commits for this day
            # Each day's branch is created from main, so it should only have
            # the squashed commits for that specific day
            assert feature_commits >= 1

            # CRITICAL TEST: Verify branch can merge back to base
            git_repo.switch_branch(current_base_branch, create=False)

            # Count files before merge
            files_before = []
            for f in git_repo.repo_path.glob("**/*"):
                if f.is_file() and '.git' not in str(f):
                    files_before.append(f)

            # Perform the merge - this should not fail!
            merge_result = git_repo.merge_branch(target_branch, f"Merge day {day_idx + 1} feature")
            assert merge_result.returncode == 0, f"Day {day_idx + 1} merge failed"

            # Verify files were added correctly
            files_after = []
            for f in git_repo.repo_path.glob("**/*"):
                if f.is_file() and '.git' not in str(f):
                    files_after.append(f)
            assert len(files_after) > len(files_before), f"Day {day_idx + 1} should have added files"

            # Update base branch for next iteration
            current_base_branch = "main"  # Always use main as base since we merge each day

            print(f"Day {day_idx + 1}: Successfully squashed and merged")

        # Final verification: Check all expected files exist
        git_repo.switch_branch("main", create=False)

        assert git_repo.file_exists("README.md")
        assert git_repo.file_exists("src/app.js")
        assert git_repo.file_exists("src/utils.js")
        assert git_repo.file_exists("CHANGELOG.md")
        assert git_repo.file_exists("package.json")

        # Verify final content is correct
        app_content = git_repo.get_file_content("src/app.js")
        assert "Lorem ipsum dolor sit amet." in app_content  # V1
        assert "Consectetur adipiscing elit" in app_content  # V2
        assert "Tempor incididunt" in app_content  # V3

        # Verify clean merge history shows all merges
        history = git_repo.get_log_graph()
        assert "Merge day 1 feature" in history
        assert "Merge day 2 feature" in history
        assert "Merge day 3 feature" in history

        print("\n--- All days successfully processed! ---")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])