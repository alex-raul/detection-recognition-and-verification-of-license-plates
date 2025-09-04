import cv2
from ultralytics import YOLO
from google.cloud import vision
import re

model = YOLO("best.pt")
client = vision.ImageAnnotatorClient()

def extract_text(frame):
    _, buffer = cv2.imencode(".jpg", frame)
    image = vision.Image(content=buffer.tobytes())
    response = client.text_detection(image=image)
    texts = response.text_annotations
    if not texts:
        return "No encontrado"
    matches = re.findall(r'[A-Z]{1,3}-?[0-9]{3,4}', texts[0].description)
    return matches[0] if matches else texts[0].description

cap = cv2.VideoCapture(0)
while cap.isOpened():
    ret, frame = cap.read()
    results = model(frame)[0]
    for box in results.boxes.xyxy.cpu().numpy():
        x1, y1, x2, y2 = map(int, box)
        roi = frame[y1:y2, x1:x2]
        text = extract_text(roi)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(frame, text, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 2)

    cv2.imshow("Live", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break
cap.release()
cv2.destroyAllWindows()
