# dbot

## Installation

* On a typical system within a virtualenv, follow these steps in the project directory:

```sh
# Install packages
pip install poetry
poetry install --no-root

# Create DB schema
mkdir -p ~/.local/state
sqlite3 ~/.local/state/dbot.db <bot.sql

cp bot.example.toml ~/.config/dbot.toml
chmod 600 ~/.config/dbot.toml

# Edit the config you just copied and run the bot:
python bot.py
```
