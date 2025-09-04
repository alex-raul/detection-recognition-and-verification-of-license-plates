import time
import requests
import base64
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from PIL import Image
import io
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def scraper_sat_captura(plate_number, api_key_2captcha='', timeout=120):
    """
    Consulta órdenes de captura vehicular en SAT Perú
    
    Args:
        plate_number (str): Número de placa a consultar
        api_key_2captcha (str): API key para resolver captchas
        timeout (int): Timeout en segundos para la operación
    
    Returns:
        dict: Resultado estructurado con información de órdenes de captura
    """
    driver = None
    start_time = datetime.now()
    
    try:
        # Configurar driver
        driver = _setup_sat_driver()
        url = "https://www.sat.gob.pe/VirtualSAT/modulos/Capturas.aspx"
        
        logger.info(f"SAT Scraper - Consultando placa: {plate_number}")
        
        # Abrir la página
        driver.get(url)
        wait = WebDriverWait(driver, 10)
        
        # Verificar timeout
        if (datetime.now() - start_time).seconds > timeout:
            raise Exception("Timeout general alcanzado")
        
        # Ingresar la placa
        placa_input = wait.until(EC.presence_of_element_located((By.NAME, "ctl00$cplPrincipal$txtPlaca")))
        placa_input.clear()
        placa_input.send_keys(plate_number.upper())
        
        # Esperar que cargue el CAPTCHA
        time.sleep(5)
        
        # Obtener y resolver CAPTCHA
        captcha_base64 = _get_captcha_image(driver)
        if not captcha_base64:
            raise Exception("No se pudo obtener la imagen del CAPTCHA")
        
        captcha_solution = _solve_captcha_2captcha(captcha_base64, api_key_2captcha)
        if not captcha_solution:
            raise Exception("No se pudo resolver el CAPTCHA")
        
        # Ingresar solución del CAPTCHA
        captcha_input = driver.find_element(By.NAME, "ctl00$cplPrincipal$txtCaptcha")
        captcha_input.clear()
        captcha_input.send_keys(captcha_solution)
        
        # Esperar antes de hacer clic en buscar
        time.sleep(3)
        
        # Hacer clic en el botón buscar
        search_button = driver.find_element(By.XPATH, "//input[@value='Buscar' or @value='BUSCAR']")
        search_button.click()
        
        # Esperar resultados
        time.sleep(5)
        
        # Obtener y procesar resultados
        resultado = _extract_sat_results(driver)
        
        # Analizar el resultado
        tiene_orden = _analyze_capture_result(resultado)
        
        return {
            'success': True,
            'data': {
                'estado_captura': resultado,
                'tiene_orden_captura': tiene_orden,
                'provincia': _extract_province(resultado),
                'fecha_actualizacion': _extract_update_date(resultado),
                'detalle_completo': resultado
            },
            'raw_data': resultado,
            'source': 'SAT (Servicio de Administración Tributaria)',
            'timestamp': datetime.now(),
            'plate_number': plate_number.upper(),
            'response_time': (datetime.now() - start_time).seconds
        }
        
    except Exception as e:
        logger.error(f"Error en SAT scraper: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'data': None,
            'source': 'SAT (Servicio de Administración Tributaria)',
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


def _setup_sat_driver():
    """Configura el driver de Chrome para SAT"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--log-level=3")
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def _get_captcha_image(driver):
    """Obtiene la imagen del CAPTCHA"""
    try:
        captcha_img = driver.find_element(By.XPATH, "//img[contains(@class, 'captcha')]")
        captcha_screenshot = captcha_img.screenshot_as_png
        captcha_base64 = base64.b64encode(captcha_screenshot).decode('utf-8')
        return captcha_base64
    except Exception as e:
        logger.error(f"Error obteniendo imagen CAPTCHA: {e}")
        return None


def _solve_captcha_2captcha(captcha_image_base64, api_key):
    """Resuelve el CAPTCHA usando 2captcha"""
    try:
        # Enviar CAPTCHA
        submit_url = "http://2captcha.com/in.php"
        submit_data = {
            'method': 'base64',
            'key': api_key,
            'body': captcha_image_base64,
            'numeric': '2',  # 2 = letras y números
            'min_len': '4',
            'max_len': '4'
        }
        
        response = requests.post(submit_url, data=submit_data, timeout=30)
        
        if response.text.startswith('OK|'):
            captcha_id = response.text.split('|')[1]
            logger.info(f"CAPTCHA SAT enviado con ID: {captcha_id}")
        else:
            raise Exception(f"Error enviando CAPTCHA: {response.text}")
        
        # Esperar resultado
        result_url = "http://2captcha.com/res.php"
        max_attempts = 30
        
        for attempt in range(max_attempts):
            time.sleep(5)
            
            result_data = {
                'key': api_key,
                'action': 'get',
                'id': captcha_id
            }
            
            try:
                response = requests.get(result_url, params=result_data, timeout=10)
                
                if response.text == 'CAPCHA_NOT_READY':
                    if attempt % 6 == 0:
                        logger.info(f"Esperando CAPTCHA SAT... ({attempt * 5}s)")
                    continue
                elif response.text.startswith('OK|'):
                    captcha_solution = response.text.split('|')[1]
                    logger.info("CAPTCHA SAT resuelto exitosamente!")
                    return captcha_solution
                else:
                    logger.warning(f"Respuesta inesperada SAT: {response.text}")
                    continue
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Error de conexión SAT en intento {attempt + 1}: {e}")
                continue
        
        raise Exception("Timeout esperando solución del CAPTCHA SAT")
        
    except Exception as e:
        raise Exception(f"Error resolviendo CAPTCHA SAT: {e}")


def _extract_sat_results(driver):
    """Extrae los resultados del SAT"""
    try:
        page_content = driver.find_element(By.TAG_NAME, "body").text
        lines = page_content.split('\n')
        
        result_lines = []
        for line in lines:
            line = line.strip()
            # Buscar líneas que contengan información relevante
            if ("no tiene orden de captura" in line.lower() or 
                "tiene orden de captura" in line.lower() or
                "informe actualizado" in line.lower() or
                "el vehículo de placa" in line.lower() or
                "provincia de" in line.lower()):
                result_lines.append(line)
        
        if result_lines:
            return '\n'.join(result_lines)
        else:
            return "No se encontró información específica sobre órdenes de captura"
            
    except Exception as e:
        logger.error(f"Error obteniendo resultados SAT: {e}")
        return f"Error extrayendo resultados: {str(e)}"


def _analyze_capture_result(resultado):
    """Analiza si el vehículo tiene orden de captura"""
    if not resultado:
        return None
    
    resultado_lower = resultado.lower()
    
    if "no tiene orden de captura" in resultado_lower:
        return False
    elif "tiene orden de captura" in resultado_lower:
        return True
    else:
        return None


def _extract_province(resultado):
    """Extrae la provincia del resultado"""
    if not resultado:
        return None
    
    # Buscar patrón "provincia de X"
    match = re.search(r'provincia de ([^.]+)', resultado, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    return None


def _extract_update_date(resultado):
    """Extrae la fecha de actualización"""
    if not resultado:
        return None
    
    # Buscar patrón de fecha "al DD/MM/YYYY"
    match = re.search(r'al (\d{2}/\d{2}/\d{4})', resultado)
    if match:
        return match.group(1)
    
    return None


# Función de prueba
def test_sat_scraper():
    """Función de prueba para el scraper SAT"""
    resultado = scraper_sat_captura("BUE220")
    print("Resultado SAT:")
    print(f"Éxito: {resultado['success']}")
    if resultado['success']:
        print("Datos:")
        print(f"  Estado: {resultado['data']['estado_captura']}")
        print(f"  Tiene orden: {resultado['data']['tiene_orden_captura']}")
        print(f"  Provincia: {resultado['data']['provincia']}")
    else:
        print(f"Error: {resultado['error']}")
    
    return resultado