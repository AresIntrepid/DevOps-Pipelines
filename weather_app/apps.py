from django.apps import AppConfig


class WeatherAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'weather_app'

    def read(sself):
        #imoprt signals to audo invalidate cache
        import weather_app.cache_manager