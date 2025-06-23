# weather_app/tests.py
from django.test import TestCase, Client
from django.contrib.auth.models import User
from unittest.mock import patch, MagicMock
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

    @patch('weather_app.views.requests.get')
    def test_index_view(self, mock_requests):
        """Test the main weather page loads - mocking external weather API"""
        # Mock the weather API response
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            'location': {'name': 'Cupertino', 'country': 'USA'},
            'current': {
                'temp_c': 22,
                'feelslike_c': 24,
                'condition': {'text': 'Sunny', 'icon': '//cdn.weatherapi.com/weather/64x64/day/113.png'},
                'humidity': 65,
                'pressure_mb': 1013,
                'wind_kph': 10
            }
        }
        mock_requests.return_value = mock_response
        
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
        
    @patch('weather_app.email_client.send_mail')
    def test_email_sending(self, mock_send_mail):
        """Test email sending logic - mocking Django's send_mail"""
        mock_send_mail.return_value = True
        
        api = EmailAPI()
        result = api.send_message(
            email_address='test@example.com',
            message='Test message',
            subject='Test Subject'
        )
        
        # Verify your email client called Django's send_mail
        mock_send_mail.assert_called_once()
        self.assertTrue(result['success'])

class ModelTestCase(TestCase):
    """Test models work correctly"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='modeltest',
            email='model@example.com',
            password='testpass123'
        )
    
    def test_email_message_str_method(self):
        """Test EmailMessage string representation"""
        message = EmailMessage.objects.create(
            user=self.user,
            message_type='morning_forecast',
            temperature=20.5,
            location='San Francisco',
            delivery_status='sent'
        )
        expected_str = f"{self.user.username} - morning_forecast - {message.timestamp}"
        self.assertEqual(str(message), expected_str)
    
    def test_celery_weather_request_str_method(self):
        """Test CeleryWeatherRequest string representation"""
        request = CeleryWeatherRequest.objects.create(
            user=self.user,
            location='New York',
            message_type='temp_alert',
            status='pending'
        )
        expected_str = f"{self.user.username} - New York - pending"
        self.assertEqual(str(request), expected_str)


