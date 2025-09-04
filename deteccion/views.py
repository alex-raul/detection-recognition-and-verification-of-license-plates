# deteccion/views.py
from django.shortcuts import render
from django.http import JsonResponse
from django.core.files.storage import FileSystemStorage
from django.contrib import messages
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Q
from google.cloud import vision
import cv2
import numpy as np
import re
import logging
import os
import requests
import base64
import easyocr
import json
from datetime import datetime, timedelta
from .models import PlateDetection
from django.views.decorators.http import require_http_methods
#from .models import PlateDetection as Detection
from django.shortcuts import render, get_object_or_404
from django.utils import timezone

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Inicializar cliente de Google Cloud Vision
try:
    client = vision.ImageAnnotatorClient()
    logger.info("Cliente de Google Vision inicializado correctamente")
except Exception as e:
    logger.error(f"Error inicializando cliente Vision: {e}")
    client = None

# Inicializar EasyOCR (solo una vez al cargar el módulo)
try:
    easyocr_reader = easyocr.Reader(['en', 'es'], gpu=False)
    logger.info("EasyOCR inicializado correctamente")
except Exception as e:
    logger.error(f"Error inicializando EasyOCR: {e}")
    easyocr_reader = None

# Configuración de Roboflow
ROBOFLOW_API_URL = "https://detect.roboflow.com/peru-license-plate/3"
ROBOFLOW_API_KEY = "q6tuzyNEjG0sHHWQnxeL"

def preprocess_license_plate(roi_image):
    """Preprocesa la imagen de la placa para mejorar el OCR"""
    try:
        height, width = roi_image.shape[:2]
        if width < 300:
            scale_factor = 300 / width
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            roi_image = cv2.resize(roi_image, (new_width, new_height), interpolation=cv2.INTER_CUBIC)

        if len(roi_image.shape) == 3:
            gray = cv2.cvtColor(roi_image, cv2.COLOR_BGR2GRAY)
        else:
            gray = roi_image

        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        binary = cv2.adaptiveThreshold(
            enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 10
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 1))
        cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        return cleaned
    except Exception as e:
        logger.error(f"Error en preprocesamiento: {e}")
        return roi_image

def extract_text_google_vision(image_bytes):
    """Extrae texto usando Google Vision API"""
    if not client:
        return "Error: Cliente no disponible", 0.0

    try:
        image = vision.Image(content=image_bytes)
        image_context = vision.ImageContext(language_hints=['es', 'en'])
        response = client.text_detection(image=image, image_context=image_context)

        if response.error.message:
            return f"Error API: {response.error.message}", 0.0

        texts = response.text_annotations
        if not texts:
            return "No encontrado", 0.0

        full_text = texts[0].description.strip()
        confidence = 0.8 if full_text else 0.0
        return full_text, confidence
    except Exception as e:
        return f"Error: {str(e)}", 0.0

def extract_text_easyocr(roi_image):
    """Extrae texto usando EasyOCR"""
    if not easyocr_reader:
        return "Error: EasyOCR no disponible", 0.0

    try:
        results = easyocr_reader.readtext(
            roi_image,
            allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-',
            width_ths=0.8,
            height_ths=0.8,
            paragraph=False,
            detail=1
        )

        if not results:
            return "No encontrado", 0.0

        all_texts = []
        confidences = []
        
        for (bbox, text, confidence) in results:
            if confidence > 0.3:
                all_texts.append(text.strip())
                confidences.append(confidence)

        if not all_texts:
            return "No encontrado", 0.0

        combined_text = ' '.join(all_texts)
        max_confidence = max(confidences)
        return combined_text, max_confidence
    except Exception as e:
        logger.error(f"Error en EasyOCR: {e}")
        return f"Error: {str(e)}", 0.0

