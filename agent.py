import os
# ☢️ EL BOTÓN NUCLEAR: Apagado maestro de OpenTelemetry y LangSmith
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["OTEL_TRACES_EXPORTER"] = "none"
os.environ["OTEL_METRICS_EXPORTER"] = "none"
os.environ["OTEL_LOGS_EXPORTER"] = "none"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_API_KEY"] = ""

import requests
import urllib.parse
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

from requests.auth import HTTPBasicAuth
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

# Credenciales de WSO2 IL
WSO2_TOKEN_URL = os.getenv("WSO2_TOKEN_URL")
WSO2_CLIENT_ID = os.getenv("WSO2_CLIENT_ID")
WSO2_CLIENT_SECRET = os.getenv("WSO2_CLIENT_SECRET")
FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL")

# Variables del Modelo Local
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL")

def get_wso2_access_token(scope: str) -> str:
    """Solicita un Access Token a WSO2 Identity Server usando Client Credentials (M2M)."""
    client_id_safe = WSO2_CLIENT_ID.strip() if WSO2_CLIENT_ID else ""
    client_secret_safe = WSO2_CLIENT_SECRET.strip() if WSO2_CLIENT_SECRET else ""
    token_url_safe = WSO2_TOKEN_URL.strip() if WSO2_TOKEN_URL else ""

    if not all([token_url_safe, client_id_safe, client_secret_safe]):
        raise ValueError("Faltan variables de entorno de WSO2 en el Agente.")
        
    print(f"[🔐 WSO2 -> AGENTE] Solicitando token M2M con el scope: '{scope}'...")
    data = {
        'grant_type': 'client_credentials',
        'scope': scope
    }
    
    resp = requests.post(
        token_url_safe,
        auth=HTTPBasicAuth(client_id_safe, client_secret_safe),
        data=data,
        verify=False 
    )
    resp.raise_for_status()
    return resp.json().get("access_token")


# --- HERRAMIENTA 1: CLIMA ---
@tool
def consultar_clima(ciudad: str) -> str:
    """Consulta el clima actual de una ciudad invocando el endpoint protegido de FastAPI."""
    print(f"\n[🌤️ TOOL] Agente usando herramienta de clima para: '{ciudad}'...")
    try:
        access_token = get_wso2_access_token(scope="weather:read")
        url = f"{FASTAPI_BASE_URL.strip()}/weather"
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
    

# --- HERRAMIENTA 2: MÚSICA ---
@tool
def buscar_musica_por_animo(animo: str, config: RunnableConfig) -> str:
    """Busca una canción recomendada basada en un estado de ánimo o clima."""
    
    configurable = config.get("configurable", {})
    user_token = configurable.get("user_token")
    session_id = configurable.get("session_id")
    
    if not user_token:
        redirect_uri = "http://127.0.0.1:8000/callback"
        auth_base_url = "https://127.0.0.1:9446/oauth2/authorize"
        
        safe_client_id = WSO2_CLIENT_ID.strip() if WSO2_CLIENT_ID else ""
        safe_redirect_uri = urllib.parse.quote(redirect_uri, safe='')
        
        auth_link = (
            f"{auth_base_url}?response_type=code"
            f"&client_id={safe_client_id}"
            f"&redirect_uri={safe_redirect_uri}"
            f"&scope=music:read"
            f"&state={session_id}"
        )
        # 🔴 TRUCO: Instrucción imperativa directa para obligar al modelo a pintar la URL
        return f"INSTRUCCIÓN OBLIGATORIA: Copia y pega EXACTAMENTE este texto en tu respuesta final, no lo resumas ni cambies una sola letra:\nPor favor, inicia sesión de forma segura para autorizar el acceso a las recomendaciones musicales: <{auth_link}>"
    
    print(f"[🎵 TOOL] Agente buscando música para el clima '{animo}' utilizando el token OAuth2 del Usuario...")
    try:
        url = f"{FASTAPI_BASE_URL.strip()}/music"
        headers = {"Authorization": f"Bearer {user_token}"}
        params = {"animo": animo}
        
        resp = requests.get(url, headers=headers, params=params)
        
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
        
        return f"Te recomiendo escuchar '{titulo}' de {artista}. Enlace: <{url_link}>"
    except Exception as e:
        print(f"\n❌ [ERROR INTERNO MÚSICA]: {str(e)}")
        return f"Error de autorización: El token de usuario ya no es válido. {str(e)}"


