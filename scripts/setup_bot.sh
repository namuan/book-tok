cd $1 || exit
uv sync --no-dev
bash ./scripts/start_screen.sh tele-book-tok 'make run'
