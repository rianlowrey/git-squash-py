# Git Squash Tool

An intelligent Git commit squashing tool that uses AI to generate meaningful commit summaries. This tool analyzes your commit history and creates well-structured, consolidated commits with descriptive messages.

## Features

- **AI-Powered Summaries**: Uses Claude AI to generate intelligent commit messages
- **Smart Grouping**: Automatically groups commits by date and splits large changes
- **Safe by Default**: Dry-run mode prevents accidental changes
- **Flexible Configuration**: Customizable message limits, branch prefixes, and formatting
- **Test Mode**: Mock AI client for testing without API keys
- **Comprehensive Analysis**: Categorizes changes (features, fixes, tests, etc.)

## Installation

### Prerequisites

- Python 3.8+
- Git repository
- Anthropic API key (optional for test mode)

### Setup

1. Clone or download this repository
2. Install dependencies:
   ```bash
   pip install anthropic  # Only needed for Claude integration
   ```
3. Set your API key (optional):
   ```bash
   export ANTHROPIC_API_KEY='your-api-key-here'
   ```

## Usage

### Basic Usage

```bash
# Dry run - show what would be done (safe)
./git-squash

# Execute the squashing
./git-squash --execute

# Test mode (no API key required)
USE_TEST_BACKEND=1 ./git-squash
```

### Advanced Options

```bash
# Squash from specific date
./git-squash --from 2024-01-15 --execute

# Custom message length limit
./git-squash --limit 600

# Show help
./git-squash --help
```

### Python Module Usage

```bash
# Using the Python module directly
python3 -m git_squash.cli --dry-run
python3 -m git_squash.cli --test-mode --execute
python3 -m git_squash.cli --start-date 2024-01-01 --message-limit 800
```

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--execute`, `-e` | Execute the squash (default is dry-run) | `false` |
| `--dry-run` | Show plan without executing | `true` |
| `--from DATE` | Start from specific date (YYYY-MM-DD) | Beginning |
| `--limit CHARS` | Message character limit | `800` |
| `--test-mode` | Use mock AI (no API key required) | `false` |
| `--claude-model MODEL` | Claude model to use | `claude-3-haiku-20240307` |
| `--help`, `-h` | Show help message | |

## How It Works

1. **Analysis**: Scans your Git history and groups commits by date
2. **Categorization**: Classifies commits (features, fixes, tests, etc.)
3. **AI Generation**: Creates meaningful commit messages using Claude AI
4. **Validation**: Ensures messages meet Git best practices (50/72 rule)
5. **Execution**: Creates a new branch with squashed commits

## Example Output

### Before Squashing
```
abc1234 Fix typo in README
def5678 Add error handling to parser
ghi9012 Update tests for parser
jkl3456 Fix parser edge case
```

### After Squashing
```
mno7890 Add parser improvements with error handling

- add comprehensive error handling to parser module
- fix: parser edge case with malformed input  
- fix: typo in README documentation
- tests: update parser test coverage
- NOTE: parser now validates input format
```

## Configuration

The tool uses sensible defaults but can be customized:

- **Message Limits**: Subject line (50 chars), body width (72 chars), total (800 chars)
- **Branch Prefixes**: Default `feature/` for new branches
- **Retry Logic**: Up to 3 attempts for message generation
- **Splitting**: Automatically splits large commit groups

### Available Claude Models

You can specify different Claude models using the `--claude-model` option:

| Model | Description | Use Case |
|-------|-------------|----------|
| `claude-3-haiku-20240307` | Fast, cost-effective | Default - good balance of speed and quality |
| `claude-3-sonnet-20240229` | Higher quality | Better summaries for complex changes |
| `claude-3-opus-20240229` | Highest quality | Most detailed and nuanced summaries |
| `claude-3-5-sonnet-20241022` | Latest Sonnet | Improved coding and reasoning capabilities |
| `claude-3-5-haiku-20241022` | Latest Haiku | Fast with Opus-level performance |
| `claude-4-opus-20241128` | Claude 4 Opus | Highest quality reasoning and analysis |
| `claude-4-sonnet-20241128` | Claude 4 Sonnet | Advanced reasoning with good speed |

Example usage:
```bash
# Use Claude 4 Sonnet for advanced reasoning
./git-squash --claude-model claude-4-sonnet-20241128 --execute

# Use Claude 4 Opus for the highest quality analysis
python3 -m git_squash.cli --claude-model claude-4-opus-20241128 --dry-run

# Use 3.5 Sonnet for improved coding summaries
./git-squash --claude-model claude-3-5-sonnet-20241022
```

**Note**: Higher-tier models provide better quality but may have different usage costs and speed characteristics. Claude 4 models offer the most advanced reasoning capabilities.

## Testing

Run the test suite:

```bash
# Using the built-in test runner
python3 run_tests.py

# Using pytest directly
python3 -m pytest tests/ -v

# With coverage
python3 run_tests.py --coverage
```

## Project Structure

```
git-squash-py/
├── git-squash              # Main executable script
├── git_squash/             # Python package
│   ├── cli.py             # Command line interface
│   ├── tool.py            # Main squashing logic
│   ├── core/              # Core functionality
│   │   ├── config.py      # Configuration management
│   │   ├── types.py       # Type definitions
│   │   └── analyzer.py    # Commit analysis
│   ├── ai/                # AI integration
│   │   ├── claude.py      # Claude AI client
│   │   ├── mock.py        # Mock AI for testing
│   │   └── interface.py   # AI client interface
│   └── git/               # Git operations
│       └── operations.py  # Git command wrappers
├── tests/                 # Test suite
└── run_tests.py           # Test runner
```

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | Claude AI authentication | Required (unless test mode) |
| `USE_TEST_BACKEND` | Enable test mode | `0` |
| `GIT_SQUASH_VERBOSE` | Enable debug logging | `0` |

## Error Handling

The tool includes comprehensive error handling:

- **Git Validation**: Ensures you're in a Git repository
- **API Failures**: Falls back to basic summaries if AI is unavailable
- **Input Validation**: Validates dates, limits, and arguments
- **Backup Creation**: Creates backup branches before changes

## Limitations

- Requires Git repository
- Claude AI integration needs API key (unless using test mode)
- Works best with English commit messages
- Designed for feature branch workflows

## Contributing

1. Run tests: `python3 run_tests.py`
2. Follow existing code style
3. Add tests for new functionality
4. Update documentation

## Security

- Input validation on all command line arguments
- Safe defaults (dry-run mode)
- No secrets logged or committed
- Backup branches created automatically

## License

This project is provided as-is for educational and development purposes.

## Troubleshooting

### Common Issues

**"ANTHROPIC_API_KEY not set"**
```bash
export ANTHROPIC_API_KEY='your-key-here'
# OR use test mode
USE_TEST_BACKEND=1 ./git-squash
```

**"Not in a git repository"**
```bash
cd /path/to/your/git/repo
./git-squash
```

**"No commits found"**
- Check if you have commits in your repository
- Try specifying a different date range with `--from`

### Debug Mode

Enable verbose logging:
```bash
export GIT_SQUASH_VERBOSE=1
./git-squash
```

## Examples

### Squash Last Week's Work
```bash
./git-squash --from $(date -d '1 week ago' +%Y-%m-%d) --execute
```

### Test Mode Demo
```bash
USE_TEST_BACKEND=1 ./git-squash --execute
```

### Custom Configuration
```bash
./git-squash --limit 500 --from 2024-01-01 --execute
```

---

**Note**: This tool creates new branches and never modifies your original commits. Your work is always safe!