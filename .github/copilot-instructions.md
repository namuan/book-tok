# BookTok AI Agent Instructions

## Project Overview

BookTok is a Telegram bot that delivers bite-sized learning snippets from PDF/EPUB books. The system:
1. Processes uploaded books (PDF/EPUB) to extract text
2. Generates digestible snippets using NLTK sentence tokenization
3. Delivers snippets via Telegram on automated schedules
4. Tracks user reading progress through a SQLite database

**Core architecture:** Single-threaded async Python application with SQLite persistence, python-telegram-bot for messaging, and a background delivery scheduler.

## Critical Architectural Patterns

### Module Structure
- `src/booktok/` - All application code under a single package
- Imports use absolute references: `from booktok.models import Book` (never relative imports)
- Public API exposed through `src/booktok/__init__.py` with explicit `__all__` exports
- Each module has a single responsibility (processor, generator, formatter, scheduler, repository)

### Data Flow Pipeline
```
Book Upload → BookProcessor → SnippetGenerator → Database Storage →
DeliveryScheduler → SnippetFormatter → TelegramBotInterface
```

**Key components:**
- `BookProcessor` ([book_processor.py](src/booktok/book_processor.py)) - Validates files, extracts text from PDF/EPUB
- `SnippetGenerator` ([snippet_generator.py](src/booktok/snippet_generator.py)) - Splits text into 800-char snippets using NLTK
- `DeliveryScheduler` ([delivery_scheduler.py](src/booktok/delivery_scheduler.py)) - Manages automated snippet delivery with timezone support
- Repository pattern ([repository.py](src/booktok/repository.py)) - All database access through repository classes

### Database Patterns

**Connection Management:**
- Use `DatabaseConnectionManager` context manager pattern for transactions
- Never create raw sqlite3 connections
- All repos initialized with `DatabaseConnectionManager` instance
- Example:
```python
with self.db.transaction() as conn:
    cursor = conn.execute("...", params)
    conn.commit()  # automatic via context manager
```

**Repository Pattern:**
- One repository per model: `UserRepository`, `BookRepository`, `SnippetRepository`, etc.
- CRUD operations return model instances (dataclasses from `models.py`)
- Database rows converted to models using `_row_to_<model>()` helper methods
- Foreign key constraints enabled via `PRAGMA foreign_keys = ON`

### Error Handling & Validation

**All user-facing operations return Result objects:**
- `ProcessingResult` (book processing)
- `SnippetGenerationResult` (snippet generation)
- `DeliveryResult` (delivery operations)
- Each has `success: bool` and `get_user_message()` for user-friendly errors

**Model validation:**
- All dataclasses have `.validate()` methods called in `__post_init__`
- Raise `ValidationError` with descriptive messages
- See [models.py](src/booktok/models.py) for patterns

### Async Patterns

**Critical:** The app uses `asyncio` with python-telegram-bot's async API:
- Bot handlers are async: `async def command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE)`
- Delivery runner uses `asyncio.create_task()` for background execution
- Message sending uses `await bot.send_message()`
- Don't mix sync/async without proper await/async def

## Development Workflows

### Setup & Dependency Management
```bash
make install          # Install with uv, setup pre-commit hooks
make install-prod     # Production-only dependencies
make upgrade          # Upgrade all dependencies
```
**Important:** This project uses `uv` (not pip/poetry). Dependencies in `pyproject.toml` under `[project.dependencies]` and `[dependency-groups.dev]`.

### Code Quality (Required Before Commits)
```bash
make check            # Runs ruff lint + pre-commit hooks + complexity checks
make metrics          # Dead code detection, cyclomatic complexity, maintainability
```
**Pre-commit hooks:** Configured in `.pre-commit-config.yaml` - runs ruff, mypy stubs, json/yaml validation.

### Testing
```bash
make test             # Run all pytest tests
make test-single TEST=test_config.py  # Single test file
```
**Testing patterns:**
- Use `PYTHONPATH=.` to ensure imports work
- Tests should mock `DatabaseConnectionManager` for isolation
- No test files exist yet - follow pytest conventions when adding

