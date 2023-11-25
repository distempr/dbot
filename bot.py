import shutil
import sqlite3
import tomllib

from datetime import datetime, UTC, timedelta

import boto3

from openai import OpenAI
from telegram import Update
from telegram.ext import Application, MessageHandler, filters


CHAT_SYSTEM_PROMPT = 'You are my personal bot. You prefer brief, to-the-point answers and help me with stupid questions.'
CHAT_TEMPERATURE = 1
CHAT_MODEL = 'gpt-4'


with open('bot.toml', 'rb') as f:
    config = tomllib.load(f)


chat_client = OpenAI(api_key=config['openai']['api_key'])

session = boto3.Session(profile_name=config['aws']['profile'])
ec2_resource = session.resource('ec2', region_name=config['aws']['region'])

con = sqlite3.connect('bot.db')
cur = con.cursor()


def chat_completion(prompt):
    messages = []
    messages.append(
        {'role': 'system', 'content': CHAT_SYSTEM_PROMPT}
    )

    cur.execute('SELECT role, content FROM (SELECT * FROM chat ORDER BY id DESC LIMIT 10) ORDER BY id ASC')
    rows = cur.fetchall()
    for message in rows:
        messages.append({'role': message[0], 'content': message[1]})

    messages.append(
        {'role': 'user', 'content': prompt}
    )

    response = chat_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        temperature=CHAT_TEMPERATURE
    )
    response = response.choices[0].message.content

    cur.execute('INSERT INTO chat (role, content) VALUES (?, ?)', ('user', prompt))
    cur.execute('INSERT INTO chat (role, content) VALUES (?, ?)', ('assistant', response))
    con.commit()

    return response


def get_ec2_instance_state(instance_id):
    return ec2_resource.Instance(instance_id).state['Name']


def get_disk_usage():
    du = shutil.disk_usage('/')
    return round((du.used / du.total) * 100, 1)


async def send_message(context, text):
    user_id = config['tg']['my_user_id']
    await context.bot.send_message(chat_id=user_id, text=text)


async def chat(update, context):
    from_user = update.message.from_user
    print(f'Received message from {from_user['username']}/{from_user['id']}')

    response = chat_completion(update.message.text)
    await update.message.reply_text(response)


async def ec2(context):
    result = cur.execute('SELECT id, name, state, notification_time FROM ec2')

    now = int(datetime.now(UTC).timestamp())

    for row in result.fetchall():
        id_, name, state, notification_time = row

        current_state = get_ec2_instance_state(id_)
        message = f'Instance {name} is {current_state}'

        if current_state != state:
            cur.execute('UPDATE ec2 SET state = ?, notification_time = ? WHERE id = ?', (current_state, now, id_))
            await send_message(context, message)
        elif current_state != 'stopped' and (now - notification_time) > (3600 * 8):
            cur.execute('UPDATE ec2 SET notification_time = ? WHERE id = ?', (now, id_))
            await send_message(context, message)
        
    con.commit()


async def du(context):
    usage = get_disk_usage()
    if usage >= config['du']['notify_at']:
        await send_message(context, f'Disk usage is at {usage}%')


def main():
    application = Application.builder().token(config['tg']['token']).build()

    user_id = config['tg']['my_user_id']
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Chat(user_id), chat))

    application.job_queue.run_repeating(ec2, 30)
    application.job_queue.run_repeating(du, config['du']['notify_every'])

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
