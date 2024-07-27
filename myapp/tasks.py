from celery import shared_task
from django.core.management import call_command

@shared_task
def close_expired_sessions():
    call_command('close_expired_sessions')

@shared_task
def check_expired_sessions():
    call_command('check_expired_sessions')
