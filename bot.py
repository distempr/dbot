import shutil
import sqlite3
import tomllib

import boto3

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes


with open('bot.toml', 'rb') as f:
    config = tomllib.load(f)

session = boto3.Session(profile_name='ec2-basics')
ec2 = session.resource('ec2', region_name=config['aws']['region'])

con = sqlite3.connect('bot.db')
cur = con.cursor()


def get_ec2_instance_state(instance_id):
    return ec2.Instance(instance_id).state['Name']


def get_disk_usage():
    du = shutil.disk_usage('/')
    return round((du.used / du.total) * 100, 1)


async def send_message(context, text):
    user_id = config['tg']['my_user_id']
    await context.bot.send_message(chat_id=user_id, text=text)


async def ec2(context):
    print('hello world')
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

    application.job_queue.run_repeating(ec2, 60)
    application.job_queue.run_repeating(du, config['du']['notify_every'])

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
