# Weather Project

A production-ready Django weather application with advanced message queuing, intelligent caching, background task processing, and real-time notifications. Built with modern DevOps practices and deployed on Railway.

## Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Django App    │────│   PostgreSQL    │    │     Redis       │
│  (Web Server)   │    │  (Persistent)   │    │  (Multi-DB)     │
│                 │    │                 │    │  DB0: Cache     │
│                 │    │ • WeatherRequest│    │  DB1: Sessions  │
│                 │    │ • UserActivity  │    │  DB2: Celery    │
│                 │    │ • PopularCity   │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                                              │
         │              ┌─────────────────┐             │
         └──────────────│    RabbitMQ     │─────────────┘
                        │ (Multi-Queue)   │
                        │ • Digest Queue  │
                        │ • Priority Queue│
                        │ • Convert Queue │
                        │ • Send Queue    │
                        │ • Dead Letter   │
                        └─────────────────┘
                                 │
                   ┌─────────────────────────────────┐
                   │         Celery Workers          │
                   │ • Weather Fetcher (Beat)        │
                   │ • Temperature Alerts            │
                   │ • Email/SMS Notifications       │
                   │ • Cache Management              │
                   └─────────────────────────────────┘
```

## Key Features

### Intelligent Weather System
- **Real-time Weather Data** - WeatherAPI.com integration for current conditions
- **Smart Caching** - 5-minute TTL with Redis LRU eviction (256MB limit)
- **Temperature Alerts** - Automatic notifications for 5°+ temperature changes
- **Scheduled Forecasts** - Daily 6am Cupertino weather reports
- **Popular Cities Tracking** - Analytics for most requested locations

### Performance & Scaling
- **Rate Limiting** - 10 requests/minute per IP with visual indicators
- **Cache Hit Tracking** - "Fresh from API" vs "⚡ From Cache" labels
- **Multi-Database Redis** - Separated cache, sessions, and task storage
- **Priority Queuing** - High-priority alerts for significant temperature changes
- **Background Processing** - Non-blocking weather updates and notifications

### Notification System
- **Multi-Channel Alerts** - Email and SMS/WhatsApp integration
- **Fan-out Architecture** - Broadcast weather alerts to multiple users
- **Batched Delivery** - 60-second digest queues to optimize API calls
- **Rate-Limited Sending** - Respects WhatsApp 20 msg/min limits

### DevOps & Monitoring
- **Containerized Deployment** - Docker with Railway hosting
- **Multiple CI/CD Options** - GitHub Actions, GitLab CI, Circle CI, Travis CI, Jenkins
- **Redis Monitoring** - RedisInsight integration for cache analytics
- **Management Commands** - Cache sync, data cleanup, performance tuning

## Tech Stack

### Core Framework
- **Django 4.x** - Web framework with custom management commands
- **PostgreSQL** - Primary database for persistent weather history
- **Redis 7** - Multi-database caching and session management
- **RabbitMQ** - Message broker with priority and dead letter queues

### Background Processing
- **Celery Workers** - Distributed task processing
- **Celery Beat** - Scheduled task execution (6am forecasts, cleanup)
- **Windows Compatible** - `--pool=solo` for Windows development

### External Integrations
- **WeatherAPI.com** - Primary weather data source
- **Gmail SMTP** - Email notifications with app passwords
- **WhatsApp/SMS** - Mobile notification delivery

### DevOps & Infrastructure
- **Docker** - Containerization with Redis 7-alpine
- **Railway** - Cloud hosting platform
- **RedisInsight** - Cache monitoring and analytics
- **GitHub Actions** - CI/CD pipeline automation

## Quick Start

### Prerequisites
- Python 3.9+
- Docker Desktop
- WeatherAPI.com API key
- Gmail app password (for notifications)

### Local Development Setup

1. **Clone and Setup Environment**
   ```bash
   git clone <your-repo-url>
   cd weather_project
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Start Redis with Docker**
   ```bash
   # Start Redis with optimized configuration
   docker run -d --name weather-redis -p 6379:6379 \
     redis:7-alpine redis-server \
     --maxmemory 256mb \
     --maxmemory-policy allkeys-lru \
     --appendonly yes
   
   # Verify Redis is running
   docker exec weather-redis redis-cli ping
   ```

