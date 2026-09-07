# test_model.py

from ultralytics import YOLO

model = YOLO(
    "model/final_pothole_detector.pt"
)

results = model(
    "No_pothole.jpg",
    save=True
)

print("Detection Complete")