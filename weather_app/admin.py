from django.contrib import admin

# Register your models here.
from .models import WeatherRequest, PopularCity, UserActivity

# Register your models with the admin interface
@admin.register(PopularCity)
class PopularCityAdmin(admin.ModelAdmin):
    list_display = ('city', 'country', 'request_count', 'last_requested')
    list_filter = ('country', 'last_requested')
    search_fields = ('city', 'country')
    ordering = ('-request_count',)

@admin.register(WeatherRequest)  
class WeatherRequestAdmin(admin.ModelAdmin):
    list_display = ('city', 'country', 'temperature', 'requested_at', 'request_type')
    list_filter = ('country', 'request_type', 'requested_at')
    search_fields = ('city', 'country')
    ordering = ('-requested_at',)

@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ('session_key', 'ip_address', 'action', 'city_requested', 'timestamp')
    list_filter = ('action', 'timestamp')
    search_fields = ('ip_address', 'city_requested')
    ordering = ('-timestamp',)
