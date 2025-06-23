# weather_app/email_client.py
from django.core.mail import send_mail
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class EmailAPI:
    def send_message(self, email_address, message, subject="🌤️ Weather Update"):
        """Send email message"""
        logger.info(f"Attempting to send email to {email_address} with subject: {subject}")
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email_address],
                fail_silently=False,
            )
            logger.info(f"Email sent successfully to {email_address}")
            return {"success": True, "messages": [{"id": "email_sent"}]}
        except Exception as e:
            logger.error(f"Email sending error: {str(e)}", exc_info=True)
            raise Exception(f"Email sending error: {str(e)}")

# Create instance
email_api = EmailAPI()


