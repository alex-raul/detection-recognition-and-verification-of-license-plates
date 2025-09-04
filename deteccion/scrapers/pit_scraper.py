import time
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def scraper_pit_papeletas(plate_number, api_key_2captcha='', timeout=120):
    """
    Consulta el estado de papeletas de tránsito en PIT Perú
    
    Args:
        plate_number (str): Número de placa a consultar
        api_key_2captcha (str): API key para resolver captchas
        timeout (int): Timeout en segundos para la operación
    
    Returns:
        dict: Resultado estructurado con información de papeletas
    """
    driver = None
    start_time = datetime.now()
    
    try:
        # Configurar driver
        driver = _setup_pit_driver()
        url = "http://www.pit.gob.pe/pit2007/EstadoCuenta.aspx"
        
        logger.info(f"PIT Scraper - Consultando placa: {plate_number}")
        
        # Abrir la página
        driver.get(url)
        wait = WebDriverWait(driver, 15)
        time.sleep(3)
        
        # Verificar timeout
        if (datetime.now() - start_time).seconds > timeout:
            raise Exception("Timeout general alcanzado")
        
        # Ingresar la placa
        placa_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']")))
        placa_input.clear()
        placa_input.send_keys(plate_number.upper())
        time.sleep(3)
        
        # Obtener y resolver reCAPTCHA
        site_key = _get_recaptcha_site_key(driver)
        if not site_key:
            raise Exception("No se pudo obtener la site key del reCAPTCHA")
        
        recaptcha_solution = _solve_recaptcha_2captcha(site_key, url, api_key_2captcha)
        if not recaptcha_solution:
            raise Exception("No se pudo resolver el reCAPTCHA")
        
        # Inyectar solución del reCAPTCHA
        driver.execute_script(f"document.getElementById('g-recaptcha-response').innerHTML = '{recaptcha_solution}';")
        driver.execute_script(f"document.getElementById('g-recaptcha-response').style.display = 'block';")
        
        # Manejar checkbox del reCAPTCHA
        _handle_recaptcha_checkbox(driver)
        
        time.sleep(3)
        
        # Hacer clic en el botón Buscar
        buscar_button = driver.find_element(By.XPATH, "//input[contains(@src, 'buscar') or @value='Buscar' or @value='BUSCAR']")
        driver.execute_script("arguments[0].click();", buscar_button)
        
        # Esperar resultados
        time.sleep(8)
        
        # Obtener y procesar resultados
        resultado = _extract_pit_results(driver)
        
        return {
            'success': True,
            'data': {
                'estado_papeletas': resultado,
                'tiene_papeletas': 'no se encontró' not in resultado.lower(),
                'detalle': resultado
            },
            'raw_data': resultado,
            'source': 'PIT (Policía de Tránsito)',
            'timestamp': datetime.now(),
            'plate_number': plate_number.upper(),
            'response_time': (datetime.now() - start_time).seconds
        }
        
    except Exception as e:
        logger.error(f"Error en PIT scraper: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'data': None,
            'source': 'PIT (Policía de Tránsito)',
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


def _setup_pit_driver():
    """Configura el driver de Chrome para PIT"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--log-level=3")
    
    return webdriver.Chrome(options=chrome_options)


def _get_recaptcha_site_key(driver):
    """Obtiene la site key del reCAPTCHA"""
    try:
        page_source = driver.page_source
        
        # Buscar data-sitekey
        site_key_pattern = r'data-sitekey="([^"]+)"'
        match = re.search(site_key_pattern, page_source)
        
        if match:
            site_key = match.group(1)
            logger.info(f"Site key encontrada: {site_key}")
            return site_key
        else:
            # Buscar en scripts
            script_pattern = r'"sitekey":\s*"([^"]+)"'
            match = re.search(script_pattern, page_source)
            if match:
                return match.group(1)
                
            raise Exception("No se pudo encontrar la site key del reCAPTCHA")
            
    except Exception as e:
        logger.error(f"Error obteniendo site key: {e}")
        return None


def _solve_recaptcha_2captcha(site_key, page_url, api_key):
    """Resuelve el reCAPTCHA usando 2captcha"""
    try:
        # Enviar reCAPTCHA
        submit_data = {
            'method': 'userrecaptcha',
            'googlekey': site_key,
            'key': api_key,
            'pageurl': page_url
        }
        
        response = requests.post("http://2captcha.com/in.php", data=submit_data, timeout=30)
        
        if response.text.startswith('OK|'):
            captcha_id = response.text.split('|')[1]
            logger.info(f"reCAPTCHA enviado con ID: {captcha_id}")
        else:
            raise Exception(f"Error enviando reCAPTCHA: {response.text}")
        
        # Esperar resultado
        logger.info("Esperando solución de reCAPTCHA...")
        for attempt in range(40):  # Hasta 200 segundos
            time.sleep(5)
            
            result_data = {
                'key': api_key,
                'action': 'get',
                'id': captcha_id
            }
            
            try:
                response = requests.get("http://2captcha.com/res.php", params=result_data, timeout=15)
                
                if response.text == 'CAPCHA_NOT_READY':
                    if attempt % 6 == 0:
                        logger.info(f"Esperando reCAPTCHA... ({attempt * 5}s)")
                    continue
                elif response.text.startswith('OK|'):
                    solution = response.text.split('|')[1]
                    logger.info("reCAPTCHA resuelto exitosamente!")
                    return solution
                else:
                    logger.warning(f"Respuesta inesperada: {response.text}")
                    continue
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Error de conexión en intento {attempt + 1}: {e}")
                continue
        
        raise Exception("Timeout esperando solución del reCAPTCHA")
        
    except Exception as e:
        raise Exception(f"Error resolviendo reCAPTCHA: {e}")


def _handle_recaptcha_checkbox(driver):
    """Maneja el checkbox del reCAPTCHA"""
    try:
        # Intentar hacer clic en el checkbox del reCAPTCHA
        recaptcha_checkbox = driver.find_element(By.XPATH, "//div[contains(@class, 'recaptcha-checkbox')]")
        driver.execute_script("arguments[0].click();", recaptcha_checkbox)
        time.sleep(2)
    except:
        # Intentar con iframe
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for iframe in iframes:
            src = iframe.get_attribute("src") or ""
            if "recaptcha" in src.lower():
                driver.switch_to.frame(iframe)
                try:
                    checkbox = driver.find_element(By.CLASS_NAME, "recaptcha-checkbox-border")
                    checkbox.click()
                except:
                    pass
                finally:
                    driver.switch_to.default_content()
                break


def _extract_pit_results(driver):
    """Extrae los resultados del estado de papeletas"""
    try:
        time.sleep(3)
        
        # Buscar el mensaje específico del resultado
        body_text = driver.find_element(By.TAG_NAME, "body").text
        lines = body_text.split('\n')
        
        # Buscar específicamente el mensaje de resultado
        for line in lines:
            line = line.strip()
            
            # Mensaje específico de "no se encontró"
            if "no se encontró papeletas pendientes" in line.lower():
                return line
            
            # Otros posibles mensajes de resultado
            if any(phrase in line.lower() for phrase in [
                "no se encontraron papeletas",
                "no tiene papeletas pendientes",
                "sin papeletas pendientes de pago",
                "no existen papeletas"
            ]):
                return line
        
        # Si no encontramos mensaje de "sin papeletas", buscar tabla con papeletas
        tables = driver.find_elements(By.TAG_NAME, "table")
        for table in tables:
            table_text = table.text.strip()
            
            # Verificar si la tabla contiene papeletas reales (con códigos P-)
            if any(keyword in table_text for keyword in ['P-', 'papeleta', 'S/', 'monto']):
                rows = table_text.split('\n')
                papeleta_rows = []
                
                for row in rows:
                    # Buscar filas que contengan información de papeletas
                    if 'P-' in row or ('S/' in row and len(row.split()) > 3):
                        papeleta_rows.append(row.strip())
                
                if papeleta_rows:
                    return f"Papeletas pendientes encontradas:\n" + '\n'.join(papeleta_rows)
        
        # Buscar en elementos específicos
        result_elements = driver.find_elements(By.XPATH, "//span | //div | //p")
        for element in result_elements:
            text = element.text.strip()
            if ("no se encontró" in text.lower() and 
                "papeletas" in text.lower() and 
                len(text) > 30 and len(text) < 150):
                return text
        
        return "No se encontró información específica sobre el estado de papeletas"
        
    except Exception as e:
        logger.error(f"Error obteniendo resultados PIT: {e}")
        return f"Error extrayendo resultados: {str(e)}"


# Función de prueba
def test_pit_scraper():
    """Función de prueba para el scraper PIT"""
    resultado = scraper_pit_papeletas("BUE220")
    print("Resultado PIT:")
    print(f"Éxito: {resultado['success']}")
    if resultado['success']:
        print("Datos:")
        print(f"  Estado: {resultado['data']['estado_papeletas']}")
        print(f"  Tiene papeletas: {resultado['data']['tiene_papeletas']}")
    else:
        print(f"Error: {resultado['error']}")
    
    return resultado