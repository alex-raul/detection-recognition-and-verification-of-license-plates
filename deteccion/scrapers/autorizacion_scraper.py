from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import re
import sys
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def scraper_autorizacion_circulacion(plate_number, timeout=60):
    """
    Consulta autorización de circulación para servicios de transporte en Puno
    
    Args:
        plate_number (str): Número de placa a consultar
        timeout (int): Timeout en segundos para la operación
    
    Returns:
        dict: Resultado estructurado con información de autorización
    """
    driver = None
    start_time = datetime.now()
    
    try:
        # Configurar driver
        driver = _setup_autorizacion_driver()
        
        logger.info(f"Autorizacion Scraper - Consultando placa: {plate_number}")
        
        # Verificar timeout
        if (datetime.now() - start_time).seconds > timeout:
            raise Exception("Timeout general alcanzado")
        
        # Ir a la página de consulta
        driver.get("https://papeletas.munipuno.gob.pe/licencias")
        
        # Buscar campo de entrada
        campo = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']"))
        )
        
        # Ingresar placa
        campo.clear()
        campo.send_keys(plate_number.upper())
        
        # Enviar formulario
        try:
            boton = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            boton.click()
        except:
            campo.send_keys("\n")
        
        # Esperar resultados
        time.sleep(3)
        
        # Obtener y procesar resultados
        html = driver.page_source
        datos = _extract_autorizacion_data(html)
        
        if datos:
            return {
                'success': True,
                'data': {
                    'tiene_autorizacion': True,
                    'numero_tarjeta': datos.get('tarjeta'),
                    'propietario': datos.get('propietario'),
                    'empresa': datos.get('empresa'),
                    'direccion': datos.get('direccion'),
                    'detalles_completos': datos
                },
                'raw_data': str(datos),
                'source': 'Municipalidad de Puno - Autorización de Circulación',
                'timestamp': datetime.now(),
                'plate_number': plate_number.upper(),
                'response_time': (datetime.now() - start_time).seconds
            }
        else:
            return {
                'success': True,
                'data': {
                    'tiene_autorizacion': False,
                    'mensaje': 'No se encontró autorización de circulación para esta placa'
                },
                'raw_data': 'Sin resultados',
                'source': 'Municipalidad de Puno - Autorización de Circulación',
                'timestamp': datetime.now(),
                'plate_number': plate_number.upper(),
                'response_time': (datetime.now() - start_time).seconds
            }
        
    except Exception as e:
        logger.error(f"Error en Autorizacion scraper: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'data': None,
            'source': 'Municipalidad de Puno - Autorización de Circulación',
            'timestamp': datetime.now(),
            'plate_number': plate_number.upper(),
            'response_time': (datetime.now() - start_time).seconds
        }
    
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


def _setup_autorizacion_driver():
    """Configura el driver de Chrome para consulta de autorización"""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--silent")
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Usar ChromeDriver sin webdriver_manager para evitar dependencias
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(10)
    return driver


def _extract_autorizacion_data(html):
    """Extrae los datos de autorización del HTML"""
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # Buscar el contenedor principal
        container = soup.find('div', {'data-v-706bd6df': True})
        
        if not container:
            # Buscar otros posibles contenedores
            container = soup.find('div', class_=re.compile(r'result|data|info'))
            
        if not container:
            return None
        
        texto = container.get_text(separator=' ', strip=True)
        
        # Si no hay contenido útil, no hay autorización
        if len(texto.strip()) < 10:
            return None
        
        # Extraer información específica
        datos = {}
        
        # Número de tarjeta (formato: LETRAS-NÚMEROS)
        match = re.search(r'([A-Z0-9]+-[0-9]+)', texto)
        if match:
            datos['tarjeta'] = match.group(1)
        
        # Propietario
        match = re.search(r'PROPIETARIO\s+([A-ZÁÉÍÓÚÑ\s]+?)(?=\s+EMPRESA|\s+DIRECCIÓN|$)', texto, re.IGNORECASE)
        if match:
            datos['propietario'] = match.group(1).strip()
        
        # Empresa
        match = re.search(r'EMPRESA\s+([A-ZÁÉÍÓÚÑ\s\.]+?)(?=\s+DIRECCIÓN|$)', texto, re.IGNORECASE)
        if match:
            datos['empresa'] = match.group(1).strip()
        
        # Dirección
        match = re.search(r'DIRECCIÓN\s+([A-ZÁÉÍÓÚÑ\s,\.0-9]+?)(?=\s|$)', texto, re.IGNORECASE)
        if match:
            datos['direccion'] = match.group(1).strip()
        
        # Si no se extrajo nada específico, pero hay texto, devolver el texto completo
        if not datos and texto.strip():
            datos['informacion_general'] = texto.strip()
        
        return datos if datos else None
        
    except Exception as e:
        logger.error(f"Error extrayendo datos de autorización: {e}")
        return None


def _clean_text(text):
    """Limpia y normaliza el texto extraído"""
    if not text:
        return None
    
    # Limpiar espacios múltiples y caracteres especiales
    text = re.sub(r'\s+', ' ', text.strip())
    text = text.replace('\n', ' ').replace('\t', ' ')
    
    return text if len(text.strip()) > 2 else None


# Función de prueba
def test_autorizacion_scraper():
    """Función de prueba para el scraper de autorización"""
    resultado = scraper_autorizacion_circulacion("X4O954")
    print("Resultado Autorización:")
    print(f"Éxito: {resultado['success']}")
    if resultado['success']:
        print("Datos:")
        if resultado['data']['tiene_autorizacion']:
            print(f"  Propietario: {resultado['data'].get('propietario', 'N/A')}")
            print(f"  Empresa: {resultado['data'].get('empresa', 'N/A')}")
            print(f"  Dirección: {resultado['data'].get('direccion', 'N/A')}")
            print(f"  Tarjeta: {resultado['data'].get('numero_tarjeta', 'N/A')}")
        else:
            print(f"  Mensaje: {resultado['data']['mensaje']}")
    else:
        print(f"Error: {resultado['error']}")
    
    return resultado