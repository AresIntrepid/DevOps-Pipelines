# weather_app/management/commands/manage_cache.py
# Django management command for database-cache operations

from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.db import transaction
from weather_app.models import WeatherRequest, PopularCity, UserActivity
from weather_app.cache_manager import CacheManager, clear_all_caches, refresh_all_caches
import redis
from django.conf import settings
from datetime import datetime, timedelta

class Command(BaseCommand):
    help = 'Manage database and cache operations for weather app'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--clear-cache',
            action='store_true',
            help='Clear all Redis cache data'
        )
        parser.add_argument(
            '--refresh-cache',
            action='store_true',
            help='Refresh cache from database'
        )
        parser.add_argument(
            '--sync-db-cache',
            action='store_true',
            help='Ensure database and cache are synchronized'
        )
        parser.add_argument(
            '--clear-old-data',
            type=int,
            metavar='DAYS',
            help='Clear database records older than N days'
        )
        parser.add_argument(
            '--populate-test-data',
            action='store_true',
            help='Populate database with test data'
        )
        parser.add_argument(
            '--show-stats',
            action='store_true',
            help='Show database and cache statistics'
        )
        parser.add_argument(
            '--invalidate-city',
            type=str,
            metavar='CITY_NAME',
            help='Invalidate cache for specific city'
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🌤️  Weather App Database & Cache Manager'))
        self.stdout.write('=' * 60)
        
        if options['show_stats']:
            self.show_statistics()
        
        if options['clear_cache']:
            self.clear_all_cache()
        
        if options['refresh_cache']:
            self.refresh_cache()
        
        if options['sync_db_cache']:
            self.sync_database_cache()
        
        if options['clear_old_data']:
            self.clear_old_data(options['clear_old_data'])
        
        if options['populate_test_data']:
            self.populate_test_data()
        
        if options['invalidate_city']:
            self.invalidate_city_cache(options['invalidate_city'])
        
        if not any(options.values()):
            self.show_help()
    
    def show_statistics(self):
        """Show current database and cache statistics"""
        self.stdout.write('\n📊 Current Statistics:')
        self.stdout.write('-' * 40)
        
        try:
            # Database statistics
            weather_requests = WeatherRequest.objects.count()
            user_activities = UserActivity.objects.count()
            popular_cities = PopularCity.objects.count()
            
            self.stdout.write(f'Database Records:')
            self.stdout.write(f'  Weather Requests: {weather_requests:,}')
            self.stdout.write(f'  User Activities:  {user_activities:,}')
            self.stdout.write(f'  Popular Cities:   {popular_cities:,}')
            
            # Cache statistics
            redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=0,
                decode_responses=True
            )
            
            # Count different types of cache keys
            weather_keys = len(redis_client.keys("weather_app:1:weather:*"))
            rate_limit_keys = len(redis_client.keys("rate_limit:*"))
            cache_stat_keys = len(redis_client.keys("cache_*"))
            
            self.stdout.write(f'\nCache Entries:')
            self.stdout.write(f'  Weather Cache:    {weather_keys}')
            self.stdout.write(f'  Rate Limiting:    {rate_limit_keys}')
            self.stdout.write(f'  Cache Statistics: {cache_stat_keys}')
            
            # Memory usage
            memory_info = redis_client.info('memory')
            used_memory = memory_info.get('used_memory_human', 'Unknown')
            self.stdout.write(f'  Redis Memory:     {used_memory}')
            
            # Recent activity
            recent_requests = WeatherRequest.objects.filter(
                requested_at__gte=datetime.now() - timedelta(hours=24)
            ).count()
            self.stdout.write(f'\nRecent Activity (24h):')
            self.stdout.write(f'  Weather Requests: {recent_requests:,}')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error getting statistics: {e}'))
    
    def clear_all_cache(self):
        """Clear all application caches"""
        self.stdout.write('\n🗑️  Clearing All Caches:')
        self.stdout.write('-' * 30)
        
        try:
            results = clear_all_caches()
            
            for cache_type, count in results.items():
                if isinstance(count, int):
                    self.stdout.write(f'  {cache_type}: {count} entries cleared')
                else:
                    self.stdout.write(f'  {cache_type}: {count}')
            
            self.stdout.write(self.style.SUCCESS('✅ All caches cleared successfully'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error clearing caches: {e}'))
    
    def refresh_cache(self):
        """Refresh cache from database"""
        self.stdout.write('\n🔄 Refreshing Cache from Database:')
        self.stdout.write('-' * 40)
        
        try:
            results = refresh_all_caches()
            
            for operation, result in results.items():
                self.stdout.write(f'  {operation}: {result}')
            
            self.stdout.write(self.style.SUCCESS('✅ Cache refreshed successfully'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error refreshing cache: {e}'))
    
    def sync_database_cache(self):
        """Ensure database and cache are synchronized"""
        self.stdout.write('\n🔗 Synchronizing Database and Cache:')
        self.stdout.write('-' * 45)
        try:
        # Clear potentially stale cache
            self.stdout.write('1. Clearing stale cache...')
            CacheManager.invalidate_popular_cities_cache()
       
        # Sync from database
            self.stdout.write('2. Syncing from database...')
            synced_count = CacheManager.sync_database_to_cache()
       
            self.stdout.write(f'  Synced {synced_count} popular cities')
            self.stdout.write(self.style.SUCCESS('✅ Database and cache synchronized'))
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error synchronizing: {e}'))

    
    def clear_old_data(self, days):
        """Clear old database records"""
        self.stdout.write(f'\n🧹 Clearing Data Older Than {days} Days:')
        self.stdout.write('-' * 45)
        
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            with transaction.atomic():
                # Clear old weather requests
                old_weather = WeatherRequest.objects.filter(requested_at__lt=cutoff_date)
                weather_count = old_weather.count()
                old_weather.delete()
                
                # Clear old user activities
                old_activities = UserActivity.objects.filter(timestamp__lt=cutoff_date)
                activity_count = old_activities.count()
                old_activities.delete()
                
                self.stdout.write(f'  Deleted {weather_count:,} old weather requests')
                self.stdout.write(f'  Deleted {activity_count:,} old user activities')
                
                # Update cache to reflect changes
                CacheManager.invalidate_popular_cities_cache()
                CacheManager.sync_database_to_cache()
                
                self.stdout.write(self.style.SUCCESS(f'✅ Cleared {weather_count + activity_count:,} old records'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error clearing old data: {e}'))
    
    def populate_test_data(self):
        """Populate database with test data"""
        self.stdout.write('\n🧪 Populating Test Data:')
        self.stdout.write('-' * 30)
        
        try:
            # Create test popular cities
            test_cities = [
                ('London', 'United Kingdom', 150),
                ('Paris', 'France', 120),
                ('Tokyo', 'Japan', 100),
                ('New York', 'United States', 80),
                ('Sydney', 'Australia', 60),
            ]
            
            created_count = 0
            for city, country, count in test_cities:
                popular_city, created = PopularCity.objects.get_or_create(
                    city=city,
                    defaults={
                        'country': country,
                        'request_count': count,
                        'last_requested': datetime.now()
                    }
                )
                if created:
                    created_count += 1
                else:
                    # Update existing
                    popular_city.request_count = count
                    popular_city.save()
            
            self.stdout.write(f'  Created/Updated {len(test_cities)} popular cities')
            self.stdout.write(f'  New cities created: {created_count}')
            
            # Refresh cache with new data
            CacheManager.sync_database_to_cache()
            
            self.stdout.write(self.style.SUCCESS('✅ Test data populated successfully'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error populating test data: {e}'))
    
    def invalidate_city_cache(self, city_name):
        """Invalidate cache for specific city"""
        self.stdout.write(f'\n🎯 Invalidating Cache for {city_name}:')
        self.stdout.write('-' * 40)
        
        try:
            result = CacheManager.invalidate_weather_cache(city_name)
            
            if result:
                self.stdout.write(self.style.SUCCESS(f'✅ Cache cleared for {city_name}'))
            else:
                self.stdout.write(self.style.WARNING(f'⚠️  No cache found for {city_name}'))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error invalidating cache: {e}'))
    
    def show_help(self):
        """Show usage examples"""
        self.stdout.write('\n💡 Usage Examples:')
        self.stdout.write('-' * 20)
        self.stdout.write('python manage.py manage_cache --show-stats')
        self.stdout.write('python manage.py manage_cache --clear-cache')
        self.stdout.write('python manage.py manage_cache --refresh-cache')
        self.stdout.write('python manage.py manage_cache --sync-db-cache')
        self.stdout.write('python manage.py manage_cache --clear-old-data 30')
        self.stdout.write('python manage.py manage_cache --populate-test-data')
        self.stdout.write('python manage.py manage_cache --invalidate-city London')

