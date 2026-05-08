import os
import requests
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_mistralai import ChatMistralAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

# Cargar variables de entorno
load_dotenv()

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

if not WEATHER_API_KEY or not MISTRAL_API_KEY:
    raise ValueError("❌ ERROR CRÍTICO: Faltan credenciales. Asegúrate de que el archivo .env existe y contiene WEATHER_API_KEY y MISTRAL_API_KEY.")

# --- HERRAMIENTA 1: CLIMA ---
@tool
def consultar_clima(ciudad: str) -> str:
    """Consulta el clima actual de una ciudad. Útil para saber si hace sol, llueve o hace frío."""
    print(f"\n[🌤️  CLIMA] Consultando clima en {ciudad}...")
    url = "http://api.weatherapi.com/v1/current.json"
    params = {"key": WEATHER_API_KEY, "q": ciudad, "lang": "es"}
    
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status() 
        datos = resp.json()
        
        temp = datos["current"]["temp_c"]
        cond = datos["current"]["condition"]["text"]
        return f"En {ciudad} hace {temp}°C y está {cond}."
    except Exception as e:
        return f"Error de conexión con WeatherAPI: {str(e)}"

# --- HERRAMIENTA 2: MÚSICA (Vía iTunes) ---
@tool
def buscar_musica_por_animo(animo: str) -> str:
    """
    Busca una canción recomendada basada en un estado de ánimo o clima.
    Ejemplo de entrada: 'lluvia', 'sol', 'fiesta', 'música tranquila'.
    """
    print(f"[🎵 MÚSICA] Buscando recomendaciones para: '{animo}'...")
    url = "https://itunes.apple.com/search"
    params = {"term": animo, "media": "music", "entity": "song", "limit": 1}
    
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        datos = resp.json()
        
        if datos["resultCount"] == 0:
            return "No encontré canciones para ese estado de ánimo."
            
        cancion = datos["results"][0]
        titulo = cancion["trackName"]
        artista = cancion["artistName"]
        url_link = cancion["trackViewUrl"]
        
        return f"Te recomiendo escuchar '{titulo}' de {artista}. Enlace: {url_link}"
    except Exception as e:
        return f"Error al buscar música: {str(e)}"

# --- CONSTRUCTOR DEL AGENTE ---
def create_agent():
    llm = ChatMistralAI(
        api_key=MISTRAL_API_KEY,
        model="mistral-large-latest",
        temperature=0.0
    )
    
    herramientas = [consultar_clima, buscar_musica_por_animo]
    
    # Checkpointer para guardar la memoria de las sesiones (thread_id)
    memory = MemorySaver()
    
    instrucciones = (
        "Eres un asistente conversacional útil y experto.\n"
        "REGLA 1: Si el usuario pregunta por el clima, usa la herramienta de clima.\n"
        "REGLA 2: Si pide música basada en el clima, usa primero el clima y luego busca música.\n"
        "REGLA 3: Redacta siempre una respuesta final amigable para el usuario con los datos obtenidos."
    )
    
    # Creamos el grafo del agente inyectando la memoria y el prompt del sistema
    agent_graph = create_react_agent(
        model=llm,           # <-- (Opcional) En versiones nuevas, el parámetro se llama formalmente 'model'
        tools=herramientas,
        checkpointer=memory,
        prompt=instrucciones # <-- ¡EL CAMBIO ESTÁ AQUÍ! Reemplazamos state_modifier por prompt
    )
    
    return agent_graph