3. **Configure Environment**
   ```bash
   # Create .env file
   cp .env.example .env
   ```
   
   Update `.env` with your credentials:
   ```env
   # Weather API
   WEATHER_API_KEY=your_weatherapi_key_here
   
   # Database
   DATABASE_URL=postgresql://user:password@localhost:5432/weather_db
   
   # Redis (Docker)
   REDIS_URL=redis://localhost:6379/0
   
   # Email Notifications
   EMAIL_HOST_USER=your_email@gmail.com
   EMAIL_HOST_PASSWORD=your_app_password_here
   
   # RabbitMQ
   CELERY_BROKER_URL=amqp://guest:guest@localhost:5672//
   
   # Django
   SECRET_KEY=your-secret-key-here
   DEBUG=True
   ALLOWED_HOSTS=localhost,127.0.0.1
   ```

4. **Database Setup**
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

5. **Start All Services**
   ```bash
   # Terminal 1: RabbitMQ (if not using Docker)
   rabbitmq-server
   
   # Terminal 2: Celery Worker (Windows compatible)
   celery -A weather_project worker --pool=solo --loglevel=info
   
   # Terminal 3: Celery Beat Scheduler
   celery -A weather_project beat --loglevel=info
   
   # Terminal 4: Django Development Server
   python manage.py runserver
   ```

## Redis Configuration

### Multi-Database Setup
```python
# Redis Database Allocation
CACHES = {
    'default': {
        'LOCATION': 'redis://127.0.0.1:6379/0',  # Weather cache
    }
}

SESSIONS = {
    'LOCATION': 'redis://127.0.0.1:6379/1',      # Django sessions
}

CELERY_RESULT_BACKEND = 'redis://127.0.0.1:6379/2'  # Task results
```

### Cache Strategy
- **Weather Data**: 5-minute TTL with automatic refresh
- **Popular Cities**: 1-hour TTL with analytics tracking
- **Rate Limiting**: 1-minute TTL with IP-based blocking
- **Cache Stats**: 24-hour TTL with daily analytics

### Memory Management
```bash
# Configure Redis eviction policy
docker exec weather-redis redis-cli config set maxmemory-policy allkeys-lru

# Monitor memory usage
docker exec weather-redis redis-cli info memory
```

## Queue Architecture

### Message Flow Pipeline
```
Weather Request → Digest Queue (60s batch) → Temperature Check → Priority Router
                                              ↓
High Priority Alert → Immediate Send Queue → WhatsApp/Email
Low Priority Update → Scheduled Send Queue → Batched Delivery
Failed Messages → Dead Letter Queue → Manual Review
```

### Queue Types
- **Digest Queue**: Batches requests for 60 seconds to reduce API calls
- **Conversion Queue**: Handles temperature unit conversions
- **Priority Queue**: Routes urgent alerts (5°+ temperature changes)
- **Send Queue**: Final delivery with rate limiting (20 msg/min)
- **Dead Letter Queue**: Failed message handling and retry logic

## Testing Your Setup

### Cache Behavior
```bash
# Test cache indicators
1. Visit http://localhost:8000
2. First load: "Fresh from API" 
3. Refresh: " From Cache"
4. Wait 5+ minutes: "Fresh from API" (TTL expired)
```

### Rate Limiting
```bash
# Test rate limits
1. Click random city button rapidly
2. After 10 requests: Rate limit exceeded
3. Wait 1 minute: Rate limit resets
```

### Background Tasks
```bash
# Test Celery integration
python manage.py shell
>>> from weather_app.tasks import trigger_scheduled_weather
>>> trigger_scheduled_weather.delay()
```

### Management Commands
```bash
# Cache management
python manage.py manage_cache --show-stats
python manage.py manage_cache --clear-cache
python manage.py manage_cache --sync-db-cache

# Redis configuration
python manage.py redis_config --stats
```

## Monitoring & Analytics

### RedisInsight Setup
1. Download RedisInsight from Redis.io
2. Connect to `localhost:6379`
3. Monitor cache hit rates, memory usage, and key patterns

### Cache Analytics
- **Hit/Miss Ratios**: Track cache efficiency
- **Popular Cities**: Identify trending locations
- **Memory Usage**: Monitor Redis capacity
- **Eviction Events**: Track LRU cleanup behavior

### Performance Metrics
```bash
# View cache statistics
curl http://localhost:8000/cache-stats/

# Check Redis memory
docker exec weather-redis redis-cli info memory | findstr used_memory_human

# Monitor active keys
docker exec weather-redis redis-cli keys "weather:*"
```

## Deployment

