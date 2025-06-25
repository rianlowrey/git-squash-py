#!/bin/bash

# Create mock repository with diverse commit history spanning multiple days

# Helper function to create commits with specific dates
create_commit() {
    local date="$1"
    local message="$2"
    local files="$3"
    
    # Set dates for both author and committer
    export GIT_AUTHOR_DATE="$date"
    export GIT_COMMITTER_DATE="$date"
    
    # Make changes
    eval "$files"
    
    # Commit
    git add -A
    git commit -m "$message"
}

# Day 1: 2025-06-20 - Initial project setup
create_commit "2025-06-20T09:00:00" "Initial commit" "echo '# Project' > README.md"
create_commit "2025-06-20T10:30:00" "Add project structure" "mkdir -p src tests docs && echo 'fn main() {}' > src/main.rs"
create_commit "2025-06-20T11:45:00" "Add Cargo.toml" "echo '[package]\nname = \"myproject\"\nversion = \"0.1.0\"' > Cargo.toml"
create_commit "2025-06-20T14:20:00" "Add basic logging" "echo 'use log::info;' >> src/main.rs"
create_commit "2025-06-20T16:00:00" "Fix typo in README" "echo '# My Project' > README.md"

# Day 2: 2025-06-21 - Core functionality
create_commit "2025-06-21T08:30:00" "Add FileBuffer module" "echo 'pub struct FileBuffer {}' > src/buffer.rs"
create_commit "2025-06-21T09:15:00" "Implement buffer read method" "echo 'impl FileBuffer { fn read(&self) {} }' >> src/buffer.rs"
create_commit "2025-06-21T10:00:00" "Add error handling" "echo 'use std::error::Error;' > src/error.rs"
create_commit "2025-06-21T11:30:00" "Refactor buffer logic" "echo 'impl FileBuffer { fn read(&self) -> Result<(), Box<dyn Error>> {} }' > src/buffer.rs"
create_commit "2025-06-21T14:45:00" "Add buffer tests" "echo '#[test]\nfn test_buffer() {}' > tests/buffer_test.rs"
create_commit "2025-06-21T15:30:00" "Fix critical bug in buffer merge" "echo '// Fixed merge logic' >> src/buffer.rs"
create_commit "2025-06-21T16:00:00" "Update dependencies" "echo 'log = \"0.4\"' >> Cargo.toml"

# Day 3: 2025-06-22 - Optimization and docs
create_commit "2025-06-22T09:00:00" "Optimize buffer performance" "echo '// Optimized algorithm' >> src/buffer.rs"
create_commit "2025-06-22T10:30:00" "Add benchmarks" "echo '#[bench]\nfn bench_buffer() {}' > benches/buffer_bench.rs"
create_commit "2025-06-22T11:00:00" "Update documentation" "echo '//! Buffer module docs' > src/buffer.rs"
create_commit "2025-06-22T14:00:00" "Add CI configuration" "echo 'name: CI' > .github/workflows/ci.yml"

# Day 4: 2025-06-23 - Feature additions
create_commit "2025-06-23T08:00:00" "Add cache module" "echo 'pub struct Cache {}' > src/cache.rs"
create_commit "2025-06-23T09:30:00" "Implement LRU cache" "echo 'impl Cache { fn get(&self, key: &str) {} }' >> src/cache.rs"
create_commit "2025-06-23T10:15:00" "Add cache tests" "echo '#[test]\nfn test_cache() {}' > tests/cache_test.rs"
create_commit "2025-06-23T11:00:00" "Integrate cache with buffer" "echo 'use crate::cache::Cache;' >> src/buffer.rs"
create_commit "2025-06-23T14:30:00" "Fix memory leak in cache" "echo '// Fixed leak' >> src/cache.rs"
create_commit "2025-06-23T15:00:00" "Add metrics collection" "echo 'pub struct Metrics {}' > src/metrics.rs"
create_commit "2025-06-23T16:30:00" "Update README with examples" "echo '## Usage Examples' >> README.md"

# Day 5: 2025-06-24 - Bug fixes and cleanup
create_commit "2025-06-24T09:00:00" "Fix edge case in parser" "echo '// Handle empty input' >> src/main.rs"
create_commit "2025-06-24T09:30:00" "Update error messages" "echo 'pub const ERR_MSG: &str = \"Error\";' >> src/error.rs"
create_commit "2025-06-24T10:00:00" "Remove debug prints" "echo '// Cleaned up' >> src/buffer.rs"
create_commit "2025-06-24T11:00:00" "Fix test flakiness" "echo '// More stable test' >> tests/buffer_test.rs"
create_commit "2025-06-24T14:00:00" "Code cleanup" "echo '// Refactored' >> src/cache.rs"

echo "Mock repository created with $(git rev-list --count HEAD) commits spanning 5 days"