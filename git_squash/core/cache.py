"""File-based caching system for git squash summaries and plans."""
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import fcntl
import hashlib
import json
import logging
import os
import shutil
import sys
import tempfile

from ..core.types import SquashPlan, SquashPlanItem, CommitInfo

logger = logging.getLogger(__name__)


# Platform-specific file locking
if sys.platform == 'win32':
    import msvcrt

    def lock_file(file_obj, exclusive=True):
        """Lock file on Windows."""
        try:
            # Seek to beginning for locking
            file_obj.seek(0)
            if exclusive:
                msvcrt.locking(file_obj.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                # Windows doesn't have shared locks, so we skip
                pass
        except IOError:
            # If we can't get lock, continue anyway
            pass

    def unlock_file(file_obj):
        """Unlock file on Windows."""
        try:
            file_obj.seek(0)
            msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 1)
        except IOError:
            pass
else:
    # Unix/Linux/Mac
    import fcntl

    def lock_file(file_obj, exclusive=True):
        """Lock file on Unix-like systems."""
        if exclusive:
            fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX)
        else:
            fcntl.flock(file_obj.fileno(), fcntl.LOCK_SH)

    def unlock_file(file_obj):
        """Unlock file on Unix-like systems."""
        fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)


@dataclass
class CacheEntry:
    """Single cache entry with metadata."""
    key: str
    value: Any
    created_at: str
    expires_at: str
    context_hash: str
    metadata: Dict[str, Any]

    def is_expired(self) -> bool:
        """Check if this entry has expired."""
        expires = datetime.fromisoformat(self.expires_at)
        return datetime.now() > expires

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CacheEntry':
        """Create from dictionary."""
        return cls(**data)


