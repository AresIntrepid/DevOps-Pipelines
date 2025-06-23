# weather_app/utils.py
import redis
from django.conf import settings

redis_client = redis.Redis(
    host=settings.REDIS_HOST, 
    port=settings.REDIS_PORT, 
    db=settings.REDIS_DB,
    decode_responses=True
)

# ORIGINAL function for views.py (IP rate limiting)
def check_rate_limit(ip_address, max_requests=100, window_minutes=1):
    """
    Check if IP address has exceeded rate limit
    Returns (allowed: bool, requests_made: int, time_until_reset: int)
    """
    key = f"rate_limit:{ip_address}"
    window_seconds = window_minutes * 60

    try:
        current_requests = redis_client.get(key)

        if current_requests is None:
            redis_client.setex(key, window_seconds, 1)
            return True, 1, 0
       
        current_requests = int(current_requests)

        if current_requests >= max_requests:
            ttl = redis_client.ttl(key)
            return False, current_requests, ttl
       
        redis_client.incr(key)
        return True, current_requests + 1, 0
   
    except redis.RedisError:
        return True, 0, 0

# NEW function for tasks.py (Email rate limiting)  
def check_email_rate_limit(email_address):
    """Email rate limiting - Returns True/False only"""
    key = f"email_rate_limit:{email_address}"
    
    try:
        current_count = redis_client.get(key) or 0
        if int(current_count) >= 500:
            return False
        
        redis_client.incr(key)
        redis_client.expire(key, 86400)  # 24 hours
        return True
        
    except Exception:
        return True  # Allow if Redis fails

