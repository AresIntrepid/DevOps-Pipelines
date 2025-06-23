# weather_app/views.py (Updated to save data to database)

import requests
import random
import time
import json
import redis
from datetime import datetime, timedelta
from django.utils import timezone
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.core.cache import cache
from django.db.models import F
from celery import current_app
from .models import WeatherRequest, UserActivity, PopularCity, EmailMessage, CeleryWeatherRequest
from django.contrib.auth.models import User

#Redis connection for rate limiting (seperate from django cache)
redis_client = redis.Redis(
    host = settings.REDIS_HOST,
    port = settings.REDIS_PORT,
    db = settings.REDIS_DB,
    decode_responses = True 
)

def get_client_ip(request):
    """Get the real IP address of the client"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def check_rate_limit(ip_address, max_requests=100, window_minutes=1):
    """
    check if IP adress hs exceeded rate limit
    returns (allowed: bool, requests_madeL int, time_until_reset: int)
    """
    key = f"rate_limit:{ip_address}"
    window_seconds = window_minutes * 60

    try:
        #Get current request count 
        current_requests = redis_client.get(key)

        if current_requests is None:
            #First request - set initial count
            redis_client.setex(key, window_seconds, 1)
            return True, 1, 0
        
        current_requests = int(current_requests)

        if current_requests >= max_requests:
            #rate limnit exceeded 
            ttl = redis_client.ttl(key)
            return False, current_requests, ttl
        
        #increment counter
        redis_client.incr(key)
        return True, current_requests + 1, 0
    
    except redis.RedisError:
        #If Redis is down, allow the request 
        return True, 0, 0


class WeatherService:
    """
    Enhanced weather service that saves all data to PostgreSQL database
    """
    
    def __init__(self, request=None):
        """Initialize with optional request for tracking"""
        self.api_key = settings.WEATHER_API_KEY
        self.base_url = "http://api.weatherapi.com/v1/current.json"
        self.request = request
        
        #cache timeouts (seconds)
        self.cache_timeout = 300 #5 minutes for weather data
        self.popular_cities_timeout = 3600 #1 hour for popular cities 

        # Predefined list of cities for random selection
        self.cities = [
            "New York", "London", "Tokyo", "Paris", "Sydney", "Berlin", "Toronto", 
            "Mumbai", "Dubai", "Singapore", "Amsterdam", "Barcelona", "Rome", 
            "Bangkok", "Seoul", "Buenos Aires", "Cairo", "Stockholm", "Vienna",
            "Prague", "Dublin", "Copenhagen", "Oslo", "Helsinki", "Warsaw",
            "Budapest", "Lisbon", "Madrid", "Brussels", "Zurich", "Mexico City",
            "São Paulo", "Rio de Janeiro", "Lima", "Santiago", "Bogotá",
            "Vancouver", "Montreal", "San Francisco", "Los Angeles", "Chicago",
            "Miami", "Seattle", "Boston", "Washington DC", "Atlanta"
        ]
    
    def get_weather_from_cache(self, city_name):
        """try to get weather data from redis cache"""
        cache_key = f"weather:{city_name.lower()}"
        cached_data = cache.get(cache_key)

        if cached_data:
            #add cache hit metric
            self.record_cache_hit(city_name, hit = True)
            return cached_data, True
        
        #record cache miss
        self.record_cache_hit(city_name, hit = False)
        return None, False
    
    def cache_weather_data(self, city_name, weather_data):
        """Store weather data in redis cache"""
        cache_key = f"weather:{city_name.lower()}"
        cache.set(cache_key, weather_data, self.cache_timeout)

    def record_cache_hit(self, city_name, hit = True):
        """Record cache hit/miss statistics"""
        today = datetime.now().strftime('%Y=%m-%d')
        hit_key = f"cache_hits:{today}"
        miss_key = f"cache_misses:{today}"

        try:
            if hit:
                redis_client.incr(hit_key)
                redis_client.expire(hit_key, 86400) #expire after 24 hours
            else:
                redis_client.incr(miss_key)
                redis_client.expire(hit_key, 86400)
        except redis.RedisError:
            pass #fail silently 

    
    def get_cache_stats(self):
        """Get cache hit/miss statistics"""
        today = datetime.now().strftime('%Y-%m-%d')
        try: 
            hits = int(redis_client.get(f"cache_hits:{today}")or 0)
            misses = int(redis_client.get(f"cache_misses:{today}")or 0)
            total = hits + misses
            hit_rate = (hits / total * 100) if total > 0 else 0

            return{
                'hits': hits,
                'misses': misses,
                'total': total,
                'hit_rate': round(hit_rate, 2)
            }
        except redis.RedisError:
            return {'hits': 0, 'misses': 0, 'total': 0, 'hit_rate': 0}
        
 
    def get_weather(self, city_name, request_type='default'):
        """
        Get weather data with redis and save to database
        
        Args:
            city_name (str): City to get weather for
            request_type (str): Type of request (default, random, search)
            
        Returns:
            dict: Weather data or error message
        """
        #first try to get data from cache
        cached_weather, from_cache = self.get_weather_from_cache(city_name)
        if from_cache:
            #add cache indidcaor to response
            cached_weather['from_cache'] = True
            cached_weather['cache_timestamp'] = cached_weather.get('timestamp', 'unkown')
            return cached_weather

        #fetch from api
        start_time = time.time()
        
        try:
            # Make API call
            url = f"{self.base_url}?key={self.api_key}&q={city_name}&aqi=no"
            response = requests.get(url, timeout=100)
            response.raise_for_status()
            data = response.json()
            
            # Calculate API response time
            api_response_time = time.time() - start_time
            
            # Format weather data
            weather_data = self.format_weather_data(data)
            weather_data['from_cache'] = False

            #cache the weather data
            self.cache_weather_data(city_name, weather_data)
            
            # Save to database
            self.save_weather_data(data, api_response_time, request_type)
            
            # Update popular cities count
            self.update_popular_city(data['location']['name'], data['location']['country'])
            
            return weather_data
            
        except requests.exceptions.RequestException as e:
            return {"error": f"Unable to fetch weather for {city_name}"}
        except Exception as e:
            return {"error": f"Error processing {city_name} weather data"}
        
    def get_popular_cities_from_cache(self):
        """get populr cities list from cache"""
        cache_key = "popular_cities"
        print(f"Looking for cache key: {cache_key}")  # DEBUG
    
        popular_cities = cache.get(cache_key)
        print(f"Cache.get result: {popular_cities}")  # DEBUG
        
        if not popular_cities:
            print("Cache miss - querying database...")  # DEBUG
            popular_cities = list(
                PopularCity.objects.values('city', 'country', 'request_count')
                .order_by('-request_count')[:10]
                )
        print(f"Database query result: {popular_cities}")  # DEBUG
        print(f"About to cache with timeout: {self.popular_cities_timeout}")  # DEBUG
        
        cache.set(cache_key, popular_cities, self.popular_cities_timeout)
        print("Cache.set completed")  # DEBUG
        
        # Test if it was actually saved
        test_get = cache.get(cache_key)
        print(f"Immediate cache test: {test_get}")  # DEBUG
        
        return popular_cities


    def save_weather_data(self, api_data, response_time, request_type):
        """Save weather data to database"""
        try:
            WeatherRequest.objects.create(
                city=api_data['location']['name'],
                country=api_data['location']['country'],
                temperature=api_data['current']['temp_c'],
                feels_like=api_data['current']['feelslike_c'],
                description=api_data['current']['condition']['text'],
                humidity=api_data['current']['humidity'],
                pressure=api_data['current']['pressure_mb'],
                wind_speed=api_data['current']['wind_kph'] * 0.277778,  # Convert to m/s
                api_response_time=response_time,
                request_type=request_type
            )
        except Exception as e:
            print(f"Error saving weather data: {e}")
    
    def update_popular_city(self, city, country):
        """Update or create popular city record and invalidate cache"""
        try:
            popular_city, created = PopularCity.objects.get_or_create(
                city=city,
                defaults={'country': country, 'request_count': 1}
            )
            if not created:
                # Increment count and update last requested time
                popular_city.request_count = F('request_count') + 1
                popular_city.last_requested = timezone.now()
                popular_city.save()

            #invalidate popular cities cache
           # cache.delete("popular_cities")

        except Exception as e:
            print(f"Error updating popular city: {e}")
    
    def log_user_activity(self, action, city_requested='', response_time=None):
        """Log user activity to database"""
        if not self.request:
            return
            
        try:
            # Get or create session key
            if not self.request.session.session_key:
                self.request.session.create()
            
            UserActivity.objects.create(
                session_key=self.request.session.session_key,
                ip_address=get_client_ip(self.request),
                user_agent=self.request.META.get('HTTP_USER_AGENT', '')[:500],  # Limit length
                action=action,
                city_requested=city_requested,
                response_time=response_time
            )
        except Exception as e:
            print(f"Error logging user activity: {e}")
    
    def format_weather_data(self, data):
        """Convert raw WeatherAPI.com response into clean, formatted data structure"""
        try:
            return {
                "city": data['location']['name'],
                "country": data['location']['country'],
                "temperature": round(data['current']['temp_c']),
                "feels_like": round(data['current']['feelslike_c']),
                "description": data['current']['condition']['text'],
                "humidity": data['current']['humidity'],
                "pressure": round(data['current']['pressure_mb']),
                "wind_speed": round(data['current']['wind_kph'] * 0.277778, 1),
                "icon": data['current']['condition']['icon'].replace('//', 'https://'),
                "timestamp": datetime.now().strftime('%H:%M:%S')
            }
        except KeyError:
            return {"error": "Error parsing weather data"}
    
    def get_random_cities_weather(self, count=4):
        """Get weather data for random cities with caching and save to database"""
        start_time = time.time()
        
        # Select random cities
        random_cities = random.sample(self.cities, count)
        weather_data = []
        
        # Fetch weather for each city
        for city in random_cities:
            weather = self.get_weather(city, request_type='random')
            weather_data.append(weather)
        
        # Log the user activity
        total_response_time = time.time() - start_time
        self.log_user_activity('random_weather', 
                             city_requested=', '.join(random_cities),
                             response_time=total_response_time)
        
        return weather_data

# Updated Django view functions (now with rate limiting)

def index(request):
    """Handle the home page request - shows Cupertino weather and logs activity"""
    start_time = time.time()

    #check rate limit
    ip_address = get_client_ip(request)
    allowed, requests_made, time_until_reset = check_rate_limit(ip_address, max_requests=10)

    if not allowed:
        context = {
            'default_weather': {
                'error': f'Rate limit exceeded. Try again in {time_until_reset} seconds.',
                'rate_limited': True
            }
        }
        return render(request, 'weather_app/index.html', context)

    # Create weather service with request for tracking
    weather_service = WeatherService(request)
    
    # Get Cupertino weather
    cupertino_weather = weather_service.get_weather("Cupertino", request_type='default')
    
    #popular citites key
    popular_cities = weather_service.get_popular_cities_from_cache()

    #rate limit info to context
    cupertino_weather['rate_limit_info'] = {
        'requests_made': requests_made,
        'requests_remaining': 100 - requests_made, 
        'window_mintues': 1
    }

    # Log page load activity
    response_time = time.time() - start_time
    weather_service.log_user_activity('page_load', 
                                    city_requested='Cupertino',
                                    response_time=response_time)
    
    context = {'default_weather': cupertino_weather}
    return render(request, 'weather_app/index.html', context)

@csrf_exempt
def get_random_weather(request):
    """API endpoint that returns weather for 4 random cities and saves to database"""
    if request.method == 'POST':
        #check rate limit
        ip_address = get_client_ip(request)
        allowed, requests_made, time_until_reset = check_rate_limit(ip_address, max_requests = 100)

        if not allowed:
            return JsonResponse({
                'error': f'Rate limit exceeded. Try agian in {time_until_reset} seconds.',
                'rate_limited': True,
                'time_until_reset': time_until_reset
            })

        weather_service = WeatherService(request)
        random_weather = weather_service.get_random_cities_weather(4)

        #add cache stats to repsonse
        cache_stats = weather_service.get_cache_stats()
        return JsonResponse({
            'cities': random_weather,
            'cache_stats': cache_stats,
            'rate_limit_info':{
                'reqeusts made': requests_made,
                'requests_remaining': 100 - requests_made
            }
        })
    
    return JsonResponse({"error": "Only POST method allowed"})

@csrf_exempt
def cache_stats(request):
    "API endpoing to get cache stats"
    weather_service = WeatherService()
    stats = weather_service.get_cache_stats()
    popular_cities = weather_service.get_popular_cities_from_cache()

    return JsonResponse({
        'cache_stats': stats,
        'popular_cities': popular_cities
    })



#DASHBOARD BACKEND
def dashboard_view(request):
    return render(request, 'weather_app/dashboard.html')

def dashboard_stats_api(request):
    """API endpoint for dashboard data"""
    today = timezone.now().date()
   
    # Message stats
    messages_today = EmailMessage.objects.filter(timestamp__date=today)
   
    stats = {
        'messages_sent': messages_today.filter(delivery_status='sent').count(),
        'messages_delivered': messages_today.filter(delivery_status='delivered').count(),
        'messages_failed': messages_today.filter(delivery_status='failed').count(),
        'messages_queued': messages_today.filter(delivery_status='queued').count(),
        'active_workers': get_active_workers_count(),
        'recent_messages': get_recent_messages(),
        'failed_messages': get_failed_messages(),
        'queue_stats': get_queue_stats()
    }
   
    return JsonResponse(stats)

def get_recent_messages():
    """Get last 20 messages"""
    messages = EmailMessage.objects.select_related('user').order_by('-timestamp')[:20]
    return [{
        'timestamp': msg.timestamp.strftime('%H:%M:%S'),
        'user_id': msg.user.id,
        'message_type': msg.message_type,
        'temperature': msg.temperature,
        'location': msg.location,
        'delivery_status': msg.delivery_status,
        'priority': msg.priority
    } for msg in messages]

def get_failed_messages():
    """Get messages that failed permanently"""
    failed = EmailMessage.objects.filter(
        delivery_status='failed',
        retry_count__gte=3
    ).order_by('-timestamp')[:10]
   
    return [{
        'id': msg.id,
        'timestamp': msg.timestamp.strftime('%H:%M:%S'),
        'user_id': msg.user.id,
        'email': msg.user.email,
        'retry_count': msg.retry_count,
        'error': 'Email sending timeout'
    } for msg in failed]

def get_queue_stats():
    """Get queue lengths"""
    inspect = current_app.control.inspect()
    reserved = inspect.reserved()
   
    return {
        'digest_queue': len(reserved.get('digest', [])) if reserved else 0,
        'conversion_queue': len(reserved.get('conversion', [])) if reserved else 0,
        'priority_queue': len(reserved.get('priority_sending', [])) if reserved else 0,
        'dead_letter': EmailMessage.objects.filter(
            delivery_status='failed',
            retry_count__gte=3
        ).count()
    }

def get_active_workers_count():
    """Check active Celery workers"""
    inspect = current_app.control.inspect()
    active_workers = inspect.active()
    return len(active_workers) if active_workers else 0


def get_worker_details():
    """Get detailed worker information"""
    inspect = current_app.control.inspect()
    active = inspect.active()
    stats = inspect.stats()
    
    if not active:
        return []
    
    workers = []
    for worker_name, tasks in active.items():
        worker_stats = stats.get(worker_name, {}) if stats else {}
        workers.append({
            'name': worker_name.split('@')[1] if '@' in worker_name else worker_name,
            'status': 'Online',
            'active_tasks': len(tasks),
            'total_tasks': worker_stats.get('total', {}).get('celery.backend_cleanup', 0),
            'pool': worker_stats.get('pool', {}).get('implementation', 'prefork'),
            'last_seen': 'Just now'
        })
    
    return workers

def get_queue_details():
    """Get detailed queue information"""
    inspect = current_app.control.inspect()
    reserved = inspect.reserved()
    scheduled = inspect.scheduled()
    
    queues = {
        'digest': {'pending': 0, 'processing': 0, 'scheduled': 0},
        'conversion': {'pending': 0, 'processing': 0, 'scheduled': 0},
        'formatting': {'pending': 0, 'processing': 0, 'scheduled': 0},
        'sending': {'pending': 0, 'processing': 0, 'scheduled': 0},
        'priority_sending': {'pending': 0, 'processing': 0, 'scheduled': 0},
        'dead_letter': {'pending': 0, 'processing': 0, 'scheduled': 0}
    }
    
    if reserved:
        for worker, tasks in reserved.items():
            for task in tasks:
                queue_name = task.get('delivery_info', {}).get('routing_key', 'unknown')
                if queue_name in queues:
                    queues[queue_name]['processing'] += 1
    
    if scheduled:
        for worker, tasks in scheduled.items():
            for task in tasks:
                queue_name = task.get('delivery_info', {}).get('routing_key', 'unknown')
                if queue_name in queues:
                    queues[queue_name]['scheduled'] += 1
    
    # Add dead letter count from database
    queues['dead_letter']['pending'] = EmailMessage.objects.filter(
        delivery_status='failed',
        retry_count__gte=3
    ).count()
    
    return queues

def get_system_health():
    """Check system component health"""
    health = {
        'rabbitmq': 'Unknown',
        'redis': 'Unknown',
        'database': 'Unknown',
        'celery_workers': 'Unknown'
    }
    
    # Check RabbitMQ
    try:
        inspect = current_app.control.inspect()
        if inspect.ping():
            health['rabbitmq'] = 'Connected'
        else:
            health['rabbitmq'] = 'Disconnected'
    except:
        health['rabbitmq'] = 'Error'
    
    # Check Redis
    try:
        import redis
        r = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB)
        if r.ping():
            health['redis'] = 'Connected'
        else:
            health['redis'] = 'Disconnected'
    except:
        health['redis'] = 'Error'
    
    # Check Database
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            health['database'] = 'Connected'
    except:
        health['database'] = 'Error'
    
    # Check Celery Workers
    worker_count = get_active_workers_count()
    if worker_count > 0:
        health['celery_workers'] = f'{worker_count} Active'
    else:
        health['celery_workers'] = 'No Workers'
    
    return health

def get_recent_activity():
    """Get recent system activity"""
    recent_emails = EmailMessage.objects.order_by('-timestamp')[:5]
    recent_requests = CeleryWeatherRequest.objects.order_by('-created_at')[:5]
    
    activity = []
    
    for email in recent_emails:
        activity.append({
            'time': email.timestamp.strftime('%H:%M:%S'),
            'type': 'Email',
            'action': f'{email.message_type} to {email.user.username}',
            'status': email.delivery_status
        })
    
    for request in recent_requests:
        activity.append({
            'time': request.created_at.strftime('%H:%M:%S'),
            'type': 'Task',
            'action': f'{request.message_type} for {request.location}',
            'status': request.status
        })
    
    # Sort by time and return latest 10
    return sorted(activity, key=lambda x: x['time'], reverse=True)[:10]

# Update your existing dashboard_stats_api function:
def dashboard_stats_api(request):
    """API endpoint for dashboard data"""
    today = timezone.now().date()
    
    # Message stats
    messages_today = EmailMessage.objects.filter(timestamp__date=today)
    
    stats = {
        'messages_sent': messages_today.filter(delivery_status='sent').count(),
        'messages_delivered': messages_today.filter(delivery_status='delivered').count(),
        'messages_failed': messages_today.filter(delivery_status='failed').count(),
        'messages_queued': messages_today.filter(delivery_status='queued').count(),
        'active_workers': get_active_workers_count(),
        'recent_messages': get_recent_messages(),
        'failed_messages': get_failed_messages(),
        'queue_stats': get_queue_stats(),
        
        # NEW: Add these dynamic data sources
        'worker_details': get_worker_details(),
        'queue_details': get_queue_details(),
        'system_health': get_system_health(),
        'recent_activity': get_recent_activity(),
        'total_users': User.objects.count(),
        'total_locations': CeleryWeatherRequest.objects.values('location').distinct().count(),
    }
    
    return JsonResponse(stats)

