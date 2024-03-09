import os
import platform
import shutil
import sqlite3
import tomllib

import boto3
import openai

from datetime import datetime, UTC, time
from pathlib import Path
from sqlite3 import Cursor, Connection

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, MessageHandler, filters, CommandHandler


config_home: Path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
state_home: Path = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
config_path: Path = config_home / "dbot.toml"
db_path: Path = state_home / "dbot" / "dbot.db"

with config_path.open("rb") as f:
    config = tomllib.load(f)

tg_user_id: int = config["tg"]["my_user_id"]
con: Connection = sqlite3.connect(db_path)

session = boto3.Session(profile_name=config["ec2"].get("profile", "default"))
ec2_resource = session.resource("ec2", region_name=config["ec2"]["region"])

chat_client = openai.OpenAI(api_key=config["chat"]["api_key"])


def populate_db() -> None:
    cur: Cursor = con.cursor()
    cur.execute("UPDATE ec2 SET active = 0")
    for name, id_ in config["ec2"].get("instances", {}).items():
        cur.execute("INSERT OR IGNORE INTO ec2 (name, id) VALUES (?, ?)", (name, id_))
        cur.execute("UPDATE ec2 SET active = 1, id = ? WHERE name = ?", (id_, name))

    con.commit()


def chat_completion(prompt: str) -> str:
    cur: Cursor = con.cursor()

    messages: list[dict] = []
    messages.append({"role": "system", "content": config["chat"]["system_prompt"]})

    cur.execute(
        "SELECT role, content FROM (SELECT * FROM chat ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
        (config["chat"]["context"],)
    )
    rows = cur.fetchall()
    for message in rows:
        messages.append({"role": message[0], "content": message[1]})

    messages.append({"role": "user", "content": prompt})

    response = chat_client.chat.completions.create(
        model=config["chat"]["model"],
        messages=messages,
        temperature=config["chat"]["temperature"],
    )
    response = response.choices[0].message.content

    cur.execute("INSERT INTO chat (role, content) VALUES (?, ?)", ("user", prompt))
    cur.execute(
        "INSERT INTO chat (role, content) VALUES (?, ?)", ("assistant", response)
    )
    con.commit()

    return response


def get_ec2_state(name: str) -> str:
    return ec2_resource.Instance(
        config["ec2"]["instances"][name]
    ).state["Name"]


def get_disk_usage() -> float:
    du = shutil.disk_usage("/")
    return round((du.used / du.total) * 100, 1)


async def send_message(context, text: str) -> None:
    await context.bot.send_message(tg_user_id, text, parse_mode=ParseMode.MARKDOWN_V2)


async def chat(update, context) -> None:
    from_user = update.message.from_user
    print(f"Received message from {from_user['username']}/{from_user['id']}")

    response = chat_completion(update.message.text)
    await update.message.reply_text(response)


async def ec2_check_state(context) -> None:
    cur: Cursor = con.cursor()
    result = cur.execute(
        "SELECT name, state, notification_time FROM ec2 WHERE active = 1"
    )

    now: int = int(datetime.now(UTC).timestamp())

    for row in result.fetchall():
        name, state, notification_time = row

        current_state: str = get_ec2_state(name)
        message: str = f"Instance `{name}` is {current_state}"

        if current_state != state:
            cur.execute(
                "UPDATE ec2 SET state = ?, notification_time = ? WHERE name = ?",
                (current_state, now, name),
            )
            await send_message(context, message)
        elif current_state != "stopped" and (now - notification_time) > (3600 * config["ec2"]["notify_every"]):
            cur.execute("UPDATE ec2 SET notification_time = ? WHERE name = ?", (now, name))
            await send_message(context, message)

    con.commit()


def toggle_ec2_state(name: str) -> None:
    now: int = int(datetime.now(UTC).timestamp())
    cur: Cursor = con.cursor()

    instance = ec2_resource.Instance(
        config["ec2"]["instances"][name]
    )
    state = instance.state["Name"]
    match state:
        case "stopped":
            instance.start()
        case "running":
            instance.stop()

    cur.execute("UPDATE ec2 SET last_toggled_time = ? WHERE name = ?", (now, name))
    con.commit()


async def ec2(update, context) -> None:
    not_found: bool = False

    for instance_name in context.args:
        if instance_name in config["ec2"]["instances"]:
            toggle_ec2_state(instance_name)
        else:
            not_found = True

    if not_found:
        await update.message.reply_text("One or more instances not found")


async def du(context) -> None:
    usage: float = get_disk_usage()
    if usage >= config["du"]["notify_at"]:
        await send_message(context, f"Disk usage is at {usage}%")


async def version(update, context) -> None:
    message: str = f"""OS: {platform.freedesktop_os_release()["PRETTY_NAME"]}
Python: {platform.python_version()}
PTB: {telegram.__version__}
Boto3: {boto3.__version__}
OpenAI: {openai.__version__}
"""

    await update.message.reply_text(message)


async def clean(context) -> None:
    print("Cleaning DB")

    cur: Cursor = con.cursor()
    cur.execute(
        "DELETE FROM chat WHERE id < (SELECT MAX(id) FROM chat) - ?",
        (config["chat"]["clean"],)
    )
    con.commit()


async def post_init(context) -> None:
    print("Application initialised")


if __name__ == "__main__":
    print("Bot started, populating DB and building application...")

    populate_db()
    application = Application \
        .builder() \
        .token(config["tg"]["token"]) \
        .post_init(post_init) \
        .build()

    application.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND
            & filters.Chat(tg_user_id),
            chat
        )
    )

    application.add_handler(
        CommandHandler(
            "ec2",
            ec2,
            filters=(
                filters.Chat(tg_user_id)
            )
        )
    )

    application.add_handler(CommandHandler("version", version))

    application.job_queue.run_repeating(ec2_check_state, config["ec2"]["check_every"])
    application.job_queue.run_repeating(
        du,
        config["du"]["notify_every"] * 3600
    )
    application.job_queue.run_daily(clean, time(hour=2))

    application.run_polling(
        allowed_updates=Update.MESSAGE,
        drop_pending_updates=True
    )
