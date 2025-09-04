# deteccion/models.py
from django.db import models
from django.utils import timezone

class PlateDetection(models.Model):
    """Modelo para almacenar las detecciones de placas"""
    
    DETECTION_TYPES = [
        ('manual', 'Subida Manual'),
        ('camera', 'Cámara Web'),
        ('upload', 'Archivo Subido'),
        ('video', 'Video'),
        ('realtime', 'Tiempo Real'),
    ]
    
    DETECTION_METHODS = [
        ('Google Vision', 'Google Vision API'),
        ('EasyOCR', 'EasyOCR'),
        ('EasyOCR Pro', 'EasyOCR Procesada'),
        ('Ninguno', 'No Detectado'),
    ]
    
    plate_number = models.CharField(
        max_length=20, 
        verbose_name="Número de Placa",
        help_text="Número de placa detectado"
    )
    
    confidence = models.FloatField(
        verbose_name="Confianza",
        help_text="Nivel de confianza de la detección (0.0 - 1.0)"
    )
    
    detection_method = models.CharField(
        max_length=20,
        choices=DETECTION_METHODS,
        default='EasyOCR',
        verbose_name="Método de Detección"
    )
    
    detection_type = models.CharField(
        max_length=20,
        choices=DETECTION_TYPES,
        default='manual',
        verbose_name="Tipo de Detección"
    )
    
    image_path = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Ruta de Imagen",
        help_text="Ruta del archivo de imagen procesado"
    )
    
    created_at = models.DateTimeField(
        default=timezone.now,
        verbose_name="Fecha de Detección"
    )
    
    notes = models.TextField(
        blank=True,
        verbose_name="Notas",
        help_text="Notas adicionales sobre la detección"
    )
    
    is_verified = models.BooleanField(
        default=False,
        verbose_name="Verificado",
        help_text="Indica si la detección ha sido verificada manualmente"
    )
    
    class Meta:
        verbose_name = "Detección de Placa"
        verbose_name_plural = "Detecciones de Placas"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['plate_number']),
            models.Index(fields=['created_at']),
            models.Index(fields=['detection_type']),
        ]
    
    def __str__(self):
        return f"{self.plate_number} - {self.created_at.strftime('%d/%m/%Y %H:%M')}"
    
    def get_confidence_percentage(self):
        """Retorna la confianza como porcentaje"""
        return round(self.confidence * 100, 1)
    
    def get_confidence_color(self):
        """Retorna el color CSS basado en el nivel de confianza"""
        if self.confidence >= 0.8:
            return 'success'  # Verde
        elif self.confidence >= 0.6:
            return 'warning'  # Amarillo
        else:
            return 'danger'   # Rojo
    
    def get_type_icon(self):
        """Retorna el ícono basado en el tipo de detección"""
        icons = {
            'manual': 'fas fa-hand-pointer',
            'camera': 'fas fa-camera',
            'upload': 'fas fa-upload',
            'video': 'fas fa-video',
            'realtime': 'fas fa-broadcast-tower',
        }
        return icons.get(self.detection_type, 'fas fa-question')
    
    def get_method_color(self):
        """Retorna el color del método de detección"""
        colors = {
            'Google Vision': 'primary',
            'EasyOCR': 'info',
            'EasyOCR Pro': 'success',
            'Ninguno': 'secondary',
        }
        return colors.get(self.detection_method, 'secondary')

class VehicleAlert(models.Model):
    """Modelo para alertas de vehículos específicos"""
    
    ALERT_TYPES = [
        ('blacklist', 'Lista Negra'),
        ('whitelist', 'Lista Blanca'),
        ('stolen', 'Reportado como Robado'),
        ('expired', 'Documentos Vencidos'),
        ('custom', 'Personalizado'),
    ]
    
    plate_number = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Número de Placa"
    )
    
    alert_type = models.CharField(
        max_length=20,
        choices=ALERT_TYPES,
        verbose_name="Tipo de Alerta"
    )
    
    description = models.TextField(
        verbose_name="Descripción",
        help_text="Descripción de la alerta"
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo"
    )
    
    created_at = models.DateTimeField(
        default=timezone.now,
        verbose_name="Fecha de Creación"
    )
    
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de Expiración"
    )
    
    class Meta:
        verbose_name = "Alerta de Vehículo"
        verbose_name_plural = "Alertas de Vehículos"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.plate_number} - {self.get_alert_type_display()}"
    
    def is_expired(self):
        """Verifica si la alerta ha expirado"""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
    
    def get_alert_color(self):
        """Retorna el color CSS basado en el tipo de alerta"""
        colors = {
            'blacklist': 'danger',
            'whitelist': 'success',
            'stolen': 'danger',
            'expired': 'warning',
            'custom': 'info',
        }
        return colors.get(self.alert_type, 'info')

class DetectionStatistics(models.Model):
    """Modelo para estadísticas diarias de detecciones"""
    
    date = models.DateField(
        unique=True,
        verbose_name="Fecha"
    )
    
    total_detections = models.IntegerField(
        default=0,
        verbose_name="Total de Detecciones"
    )
    
    camera_detections = models.IntegerField(
        default=0,
        verbose_name="Detecciones por Cámara"
    )
    
    upload_detections = models.IntegerField(
        default=0,
        verbose_name="Detecciones por Subida"
    )
    
    video_detections = models.IntegerField(
        default=0,
        verbose_name="Detecciones por Video"
    )
    
    unique_plates = models.IntegerField(
        default=0,
        verbose_name="Placas Únicas"
    )
    
    avg_confidence = models.FloatField(
        default=0.0,
        verbose_name="Confianza Promedio"
    )
    
    alerts_triggered = models.IntegerField(
        default=0,
        verbose_name="Alertas Activadas"
    )
    
    class Meta:
        verbose_name = "Estadística de Detección"
        verbose_name_plural = "Estadísticas de Detecciones"
        ordering = ['-date']
    
    def __str__(self):
        return f"Estadísticas del {self.date.strftime('%d/%m/%Y')}"
    
    @classmethod
    def update_daily_stats(cls, date=None):
        """Actualiza las estadísticas diarias"""
        if date is None:
            date = timezone.now().date()
        detections = PlateDetection.objects.filter(created_at__date=date)
        
        stats, created = cls.objects.get_or_create(
            date=date,
            defaults={
                'total_detections': 0,
                'camera_detections': 0,
                'upload_detections': 0,
                'video_detections': 0,
                'unique_plates': 0,
                'avg_confidence': 0.0,
                'alerts_triggered': 0,
            }
        )
        
        # Calcular estadísticas
        stats.total_detections = detections.count()
        stats.camera_detections = detections.filter(detection_type='camera').count()
        stats.upload_detections = detections.filter(detection_type='upload').count()
        stats.video_detections = detections.filter(detection_type='video').count()
        stats.unique_plates = detections.values('plate_number').distinct().count()
        
        if stats.total_detections > 0:
            stats.avg_confidence = detections.aggregate(
                avg=models.Avg('confidence')
            )['avg'] or 0.0
        
        stats.save()
        return stats   
    
'''class Detection(models.Model):
    # ... campos existentes ...
    
    # Campos para edición (opcional)
    is_edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(blank=True, null=True)
    original_plate_number = models.CharField(max_length=20, blank=True, null=True)'''