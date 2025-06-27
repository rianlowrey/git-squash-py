"""Comprehensive tests for the GitSquashCache implementation."""
import pytest
import json
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from git_squash.core.cache import GitSquashCache, CacheEntry
from git_squash.core.types import CommitInfo, SquashPlan, SquashPlanItem
from git_squash.core.config import GitSquashConfig


class TestCacheEntry:
    """Test CacheEntry class."""

    def test_create_cache_entry(self):
        """Test creating a cache entry."""
        now = datetime.now()
        expires = now + timedelta(days=1)

        entry = CacheEntry(
            key="test_key",
            value="test_value",
            created_at=now.isoformat(),
            expires_at=expires.isoformat(),
            context_hash="abc123",
            metadata={"test": "data"}
        )

        assert entry.key == "test_key"
        assert entry.value == "test_value"
        assert not entry.is_expired()

    def test_cache_entry_expiration(self):
        """Test cache entry expiration."""
        now = datetime.now()
        past = now - timedelta(days=1)

        entry = CacheEntry(
            key="test_key",
            value="test_value",
            created_at=past.isoformat(),
            expires_at=past.isoformat(),  # Already expired
            context_hash="abc123",
            metadata={}
        )

        assert entry.is_expired()

    def test_cache_entry_serialization(self):
        """Test cache entry to/from dict conversion."""
        now = datetime.now()
        expires = now + timedelta(days=1)

        entry = CacheEntry(
            key="test_key",
            value="test_value",
            created_at=now.isoformat(),
            expires_at=expires.isoformat(),
            context_hash="abc123",
            metadata={"count": 5}
        )

        # Test to_dict
        entry_dict = entry.to_dict()
        assert entry_dict["key"] == "test_key"
        assert entry_dict["value"] == "test_value"
        assert entry_dict["metadata"]["count"] == 5

        # Test from_dict
        restored_entry = CacheEntry.from_dict(entry_dict)
        assert restored_entry.key == entry.key
        assert restored_entry.value == entry.value
        assert restored_entry.metadata == entry.metadata


