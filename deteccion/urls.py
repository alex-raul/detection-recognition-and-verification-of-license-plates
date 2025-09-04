
# deteccion/urls.py
from django.urls import path
from . import views

app_name = 'deteccion'

urlpatterns = [
    # Página principal de bienvenida
    path('', views.index, name='index'),
    
    # Sistema de control vehicular principal
    path('control/', views.control_vehicular, name='control_vehicular'),
    
    path('detection/<int:detection_id>/details/', views.detection_details, name='detection_details'),
    
    # APIs para funcionalidades AJAX
    path('api/upload/', views.upload_file, name='upload_file'),
    path('api/capture/', views.capture_photo, name='capture_photo'),
    path('api/detections/', views.get_detections_history, name='get_detections'),
    path('api/detections/<int:detection_id>/delete/', views.delete_detection, name='delete_detection'),
    path('api/detections/clear/', views.clear_all_detections, name='clear_detections'),
    path('api/detections/<int:detection_id>/edit/', views.edit_detection, name='edit_detection'),

    path('api/test-aap/', views.test_aap_scraper_view, name='test_aap_scraper'),
    path('detection/<int:detection_id>/search-aap/', views.search_aap_info, name='search_aap_info'),

    path('api/test-pit/', views.test_pit_scraper_view, name='test_pit_scraper'), 

    path('detection/<int:detection_id>/search-all/', views.search_all_vehicle_info, name='search_all_info'),

    path('api/test-sat/', views.test_sat_scraper_view, name='test_sat_scraper'),

    path('api/test-autorizacion/', views.test_autorizacion_scraper_view, name='test_autorizacion_scraper'),

    path('api/test-soat/', views.test_soat_scraper_view, name='test_soat_scraper'),
]