class GitSquashCache:
    """File-based cache for commit summaries and squash plans.

    Features:
    - Persistent file-based storage
    - Atomic writes with file locking
    - TTL-based expiration
    - Context-aware caching (based on commits, diff, config)
    - Automatic cleanup of expired entries
    - Cache versioning for compatibility
    """

    CACHE_VERSION = "1.0"
    DEFAULT_TTL_DAYS = 7
    SUMMARY_CACHE_FILE = "summary_cache.json"
    PLAN_CACHE_FILE = "plan_cache.json"
    CACHE_LOCK_TIMEOUT = 5.0

    def __init__(self, cache_dir: Optional[Path] = None, ttl_days: int = DEFAULT_TTL_DAYS):
        """Initialize cache with directory and TTL.

        Args:
            cache_dir: Directory for cache files. Defaults to ~/.cache/git-squash
            ttl_days: Time-to-live for cache entries in days
        """
        if cache_dir is None:
            cache_dir = Path.home() / ".cache" / "git-squash"

        self.cache_dir = Path(cache_dir)
        self.ttl_days = ttl_days

        # Create cache directory if it doesn't exist
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Cache file paths
        self.summary_cache_path = self.cache_dir / self.SUMMARY_CACHE_FILE
        self.plan_cache_path = self.cache_dir / self.PLAN_CACHE_FILE

        # Initialize cache files if they don't exist
        self._initialize_cache_files()

        # Load caches into memory
        self._summary_cache: Dict[str, CacheEntry] = {}
        self._plan_cache: Dict[str, CacheEntry] = {}
        self._load_caches()

        logger.info("Initialized cache at %s with %d day TTL",
                    self.cache_dir, ttl_days)

    def _initialize_cache_files(self):
        """Create cache files with initial structure if they don't exist."""
        initial_data = {
            "version": self.CACHE_VERSION,
            "created_at": datetime.now().isoformat(),
            "entries": {}
        }

        for cache_path in [self.summary_cache_path, self.plan_cache_path]:
            if not cache_path.exists():
                self._write_json_atomic(cache_path, initial_data)

    def _load_caches(self):
        """Load caches from disk into memory."""
        # Load summary cache
        try:
            data = self._read_json_locked(self.summary_cache_path)
            if data.get("version") == self.CACHE_VERSION:
                for key, entry_dict in data.get("entries", {}).items():
                    entry = CacheEntry.from_dict(entry_dict)
                    if not entry.is_expired():
                        self._summary_cache[key] = entry
                    else:
                        logger.debug(
                            "Skipping expired summary cache entry: %s", key)
            else:
                logger.warning(
                    "Summary cache version mismatch, starting fresh")
                self._summary_cache = {}
        except Exception as e:
            logger.error("Failed to load summary cache: %s", e)
            self._summary_cache = {}

        # Load plan cache
        try:
            data = self._read_json_locked(self.plan_cache_path)
            if data.get("version") == self.CACHE_VERSION:
                for key, entry_dict in data.get("entries", {}).items():
                    entry = CacheEntry.from_dict(entry_dict)
                    if not entry.is_expired():
                        self._plan_cache[key] = entry
                    else:
                        logger.debug(
                            "Skipping expired plan cache entry: %s", key)
            else:
                logger.warning("Plan cache version mismatch, starting fresh")
                self._plan_cache = {}
        except Exception as e:
            logger.error("Failed to load plan cache: %s", e)
            self._plan_cache = {}

    def _persist_caches(self):
        """Persist in-memory caches to disk."""
        # Save summary cache
        summary_data = {
            "version": self.CACHE_VERSION,
            "updated_at": datetime.now().isoformat(),
            "entries": {k: v.to_dict() for k, v in self._summary_cache.items()}
        }
        self._write_json_atomic(self.summary_cache_path, summary_data)

        # Save plan cache
        plan_data = {
            "version": self.CACHE_VERSION,
            "updated_at": datetime.now().isoformat(),
            "entries": {k: v.to_dict() for k, v in self._plan_cache.items()}
        }
        self._write_json_atomic(self.plan_cache_path, plan_data)

    def _read_json_locked(self, path: Path) -> Dict[str, Any]:
        """Read JSON file with file locking (cross-platform)."""
        with open(path, 'r') as f:
            # Acquire shared lock for reading
            lock_file(f, exclusive=False)
            try:
                return json.load(f)
            finally:
                unlock_file(f)

    def _write_json_atomic(self, path: Path, data: Dict[str, Any]):
        """Write JSON file atomically with exclusive locking (cross-platform)."""
        # Write to temporary file first
        temp_fd, temp_path = tempfile.mkstemp(dir=self.cache_dir, suffix='.tmp')
        try:
            with os.fdopen(temp_fd, 'w') as f:
                # Acquire exclusive lock
                lock_file(f, exclusive=True)
                try:
                    json.dump(data, f, indent=2, default=str)
                    f.flush()
                    # fsync works on all platforms
                    os.fsync(f.fileno())
                finally:
                    unlock_file(f)
            
            # Atomic rename (works on all platforms in Python 3.3+)
            # On Windows, this will overwrite existing file
            os.replace(temp_path, path)
        except Exception:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def _generate_summary_key(
        self,
        date: str,
        commit_hashes: List[str],
        diff_hash: str,
        config_hash: str
    ) -> str:
        """Generate cache key for a summary.

        Args:
            date: Date of commits
            commit_hashes: List of commit hashes
            diff_hash: Hash of diff content
            config_hash: Hash of relevant config

        Returns:
            Unique cache key
        """
        # Create deterministic key from inputs
        key_parts = [
            "summary",
            date,
            "-".join(commit_hashes[:3]),  # First 3 commits
            f"n{len(commit_hashes)}",     # Total count
            diff_hash[:8],                 # Diff hash prefix
            config_hash[:8]                # Config hash prefix
        ]

        key_string = "|".join(key_parts)
        return hashlib.sha256(key_string.encode()).hexdigest()[:16]

    def _generate_plan_key(
        self,
        start_date: Optional[str],
        end_date: Optional[str],
        commit_count: int,
        first_hash: str,
        last_hash: str,
        config_hash: str
    ) -> str:
        """Generate cache key for a squash plan."""
        key_parts = [
            "plan",
            start_date or "begin",
            end_date or "head",
            f"n{commit_count}",
            first_hash[:8],
            last_hash[:8],
            config_hash[:8]
        ]

        key_string = "|".join(key_parts)
        return hashlib.sha256(key_string.encode()).hexdigest()[:16]

    def _hash_content(self, content: str) -> str:
        """Generate hash of content."""
        return hashlib.sha256(content.encode()).hexdigest()

    def _hash_config(self, config: Any) -> str:
        """Generate hash of configuration."""
        config_dict = {
            "subject_line_limit": config.subject_line_limit,
            "body_line_width": config.body_line_width,
            "total_message_limit": config.total_message_limit,
            "model": config.model
        }
        config_str = json.dumps(config_dict, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()

    def get_summary(
        self,
        date: str,
        commits: List[CommitInfo],
        diff_content: str,
        config: Any
    ) -> Optional[str]:
        """Get cached summary if available.

        Args:
            date: Date of commits
            commits: List of commits
            diff_content: Diff content
            config: GitSquashConfig

        Returns:
            Cached summary or None
        """
        commit_hashes = [c.hash for c in commits]
        diff_hash = self._hash_content(diff_content)
        config_hash = self._hash_config(config)

        key = self._generate_summary_key(
            date, commit_hashes, diff_hash, config_hash)

        entry = self._summary_cache.get(key)
        if entry and not entry.is_expired():
            logger.debug("Cache hit for summary: %s", key)
            return entry.value

        logger.debug("Cache miss for summary: %s", key)
        return None

    def set_summary(
        self,
        date: str,
        commits: List[CommitInfo],
        diff_content: str,
        config: Any,
        summary: str
    ):
        """Cache a summary.

        Args:
            date: Date of commits
            commits: List of commits
            diff_content: Diff content
            config: GitSquashConfig
            summary: Generated summary to cache
        """
        commit_hashes = [c.hash for c in commits]
        diff_hash = self._hash_content(diff_content)
        config_hash = self._hash_config(config)

        key = self._generate_summary_key(
            date, commit_hashes, diff_hash, config_hash)

        # Create cache entry
        now = datetime.now()
        expires = now + timedelta(days=self.ttl_days)

        entry = CacheEntry(
            key=key,
            value=summary,
            created_at=now.isoformat(),
            expires_at=expires.isoformat(),
            context_hash=diff_hash,
            metadata={
                "date": date,
                "commit_count": len(commits),
                "first_commit": commit_hashes[0][:8] if commit_hashes else "",
                "last_commit": commit_hashes[-1][:8] if commit_hashes else "",
                "summary_length": len(summary)
            }
        )

        self._summary_cache[key] = entry
        self._persist_caches()

        logger.debug("Cached summary: %s", key)

    def get_plan(
        self,
        start_date: Optional[str],
        end_date: Optional[str],
        all_commits: List[CommitInfo],
        config: Any
    ) -> Optional[Dict[str, Any]]:
        """Get cached squash plan if available.

        Returns serialized plan data or None.
        """
        if not all_commits:
            return None

        commit_count = len(all_commits)
        first_hash = all_commits[0].hash
        last_hash = all_commits[-1].hash
        config_hash = self._hash_config(config)

        key = self._generate_plan_key(
            start_date, end_date, commit_count,
            first_hash, last_hash, config_hash
        )

        entry = self._plan_cache.get(key)
        if entry and not entry.is_expired():
            logger.debug("Cache hit for plan: %s", key)
            return entry.value

        logger.debug("Cache miss for plan: %s", key)
        return None

    def set_plan(
        self,
        start_date: Optional[str],
        end_date: Optional[str],
        all_commits: List[CommitInfo],
        config: Any,
        plan: SquashPlan
    ):
        """Cache a squash plan."""
        if not all_commits:
            return

        commit_count = len(all_commits)
        first_hash = all_commits[0].hash
        last_hash = all_commits[-1].hash
        config_hash = self._hash_config(config)

        key = self._generate_plan_key(
            start_date, end_date, commit_count,
            first_hash, last_hash, config_hash
        )

        # Serialize plan
        plan_data = {
            "total_original_commits": plan.total_original_commits,
            "items": [
                {
                    "date": item.date,
                    "commit_count": len(item.commits),
                    "summary": item.summary,
                    "part": item.part,
                    "commit_hashes": [c.hash for c in item.commits]
                }
                for item in plan.items
            ]
        }

        # Create cache entry
        now = datetime.now()
        expires = now + timedelta(days=self.ttl_days)

        entry = CacheEntry(
            key=key,
            value=plan_data,
            created_at=now.isoformat(),
            expires_at=expires.isoformat(),
            context_hash=config_hash,
            metadata={
                "start_date": start_date,
                "end_date": end_date,
                "total_commits": commit_count,
                "squashed_commits": len(plan.items)
            }
        )

        self._plan_cache[key] = entry
        self._persist_caches()

        logger.debug("Cached plan: %s", key)

    def invalidate_plan(self, plan: SquashPlan):
        """Invalidate a plan after execution."""
        # Remove any cached plans that might contain these commits
        commits_in_plan = set()
        for item in plan.items:
            for commit in item.commits:
                commits_in_plan.add(commit.hash)

        # Check all cached plans
        keys_to_remove = []
        for key, entry in self._plan_cache.items():
            plan_data = entry.value
            # Check if any commits overlap
            for item_data in plan_data.get("items", []):
                if any(h in commits_in_plan for h in item_data.get("commit_hashes", [])):
                    keys_to_remove.append(key)
                    break

        # Remove invalidated entries
        for key in keys_to_remove:
            del self._plan_cache[key]
            logger.debug("Invalidated plan cache: %s", key)

        if keys_to_remove:
            self._persist_caches()

    def clear_expired(self):
        """Remove all expired entries from cache."""
        now = datetime.now()

        # Clear expired summaries
        expired_summaries = []
        for key, entry in self._summary_cache.items():
            if entry.is_expired():
                expired_summaries.append(key)

        for key in expired_summaries:
            del self._summary_cache[key]

        # Clear expired plans
        expired_plans = []
        for key, entry in self._plan_cache.items():
            if entry.is_expired():
                expired_plans.append(key)

        for key in expired_plans:
            del self._plan_cache[key]

        if expired_summaries or expired_plans:
            self._persist_caches()
            logger.info("Cleared %d expired summaries and %d expired plans",
                        len(expired_summaries), len(expired_plans))

    def clear_all(self):
        """Clear all cache entries."""
        self._summary_cache.clear()
        self._plan_cache.clear()
        self._persist_caches()
        logger.info("Cleared all cache entries")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_summaries = len(self._summary_cache)
        total_plans = len(self._plan_cache)

        # Calculate sizes
        summary_size = sum(len(e.value) for e in self._summary_cache.values())
        plan_size = sum(len(json.dumps(e.value))
                        for e in self._plan_cache.values())

        return {
            "cache_dir": str(self.cache_dir),
            "total_summaries": total_summaries,
            "total_plans": total_plans,
            "summary_cache_size_bytes": summary_size,
            "plan_cache_size_bytes": plan_size,
            "total_size_bytes": summary_size + plan_size,
            "ttl_days": self.ttl_days
        }