class TestGitSquashCache:
    """Test GitSquashCache class."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create temporary directory for cache
        self.temp_dir = tempfile.mkdtemp()
        self.cache_dir = Path(self.temp_dir) / "test_cache"

        # Create test config
        self.config = GitSquashConfig()

        # Create test commits
        from datetime import datetime
        self.commits = [
            CommitInfo(
                hash="abc123",
                subject="Add feature A",
                author_name="Test User",
                author_email="test@example.com",
                date="2025-01-01",
                datetime=datetime(2025, 1, 1, 12, 0, 0)
            ),
            CommitInfo(
                hash="def456",
                subject="Fix bug B",
                author_name="Test User",
                author_email="test@example.com",
                date="2025-01-01",
                datetime=datetime(2025, 1, 1, 12, 30, 0)
            ),
            CommitInfo(
                hash="ghi789",
                subject="Update docs",
                author_name="Test User",
                author_email="test@example.com",
                date="2025-01-01",
                datetime=datetime(2025, 1, 1, 13, 0, 0)
            )
        ]

        self.diff_content = "diff --git a/test.py b/test.py\n+print('hello')"

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_cache_initialization(self):
        """Test cache initialization."""
        cache = GitSquashCache(cache_dir=self.cache_dir, ttl_days=5)

        assert cache.cache_dir == self.cache_dir
        assert cache.ttl_days == 5
        assert cache.cache_dir.exists()
        assert cache.summary_cache_path.exists()
        assert cache.plan_cache_path.exists()

        # Check initial file structure
        with open(cache.summary_cache_path) as f:
            data = json.load(f)
            assert data["version"] == "1.0"
            assert "created_at" in data
            assert data["entries"] == {}

    def test_cache_initialization_default_location(self):
        """Test cache initialization with default location."""
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = Path(self.temp_dir)
            cache = GitSquashCache()

            expected_dir = Path(self.temp_dir) / ".cache" / "git-squash"
            assert cache.cache_dir == expected_dir
            assert cache.cache_dir.exists()

    def test_summary_cache_set_and_get(self):
        """Test setting and getting summary cache."""
        cache = GitSquashCache(cache_dir=self.cache_dir)

        # Cache a summary
        summary = "Add awesome features\n\n- implement feature A\n- fix critical bug B"
        cache.set_summary("2025-01-01", self.commits, self.diff_content, self.config, summary)

        # Retrieve the summary
        cached_summary = cache.get_summary("2025-01-01", self.commits, self.diff_content, self.config)

        assert cached_summary == summary

        # Verify it persisted to disk
        cache2 = GitSquashCache(cache_dir=self.cache_dir)
        cached_summary2 = cache2.get_summary("2025-01-01", self.commits, self.diff_content, self.config)
        assert cached_summary2 == summary

    def test_summary_cache_miss_different_diff(self):
        """Test cache miss when diff content changes."""
        cache = GitSquashCache(cache_dir=self.cache_dir)

        # Cache with original diff
        summary = "Original summary"
        cache.set_summary("2025-01-01", self.commits, self.diff_content, self.config, summary)

        # Try to get with different diff
        different_diff = "diff --git a/other.py b/other.py\n+print('world')"
        cached_summary = cache.get_summary("2025-01-01", self.commits, different_diff, self.config)

        assert cached_summary is None

    def test_summary_cache_miss_different_config(self):
        """Test cache miss when config changes."""
        cache = GitSquashCache(cache_dir=self.cache_dir)

        # Cache with original config
        summary = "Original summary"
        cache.set_summary("2025-01-01", self.commits, self.diff_content, self.config, summary)

        # Try to get with different config
        different_config = GitSquashConfig(model="claude-3-opus-20240229")
        cached_summary = cache.get_summary("2025-01-01", self.commits, self.diff_content, different_config)

        assert cached_summary is None

    def test_summary_cache_miss_different_commits(self):
        """Test cache miss when commits change."""
        cache = GitSquashCache(cache_dir=self.cache_dir)

        # Cache with original commits
        summary = "Original summary"
        cache.set_summary("2025-01-01", self.commits, self.diff_content, self.config, summary)

        # Try to get with different commits
        different_commits = [
            CommitInfo(
                hash="xyz999",
                subject="Different commit",
                author_name="Test User",
                author_email="test@example.com",
                date="2025-01-01",
                datetime=datetime(2025, 1, 1, 14, 0, 0)
            )
        ]
        cached_summary = cache.get_summary("2025-01-01", different_commits, self.diff_content, self.config)

        assert cached_summary is None

    def test_plan_cache_set_and_get(self):
        """Test setting and getting plan cache."""
        cache = GitSquashCache(cache_dir=self.cache_dir)

        # Create a squash plan
        plan_items = [
            SquashPlanItem(
                date="2025-01-01",
                commits=self.commits[:2],
                summary="Add features and fixes",
                part=1
            ),
            SquashPlanItem(
                date="2025-01-01",
                commits=self.commits[2:],
                summary="Update documentation",
                part=2
            )
        ]
        plan = SquashPlan(items=plan_items, total_original_commits=len(self.commits), config=self.config)

        # Cache the plan
        cache.set_plan("2025-01-01", "2025-01-01", self.commits, self.config, plan)

        # Retrieve the plan
        cached_plan_data = cache.get_plan("2025-01-01", "2025-01-01", self.commits, self.config)

        assert cached_plan_data is not None
        assert cached_plan_data["total_original_commits"] == len(self.commits)
        assert len(cached_plan_data["items"]) == 2
        assert cached_plan_data["items"][0]["summary"] == "Add features and fixes"
        assert cached_plan_data["items"][1]["summary"] == "Update documentation"

        # Verify it persisted to disk
        cache2 = GitSquashCache(cache_dir=self.cache_dir)
        cached_plan_data2 = cache2.get_plan("2025-01-01", "2025-01-01", self.commits, self.config)
        assert cached_plan_data2 == cached_plan_data

    def test_plan_cache_miss_different_commits(self):
        """Test plan cache miss when commits change."""
        cache = GitSquashCache(cache_dir=self.cache_dir)

        # Create and cache a plan
        plan_items = [SquashPlanItem(date="2025-01-01", commits=self.commits, summary="Test", part=1)]
        plan = SquashPlan(items=plan_items, total_original_commits=len(self.commits), config=self.config)
        cache.set_plan("2025-01-01", "2025-01-01", self.commits, self.config, plan)

        # Try to get with different commits
        different_commits = [
            CommitInfo(
                hash="new123",
                subject="New commit",
                author_name="Test User",
                author_email="test@example.com",
                date="2025-01-01",
                datetime=datetime(2025, 1, 1, 15, 0, 0)
            )
        ]
        cached_plan = cache.get_plan("2025-01-01", "2025-01-01", different_commits, self.config)

        assert cached_plan is None

    def test_cache_expiration(self):
        """Test cache expiration functionality."""
        # Use very short TTL for testing
        cache = GitSquashCache(cache_dir=self.cache_dir, ttl_days=0.000001)  # ~0.1 seconds

        # Cache a summary
        summary = "Test summary"
        cache.set_summary("2025-01-01", self.commits, self.diff_content, self.config, summary)

        # Should be available immediately
        cached_summary = cache.get_summary("2025-01-01", self.commits, self.diff_content, self.config)
        assert cached_summary == summary

        # Wait for expiration
        time.sleep(0.2)

        # Should be expired now
        cached_summary = cache.get_summary("2025-01-01", self.commits, self.diff_content, self.config)
        assert cached_summary is None

    def test_clear_expired(self):
        """Test clearing expired cache entries."""
        cache = GitSquashCache(cache_dir=self.cache_dir, ttl_days=7)

        # Manually create expired entry
        expired_entry = CacheEntry(
            key="expired_key",
            value="expired_value",
            created_at=(datetime.now() - timedelta(days=10)).isoformat(),
            expires_at=(datetime.now() - timedelta(days=3)).isoformat(),
            context_hash="abc",
            metadata={}
        )
        cache._summary_cache["expired_key"] = expired_entry

        # Create valid entry
        cache.set_summary("2025-01-01", self.commits, self.diff_content, self.config, "Valid summary")

        # Clear expired entries
        cache.clear_expired()

        # Expired entry should be gone
        assert "expired_key" not in cache._summary_cache

        # Valid entry should remain
        cached_summary = cache.get_summary("2025-01-01", self.commits, self.diff_content, self.config)
        assert cached_summary == "Valid summary"

    def test_clear_all(self):
        """Test clearing all cache entries."""
        cache = GitSquashCache(cache_dir=self.cache_dir)

        # Add some cache entries
        cache.set_summary("2025-01-01", self.commits, self.diff_content, self.config, "Summary 1")
        cache.set_summary("2025-01-02", self.commits, self.diff_content, self.config, "Summary 2")

        # Verify they exist
        assert cache.get_summary("2025-01-01", self.commits, self.diff_content, self.config) == "Summary 1"
        assert cache.get_summary("2025-01-02", self.commits, self.diff_content, self.config) == "Summary 2"

        # Clear all
        cache.clear_all()

        # Should be empty
        assert cache.get_summary("2025-01-01", self.commits, self.diff_content, self.config) is None
        assert cache.get_summary("2025-01-02", self.commits, self.diff_content, self.config) is None

    def test_plan_invalidation(self):
        """Test plan cache invalidation after execution."""
        cache = GitSquashCache(cache_dir=self.cache_dir)

        # Create and cache multiple plans
        plan1_items = [SquashPlanItem(date="2025-01-01", commits=self.commits[:2], summary="Plan 1", part=1)]
        plan1 = SquashPlan(items=plan1_items, total_original_commits=2, config=self.config)
        cache.set_plan("2025-01-01", "2025-01-01", self.commits[:2], self.config, plan1)

        plan2_items = [SquashPlanItem(date="2025-01-02", commits=self.commits[2:], summary="Plan 2", part=1)]
        plan2 = SquashPlan(items=plan2_items, total_original_commits=1, config=self.config)
        cache.set_plan("2025-01-02", "2025-01-02", self.commits[2:], self.config, plan2)

        # Verify both plans are cached
        assert cache.get_plan("2025-01-01", "2025-01-01", self.commits[:2], self.config) is not None
        assert cache.get_plan("2025-01-02", "2025-01-02", self.commits[2:], self.config) is not None

        # Invalidate plan1 (should only affect plan1)
        cache.invalidate_plan(plan1)

        # Plan1 should be invalidated, plan2 should remain
        assert cache.get_plan("2025-01-01", "2025-01-01", self.commits[:2], self.config) is None
        assert cache.get_plan("2025-01-02", "2025-01-02", self.commits[2:], self.config) is not None

    def test_cache_stats(self):
        """Test cache statistics."""
        cache = GitSquashCache(cache_dir=self.cache_dir, ttl_days=5)

        # Initially empty
        stats = cache.get_stats()
        assert stats["total_summaries"] == 0
        assert stats["total_plans"] == 0
        assert stats["ttl_days"] == 5
        assert stats["cache_dir"] == str(self.cache_dir)

        # Add some cache entries
        cache.set_summary("2025-01-01", self.commits, self.diff_content, self.config, "Test summary")

        plan_items = [SquashPlanItem(date="2025-01-01", commits=self.commits, summary="Test plan", part=1)]
        plan = SquashPlan(items=plan_items, total_original_commits=len(self.commits), config=self.config)
        cache.set_plan("2025-01-01", "2025-01-01", self.commits, self.config, plan)

        # Check updated stats
        stats = cache.get_stats()
        assert stats["total_summaries"] == 1
        assert stats["total_plans"] == 1
        assert stats["summary_cache_size_bytes"] > 0
        assert stats["plan_cache_size_bytes"] > 0
        assert stats["total_size_bytes"] > 0

    def test_cache_key_generation(self):
        """Test cache key generation consistency."""
        cache = GitSquashCache(cache_dir=self.cache_dir)

        # Generate key for same inputs multiple times
        key1 = cache._generate_summary_key(
            "2025-01-01",
            ["abc123", "def456"],
            "diff_hash",
            "config_hash"
        )
        key2 = cache._generate_summary_key(
            "2025-01-01",
            ["abc123", "def456"],
            "diff_hash",
            "config_hash"
        )

        # Should be identical
        assert key1 == key2

        # Different inputs should give different keys
        key3 = cache._generate_summary_key(
            "2025-01-02",  # Different date
            ["abc123", "def456"],
            "diff_hash",
            "config_hash"
        )

        assert key1 != key3

    def test_cache_version_mismatch(self):
        """Test handling of cache version mismatches."""
        cache = GitSquashCache(cache_dir=self.cache_dir)

        # Manually write cache file with wrong version
        wrong_version_data = {
            "version": "0.9",  # Wrong version
            "created_at": datetime.now().isoformat(),
            "entries": {
                "test_key": {
                    "key": "test_key",
                    "value": "test_value",
                    "created_at": datetime.now().isoformat(),
                    "expires_at": (datetime.now() + timedelta(days=1)).isoformat(),
                    "context_hash": "abc",
                    "metadata": {}
                }
            }
        }

        with open(cache.summary_cache_path, 'w') as f:
            json.dump(wrong_version_data, f)

        # Create new cache instance - should handle version mismatch gracefully
        cache2 = GitSquashCache(cache_dir=self.cache_dir)

        # Should be empty due to version mismatch
        assert len(cache2._summary_cache) == 0

    def test_cache_corrupted_file_handling(self):
        """Test handling of corrupted cache files."""
        cache = GitSquashCache(cache_dir=self.cache_dir)

        # Write corrupted JSON to cache file
        with open(cache.summary_cache_path, 'w') as f:
            f.write("invalid json content {{{")

        # Create new cache instance - should handle corruption gracefully
        cache2 = GitSquashCache(cache_dir=self.cache_dir)

        # Should start with empty cache
        assert len(cache2._summary_cache) == 0

        # Should be able to add new entries
        cache2.set_summary("2025-01-01", self.commits, self.diff_content, self.config, "New summary")
        cached = cache2.get_summary("2025-01-01", self.commits, self.diff_content, self.config)
        assert cached == "New summary"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])