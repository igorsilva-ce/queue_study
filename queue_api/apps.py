from django.apps import AppConfig


class QueueApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "queue_api"
    verbose_name = "Queue API & Celery Tasks"
