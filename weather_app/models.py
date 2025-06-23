
# weather_app/models.py
# Database models to store weather data and user activity

from django.db import models
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import User


class WeatherRequest(models.Model):
    """
    Store every weather API request and response
    This helps us track usage and cache popular cities
    """
    # Basic location info
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
   
    # Weather data
    temperature = models.FloatField()
    feels_like = models.FloatField()
    description = models.CharField(max_length=200)
    humidity = models.IntegerField()
    pressure = models.FloatField()
    wind_speed = models.FloatField()
   
    # Metadata
    requested_at = models.DateTimeField(default=timezone.now)
    api_response_time = models.FloatField(help_text="API response time in seconds")
    request_type = models.CharField(
        max_length=20,
        choices=[
            ('default', 'Default Cupertino'),
            ('random', 'Random Cities'),
            ('search', 'User Search')  # For future features
        ],
        default='default'
    )
   
    class Meta:
        ordering = ['-requested_at']  # Most recent first
        indexes = [
            models.Index(fields=['city']),
            models.Index(fields=['requested_at']),
        ]
   
    def __str__(self):
        return f"{self.city}, {self.country} - {self.temperature}°C ({self.requested_at})"


class UserActivity(models.Model):
    """
    Track user interactions for analytics and rate limiting
    """
    # User identification (no login required)
    session_key = models.CharField(max_length=40)  # Django session key
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
   
    # Activity details
    action = models.CharField(
        max_length=50,
        choices=[
            ('page_load', 'Page Load'),
            ('random_weather', 'Random Weather Request'),
            ('search_weather', 'Search Weather Request'),
        ]
    )
    city_requested = models.CharField(max_length=100, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)
   
    # Performance tracking
    response_time = models.FloatField(null=True, blank=True, help_text="Total response time in seconds")
   
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['ip_address']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['session_key']),
        ]
   
    def __str__(self):
        return f"{self.action} from {self.ip_address} at {self.timestamp}"


class PopularCity(models.Model):
    """
    Track which cities are requested most often
    Useful for caching and analytics
    """
    city = models.CharField(max_length=100, unique=True)
    country = models.CharField(max_length=100)
    request_count = models.IntegerField(default=1)
    last_requested = models.DateTimeField(default=timezone.now)
   
    class Meta:
        ordering = ['-request_count']
        verbose_name_plural = "Popular Cities"
   
    def __str__(self):
        return f"{self.city}, {self.country} ({self.request_count} requests)"


# Email message logging in DB
class EmailMessage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message_type = models.CharField(max_length=50)  # 'morning_forecast', 'temp_alert'
    timestamp = models.DateTimeField(auto_now_add=True)
    temperature = models.FloatField()
    location = models.CharField(max_length=100)
    email_message_id = models.CharField(max_length=100, null=True, blank=True)
    delivery_status = models.CharField(max_length=20)  # 'queued', 'sent', 'delivered', 'failed'
    priority = models.CharField(max_length=10, default='normal')
    retry_count = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.user.username} - {self.message_type} - {self.timestamp}"


# NEW MODELS FOR CELERY TASKS
class CeleryWeatherRequest(models.Model):
    """
    For Celery task queue - different from API logging above
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    location = models.CharField(max_length=100)
    message_type = models.CharField(max_length=50)
    priority = models.CharField(max_length=10, default='normal')
    status = models.CharField(max_length=20, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.location} - {self.status}"


class DeadLetterMessage(models.Model):
    """
    For permanently failed Email messages
    """
    user_id = models.IntegerField()
    phone_number = models.CharField(max_length=100)  # Actually stores email, keeping field name for compatibility
    message = models.TextField()
    error = models.TextField()
    failed_at = models.DateTimeField()
    status = models.CharField(max_length=20, default='failed')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-failed_at']

    def __str__(self):
        return f"Failed message to {self.phone_number} at {self.failed_at}"

