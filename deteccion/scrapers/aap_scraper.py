import time
import os
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from datetime import datetime
import tempfile
import logging

logger = logging.getLogger(__name__)

def scraper_aap_vehiculo(plate_number, api_key_2captcha='', timeout=60):
    """
    Obtiene datos oficiales del vehículo desde la AAP (Asociación Automotriz del Perú)
    
    Args:
        plate_number (str): Número de placa a consultar
        api_key_2captcha (str): API key para resolver captchas
        timeout (int): Timeout en segundos para la operación
    
    Returns:
        dict: Resultado estructurado con los datos del vehículo
    """
    driver = None
    start_time = datetime.now()
    
    try:
        # Configurar driver
        driver = _setup_chrome_driver()
        url = 'https://www.placas.pe/Public/CheckPlateStatus.aspx'
        
        # Intentar hasta 2 veces
        for intento in range(2):
            try:
                logger.info(f"AAP Scraper - Intento {intento + 1} para placa: {plate_number}")
                
                # Verificar timeout
                if (datetime.now() - start_time).seconds > timeout:
                    raise TimeoutException("Timeout general alcanzado")
                
                # Cargar página
                driver.get(url)
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                time.sleep(2)
                
                # Completar placa
                input_placa = driver.find_element(By.ID, "MainContent_txtPlateNumber")
                input_placa.clear()
                input_placa.send_keys(plate_number.upper())
                
                # Resolver captcha
                captcha_text = _resolver_captcha_2captcha(driver, api_key_2captcha)
                if not captcha_text:
                    logger.warning("Error resolviendo captcha, reintentando...")
                    continue
                
                # Completar captcha
                captcha_input = driver.find_element(By.ID, "MainContent_txtimgcode")
                captcha_input.clear()
                captcha_input.send_keys(captcha_text)
                
                # Configurar tipo de placa
                dropdown = Select(driver.find_element(By.ID, "MainContent_wddTypePlate"))
                if dropdown.first_selected_option.get_attribute('value') == '0':
                    dropdown.select_by_visible_text('Regular')
                
                # Enviar formulario
                boton_buscar = driver.find_element(By.CSS_SELECTOR, "button.g-recaptcha.btnButton")
                
                # Manejar reCAPTCHA si existe
                try:
                    driver.find_element(By.CSS_SELECTOR, ".g-recaptcha")
                    time.sleep(3)
                except NoSuchElementException:
                    pass
                
                boton_buscar.click()
                time.sleep(5)
                
                # Verificar errores
                try:
                    error_element = driver.find_element(By.ID, "MainContent_lblMessage")
                    error_text = error_element.text.strip()
                    if error_text and any(word in error_text.lower() for word in ['incorrecto', 'invalid', 'error']):
                        logger.warning(f"Error detectado: {error_text}")
                        continue
                except NoSuchElementException:
                    pass
                
                # Buscar resultados
                tablas = driver.find_elements(By.TAG_NAME, "table")
                for tabla in tablas:
                    tabla_text = tabla.text.strip()
                    if "DATOS DE LA PLACA" in tabla_text:
                        datos_limpios = _extraer_datos_vehiculo_aap(tabla_text)
                        if datos_limpios:
                            return {
                                'success': True,
                                'data': datos_limpios,
                                'raw_data': tabla_text,
                                'source': 'AAP (Asociación Automotriz del Perú)',
                                'timestamp': datetime.now(),
                                'plate_number': plate_number.upper(),
                                'response_time': (datetime.now() - start_time).seconds
                            }
                
                logger.warning("No se encontraron resultados válidos")
                
            except Exception as e:
                logger.error(f"Error en intento {intento + 1}: {str(e)}")
                if intento == 1:  # Último intento
                    break
        
        # Si llegamos aquí, no se encontraron datos
        return {
            'success': False,
            'error': 'No se encontraron datos después de todos los intentos',
            'data': None,
            'source': 'AAP (Asociación Automotriz del Perú)',
            'timestamp': datetime.now(),
            'plate_number': plate_number.upper(),
            'response_time': (datetime.now() - start_time).seconds
        }
        
    except Exception as e:
        logger.error(f"Error general en AAP scraper: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'data': None,
            'source': 'AAP (Asociación Automotriz del Perú)',
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


def _setup_chrome_driver():
    """Configura Chrome con opciones anti-detección"""
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # Modo headless para producción
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-logging")
    options.add_argument("--log-level=3")
    
    driver = webdriver.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def _resolver_captcha_2captcha(driver, api_key):
    """Resuelve el captcha usando 2captcha"""
    temp_file_path = None
    try:
        # Capturar imagen del captcha
        captcha_img = driver.find_element(By.ID, "MainContent_Image2")
        
        # Usar archivo temporal con mejor manejo
        import tempfile
        import uuid
        
        # Crear nombre único para evitar conflictos
        temp_filename = f"captcha_{uuid.uuid4().hex}.png"
        temp_file_path = os.path.join(tempfile.gettempdir(), temp_filename)
        
        # Tomar screenshot
        captcha_img.screenshot(temp_file_path)
        
        # Esperar un poco para asegurar que el archivo se escribió completamente
        time.sleep(0.5)
        
        # Enviar a 2captcha
        with open(temp_file_path, "rb") as f:
            response = requests.post(
                "http://2captcha.com/in.php", 
                files={"file": f},
                data={"key": api_key, "method": "post", "json": 1},
                timeout=30
            ).json()
        
        if response.get("status") != 1:
            logger.error(f"Error enviando captcha: {response}")
            return None
        
        captcha_id = response["request"]
        
        # Esperar resultado
        for intento in range(20):  # Máximo 100 segundos
            time.sleep(5)
            try:
                res = requests.get(
                    f"http://2captcha.com/res.php?key={api_key}&action=get&id={captcha_id}&json=1",
                    timeout=10
                ).json()
                
                if res["status"] == 1:
                    logger.info("Captcha resuelto exitosamente")
                    return res["request"]
                elif res.get("error_text"):
                    logger.error(f"Error en 2captcha: {res['error_text']}")
                    return None
                    
            except requests.RequestException as e:
                logger.error(f"Error consultando 2captcha (intento {intento}): {e}")
                continue
        
        logger.error("Timeout esperando respuesta de 2captcha")
        return None
        
    except Exception as e:
        logger.error(f"Error general resolviendo captcha: {e}")
        return None
    
    finally:
        # Limpiar archivo temporal de forma segura
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                time.sleep(0.1)  # Pequeña pausa antes de eliminar
                os.unlink(temp_file_path)
                logger.debug(f"Archivo temporal eliminado: {temp_file_path}")
            except Exception as e:
                logger.warning(f"No se pudo eliminar archivo temporal: {e}")
                # Intentar eliminar después
                try:
                    time.sleep(1)
                    os.unlink(temp_file_path)
                except:
                    pass  # Si no se puede eliminar, no es crítico


def _extraer_datos_vehiculo_aap(texto_completo):
    """Extrae y estructura los datos relevantes del vehículo"""
    try:
        lineas = texto_completo.split('\n')
        datos_vehiculo = {}
        
        # Mapeo de campos
        campos_mapeo = {
            'Placa Nueva:': 'placa_nueva',
            'Placa Anterior:': 'placa_anterior', 
            'Estado:': 'estado',
            'Punto Entrega:': 'punto_entrega',
            'Fecha Entrega:': 'fecha_entrega',
            'Nro. Serie:': 'numero_serie',
            'Marca:': 'marca',
            'Modelo:': 'modelo',
            'Propietario:': 'propietario',
            'Tipo Uso:': 'tipo_uso',
            'Tipo de Sol.:': 'tipo_solicitud'
        }
        
        for linea in lineas:
            linea = linea.strip()
            for campo_original, campo_key in campos_mapeo.items():
                if linea.startswith(campo_original):
                    valor = linea.replace(campo_original, '').strip()
                    datos_vehiculo[campo_key] = valor
                    break
        
        # Verificar que tenemos datos mínimos
        if len(datos_vehiculo) >= 3:
            return datos_vehiculo
        else:
            return None
            
    except Exception as e:
        logger.error(f"Error extrayendo datos AAP: {e}")
        return None


# Función de prueba
def test_aap_scraper():
    """Función de prueba para el scraper AAP"""
    resultado = scraper_aap_vehiculo("BUE228")
    print("Resultado AAP:")
    print(f"Éxito: {resultado['success']}")
    if resultado['success']:
        print("Datos estructurados:")
        for key, value in resultado['data'].items():
            print(f"  {key}: {value}")
    else:
        print(f"Error: {resultado['error']}")
    
    return resultado

def scraper_aap_vehiculo_test(plate_number):
    """Versión de prueba que simula el proceso real"""
    import time
    from datetime import datetime
    
    # Simular tiempo de procesamiento
    time.sleep(2)
    
    return {
        'success': True,
        'data': {
            'placa_nueva': f'{plate_number} - D1',
            'placa_anterior': plate_number,
            'estado': 'ENTREGADO A CLIENTE (SIMULADO)',
            'marca': 'TOYOTA (PRUEBA)',
            'modelo': 'ETIOS (PRUEBA)',
            'propietario': 'EMPRESA DE PRUEBA S.A.C.',
            'tipo_uso': 'Taxis y Colectivos (SIMULADO)',
            'fecha_entrega': '01/07/2024 10:28:23',
            'numero_serie': '9BRB29BT7M2264995'
        },
        'source': 'AAP (Simulado)',
        'timestamp': datetime.now(),
        'plate_number': plate_number.upper(),
        'response_time': 2
    }