### Railway Deployment
1. **Prepare for Production**
   ```bash
   # Collect static files
   python manage.py collectstatic --noinput
   
   # Run migrations
   python manage.py migrate --settings=weather_project.settings_production
   ```

2. **Environment Variables on Railway**
   ```env
   WEATHER_API_KEY=your_production_key
   DATABASE_URL=postgresql://...  # Railway PostgreSQL
   REDIS_URL=redis://...          # Railway Redis
   DJANGO_SETTINGS_MODULE=weather_project.settings_production
   ```

3. **Worker Configuration**
   ```bash
   # Procfile for Railway
   web: gunicorn weather_project.wsgi:application
   worker: celery -A weather_project worker --pool=solo
   beat: celery -A weather_project beat
   ```

### Docker Production Setup
```bash
# Build production image
docker build -t weather-app .

# Run with environment file
docker run -d --env-file .env.production weather-app
```

## Notification Setup

### Gmail Integration
1. Enable 2-factor authentication
2. Generate app password: Google Account → Security → App passwords
3. Use 16-character password in `EMAIL_HOST_PASSWORD`

### WhatsApp/SMS Setup
```python
# Configure in settings.py
TWILIO_ACCOUNT_SID = 'your_account_sid'
TWILIO_AUTH_TOKEN = 'your_auth_token'
WHATSAPP_FROM = 'whatsapp:+14155238886'  # Twilio sandbox
```

## Production Considerations

### Security
- Environment variables for all sensitive data
- Rate limiting to prevent API abuse
- CSRF protection and secure headers
- Database connection encryption

### Scalability
- Horizontal Celery worker scaling
- Redis cluster for high availability
- PostgreSQL read replicas
- CDN for static assets

### Monitoring
- Health check endpoints (`/health/`, `/health/db/`, `/health/redis/`)
- Error tracking and alerting
- Performance monitoring
- Queue length monitoring

## Troubleshooting

### Common Docker Issues
```bash
# Redis connection failed
docker ps | findstr weather-redis
docker logs weather-redis
docker restart weather-redis

# Port conflicts
netstat -an | findstr 6379
docker stop weather-redis
docker start weather-redis
```

### Celery Worker Issues
```bash
# Windows: Use solo pool
celery -A weather_project worker --pool=solo

# Check RabbitMQ connection
docker exec weather-redis redis-cli ping
```

### Cache Issues
```bash
# Clear all weather cache
python manage.py manage_cache --clear-cache

# Sync database and cache
python manage.py manage_cache --sync-db-cache

# Check Redis memory
docker exec weather-redis redis-cli info memory
```

## Project Structure

```
weather_project/
├── .github/workflows/
├── weather_project/
│   ├── settings.py           # Base configuration
│   ├── settings_ci.py        # CI-specific settings
│   ├── settings_production.py # Production config
│   ├── celery.py            # Celery configuration
│   └── urls.py
├── weather_app/
│   ├── models.py            # WeatherRequest, UserActivity, PopularCity
│   ├── views.py             # Weather display and API endpoints
│   ├── tasks.py             # Celery background tasks
│   ├── cache_manager.py     # Redis cache operations
│   ├── tests.py             # Test suite
│   └── management/commands/ # Custom Django commands
├── templates/
├── static/
├── requirements.txt
├── Dockerfile
├── Procfile                 # Railway deployment
└── README.md
```

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/queue-optimization`)
3. Test locally with full stack (Redis, RabbitMQ, Celery)
4. Ensure CI pipeline passes
5. Submit pull request

### Testing Guidelines
```bash
# Run full test suite
python manage.py test --settings=weather_project.settings_ci

# Test with Redis integration
python manage.py test weather_app.tests.CacheTestCase

# Load testing
python manage.py test weather_app.tests.RateLimitTestCase
```

## API Documentation

### Weather Endpoints
- `GET /` - Homepage with Cupertino weather
- `POST /random-weather/` - Get random city weather
- `GET /cache-stats/` - View cache analytics
- `GET /health/` - System health check

### Management Endpoints
- `POST /admin/cache/clear/` - Clear cache (admin only)
- `GET /admin/analytics/` - View system analytics
- `POST /admin/notify/` - Send test notifications

## Roadmap

- [ ] Kubernetes deployment manifests
- [ ] Prometheus metrics integration
- [ ] Weather forecast predictions (7-day)
- [ ] User subscriptions and preferences
- [ ] Advanced notification rules engine
- [ ] Multi-language support
- [ ] Weather data visualization charts

---

**Production URL**: [Your Railway deployment URL]
