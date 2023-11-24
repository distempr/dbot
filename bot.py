import shutil
import sqlite3
import tomllib

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

session = boto3.Session(profile_name='ec2-basics')
ec2 = session.resource('ec2', region_name=config['aws']['region'])

con = sqlite3.connect('bot.db')
cur = con.cursor()


def chat_completion(prompt):
    messages = [
        {'role': 'system', 'content': CHAT_SYSTEM_PROMPT},
        {'role': 'user', 'content': prompt}
    ]

    response = chat_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        temperature=CHAT_TEMPERATURE
    )

    return response.choices[0].message.content


def get_ec2_instance_state(instance_id):
    return ec2.Instance(instance_id).state['Name']


def get_disk_usage():
    du = shutil.disk_usage('/')
    return round((du.used / du.total) * 100, 1)


async def send_message(context, text):
    user_id = config['tg']['my_user_id']
    await context.bot.send_message(chat_id=user_id, text=text)


async def chat(update, context):
    user_id = config['tg']['my_user_id']
    if update.message.from_user['id'] != user_id:
        print('Message not from myself')
        return None

    response = chat_completion(update.message.text)
    await update.message.reply_text(response)


async def ec2(context):
    # run some code and then if conditions are met...
    condition = False
    if condition:
        await send_message(context)


async def du(context):
    usage = get_disk_usage()
    if usage >= config['du']['notify_at']:
        await send_message(context, f'Disk usage is at {usage}%')


def main():
    application = Application.builder().token(config['tg']['token']).build()

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    application.job_queue.run_repeating(ec2, 60)
    application.job_queue.run_repeating(du, config['du']['notify_every'])

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
