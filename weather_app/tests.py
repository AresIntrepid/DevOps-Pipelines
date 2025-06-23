import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'weather_project.settings')
django.setup()

from django.core.mail import send_mail
from django.conf import settings

# Create your tests here.

def test_email_sending():
    """Test if email sending works"""
    try:
        send_mail(
            subject='Test Email',
            message='This is a test email',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=['neilk0832@gmail.com'],
            fail_silently=False,
        )
        print("Email sent successfully!")
    except Exception as e:
        print(f"Email sending failed: {str(e)}")

if __name__ == '__main__':
    test_email_sending()



# weather_app/tests.py
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from .models import EmailMessage, CeleryWeatherRequest
from .email_client import EmailAPI

class WeatherAppTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_index_view(self):
        """Test the main weather page loads"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_dashboard_view(self):
        """Test dashboard loads"""
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)

    def test_dashboard_api(self):
        """Test dashboard API returns JSON"""
        response = self.client.get('/api/dashboard-stats/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_email_message_creation(self):
        """Test EmailMessage model"""
        message = EmailMessage.objects.create(
            user=self.user,
            message_type='test',
            temperature=25.0,
            location='Test City',
            delivery_status='sent'
        )
        self.assertEqual(message.user, self.user)
        self.assertEqual(message.temperature, 25.0)

    def test_celery_weather_request_creation(self):
        """Test CeleryWeatherRequest model""" 
        request = CeleryWeatherRequest.objects.create(
            user=self.user,
            location='Test City',
            message_type='test',
            status='pending'
        )
        self.assertEqual(request.user, self.user)
        self.assertEqual(request.status, 'pending')

class EmailClientTestCase(TestCase):
    def test_email_api_initialization(self):
        """Test EmailAPI can be initialized"""
        api = EmailAPI()
        self.assertIsInstance(api, EmailAPI)

