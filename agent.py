import os
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

# IMPORTANTE: Usamos OpenAI porque LM Studio emula su API nativamente
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

# Cargar variables de entorno
load_dotenv()

# Credenciales de WSO2 IS 
WSO2_TOKEN_URL = os.getenv("WSO2_TOKEN_URL", "https://127.0.0.1:9446/oauth2/token")
WSO2_CLIENT_ID = os.getenv("WSO2_CLIENT_ID")
WSO2_CLIENT_SECRET = os.getenv("WSO2_CLIENT_SECRET")
FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "http://127.0.0.1:8000")

# Variables del Modelo Local (LM Studio)
LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:1234/v1")
LOCAL_LLM_API_KEY = os.getenv("LOCAL_LLM_API_KEY", "lm-studio")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "hermes-2-pro-llama-3-8b")

def get_wso2_access_token(scope: str) -> str:
    """Solicita un Access Token a WSO2 Identity Server usando Client Credentials (M2M)."""
    if not all([WSO2_TOKEN_URL, WSO2_CLIENT_ID, WSO2_CLIENT_SECRET]):
        raise ValueError("Faltan variables de entorno de WSO2 en el Agente.")
        
    print(f"[🔐 WSO2 -> AGENTE] Solicitando token M2M con el scope: '{scope}'...")
    data = {
        'grant_type': 'client_credentials',
        'scope': scope
    }
    
    resp = requests.post(
        WSO2_TOKEN_URL,
        auth=HTTPBasicAuth(WSO2_CLIENT_ID, WSO2_CLIENT_SECRET),
        data=data,
        verify=False 
    )
    resp.raise_for_status()
    return resp.json().get("access_token")


# --- HERRAMIENTA 1: CLIMA (Mantiene Client Credentials) ---
@tool
def consultar_clima(ciudad: str) -> str:
    """Consulta el clima actual de una ciudad invocando el endpoint protegido de FastAPI."""
    print(f"\n[🌤️ TOOL] Agente usando herramienta de clima para: '{ciudad}'...")
    try:
        access_token = get_wso2_access_token(scope="weather:read")
        url = f"{FASTAPI_BASE_URL}/weather"
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"ciudad": ciudad}
        
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        datos = resp.json()
        
        temp = datos["current"]["temp_c"]
        cond = datos["current"]["condition"]["text"]
        return f"En {ciudad} hace {temp}°C y está {cond}."
    except Exception as e:
        print(f"\n❌ [ERROR INTERNO CLIMA]: {str(e)}")
        return f"Error en la herramienta de clima: {str(e)}"
    

# --- HERRAMIENTA 2: MÚSICA (Exige token de flujo interactivo) ---
@tool
def buscar_musica_por_animo(animo: str, config: RunnableConfig) -> str:
    """Busca una canción recomendada basada en un estado de ánimo o clima."""
    
    # Extraemos el token del usuario y el session_id desde el main.py
    configurable = config.get("configurable", {})
    user_token = configurable.get("user_token")
    session_id = configurable.get("session_id")
    
    # Si NO hay token, la herramienta ya devuelve el enlace listo con los brackets < >
    if not user_token:
        redirect_uri = "http://127.0.0.1:8000/callback"
        auth_base_url = "https://127.0.0.1:9446/oauth2/authorize"
        
        auth_link = (
            f"{auth_base_url}?response_type=code"
            f"&client_id={WSO2_CLIENT_ID}"
            f"&redirect_uri={redirect_uri}"
            f"&scope=music:read"
            f"&state={session_id}"
        )
        return f"REQUIRES_AUTH_LINK: <{auth_link}>"

    print(f"[🎵 TOOL] Agente buscando música para el clima '{animo}' utilizando el token OAuth2 del Usuario...")
    try:
        url = f"{FASTAPI_BASE_URL}/music"
        headers = {"Authorization": f"Bearer {user_token}"}
        params = {"animo": animo}
        
        resp = requests.get(url, headers=headers, params=params)
        
        # 🛠️ MICROCIRUGÍA 1: Si es 403, devolvemos un código que el LLM no puede "inventar"
        if resp.status_code == 403:
            return "RESULTADO_403: Su usuario no tiene acceso a la busqueda de canciones, verifique sus permisos."

        resp.raise_for_status()
        datos = resp.json()
        
        if datos.get("resultCount", 0) == 0:
            return f"No encontré canciones para el estado de ánimo '{animo}'."
            
        cancion = datos["results"][0]
        titulo = cancion["trackName"]
        artista = cancion["artistName"]
        url_link = cancion["trackViewUrl"]
        
        return f"Te recomiendo escuchar '{titulo}' de {artista}. Enlace: {url_link}"
    except Exception as e:
        print(f"\n❌ [ERROR INTERNO MÚSICA]: {str(e)}")
        return f"Error de autorización: El token de usuario ya no es válido. {str(e)}"


# --- CONSTRUCTOR DEL AGENTE ---
def create_agent():
    llm = ChatOpenAI(
        base_url=LOCAL_LLM_BASE_URL,
        api_key=LOCAL_LLM_API_KEY,
        model=LOCAL_LLM_MODEL,
        temperature=0.0
    )
    
    herramientas = [consultar_clima, buscar_musica_por_animo]
    memory = MemorySaver()

    # Optimizamos la REGLA 3 para evitar que el LLM oculte o elimine el enlace
    instrucciones = (
        "Eres un asistente corporativo automatizado de alta seguridad.\n"
        "REGLA 1: Para consultar el clima de una ciudad, usa la herramienta 'consultar_clima'.\n"
        "REGLA 2: Para recomendar música basada en el clima o ánimo, usa la herramienta 'buscar_musica_por_animo'.\n"
        "REGLA 3 (CRÍTICA): Si la herramienta 'buscar_musica_por_animo' te devuelve un texto que contiene un enlace entre '<' y '>', DEBES copiar e imprimir ese enlace EXACTAMENTE igual en tu respuesta final (manteniendo los símbolos '<' y '>'). NO omitas el enlace, el frontend lo necesita textualmente para construir el botón de login.\n"
        "REGLA 4 (CRÍTICA): Si el usuario regresa al chat indicando que ya inició sesión, que completó la autenticación, o te pide continuar, DEBES INVOCAR INMEDIATAMENTE la herramienta 'buscar_musica_por_animo'. Revisa el historial para recordar qué clima hacía y úsalo como el argumento 'animo'.\n"
        "REGLA 5 (ESTRICTA): BAJO NINGUNA CIRCUNSTANCIA le pidas al usuario códigos de autorización o enlaces en el chat.\n"
        "REGLA 6 (CRÍTICA): ÚNICAMENTE si la herramienta 'buscar_musica_por_animo' te devuelve un texto que empieza con 'RESULTADO_403:', DEBES mostrar el resto de ese mensaje textualmente en el chat y terminar. NUNCA menciones problemas de permisos si no has llamado a la herramienta primero."
    )
    
    agent_graph = create_react_agent(
        model=llm,
        tools=herramientas,
        checkpointer=memory,
        prompt=instrucciones
    )
    
    return agent_graph