def clean_license_plate_text(text):
    """Limpia y valida el texto de la placa detectada"""
    if not text or "Error" in text:
        return ""
    
    text = re.sub(r'[^\w\s-]', '', text)
    text = text.upper().strip()
    text = re.sub(r'\s+', ' ', text)
    
    corrections = {
        'O': '0', 'I': '1', 'S': '5', 'B': '8', 'G': '6', 'Z': '2',
        'Q': '0', 'L': '1', 'T': '7', 'D': '0'
    }
    
    patterns = [
        r'([A-Z]{3})\s*-?\s*([0-9]{3})',  # ABC-123
        r'([A-Z]{2})\s*-?\s*([0-9]{4})',  # AB-1234
        r'([0-9]{3})\s*-?\s*([A-Z]{3})',  # 123-ABC
        r'([A-Z]{1})\s*([A-Z]{2})\s*-?\s*([0-9]{3})',  # A BC-123
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            if len(matches[0]) == 2:
                letters, numbers = matches[0]
                corrected_numbers = ''.join([corrections.get(c, c) if c.isdigit() else c for c in numbers])
                return f"{letters}-{corrected_numbers}"
            elif len(matches[0]) == 3:
                return f"{matches[0][0]}{matches[0][1]}-{matches[0][2]}"
    
    return text.replace(' ', '').replace('-', '') if len(text) <= 8 else text

def get_best_ocr_result(roi_original, roi_processed):
    """Compara resultados de OCR y devuelve el mejor"""
    results = []
    
    # Google Vision - Original
    success, buffer = cv2.imencode('.jpg', roi_original)
    if success:
        google_text, google_conf = extract_text_google_vision(buffer.tobytes())
        google_cleaned = clean_license_plate_text(google_text)
        results.append({
            'text': google_cleaned,
            'confidence': google_conf,
            'method': 'Google Vision',
            'score': len(google_cleaned) * google_conf
        })
    
    # EasyOCR - Original
    easy_text, easy_conf = extract_text_easyocr(roi_original)
    easy_cleaned = clean_license_plate_text(easy_text)
    results.append({
        'text': easy_cleaned,
        'confidence': easy_conf,
        'method': 'EasyOCR',
        'score': len(easy_cleaned) * easy_conf
    })
    
    # EasyOCR - Procesada
    easy_text_proc, easy_conf_proc = extract_text_easyocr(roi_processed)
    easy_cleaned_proc = clean_license_plate_text(easy_text_proc)
    results.append({
        'text': easy_cleaned_proc,
        'confidence': easy_conf_proc,
        'method': 'EasyOCR Pro',
        'score': len(easy_cleaned_proc) * easy_conf_proc
    })
    
    valid_results = [r for r in results if r['text'] and len(r['text']) >= 3]
    
    if not valid_results:
        valid_results = [r for r in results if r['text']]
    
    if not valid_results:
        return "No detectada", 0.0, "Ninguno", []
    
    valid_results.sort(key=lambda x: x['score'], reverse=True)
    best = valid_results[0]
    
    return best['text'], best['confidence'], best['method'], valid_results

def save_plate_detection(plate_text, confidence, method, image_path=None, detection_type='manual'):
    """Guarda la detección en la base de datos"""
    try:
        detection = PlateDetection.objects.create(
            plate_number=plate_text,
            confidence=confidence,
            detection_method=method,
            image_path=image_path,
            detection_type=detection_type
        )
        return detection
    except Exception as e:
        logger.error(f"Error guardando detección: {e}")
        return None

def process_image_detection(image_path):
    """Procesa una imagen para detectar placas"""
    try:
        # Enviar a Roboflow
        with open(image_path, "rb") as f:
            response = requests.post(
                f"{ROBOFLOW_API_URL}?api_key={ROBOFLOW_API_KEY}",
                files={"file": ("image.jpg", f, "image/jpeg")}
            )

        if response.status_code != 200:
            return {"error": "Error en la detección", "placas": []}

        data = response.json()
        detections = data.get("predictions", [])
        
        image_cv2 = cv2.imread(image_path)
        placas = []

        for i, det in enumerate(detections):
            confidence = det.get("confidence", 0)
            
            if confidence < 0.4:
                continue
            
            x, y, w, h = int(det["x"]), int(det["y"]), int(det["width"]), int(det["height"])
            x1, y1 = max(0, x - w // 2), max(0, y - h // 2)
            x2, y2 = min(image_cv2.shape[1], x + w // 2), min(image_cv2.shape[0], y + h // 2)
            
            padding = 8
            x1, y1 = max(0, x1 - padding), max(0, y1 - padding)
            x2, y2 = min(image_cv2.shape[1], x2 + padding), min(image_cv2.shape[0], y2 + padding)
            
            roi = image_cv2[y1:y2, x1:x2]
            
            if roi.size == 0:
                continue

            processed_roi = preprocess_license_plate(roi.copy())
            plate_text, ocr_confidence, best_method, all_results = get_best_ocr_result(roi, processed_roi)

            if plate_text and plate_text != "No detectada":
                # Guardar en base de datos
                detection = save_plate_detection(
                    plate_text, 
                    ocr_confidence, 
                    best_method, 
                    image_path,
                    'upload'
                )
                
                placas.append({
                    'id': detection.id if detection else None,
                    'texto': plate_text,
                    'confianza': f"{ocr_confidence:.2f}",
                    'metodo': best_method,
                    'coordenadas': [x1, y1, x2, y2],
                    'timestamp': timezone.now().isoformat()
                })

                # Dibujar rectángulo
                color = (0, 255, 0) if ocr_confidence > 0.7 else (0, 165, 255)
                cv2.rectangle(image_cv2, (x1, y1), (x2, y2), color, 2)
                cv2.putText(image_cv2, f"{plate_text}", (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # Guardar imagen procesada
        nombre_salida = f"resultado_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        ruta_salida = os.path.join(settings.MEDIA_ROOT, nombre_salida)
        cv2.imwrite(ruta_salida, image_cv2)

        return {
            "placas": placas,
            "imagen_resultado": os.path.join(settings.MEDIA_URL, nombre_salida),
            "total_placas": len(placas)
        }

    except Exception as e:
        logger.error(f"Error procesando imagen: {e}")
        return {"error": str(e), "placas": []}

# VISTAS PRINCIPALES

def index(request):
    """Página de bienvenida/acceso"""
    return render(request, 'deteccion/index.html')

def control_vehicular(request):
    """Página principal del sistema de control vehicular"""
    # Obtener últimas detecciones
    recent_detections = PlateDetection.objects.order_by('-created_at')[:10]
    
    # Estadísticas básicas
    today = timezone.now().date()
    today_count = PlateDetection.objects.filter(created_at__date=today).count()
    total_count = PlateDetection.objects.count()
    
    context = {
        'recent_detections': recent_detections,
        'today_count': today_count,
        'total_count': total_count,
    }
    
    return render(request, 'deteccion/control_vehicular.html', context)

@csrf_exempt
def upload_file(request):
    """Procesa archivos subidos (imagen/video)"""
    if request.method == "POST":
        try:
            if 'file' not in request.FILES:
                return JsonResponse({'error': 'No se seleccionó archivo'}, status=400)

            file = request.FILES['file']
            fs = FileSystemStorage()
            filename = fs.save(file.name, file)
            filepath = fs.path(filename)

            # Verificar tipo de archivo
            file_ext = os.path.splitext(filename)[1].lower()
            
            if file_ext in ['.jpg', '.jpeg', '.png', '.bmp']:
                # Procesar imagen
                result = process_image_detection(filepath)
                return JsonResponse(result)
            
            elif file_ext in ['.mp4', '.avi', '.mov', '.mkv']:
                # Procesar video (frame por frame)
                return process_video_detection(filepath)
            
            else:
                return JsonResponse({'error': 'Tipo de archivo no soportado'}, status=400)

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Método no permitido'}, status=405)

def process_video_detection(video_path):
    """Procesa un video para detectar placas"""
    try:
        cap = cv2.VideoCapture(video_path)
        frame_count = 0
        detected_plates = []
        
        while cap.read()[0]:
            frame_count += 1
        
        cap.release()
        
        # Procesar cada 30 frames para videos largos
        cap = cv2.VideoCapture(video_path)
        current_frame = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            if current_frame % 30 == 0:  # Procesar cada 30 frames
                # Guardar frame temporalmente
                temp_frame_path = f"/tmp/frame_{current_frame}.jpg"
                cv2.imwrite(temp_frame_path, frame)
                
                # Procesar frame
                result = process_image_detection(temp_frame_path)
                
                if result.get('placas'):
                    for placa in result['placas']:
                        placa['frame'] = current_frame
                        detected_plates.append(placa)
                
                # Limpiar archivo temporal
                if os.path.exists(temp_frame_path):
                    os.remove(temp_frame_path)
            
            current_frame += 1
        
        cap.release()
        
        return JsonResponse({
            'placas': detected_plates,
            'total_frames': frame_count,
            'total_placas': len(detected_plates)
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def capture_photo(request):
    """Captura foto desde la cámara web"""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            image_data = data.get('image')
            
            if not image_data:
                return JsonResponse({'error': 'No se recibió imagen'}, status=400)
            
            # Decodificar imagen base64
            image_data = image_data.split(',')[1]  # Remover prefijo data:image/jpeg;base64,
            image_bytes = base64.b64decode(image_data)
            
            # Guardar imagen
            filename = f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            filepath = os.path.join(settings.MEDIA_ROOT, filename)
            
            with open(filepath, 'wb') as f:
                f.write(image_bytes)
            
            # Procesar imagen
            result = process_image_detection(filepath)
            
            # Agregar tipo de detección
            for placa in result.get('placas', []):
                placa['detection_type'] = 'camera'
            
            return JsonResponse(result)
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)

def get_detections_history(request):
    """Obtiene el historial de detecciones"""
    try:
        # Parámetros de paginación
        page = int(request.GET.get('page', 1))
        search = request.GET.get('search', '')
        
        # Filtrar detecciones
        detections = PlateDetection.objects.all()
        
        if search:
            detections = detections.filter(
                Q(plate_number__icontains=search)
            )
        
        detections = detections.order_by('-created_at')
        
        # Paginar
        paginator = Paginator(detections, 20)
        page_obj = paginator.get_page(page)
        
        # Convertir a formato JSON
        detections_data = []
        for detection in page_obj:
            detections_data.append({
                'id': detection.id,
                'plate_number': detection.plate_number,
                'confidence': detection.confidence,
                'detection_method': detection.detection_method,
                'detection_type': detection.detection_type,
                'created_at': detection.created_at.isoformat(),
                'formatted_date': detection.created_at.strftime('%d/%m/%Y %H:%M:%S')
            })
        
        return JsonResponse({
            'detections': detections_data,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
            'current_page': page_obj.number,
            'total_pages': paginator.num_pages,
            'total_count': paginator.count
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def delete_detection(request, detection_id):
    if request.method == 'POST':
        try:
            detection = Detection.objects.get(id=detection_id)
            detection.delete()
            return JsonResponse({'success': True})
        except Detection.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'No encontrada'})
    return JsonResponse({'success': False, 'message': 'Método no permitido'})

def clear_all_detections(request):
    """Limpia todas las detecciones"""
    if request.method == "POST":
        try:
            count = PlateDetection.objects.all().delete()[0]
            return JsonResponse({'success': True, 'deleted_count': count})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)

@require_http_methods(["POST"])
def edit_detection(request, detection_id):
    try:
        data = json.loads(request.body)
        plate_number = data.get('plate_number', '').strip().upper()
        confidence = float(data.get('confidence', 0))
        original_text = data.get('original_text', '')
        
        if not plate_number:
            return JsonResponse({
                'success': False,
                'message': 'Texto de placa requerido'
            }, status=400)
        
        try:
            detection = PlateDetection.objects.get(id=detection_id)
            detection.plate_number = plate_number
            detection.confidence = confidence
            detection.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Placa actualizada correctamente'
            })
            
        except PlateDetection.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Detección no encontrada'
            }, status=404)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error interno: {str(e)}'
        }, status=500)
    

