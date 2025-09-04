from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def run_all_scrapers(plate_number):
    """Ejecuta AAP y PIT en paralelo"""
    start_time = datetime.now()
    
    # Importar scrapers
    #from .aap_scraper import scraper_aap_vehiculo_test  # Usar la versión de prueba por ahora
    from .aap_scraper import scraper_aap_vehiculo
    from .pit_scraper import scraper_pit_papeletas
    
    results = {}
    
    # Ejecutar en paralelo
    with ThreadPoolExecutor(max_workers=2) as executor:
        # Enviar ambas tareas
        future_aap = executor.submit(scraper_aap_vehiculo, plate_number)
        future_pit = executor.submit(scraper_pit_papeletas, plate_number)
        
        # Recoger resultados
        try:
            results['aap'] = future_aap.result(timeout=30)  # AAP es rápido (simulado)
            logger.info("AAP completado")
        except Exception as e:
            results['aap'] = {
                'success': False,
                'error': str(e),
                'source': 'AAP (Asociación Automotriz del Perú)'
            }
        
        try:
            results['pit'] = future_pit.result(timeout=180)  # PIT puede tardar más
            logger.info("PIT completado")
        except Exception as e:
            results['pit'] = {
                'success': False,
                'error': str(e),
                'source': 'PIT (Policía de Tránsito)'
            }
    
    # Estadísticas
    total_time = (datetime.now() - start_time).seconds
    successful = sum(1 for r in results.values() if r.get('success', False))
    
    return {
        'success': True,
        'plate_number': plate_number.upper(),
        'results': results,
        'summary': {
            'total_scrapers': 2,
            'successful_scrapers': successful,
            'failed_scrapers': 2 - successful,
            'total_time_seconds': total_time
        },
        'timestamp': datetime.now().isoformat()
    }