# Books Directory Feature - Implementation Summary

## Overview
This implementation adds functionality to load and list EPUB/PDF books from a pre-defined directory, configurable via environment variables.

## Changes Made

### 1. Configuration Updates

#### `src/booktok/config.py`
- Added `BooksConfig` dataclass with `directory` field (default: "books")
- Updated `AppConfig` to include `books: BooksConfig` field
- Added environment variable loading for `BOOKTOK_BOOKS_DIR`

#### `.env.example`
- Added `BOOKTOK_BOOKS_DIR` configuration with default value "books"
- Added documentation explaining the books directory purpose

### 2. New Module: Book Scanner

#### `src/booktok/book_scanner.py`
Created a new module with:
- **`BookFile` dataclass**: Represents a discovered book file with metadata (path, filename, file_type, size_bytes)
- **`BookScanner` class**: Scans directories for PDF/EPUB files
  - `scan()`: Returns list of all valid book files in the directory
  - `get_book_by_name(filename)`: Retrieves a specific book by filename
  - `format_size(size_bytes)`: Formats file sizes in human-readable format (B, KB, MB, GB)

Key features:
- Supports PDF and EPUB file types
- Automatically filters by supported extensions (.pdf, .epub)
- Returns sorted list by filename
- Handles missing/invalid directories gracefully

### 3. Telegram Bot Updates

#### `src/booktok/telegram_bot.py`
- **New `/books` command**: Lists all available books from the configured directory
  - Shows book count
  - Displays each book with:
    - Display name (filename without extension)
    - Full filename
    - File type (PDF/EPUB)
    - File size in human-readable format
  - Handles empty directory with helpful message
- Updated `HELP_MESSAGE` to include `/books` command
- Updated `UNRECOGNIZED_COMMAND_MESSAGE` to include `/books` in suggestions
- Updated `VALID_COMMANDS` list to include "books"
- Added `BookScanner` and `BooksConfig` imports
- Modified `__init__()` to accept `books_config` parameter
- Initialized `book_scanner` instance in constructor

### 4. Main Application Updates

#### `src/main.py`
- Updated `TelegramBotInterface` initialization to pass `self.config.books`

#### `src/booktok/__init__.py`
- Added exports for `BookFile`, `BookScanner`, and `BooksConfig`

## Usage

### Setup

1. **Configure books directory** in `.env`:
   ```env
   BOOKTOK_BOOKS_DIR=/path/to/your/books
   # Or use relative path (default: books/)
   BOOKTOK_BOOKS_DIR=books
   ```

2. **Place book files** in the configured directory:
   - Supported formats: PDF (.pdf), EPUB (.epub)
   - Files will be automatically discovered

3. **Run the bot** as usual:
   ```bash
   make run
   ```

### Telegram Commands

Users can now use:
```
/books
```

This command will:
- List all available books in the configured directory
- Show file details (name, type, size)
- Display helpful message if no books are found

### Example Output

```
📚 Available Books

Found 3 book(s):

1. Python Programming Basics
   📄 File: `python_basics.pdf`
   📊 Type: PDF | Size: 2.3 MB

2. Learning Django
   📄 File: `django_guide.epub`
   📊 Type: EPUB | Size: 1.8 MB

3. Advanced Algorithms
   📄 File: `algorithms_advanced.pdf`
   📊 Type: PDF | Size: 5.1 MB

💡 Coming Soon:
Selection and processing features are under development.
Stay tuned!
```

## Architecture Notes

### Design Decisions

1. **Separation of Concerns**: Created dedicated `BookScanner` module rather than adding scanning logic to `BookProcessor`
2. **Configuration-driven**: Books directory is fully configurable via environment variables
3. **Extensibility**: `BookFile` dataclass can be easily extended with additional metadata
4. **Error Handling**: Gracefully handles missing directories, invalid files, and permission errors
5. **User Experience**: Provides clear, formatted output with emoji indicators and helpful messages

### Future Enhancements

The current implementation provides listing functionality. Future work could include:
- Book selection and processing from the directory
- Automatic import of selected books into the database
- Book metadata extraction (author, title from PDF/EPUB metadata)
- Search/filter capabilities
- Pagination for large book collections
- Interactive selection using Telegram inline keyboards

## Testing

To test the feature:

1. Create a books directory:
   ```bash
   mkdir -p books
   ```

2. Add sample PDF/EPUB files to the directory

3. Start the bot and use `/books` command

4. Verify that books are listed correctly with proper metadata

## Files Modified

- `src/booktok/config.py` - Added BooksConfig
- `src/booktok/book_scanner.py` - New module
- `src/booktok/telegram_bot.py` - Added /books command
- `src/main.py` - Updated bot initialization
- `src/booktok/__init__.py` - Added exports
- `.env.example` - Added BOOKTOK_BOOKS_DIR

## Compatibility

- Maintains backward compatibility with existing functionality
- No breaking changes to existing commands or database schema
- Works with existing book processing pipeline
