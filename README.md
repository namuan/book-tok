# BookTok - Telegram Book Snippet Delivery Bot

BookTok is a Telegram bot that delivers bite-sized learning snippets from PDF and EPUB books on a scheduled basis.

## Features

- 📚 Process PDF/EPUB books into digestible snippets
- ⏰ Schedule automated delivery of book snippets
- 🤖 Interactive Telegram bot interface
- 🔒 Secure configuration via environment variables
- 📊 Database persistence for user preferences
- ✅ Comprehensive logging and monitoring

## Prerequisites

- Python 3.12+
- [UV](https://github.com/astral-sh/uv) package manager
- Telegram Bot Token ([Get from BotFather](https://core.telegram.org/bots#how-do-i-create-a-bot))

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/book-tok.git
cd book-tok
```

2. Create and configure environment file:
```bash
cp .env.example .env
# Edit .env with your Telegram bot token and other settings
```

3. Install dependencies:
```bash
make install
```

## Configuration

Configure via `.env` file or environment variables:

| Variable               | Description                          | Default       |
|------------------------|--------------------------------------|---------------|
| `TELEGRAM_BOT_TOKEN`   | **Required** Bot authentication token| -             |
| `BOOKTOK_DB_PATH`      | Database file path                   | `booktok.db`  |
| `BOOKTOK_BOOKS_DIR`    | Directory containing book files      | `books`       |
| `BOOKTOK_LOG_LEVEL`    | Logging verbosity                    | `INFO`        |
| `BOOKTOK_LOG_FILE`     | Optional log file path               | -             |

## Usage

For detailed usage instructions, see [USER_GUIDE.md](USER_GUIDE.md)

### Running the Bot
```bash
make run
```

### Development Commands
```bash
make check      # Run all code quality checks
make test       # Run unit tests
make metrics    # Analyze code complexity and quality
make clean      # Remove build artifacts
```

### Deployment
1. Configure server access in Makefile
2. Deploy to production:
```bash
make deploy
make start
```

## Contributing

1. Create feature branch:
```bash
git checkout -b feature/new-feature
```

2. Implement changes with tests

3. Verify code quality:
```bash
make check
make test
```

4. Commit using [Conventional Commits](https://www.conventionalcommits.org/)
5. Create pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
