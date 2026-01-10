# BookTok AI Agent Documentation

## Project Overview
BookTok is a Telegram bot that delivers bite-sized learning snippets from PDF/EPUB books. The system:
1. Processes books from a configurable directory
2. Generates digestible snippets using NLTK sentence tokenization
3. Provides interactive book selection and progress tracking
4. Delivers snippets via Telegram on automated schedules
5. Maintains SQLite database for persistence

**Core architecture:** Single-threaded async Python application with:
- python-telegram-bot for messaging
- Background delivery scheduler
- Shared book processing pipeline
- Smart caching system

## Critical Architectural Patterns

### Module Structure
- `src/booktok/` - All application code under single package
- Absolute imports: `from booktok.models import Book`
- Public API exposed through `src/booktok/__init__.py`
- Single responsibility per module (processor, generator, formatter, scheduler, repository)

### Data Flow Pipeline
```
Book Directory → BookScanner → Book Selection → BookProcessor → SnippetGenerator →
Database Storage → DeliveryScheduler → SnippetFormatter → TelegramBotInterface
```

### Key Components
- `BookScanner` - Discovers books in configured directory
- `BookProcessor` - Validates files, extracts text from PDF/EPUB
- `SnippetGenerator` - Splits text into 800-char snippets using NLTK
- `DeliveryScheduler` - Manages automated snippet delivery with timezone support
- Repository pattern - Database access through repository classes

## Core Features

### Book Directory Management
- Configurable via `BOOKTOK_BOOKS_DIR` environment variable
- Automatic discovery of PDF/EPUB files
- Human-readable file size formatting
- Telegram `/books` command listing with metadata:
  - Display name (filename without extension)
  - File type (PDF/EPUB)
  - File size
  - Sorting by filename

### Interactive Book Selection
- Inline keyboard interface for book selection
- Smart caching of processed books
- Automatic text extraction and snippet generation
- Progress tracking with position reset on book change
- Shared book resources across multiple users

#### User Workflow:
1. User runs `/books` to see available books
2. Selects book via inline button
3. System processes book (or retrieves cached version)
4. User receives success message with snippet count
5. Uses `/next` to start reading

### Processing Pipeline
1. **Validation**: File type, size, and magic bytes check
2. **Text Extraction**:
   - PDF: PyPDF2 text extraction
   - EPUB: ebooklib with BeautifulSoup HTML parsing
3. **Snippet Generation**: NLTK sentence tokenization
4. **Database Storage**:
   - Book metadata (processed status)
   - Snippets (book-scoped)
   - User progress (position tracking)

## Database Patterns

### Connection Management
- `DatabaseConnectionManager` context manager
- Automatic transaction handling
- Foreign keys enabled via `PRAGMA foreign_keys = ON`

```python
with self.db.transaction() as conn:
    cursor = conn.execute("...", params)
```

### Repository Pattern
- One repository per model (`UserRepository`, `BookRepository`, etc.)
- CRUD operations return model instances
- Database rows converted to dataclasses

## Development Workflows

### Setup & Dependencies
```bash
make install          # Install with uv
make install-prod     # Production-only dependencies
make upgrade          # Upgrade all dependencies
```

**Dependency management:** Uses `uv` with dependencies in `pyproject.toml`

### Code Quality
```bash
make check            # Runs ruff lint + pre-commit hooks
make metrics          # Code complexity analysis
```

### Testing
```bash
make test             # Run all pytest tests
make test-single TEST=test_file.py
```

### Running
```bash
make run              # Starts bot (requires TELEGRAM_BOT_TOKEN)
```

## Error Handling
- **Result objects**: `ProcessingResult`, `SnippetGenerationResult`, etc.
- User-friendly error messages via `get_user_message()`
- Comprehensive logging:
  - Book selection events
  - Processing status (new vs cached)
  - Error conditions with stack traces
  - Progress changes

## Configuration
Environment variables:
- `TELEGRAM_BOT_TOKEN` - Required for bot operation
- `BOOKTOK_DB_PATH` - Database location (default: `booktok.db`)
- `BOOKTOK_BOOKS_DIR` - Books directory (default: `books/`)
- `BOOKTOK_LOG_LEVEL` - Logging level (default: `INFO`)

## Future Enhancements
1. Book metadata extraction (author/title from files)
2. Multiple active books per user
3. Progress preservation when re-selecting books
4. Reading statistics and completion tracking
5. Search/filter capabilities for large libraries
6. Book recommendation system

## Common Gotchas
1. NLTK data requires internet on first run (`punkt_tab`)
2. Foreign keys must be explicitly enabled per connection
3. Telegram message limit (4096 chars) - snippets capped at 3500
4. Timezone handling in scheduler requires proper configuration
5. File validation includes magic bytes check beyond extensions

## Architectural Decisions
1. **Separation of Concerns**:
   - Dedicated `BookScanner` module
   - Processing logic separate from Telegram interface
2. **Configuration-driven**:
   - Books directory configurable via env vars
   - All critical paths parameterized
3. **Extensibility**:
   - Dataclasses designed for easy expansion
   - Modular pipeline components
4. **Performance**:
   - Book processing cached per file hash
   - Snippets generated once per book
   - Fast database lookups for shared resources

## When Adding Features
1. New models: Add to `models.py` with validation
2. New database tables: Update `create_tables()` in `database.py`
3. New bot commands: Register via `CommandHandler` in `telegram_bot.py`
4. New configurations: Extend `config.py` dataclasses
5. Always:
   - Maintain type hints
   - Run `make check` before commits
   - Update documentation
