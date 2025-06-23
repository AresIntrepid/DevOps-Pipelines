# your_weather_project/celery.py
import os
from celery import Celery
from kombu import Queue, Exchange

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'weather_project.settings')

# Create Celery app
app = Celery('weather_project')

# Load Django settings with CELERY_ prefix
app.config_from_object('django.conf:settings', namespace='CELERY')

# Define exchanges
weather_exchange = Exchange('weather', type='direct')
priority_exchange = Exchange('priority', type='direct')

# Define task routes (corrected task names)
CELERY_TASK_ROUTES = {
    'weather_app.tasks.collect_weather_requests': {'queue': 'digest'},
    'weather_app.tasks.convert_temperature': {'queue': 'conversion'},
    'weather_app.tasks.format_message': {'queue': 'formatting'},
    'weather_app.tasks.send_message': {'queue': 'sending'},
    'weather_app.tasks.send_priority_message': {'queue': 'priority_sending'},
    'weather_app.tasks.trigger_scheduled_weather': {'queue': 'digest'},
    'weather_app.tasks.check_temperature_changes': {'queue': 'conversion'},
    'weather_app.tasks.process_dead_letter_queue': {'queue': 'dead_letter'},
    'weather_app.tasks.send_to_dead_letter': {'queue': 'dead_letter'},
}

# Define queues
CELERY_TASK_QUEUES = (
    Queue('digest', weather_exchange, routing_key='digest'),
    Queue('conversion', weather_exchange, routing_key='conversion'),
    Queue('formatting', weather_exchange, routing_key='formatting'),
    Queue('sending', weather_exchange, routing_key='sending'),
    Queue('priority_sending', priority_exchange, routing_key='priority'),
    Queue('dead_letter', weather_exchange, routing_key='dead_letter'),
)

# Apply configuration to the app
app.conf.task_routes = CELERY_TASK_ROUTES
app.conf.task_queues = CELERY_TASK_QUEUES

# Set queue priorities (optional)
app.conf.task_default_priority = 5
app.conf.worker_prefetch_multiplier = 1

# Automatically discover tasks from Django apps
app.autodiscover_tasks()

# Optional: Add some additional Celery settings
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='America/Los_Angeles',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=60,  # 1 minute
    worker_max_tasks_per_child=1000,
)

