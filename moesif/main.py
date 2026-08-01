import os
import time  # <-- Importamos time para medir el rendimiento
from fastapi import FastAPI, HTTPException, Header, Request # <-- Importamos Request
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime
from dotenv import load_dotenv

# ==========================================
# 1. Cargar variables de entorno (.env)
# ==========================================
load_dotenv()

# ==========================================
# 2. Definición de Modelos (Pydantic)
# ==========================================
class MetricValue(BaseModel):
    feature: str
    value: float 
    direction: Optional[str] = None 

class MoesifAlertPayload(BaseModel):
    type: str
    name: str
    metric: str
    grouping_feature_level1: Optional[str] = None
    grouping_feature_level2: Optional[str] = None
    metric_values: List[MetricValue]
    timestamp: datetime
    history: Optional[Dict[str, List[MetricValue]]] = None

# ==========================================
# 3. Inicialización de la App FastAPI
# ==========================================
app = FastAPI(
    title="Moesif Webhook Receiver",
    description="Servicio para recibir y procesar alertas de Moesif"
)

# ==========================================
# 4. MIDDLEWARE: Medidor de tiempo
# ==========================================
@app.middleware("http")
async def log_process_time(request: Request, call_next):
    # Inicia el cronómetro (perf_counter es el más preciso para medir tiempos cortos)
    start_time = time.perf_counter()
    
    # Pasa la petición al endpoint correspondiente
    response = await call_next(request)
    
    # Detiene el cronómetro y calcula la diferencia
    process_time = time.perf_counter() - start_time
    process_time_ms = process_time * 1000 # Lo pasamos a milisegundos
    
    # Imprime el tiempo justo antes de que Uvicorn lance su log "200 OK"
    print(f"⏱️  [Rendimiento] {request.method} {request.url.path} completado en {process_time_ms:.2f} ms")
    
    # (Opcional pero recomendado) Agrega el tiempo como cabecera oculta en la respuesta
    response.headers["X-Process-Time-Ms"] = str(round(process_time_ms, 2))
    
    return response

# ==========================================
# 5. Endpoint POST (El Webhook para Moesif)
# ==========================================
@app.post("/moesif-webhook", status_code=200)
async def receive_moesif_alert(
    payload: MoesifAlertPayload, 
    x_moesif_secret: Optional[str] = Header(None) 
):
    expected_secret = os.getenv("MOESIF_SECRET")

    # Validación de seguridad
    if not expected_secret or x_moesif_secret != expected_secret:
        print("❌ Intento de acceso no autorizado detectado.")
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid Secret")

    # Procesamiento si la seguridad es correcta
    print("\n" + "="*50)
    print(f"✅ ACCESO AUTORIZADO - NUEVA ALERTA 🚨")
    print("="*50)
    
    print("📦 PAYLOAD COMPLETO RECIBIDO EN FORMATO JSON:")
    if hasattr(payload, 'model_dump_json'):
        print(payload.model_dump_json(indent=4))
    else:
        print(payload.json(indent=4))
    print("="*50 + "\n")

    return {
        "status": "success", 
        "message": f"Alerta '{payload.name}' procesada correctamente"
    }

# ==========================================
# 6. Ejecución directa con Python
# ==========================================
if __name__ == "__main__":
    import uvicorn
    
    HOST = os.getenv("APP_HOST", "127.0.0.1")
    PORT = int(os.getenv("APP_PORT", 1030))
    
    print(f"🚀 Iniciando servidor FastAPI en http://{HOST}:{PORT}")
    
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)