def detection_details(request, detection_id):
    """
    Vista para mostrar los detalles completos de una detección específica
    """
    try:
        # Obtener la detección o mostrar 404 si no existe
        detection = get_object_or_404(PlateDetection, id=detection_id)
        
        # Preparar contexto para el template
        context = {
            'detection': detection,
        }
        
        return render(request, 'detection_details.html', context)
        
    except Exception as e:
        # En caso de error, hacer redirect en lugar de render
        from django.shortcuts import redirect
        from django.contrib import messages
        
        messages.error(request, f'Error al cargar los detalles de la detección: {str(e)}')
        return redirect('deteccion:control_vehicular')
    
################### scraping
# AAP
# Agregar estos imports al inicio del archivo
#from django.conf import settings
import json
from .scrapers.aap_scraper import scraper_aap_vehiculo
# Nueva vista para probar el scraper (agregar al final del archivo)
def test_aap_scraper_view(request):
    """Vista para probar el scraper AAP"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            plate_number = data.get('plate_number', '').strip().upper()
            
            if not plate_number:
                return JsonResponse({'error': 'Número de placa requerido'}, status=400)
            
            # Importar y ejecutar scraper
            from .scrapers.aap_scraper import scraper_aap_vehiculo
            resultado = scraper_aap_vehiculo(plate_number)
            
            return JsonResponse(resultado)
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e),
                'source': 'AAP Test'
            }, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)

def search_aap_info(request, detection_id):
    """Ejecuta scraping AAP para una detección específica"""
    if request.method == 'POST':
        try:
            detection = get_object_or_404(PlateDetection, id=detection_id)
            data = json.loads(request.body)
            plate_number = data.get('plate_number', detection.plate_number).strip().upper()
            
            # ✅ ACTIVAR SCRAPER REAL
            from .scrapers.aap_scraper import scraper_aap_vehiculo
            resultado = scraper_aap_vehiculo(plate_number)
            
            return JsonResponse(resultado)
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e),
                'source': 'AAP Search'
            }, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)

    ############## papeletas

def test_pit_scraper_view(request):
    """Vista para probar el scraper PIT (separada de AAP)"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            plate_number = data.get('plate_number', '').strip().upper()
            
            if not plate_number:
                return JsonResponse({'error': 'Número de placa requerido'}, status=400)
            
            # Importar y ejecutar scraper PIT
            from .scrapers.pit_scraper import scraper_pit_papeletas
            resultado = scraper_pit_papeletas(plate_number)
            
            return JsonResponse(resultado)
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e),
                'source': 'PIT Test'
            }, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)

