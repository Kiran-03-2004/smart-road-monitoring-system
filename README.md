# AI-Powered Smart Road Infrastructure Monitoring and Pothole Severity Analysis System

A Smart City infrastructure monitoring platform built around a trained YOLOv8
pothole detector. It detects potholes in real time, tracks and de-duplicates
them, estimates severity, captures GPS location, reverse-geocodes to place
names, computes a road-health score, stores everything in SQLite, and produces
interactive maps, weighted heatmaps, and municipal PDF reports — all surfaced
through a Streamlit dashboard.

## Model

The system wraps an existing model at `model/final_pothole_detector.pt`.

| Metric | Value |
| --- | --- |
| Precision | 85.26% |
| Recall | 68.68% |
| mAP@50 | 79.81% |
| mAP@50-95 | 50.37% |

## Features

1. Real-time webcam / video / image detection (OpenCV + Ultralytics YOLOv8).
2. Object tracking (IoU + Hungarian assignment) to prevent duplicate counting.
3. Severity classification (Low / Medium / High / Critical) from bounding-box area.
4. Road-health scoring with rating and municipal maintenance priority.
5. GPS tracking (simulated now, replaceable with a real device later).
6. Cached reverse geocoding (road / city / state) via geopy.
7. SQLite persistence with `TRIPS`, `DETECTIONS`, and `REPORTS` tables.
8. Color-coded folium route maps.
9. Severity-weighted folium heatmaps.
10. Municipal PDF reports (reportlab).
11. Streamlit dashboard: Dashboard, Live Monitoring, Maps, Heatmaps, Reports, Settings.

## Project Structure

```
smart-road-monitoring-system/
├── app.py                     # Streamlit dashboard (entry point)
├── config.py                  # Central configuration
├── requirements.txt
├── README.md
├── model/
│   └── final_pothole_detector.pt
├── database/                  # SQLite database (auto-created)
├── data/                      # CSV log + geocode cache (auto-created)
├── reports/                   # Generated PDFs (auto-created)
├── maps/                      # Saved HTML maps (auto-created)
├── captures/potholes/         # Saved pothole snapshots (auto-created)
├── logs/                      # Rotating application logs (auto-created)
└── src/
    ├── detector.py            # YOLOv8 inference + pipeline orchestration
    ├── tracker.py             # IoU-based multi-object tracker (de-dup)
    ├── severity.py            # Bounding-box-area severity classification
    ├── gps_tracker.py         # Simulated (replaceable) GPS source
    ├── geocoder.py            # Cached reverse geocoding
    ├── road_health.py         # Road-health scoring
    ├── database.py            # SQLite persistence layer
    ├── map_generator.py       # folium route maps
    ├── heatmap_generator.py   # Weighted folium heatmaps
    ├── report_generator.py    # Municipal PDF reports
    └── utils.py               # Logging + shared helpers
```

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows PowerShell
# source venv/bin/activate   # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt
```

Ensure `model/final_pothole_detector.pt` is present.

## Running

```bash
streamlit run app.py
```

Then open the URL Streamlit prints (default http://localhost:8501).

- Use **Live Monitoring** to run detection on an image, video, or local webcam.
  Webcam capture only works when the app runs on your own machine.
- **Dashboard**, **Maps**, **Heatmaps**, and **Reports** read from the SQLite
  database populated by monitoring sessions.

### Quick model smoke test

```bash
python test_model.py
```

## Severity Rules

Severity is derived from the detection bounding-box area (pixels):

| Area (px) | Severity |
| --- | --- |
| `< 3000` | Low |
| `3000 – 8000` | Medium |
| `8000 – 15000` | High |
| `>= 15000` | Critical |

## Road-Health Score

```
score = 100
        - (critical * 8)
        - (high     * 6)
        - (medium   * 3)
        - (low      * 1)
```

Clamped to a minimum of 0 and classified as:

| Score | Rating |
| --- | --- |
| `>= 90` | Excellent |
| `>= 70` | Good |
| `>= 50` | Moderate |
| `< 50` | Poor |

## Configuration

All tunables live in `config.py` and can be overridden via environment
variables (see `.env.example`): detection thresholds, device (`cpu`/`cuda`),
GPS origin, geocoder settings, and tracker parameters.

## Replacing Simulated GPS

`src/gps_tracker.py` defines `BaseGPSTracker`. To use a real device, subclass
it, implement `get_current_location()`, and return your implementation from
`create_gps_tracker()`. No caller changes are required.

## Cloud Deployment (prepared)

The codebase is deployment-ready:

- Directory creation is automatic and idempotent (`config.ensure_directories`).
- Configuration is environment-driven (`.env` / environment variables).
- The database path is configurable for a mounted volume or managed store.
- For hosted deployments, disable webcam capture (browser sandboxes block it)
  and drive detection from uploaded video/images.
- Package with a container image; set `DEVICE=cpu` unless a GPU is available.

## Notes

- Reverse geocoding uses the public Nominatim service and is rate-limited and
  cached. It degrades gracefully to coordinate labels when offline.
- Object tracking counts each physical pothole once by only persisting a
  detection on the frame a track first becomes confirmed.
