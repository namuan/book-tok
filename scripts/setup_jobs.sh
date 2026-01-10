cd $1 || exit
uv sync --no-dev
bash ./scripts/start_screen.sh tele-spy-alert-bot 'make run'