def search_all_vehicle_info(request, detection_id):
    """Ejecuta todos los scrapers en paralelo"""
    if request.method == 'POST':
        try:
            detection = get_object_or_404(PlateDetection, id=detection_id)
            data = json.loads(request.body)
            plate_number = data.get('plate_number', detection.plate_number).strip().upper()
            
            # DEBUGGING: Ver si llega hasta aquí
            print(f"DEBUG: Iniciando búsqueda para placa: {plate_number}")
            
            # Ejecutar todos los scrapers
            from .scrapers.unified_scraper import run_all_scrapers
            resultado = run_all_scrapers(plate_number)
            
            print(f"DEBUG: Resultado obtenido: {resultado}")
            
            return JsonResponse(resultado)
            
        except Exception as e:
            print(f"DEBUG ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            
            return JsonResponse({
                'success': False,
                'error': str(e),
                'source': 'Unified Search'
            }, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)

########## SAT
def test_sat_scraper_view(request):
    """Vista para probar el scraper SAT (separada de AAP y PIT)"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            plate_number = data.get('plate_number', '').strip().upper()
            
            if not plate_number:
                return JsonResponse({'error': 'Número de placa requerido'}, status=400)
            
            # Importar y ejecutar scraper SAT
            from .scrapers.sat_scraper import scraper_sat_captura
            resultado = scraper_sat_captura(plate_number)
            
            return JsonResponse(resultado)
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e),
                'source': 'SAT Test'
            }, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)

############### autorizacion
def test_autorizacion_scraper_view(request):
    """Vista para probar el scraper de Autorización (separada de las demás)"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            plate_number = data.get('plate_number', '').strip().upper()
            
            if not plate_number:
                return JsonResponse({'error': 'Número de placa requerido'}, status=400)
            
            # Importar y ejecutar scraper Autorización
            from .scrapers.autorizacion_scraper import scraper_autorizacion_circulacion
            resultado = scraper_autorizacion_circulacion(plate_number)
            
            return JsonResponse(resultado)
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e),
                'source': 'Autorizacion Test'
            }, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)

########### soat
def test_soat_scraper_view(request):
    """Vista para probar el scraper SOAT (separada de las demás)"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            plate_number = data.get('plate_number', '').strip().upper()
            
            if not plate_number:
                return JsonResponse({'error': 'Número de placa requerido'}, status=400)
            
            # Importar y ejecutar scraper SOAT
            from .scrapers.soat_scraper import scraper_soat_seguro
            resultado = scraper_soat_seguro(plate_number)
            
            return JsonResponse(resultado)
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e),
                'source': 'SOAT Test'
            }, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)