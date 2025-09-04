import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def scraper_soat_seguro(plate_number, timeout=90):
    """
    Consulta información de SOAT en SBS Perú
    
    Args:
        plate_number (str): Número de placa a consultar
        timeout (int): Timeout en segundos para la operación
    
    Returns:
        dict: Resultado estructurado con información de SOAT
    """
    driver = None
    start_time = datetime.now()
    
    try:
        # Configurar driver
        driver = _setup_soat_driver()
        url = "https://servicios.sbs.gob.pe/reportesoat/"
        
        logger.info(f"SOAT Scraper - Consultando placa: {plate_number}")
        
        # Verificar timeout
        if (datetime.now() - start_time).seconds > timeout:
            raise Exception("Timeout general alcanzado")
        
        # Abrir la página
        driver.get(url)
        wait = WebDriverWait(driver, 15)
        time.sleep(3)
        
        # Ingresar la placa
        placa_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']")))
        placa_input.clear()
        placa_input.send_keys(plate_number.upper())
        
        # Verificar que SOAT esté seleccionado
        try:
            soat_radio = driver.find_element(By.XPATH, "//input[@type='radio' and @value='SOAT']")
            if not soat_radio.is_selected():
                soat_radio.click()
        except:
            pass  # SOAT ya está seleccionado por defecto
        
        # Esperar antes de consultar
        time.sleep(2)
        
        # Hacer clic en Consultar
        consultar_button = driver.find_element(By.XPATH, "//input[@value='Consultar']")
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", consultar_button)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", consultar_button)
        
        # Esperar resultados
        time.sleep(8)
        
        # Obtener y procesar resultados
        resultado_completo = _extract_soat_results(driver)
        
        # Parsear datos específicos
        datos_parseados = _parse_soat_data(resultado_completo)
        
        return {
            'success': True,
            'data': datos_parseados,
            'raw_data': resultado_completo,
            'source': 'SBS (Superintendencia de Banca y Seguros)',
            'timestamp': datetime.now(),
            'plate_number': plate_number.upper(),
            'response_time': (datetime.now() - start_time).seconds
        }
        
    except Exception as e:
        logger.error(f"Error en SOAT scraper: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'data': None,
            'source': 'SBS (Superintendencia de Banca y Seguros)',
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


def _setup_soat_driver():
    """Configura el driver de Chrome para SOAT"""
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


def _extract_soat_results(driver):
    """Extrae los resultados completos de la consulta SOAT"""
    try:
        # Buscar todas las tablas
        tables = driver.find_elements(By.TAG_NAME, "table")
        result_parts = []
        
        # Información básica (primera tabla)
        if len(tables) >= 1:
            first_table = tables[0]
            basic_info = first_table.text.strip()
            if basic_info:
                result_parts.append("=== INFORMACIÓN DE CONSULTA ===")
                result_parts.append(basic_info)
        
        # Resultado de consulta (texto sobre accidentes)
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            lines = body_text.split('\n')
            for line in lines:
                if ("accidentes coberturados" in line.lower() or 
                    "la placa consultada cuenta" in line.lower()):
                    result_parts.append("\n=== RESULTADO DE CONSULTA ===")
                    result_parts.append(line.strip())
                    break
        except:
            pass
        
        # Listado de pólizas SOAT (tabla principal) - MEJORADO
        polizas_encontradas = False
        for i, table in enumerate(tables):
            table_text = table.text.strip()
            if ("compañía" in table_text.lower() and 
                "aseguradora" in table_text.lower() and
                "póliza" in table_text.lower()):
                
                result_parts.append("\n=== LISTADO DE PÓLIZAS SOAT ===")
                result_parts.append(table_text)
                polizas_encontradas = True
                break
        
        # Si no encontramos la tabla principal, buscar otras tablas con datos de pólizas
        if not polizas_encontradas:
            for table in tables:
                table_text = table.text.strip()
                # Buscar tablas que contengan información de seguros
                if any(keyword in table_text.lower() for keyword in ['rímac', 'positiva', 'interseguro', 'póliza', 'vigencia']):
                    if len(table_text.split('\n')) > 2:  # Asegurar que tiene contenido
                        result_parts.append("\n=== LISTADO DE PÓLIZAS SOAT ===")
                        result_parts.append(table_text)
                        break
        
        return '\n'.join(result_parts) if result_parts else "No se encontraron resultados"
        
    except Exception as e:
        logger.error(f"Error obteniendo resultados SOAT: {e}")
        return f"Error extrayendo resultados: {str(e)}"


def _parse_soat_data(resultado_completo):
    """Parsea los datos específicos del SOAT"""
    try:
        datos = {
            'tiene_soat': False,
            'numero_accidentes': None,
            'fecha_consulta': None,
            'informacion_actualizada': None,
            'polizas': [],
            'resultado_consulta': None,
            'listado_polizas_texto': None
        }
        
        if not resultado_completo:
            return datos
        
        # Extraer número de accidentes
        match = re.search(r'número de accidentes coberturados.*?(\d+)', resultado_completo, re.IGNORECASE)
        if match:
            datos['numero_accidentes'] = int(match.group(1))
            datos['tiene_soat'] = True
        
        # Extraer fecha de consulta
        match = re.search(r'Fecha de consulta:\s*([^\n]+)', resultado_completo)
        if match:
            datos['fecha_consulta'] = match.group(1).strip()
        
        # Extraer información actualizada
        match = re.search(r'Información actualizada a:\s*([^\n]+)', resultado_completo)
        if match:
            datos['informacion_actualizada'] = match.group(1).strip()
        
        # Extraer resultado de consulta completo
        if "=== RESULTADO DE CONSULTA ===" in resultado_completo:
            parts = resultado_completo.split("=== RESULTADO DE CONSULTA ===")
            if len(parts) > 1:
                resultado_lines = parts[1].split('\n')
                for line in resultado_lines:
                    line = line.strip()
                    if line and "LISTADO" not in line:
                        datos['resultado_consulta'] = line
                        break
        
        # Extraer listado de pólizas
        if "=== LISTADO DE PÓLIZAS SOAT ===" in resultado_completo:
            parts = resultado_completo.split("=== LISTADO DE PÓLIZAS SOAT ===")
            if len(parts) > 1:
                datos['listado_polizas_texto'] = parts[1].strip()
                datos['polizas'] = _parse_polizas_table(parts[1])
        
        return datos
        
    except Exception as e:
        logger.error(f"Error parseando datos SOAT: {e}")
        return {
            'tiene_soat': False,
            'error_parsing': str(e),
            'resultado_completo': resultado_completo
        }


def _parse_polizas_table(tabla_texto):
    """Parsea la tabla de pólizas para extraer información estructurada"""
    polizas = []
    
    try:
        lines = tabla_texto.strip().split('\n')
        header_found = False
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Buscar la línea de encabezado
            if "compañía" in line.lower() and "aseguradora" in line.lower():
                header_found = True
                continue
            
            # Procesar líneas de datos después del encabezado
            if header_found and line:
                # Patrones específicos para diferentes aseguradoras
                poliza = {}
                
                # Para Rímac Seguros
                if line.startswith('Rímac') or 'Rímac' in line:
                    parts = line.split()
                    if len(parts) >= 8:
                        poliza = {
                            'compania': 'Rímac Seguros',  # Mantener nombre completo
                            'clase_vehiculo': parts[2] if len(parts) > 2 else '',
                            'uso': f"{parts[3]} {parts[4]}" if len(parts) > 4 else parts[3] if len(parts) > 3 else '',  # "Transporte Urbano"
                            'accidentes': parts[5] if len(parts) > 5 else '',
                            'numero_poliza': parts[6] if len(parts) > 6 else '',
                            'certificado': parts[7] if len(parts) > 7 else '',
                            'inicio_vigencia': parts[8] if len(parts) > 8 else '',
                            'fin_vigencia': parts[9] if len(parts) > 9 else '',
                            'comentario': ' '.join(parts[10:]) if len(parts) > 10 else ''
                        }
                
                # Para La Positiva
                elif line.startswith('La Positiva') or 'Positiva' in line:
                    parts = line.split()
                    if len(parts) >= 7:
                        poliza = {
                            'compania': 'La Positiva',
                            'clase_vehiculo': parts[2] if len(parts) > 2 else '',
                            'uso': f"{parts[3]} {parts[4]}" if len(parts) > 4 else parts[3] if len(parts) > 3 else '',
                            'accidentes': parts[5] if len(parts) > 5 else '',
                            'numero_poliza': parts[6] if len(parts) > 6 else '',
                            'certificado': parts[7] if len(parts) > 7 else '',
                            'inicio_vigencia': parts[8] if len(parts) > 8 else '',
                            'fin_vigencia': parts[9] if len(parts) > 9 else '',
                            'comentario': ' '.join(parts[10:]) if len(parts) > 10 else ''
                        }
                
                # Para Interseguro
                elif line.startswith('Interseguro') or 'Interseguro' in line:
                    parts = line.split()
                    if len(parts) >= 7:
                        poliza = {
                            'compania': 'Interseguro',
                            'clase_vehiculo': parts[1] if len(parts) > 1 else '',
                            'uso': f"{parts[2]} {parts[3]}" if len(parts) > 3 else parts[2] if len(parts) > 2 else '',
                            'accidentes': parts[4] if len(parts) > 4 else '',
                            'numero_poliza': parts[5] if len(parts) > 5 else '',
                            'certificado': parts[6] if len(parts) > 6 else '',
                            'inicio_vigencia': parts[7] if len(parts) > 7 else '',
                            'fin_vigencia': parts[8] if len(parts) > 8 else '',
                            'comentario': ' '.join(parts[9:]) if len(parts) > 9 else ''
                        }
                
                # Patrón genérico para otras aseguradoras
                else:
                    # Intentar división por espacios múltiples primero
                    parts = re.split(r'\s{2,}', line)
                    
                    if len(parts) < 6:  # Si no funciona, usar espacios simples
                        parts = line.split()
                    
                    if len(parts) >= 6:
                        poliza = {
                            'compania': parts[0],
                            'clase_vehiculo': parts[1] if len(parts) > 1 else '',
                            'uso': parts[2] if len(parts) > 2 else '',
                            'accidentes': parts[3] if len(parts) > 3 else '',
                            'numero_poliza': parts[4] if len(parts) > 4 else '',
                            'certificado': parts[5] if len(parts) > 5 else '',
                            'inicio_vigencia': parts[6] if len(parts) > 6 else '',
                            'fin_vigencia': parts[7] if len(parts) > 7 else '',
                            'comentario': ' '.join(parts[8:]) if len(parts) > 8 else ''
                        }
                
                # Solo agregar si tiene datos mínimos válidos
                if poliza and poliza.get('compania') and poliza.get('numero_poliza'):
                    polizas.append(poliza)
        
    except Exception as e:
        logger.error(f"Error parseando tabla de pólizas: {e}")
    
    return polizas


# Función de prueba
def test_soat_scraper():
    """Función de prueba para el scraper SOAT"""
    resultado = scraper_soat_seguro("BUE220")
    print("Resultado SOAT:")
    print(f"Éxito: {resultado['success']}")
    if resultado['success']:
        print("Datos:")
        print(f"  Tiene SOAT: {resultado['data']['tiene_soat']}")
        print(f"  Accidentes: {resultado['data']['numero_accidentes']}")
        print(f"  Fecha consulta: {resultado['data']['fecha_consulta']}")
        print(f"  Pólizas encontradas: {len(resultado['data']['polizas'])}")
    else:
        print(f"Error: {resultado['error']}")
    
    return resultado