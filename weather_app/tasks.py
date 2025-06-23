# weather_app/tasks.py
from celery import shared_task
from django.utils import timezone
from django.contrib.auth.models import User
import redis
from .models import EmailMessage, WeatherRequest, DeadLetterMessage, CeleryWeatherRequest
from .email_client import email_api
from .views import WeatherService
from .utils import check_email_rate_limit
import logging

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

logger = logging.getLogger(__name__)

def get_weather_from_api(location):
    """Get weather data using existing WeatherService"""
    weather_service = WeatherService()
    return weather_service.get_weather(location)

def log_message_sent(user_id, message, priority, status):
    """Log message sending to database"""
    print(f"Message sent - User: {user_id}, Priority: {priority}, Status: {status}")

# DIGEST TASKS
@shared_task
def collect_weather_requests():
    """Runs every 60 seconds to batch requests"""
    pending_requests = CeleryWeatherRequest.objects.filter(status='pending')
    
    if pending_requests.exists():
        locations = pending_requests.values_list('location', flat=True).distinct()
        
        for location in locations:
            location_requests = list(pending_requests.filter(location=location).values())
            convert_temperature.delay(location, location_requests)

@shared_task
def trigger_scheduled_weather():
    """6 AM Cupertino forecast"""
    users = User.objects.filter(is_active=True)[:5]
    for user in users:
        CeleryWeatherRequest.objects.create(
            user=user,
            location='Cupertino',
            message_type='morning_forecast',
            priority='normal'
        )

# CONVERSION TASKS  
@shared_task
def convert_temperature(location, user_requests):
    """Convert Fahrenheit to Celsius + detect changes"""
    weather_data = get_weather_from_api(location)
    
    if 'error' in weather_data:
        return
    
    temp_c = weather_data.get('temperature', 0)
    
    # Check for temperature changes
    last_temp_key = f"last_temp:{location}"
    last_temp = redis_client.get(last_temp_key)
    temp_change = abs(temp_c - float(last_temp)) if last_temp else 0
    
    # Determine priority
    priority = 'high' if temp_change >= 5 else 'normal'
    
    # Update last temperature
    redis_client.set(last_temp_key, temp_c)
    
    # Send to formatting queue
    for request in user_requests:
        format_message.delay(
            request['user_id'],
            location,
            temp_c,
            temp_change,
            priority
        )

# FORMATTING TASKS
@shared_task
def format_message(user_id, location, temp_c, temp_change, priority):
    """Format message based on context"""
    try:
        user = User.objects.get(id=user_id)
        
        if temp_change >= 5:
            message = f"🚨 Temperature alert for {location}!\nChanged by {temp_change:.1f}°C\nCurrent: {temp_c:.1f}°C"
        else:
            message = f"🌤️ Weather update for {location}: {temp_c:.1f}°C"
        
        # Route to appropriate sending queue
        if priority == 'high':
            send_priority_message.delay(user.email, message, user_id, location, temp_c, 'temp_alert')
        else:
            send_message.apply_async(
                args=[user.email, message, user_id, location, temp_c, 'weather_update'],
                countdown=5
            )
    except User.DoesNotExist:
        print(f"User {user_id} not found")

# SENDING TASKS
@shared_task(bind=True, max_retries=3)
def send_message(self, email_address, message, user_id, location, temperature, message_type):
    logger.info(f"Starting send_message task for {email_address}")
    try:
        # Create DB record
        msg_record = EmailMessage.objects.create(
            user_id=user_id,
            message_type=message_type,
            temperature=temperature,
            location=location,
            delivery_status='queued',
            retry_count=self.request.retries
        )
        
        # Check rate limit
        if not check_email_rate_limit(email_address):
            logger.warning(f"Rate limit exceeded for {email_address}, retrying...")
            self.retry(countdown=30)
        
        # Send message
        subject = "🚨 Temperature Alert" if message_type == 'temp_alert' else "🌤️ Weather Update"
        logger.info(f"Sending email to {email_address} with subject: {subject}")
        
        try:
            result = email_api.send_message(email_address, message, subject)
            logger.info(f"Email sent successfully: {result}")
            
            # Update record
            msg_record.email_message_id = result.get('messages', [{}])[0].get('id', '')
            msg_record.delivery_status = 'sent'
            msg_record.save()
            
            return result
        except Exception as email_error:
            logger.error(f"Email sending failed: {str(email_error)}", exc_info=True)
            raise
        
    except Exception as exc:
        logger.error(f"Error in send_message: {exc}", exc_info=True)
        # Update retry count
        if 'msg_record' in locals():
            msg_record.retry_count = self.request.retries + 1
            msg_record.delivery_status = 'failed' if self.request.retries >= 2 else 'queued'
            msg_record.save()
        
        if self.request.retries >= self.max_retries:
            send_to_dead_letter.delay(email_address, message, user_id, str(exc))
            return
        self.retry(countdown=60 * (self.request.retries + 1), exc=exc)

@shared_task(bind=True, max_retries=3)
def send_priority_message(self, email_address, message, user_id, location, temperature, message_type):
    """High priority - immediate send"""
    try:
        subject = "🚨 URGENT: Temperature Alert"
        result = email_api.send_message(email_address, message, subject)
        log_message_sent(user_id, message, 'high_priority', 'sent')
        return result
    except Exception as exc:
        self.retry(countdown=60 * (self.request.retries + 1), exc=exc)

# DEAD LETTER TASKS
@shared_task
def send_to_dead_letter(email_address, message, user_id, error):
    """Handle permanently failed messages"""
    DeadLetterMessage.objects.create(
        user_id=user_id,
        phone_number=email_address,  # Storing email in phone_number field for compatibility
        message=message,
        error=error,
        failed_at=timezone.now()
    )
    
    send_admin_alert.delay(f"Message failed permanently: {error}")

@shared_task
def send_admin_alert(alert_message):
    """Send alert to admin"""
    print(f"ADMIN ALERT: {alert_message}")

@shared_task
def process_dead_letter_queue():
    """Retry dead letter messages after manual review"""
    reviewed_messages = DeadLetterMessage.objects.filter(status='retry_approved')
    
    for msg in reviewed_messages:
        send_message.delay(msg.phone_number, msg.message, msg.user_id, 'Unknown', 0, 'retry')
        msg.status = 'retried'
        msg.save()

@shared_task
def check_temperature_changes():
    """Check for temperature changes across all locations"""
    locations = ['Cupertino', 'San Francisco', 'New York', 'London']
    
    for location in locations:
        convert_temperature.delay(location, [])

 