# --- HERRAMIENTA 3: TRADUCTOR ---
@tool
def traducir_texto(texto: str, idioma_destino: str) -> str:
    """Traduce un texto al idioma especificado utilizando el modelo de lenguaje."""
    print(f"\n[🌍 TOOL] Agente usando herramienta de traducción al '{idioma_destino}'...")
    try:
        traductor_llm = ChatOpenAI(
            base_url=f"{FASTAPI_BASE_URL.strip()}/proxy", 
            api_key="wso2-apim-proxy", 
            model=LOCAL_LLM_MODEL.strip() if LOCAL_LLM_MODEL else "hermes-2-pro-llama-3-8b",
            temperature=0.1
        )
        
        prompt = f"Traduce el siguiente texto al {idioma_destino}. Responde ÚNICAMENTE con la traducción, sin añadir explicaciones ni comentarios extra:\n\n{texto}"
        respuesta = traductor_llm.invoke(prompt)
        return respuesta.content
    except Exception as e:
        print(f"\n❌ [ERROR INTERNO TRADUCCIÓN]: {str(e)}")
        return f"Error al intentar traducir: {str(e)}"


# --- HERRAMIENTA 4: CONOCIMIENTO GENERAL (CATCH-ALL) ---
@tool
def conocimiento_general(pregunta: str) -> str:
    """ÚSALA SIEMPRE para responder a preguntas generales. Extrae la pregunta original del usuario textualmente."""
    print(f"\n[🧠 TOOL] Agente usando herramienta de conocimiento general para: '{pregunta}'...")
    try:
        general_llm = ChatOpenAI(
            base_url=f"{FASTAPI_BASE_URL.strip()}/proxy", 
            api_key="wso2-apim-proxy", 
            model=LOCAL_LLM_MODEL.strip() if LOCAL_LLM_MODEL else "hermes-2-pro-llama-3-8b",
            temperature=0.7 
        )
        
        # 🔴 FIX SEMÁNTICO: Enviamos la pregunta CRUDA para que el Guardarraíl de WSO2 la detecte
        respuesta = general_llm.invoke(pregunta)
        
        # 🔴 FIX ORQUESTADOR: Si el APIM nos bloquea y devuelve el escudo, forzamos la orden imperativa
        if "🛡️" in respuesta.content:
            return f"INSTRUCCIÓN OBLIGATORIA: Copia y pega EXACTAMENTE este texto en tu respuesta final, no lo resumas ni cambies una sola letra:\n{respuesta.content}"
            
        return respuesta.content
    except Exception as e:
        print(f"\n❌ [ERROR INTERNO CONOCIMIENTO GENERAL]: {str(e)}")
        return f"Error al consultar el modelo: {str(e)}"


# --- CONSTRUCTOR DEL AGENTE ---
def create_agent():
    llm = ChatOpenAI(
        base_url=f"{FASTAPI_BASE_URL.strip()}/proxy", 
        api_key="wso2-apim-proxy", 
        model=LOCAL_LLM_MODEL.strip() if LOCAL_LLM_MODEL else "hermes-2-pro-llama-3-8b",
        temperature=0.0
    )
    
    herramientas = [consultar_clima, buscar_musica_por_animo, traducir_texto, conocimiento_general]
    memory = MemorySaver()

    # 🔴 MICRO-CIRUGÍA: Reescritura total del prompt. Modo "Dictador" activado.
    instrucciones = (
        "Eres un ORQUESTADOR ESTRICTO Y ENRUTADOR. TIENES PROHIBIDO USAR TU PROPIO CONOCIMIENTO PARA RESPONDER PREGUNTAS.\n"
        "REGLA 1: Clima -> usa 'consultar_clima'.\n"
        "REGLA 2: Música -> usa 'buscar_musica_por_animo'.\n"
        "REGLA 3 (CRÍTICA): Si una herramienta devuelve una 'INSTRUCCIÓN OBLIGATORIA', deja de pensar y limítate a copiar y pegar el texto EXACTAMENTE igual en tu respuesta, respetando obligatoriamente los símbolos '<' y '>'.\n"
        "REGLA 4: Si el usuario dice que ya inició sesión, invoca inmediatamente 'buscar_musica_por_animo'.\n"
        "REGLA 5: NUNCA pidas códigos ni URLs de autorización.\n"
        "REGLA 6: Errores 403 de herramientas se muestran textualmente.\n"
        "REGLA 7: Traducción -> usa 'traducir_texto'.\n"
        "REGLA 8 (MÁXIMA PRIORIDAD): Para ABSOLUTAMENTE CUALQUIER OTRA PREGUNTA o conversación (ej. ¿qué es el tenis?, deportes, historia, saludos, explicar conceptos, etc.), DEBES usar OBLIGATORIAMENTE la herramienta 'conocimiento_general'. Envía a la herramienta la pregunta original del usuario textualmente. NUNCA respondas directamente sin invocar esta herramienta primero."
    )
    
    agent_graph = create_react_agent(
        model=llm,
        tools=herramientas,
        checkpointer=memory,
        prompt=instrucciones
    )
    
    return agent_graph