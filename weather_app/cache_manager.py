# weather_app/cache_manager.py
# Service to handle database-cache coordination

import logging
from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import WeatherRequest, PopularCity, UserActivity
from datetime import datetime

logger = logging.getLogger(__name__)

class CacheManager:
    """
    Manages cache invalidation when database is updated
    Ensures consistency between PostgreSQL and Redis
    """
    
    @staticmethod
    def invalidate_weather_cache(city_name):
        """
        Invalidate weather cache for a specific city
        Call this when weather data becomes stale
        """
        cache_key = f"weather:{city_name.lower()}"
        result = cache.delete(cache_key)
        logger.info(f"Invalidated weather cache for {city_name}: {result}")
        return result
    
    @staticmethod
    def invalidate_popular_cities_cache():
        """
        Invalidate popular cities cache
        Call this when PopularCity model is updated
        """
        result = cache.delete("popular_cities")
        logger.info(f"Invalidated popular cities cache: {result}")
        return result
    
    @staticmethod
    def invalidate_cache_stats():
        """
        Clear cache statistics
        Call this for cache reset or testing
        """
        import redis
        from django.conf import settings
        
        try:
            redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                decode_responses=True
            )
            
            # Delete cache statistics keys
            today = datetime.now().strftime('%Y-%m-%d')
            keys_to_delete = [
                f"cache_hits:{today}",
                f"cache_misses:{today}"
            ]
            
            deleted_count = 0
            for key in keys_to_delete:
                if redis_client.delete(key):
                    deleted_count += 1
            
            logger.info(f"Cleared {deleted_count} cache statistics keys")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error clearing cache stats: {e}")
            return 0
    
    @staticmethod
    def invalidate_all_weather_cache():
        """
        Clear all weather cache entries
        Use for bulk cache refresh or testing
        """
        try:
            # Get all weather cache keys
            import redis
            from django.conf import settings
            
            redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=0,  # Weather cache DB
                decode_responses=True
            )
            
            # Find all weather cache keys
            weather_keys = redis_client.keys("weather_app:1:weather:*")
            
            if weather_keys:
                deleted_count = redis_client.delete(*weather_keys)
                logger.info(f"Cleared {deleted_count} weather cache entries")
                return deleted_count
            else:
                logger.info("No weather cache entries to clear")
                return 0
                
        except Exception as e:
            logger.error(f"Error clearing all weather cache: {e}")
            return 0
    
    '''@staticmethod
    def warm_cache_for_popular_cities():
        """
        Pre-populate cache with popular cities weather
        Call this after cache clearing or during maintenance
        """
        #from .tasks import preload_popular_cities_cache
        
        try:
            # Start async task to warm cache
            task = preload_popular_cities_cache.delay()
            logger.info(f"Started cache warming task: {task.id}")
            return task.id
            
        except Exception as e:
            logger.error(f"Error starting cache warming: {e}")
            return None
    '''
    @staticmethod
    def sync_database_to_cache():
        """
        Update cache to match current database state
        Use for ensuring consistency after database updates
        """
        try:
            # Refresh popular cities cache from database
            from .models import PopularCity
            
            popular_cities = list(
                PopularCity.objects.values('city', 'country', 'request_count')
                .order_by('-request_count')[:10]
            )
            
            # Update cache
            cache.set("popular_cities", popular_cities, 3600)  # 1 hour
            
            logger.info(f"Synced {len(popular_cities)} popular cities to cache")
            return len(popular_cities)
            
        except Exception as e:
            logger.error(f"Error syncing database to cache: {e}")
            return 0

# Django signals to auto-invalidate cache when database changes

@receiver(post_save, sender=PopularCity)
def invalidate_popular_cities_on_save(sender, instance, **kwargs):
   
   #Automatically invalidate popular cities cache when PopularCity is updated
   
   CacheManager.invalidate_popular_cities_cache()
   logger.info(f"Auto-invalidated popular cities cache due to {instance.city} update")

@receiver(post_delete, sender=PopularCity)
def invalidate_popular_cities_on_delete(sender, instance, **kwargs):
   
   # Automatically invalidate popular cities cache when PopularCity is deleted
   
   CacheManager.invalidate_popular_cities_cache()
   logger.info(f"Auto-invalidated popular cities cache due to {instance.city} deletion")


@receiver(post_save, sender=WeatherRequest)
def update_cache_stats_on_weather_save(sender, instance, **kwargs):
    """
    Update cache statistics when new weather request is saved
    """
    # This could trigger cache warming for frequently requested cities
    if instance.request_type == 'default':  # Cupertino requests
        # Consider pre-loading Cupertino weather if not cached
        cache_key = f"weather:{instance.city.lower()}"
        #if not cache.get(cache_key):
           #from .tasks import fetch_weather_async
            #fetch_weather_async.delay(instance.city, 'preload')

# Management functions for manual cache operations

def clear_all_caches():
    """
    Utility function to clear all application caches
    Use for testing or emergency cache reset
    """
    results = {
        'weather_cache': CacheManager.invalidate_all_weather_cache(),
        'popular_cities': CacheManager.invalidate_popular_cities_cache(),
        'cache_stats': CacheManager.invalidate_cache_stats(),
    }
    
    logger.info(f"Cache clearing results: {results}")
    return results

def refresh_all_caches():
    """
    Utility function to refresh all caches from database
    Use after bulk database updates
    """
    results = {
        'sync_popular_cities': CacheManager.sync_database_to_cache(),
        #'warm_weather_cache': CacheManager.warm_cache_for_popular_cities(),
    }
    
    logger.info(f"Cache refresh results: {results}")
    return results

