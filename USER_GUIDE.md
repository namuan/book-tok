# BookTok User Guide - Book Selection

## Quick Start

### 1. Setup Your Profile
```
/start
```
Creates your BookTok profile and welcomes you to the bot.

### 2. Browse Available Books
```
/books
```
Shows a list of all available books with interactive buttons.

**You'll see:**
- Book titles
- File type (PDF or EPUB)
- File size
- Clickable buttons to select each book

### 3. Select a Book
Click any book button from the list.

**What happens:**
- ⏳ Bot shows "Processing..." message
- 📖 Bot extracts text and generates snippets (first time only)
- ✅ Bot confirms selection with snippet count
- 📍 Shows your starting position

**Processing time:**
- **First time**: 5-30 seconds (depending on book size)
- **Already processed**: Instant

### 4. Start Reading
```
/next
```
Get the next snippet from your selected book.

**Each snippet includes:**
- Book title and author (if available)
- Your progress (e.g., "Snippet 5/150")
- Content (optimized for mobile reading)
- Progress bar

## Common Tasks

### Switch to a Different Book
1. Run `/books` again
2. Click a different book button
3. Your progress resets to the beginning of the new book
4. Start reading with `/next`

**Note:** Your progress on the previous book is saved but becomes inactive.

### Re-start the Same Book
1. Run `/books`
2. Click the same book you're reading
3. Your progress resets to the beginning
4. Confirmation message shows you're starting from position 1

### Continue Reading
```
/next
```
Delivers the next snippet in sequence from your active book.

### Pause Automatic Delivery
```
/pause
```
Stops scheduled snippet deliveries. You can still use `/next` manually.

### Resume Automatic Delivery
```
/resume
```
Restarts scheduled snippet deliveries.

## Understanding Book Status

### "Processing Book..."
- Bot is extracting text from the PDF/EPUB
- Generating bite-sized snippets
- Saving to database
- Usually takes 5-30 seconds

### "Book Selected ✅"
- Book is ready to read
- Shows total snippet count
- Shows your current position
- You can start with `/next`

### "Book Not Found ❌"
- The book file was removed from the directory
- Use `/books` to see current available books
- Contact administrator if this is unexpected

## Tips & Best Practices

### 1. Browse Before Selecting
- Review all available books with `/books`
- Check file sizes (larger = more snippets)
- Note the file type if you have a preference

### 2. One Book at a Time
- Only one book can be "active" for reading
- Switching books starts the new one from the beginning
- Your old progress is preserved but inactive

### 3. Patient During First Load
- First-time processing can take 30+ seconds for large books
- Subsequent selections are instant (cached)
- Other users benefit from your initial processing

### 4. Regular Reading
- Use `/next` to get one snippet at a time
- Set up automatic delivery (coming soon) for scheduled reading
- Track your progress with each snippet

## Example Session

```
User: /start
Bot: 📚 Welcome to BookTok!
     I'm your personal reading companion...

User: /books
Bot: 📚 Available Books
     Found 3 book(s):
     Select a book to start reading:

     1. Python Programming Basics
        📊 PDF | 2.3 MB
     [Button: 1. Python Programming Basics]

     2. Learning Django
        📊 EPUB | 1.8 MB
     [Button: 2. Learning Django]

     3. Advanced Algorithms
        📊 PDF | 5.1 MB
     [Button: 3. Advanced Algorithms]

User: *clicks "1. Python Programming Basics"*
Bot: ⏳ Processing Book
     Selected: Python Programming Basics
     Processing the book and generating snippets...
     This may take a moment.

     [Processing...]

     ✅ Book Selected
     Python Programming Basics

     📚 Total snippets: 150
     📍 Your position: 1/150

     Use /next to start reading!

User: /next
Bot: 📖 Python Programming Basics

     Snippet 1/150 (1%)
     ━━━━━━━━━━━━━━━━━━━━

     [Snippet content here...]

     ▓░░░░░░░░░░░░░░░░░░░ 1%

User: /next
Bot: 📖 Python Programming Basics

     Snippet 2/150 (1%)
     ━━━━━━━━━━━━━━━━━━━━

     [Next snippet content...]

     ▓░░░░░░░░░░░░░░░░░░░ 1%
```

## Troubleshooting

### "Please use /start first to create your profile"
**Solution:** Run `/start` to create your profile before selecting books.

### "No Books Available"
**Possible causes:**
- Books directory is empty
- No PDF or EPUB files in the directory
- Configuration issue

**Solution:** Contact the administrator to add books.

### "Processing Failed"
**Possible causes:**
- Corrupted PDF/EPUB file
- File is encrypted or password-protected
- Unsupported PDF/EPUB format

**Solution:**
- Try a different book
- Contact administrator about the problematic file

### "Book Not Found"
**Possible causes:**
- Book file was deleted from the directory
- File was renamed or moved

**Solution:**
- Run `/books` to see current available books
- Contact administrator if the book should be available

## Need Help?

### Available Commands
```
/start  - Create your profile
/help   - See all commands
/books  - Browse and select books
/next   - Get next snippet
/pause  - Pause deliveries
/resume - Resume deliveries
```

### Getting Support
- Send any message to the bot for assistance
- Check `/help` for command reference
- Review this guide for common questions

## Coming Soon

- 📅 Scheduled snippet delivery
- 📊 Reading progress dashboard
- 🎯 Reading goals and streaks
- 🔖 Bookmarks and highlights
- 📈 Reading statistics
- 🔍 Book search and filtering

Happy reading! 📚
