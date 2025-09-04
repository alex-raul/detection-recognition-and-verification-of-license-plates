# deteccion/apps.py
from django.apps import AppConfig

class DeteccionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'deteccion'
    verbose_name = 'Sistema de Detección de Placas'
    
    def ready(self):
        """Código que se ejecuta cuando la app está lista"""
        # Aquí puedes agregar signals o configuraciones adicionales
        pass