# deteccion/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import PlateDetection, VehicleAlert, DetectionStatistics

@admin.register(PlateDetection)
class PlateDetectionAdmin(admin.ModelAdmin):
    list_display = [
        'plate_number', 
        'confidence_display', 
        'detection_method', 
        'detection_type', 
        'created_at',
        'verification_status'
    ]
    list_filter = [
        'detection_method', 
        'detection_type', 
        'is_verified', 
        'created_at'
    ]
    search_fields = ['plate_number']
    readonly_fields = ['created_at', 'confidence_display']
    date_hierarchy = 'created_at'
    list_per_page = 50
    
    fieldsets = (
        ('Información Principal', {
            'fields': ('plate_number', 'confidence', 'confidence_display')
        }),
        ('Detección', {
            'fields': ('detection_method', 'detection_type', 'image_path')
        }),
        ('Estado', {
            'fields': ('is_verified', 'notes')
        }),
        ('Metadatos', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def confidence_display(self, obj):
        """Muestra la confianza con color"""
        percentage = obj.get_confidence_percentage()
        color = obj.get_confidence_color()
        return format_html(
            '<span class="badge badge-{}">{:.1f}%</span>',
            color,
            percentage
        )
    confidence_display.short_description = 'Confianza'
    
    def verification_status(self, obj):
        """Muestra el estado de verificación"""
        if obj.is_verified:
            return format_html('<span style="color: green;">✓ Verificado</span>')
        else:
            return format_html('<span style="color: orange;">⏳ Pendiente</span>')
    verification_status.short_description = 'Estado'
    
    actions = ['mark_as_verified', 'mark_as_unverified']
    
    def mark_as_verified(self, request, queryset):
        """Marcar detecciones como verificadas"""
        updated = queryset.update(is_verified=True)
        self.message_user(
            request, 
            f'{updated} detección(es) marcada(s) como verificada(s).'
        )
    mark_as_verified.short_description = "Marcar como verificado"
    
    def mark_as_unverified(self, request, queryset):
        """Marcar detecciones como no verificadas"""
        updated = queryset.update(is_verified=False)
        self.message_user(
            request, 
            f'{updated} detección(es) marcada(s) como no verificada(s).'
        )
    mark_as_unverified.short_description = "Marcar como no verificado"

@admin.register(VehicleAlert)
class VehicleAlertAdmin(admin.ModelAdmin):
    list_display = [
        'plate_number', 
        'alert_type', 
        'alert_status',
        'is_active', 
        'created_at',
        'expires_at'
    ]
    list_filter = ['alert_type', 'is_active', 'created_at']
    search_fields = ['plate_number', 'description']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Información de la Placa', {
            'fields': ('plate_number', 'alert_type')
        }),
        ('Detalles de la Alerta', {
            'fields': ('description', 'is_active')
        }),
        ('Vigencia', {
            'fields': ('created_at', 'expires_at'),
            'classes': ('collapse',)
        }),
    )
    
    def alert_status(self, obj):
        """Muestra el estado de la alerta con color"""
        if not obj.is_active:
            return format_html('<span style="color: gray;">⚫ Inactiva</span>')
        elif obj.is_expired():
            return format_html('<span style="color: red;">🔴 Expirada</span>')
        else:
            color = obj.get_alert_color()
            return format_html('<span style="color: {};">🟢 Activa</span>', 
                             'red' if color == 'danger' else 'green')
    alert_status.short_description = 'Estado'

@admin.register(DetectionStatistics)
class DetectionStatisticsAdmin(admin.ModelAdmin):
    list_display = [
        'date', 
        'total_detections', 
        'unique_plates',
        'avg_confidence_display',
        'camera_detections',
        'upload_detections',
        'alerts_triggered'
    ]
    list_filter = ['date']
    date_hierarchy = 'date'
    readonly_fields = ['date']
    
    def avg_confidence_display(self, obj):
        """Muestra la confianza promedio formateada"""
        return f"{obj.avg_confidence:.1%}"
    avg_confidence_display.short_description = 'Confianza Promedio'
    
    def has_add_permission(self, request):
        """No permitir agregar estadísticas manualmente"""
        return False

# Configuraciones globales del admin
admin.site.site_header = "Control Vehicular - Administración"
admin.site.site_title = "Control Vehicular"
admin.site.index_title = "Panel de Administración"