### Running the Application
```bash
make run              # Starts the bot (requires TELEGRAM_BOT_TOKEN in .env)
```
**Environment variables:**
- `TELEGRAM_BOT_TOKEN` - Required for bot operation
- `BOOKTOK_DB_PATH` - Database location (default: `booktok.db`)
- `BOOKTOK_LOG_LEVEL` - Logging level (default: `INFO`)
- See [config.py](src/booktok/config.py) for all config options

## Project-Specific Conventions

### Type Safety
- **Strict mypy enabled:** All functions must have type hints (`disallow_untyped_defs = true`)
- Optional types explicit: `Optional[str]` not `str | None` (though both work)
- External libraries without stubs (ebooklib, nltk) have `ignore_missing_imports` overrides in `pyproject.toml`

### Logging
- Use module-level logger: `logger = logging.getLogger(__name__)`
- Log important state changes at `INFO` level
- User errors at `WARNING`, system errors at `ERROR`
- Never log sensitive data (tokens, user content)

### Constants
- User-facing messages as module-level constants (see `telegram_bot.py`: `WELCOME_MESSAGE`, `HELP_MESSAGE`)
- Magic numbers extracted to module constants (see `book_processor.py`: `MAX_FILE_SIZE_BYTES`, `MIN_SNIPPET_LENGTH`)

### File Organization
- One class per file (except small helpers/dataclasses)
- Models in `models.py` as dataclasses with validation
- Exceptions defined near usage (e.g., `BookProcessingError` in `book_processor.py`)

## Integration Points

### External Dependencies
- **python-telegram-bot:** Async API, version constraints in pyproject.toml
- **NLTK:** Downloads `punkt_tab` tokenizer data on first use (see `_ensure_nltk_data()` pattern)
- **PyPDF2:** PDF text extraction (handles `PdfReadError` exceptions)
- **ebooklib:** EPUB processing with BeautifulSoup for HTML parsing

### Telegram Bot Commands
Defined in `telegram_bot.py` - register new commands via `CommandHandler`:
```python
self.application.add_handler(CommandHandler("command", self._handle_command))
```
All commands validated against `VALID_COMMANDS` list for error messages.

### Scheduler Integration
`AutomatedDeliveryRunner` creates background asyncio task that:
1. Checks for due deliveries every N seconds (configurable)
2. Calls `send_message_func` (injected dependency from `main.py`)
3. Updates delivery schedules and user progress
4. Uses exponential backoff for retries

## Ralph Agent Context

The `scripts/ralph/` directory contains a workflow agent for iterative development:
- Uses `prd.json` for story tracking
- Appends learnings to `progress.txt`
- Requires passing quality checks before commits
- See [prompt.md](scripts/ralph/prompt.md) for workflow details

**Pattern consolidation:** When discovering reusable patterns, add to `## Codebase Patterns` section in progress.txt before committing.

## Common Gotchas

1. **NLTK data initialization:** First snippet generation requires internet for downloading `punkt_tab` - handle in tests with mocking
2. **Database foreign keys:** Must be explicitly enabled per connection with `PRAGMA foreign_keys = ON`
3. **Timezone handling:** Always convert to user's timezone for display using `ZoneInfo` (see `DeliveryScheduler`)
4. **Telegram message limits:** Max 4096 chars - snippets capped at 3500, formatter handles truncation
5. **File validation:** Check file existence, size, and magic bytes before processing (see `BookProcessor.validate_file()`)
6. **Import structure:** Run from project root with `python -m booktok.main` or via `make run` for proper module resolution

## When Adding Features

1. **New models:** Add to `models.py` as dataclass with validation, update `__init__.py` exports
2. **New database tables:** Add to `create_tables()` in `database.py`, create repository in `repository.py`
3. **New bot commands:** Add handler in `telegram_bot.py`, update `VALID_COMMANDS` list
4. **New configurations:** Add to `config.py` dataclasses with env var loading
5. Always update type hints and run `make check` before committing
