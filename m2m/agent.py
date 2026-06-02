import os
import ssl
import urllib.parse
from dotenv import load_dotenv

# ☢️ BYPASS SSL SÚPER NUCLEAR (Para desarrollo local con WSO2)
ssl.create_default_context = ssl._create_unverified_context
ssl._create_default_https_context = ssl._create_unverified_context

os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_API_KEY"] = ""

load_dotenv()

# =====================================================================
# 🕵️‍♂️ MODO SNIFFER 2.0: EXTRACCIÓN PROFUNDA DE PAYLOADS
# =====================================================================
import httpx
import requests

_original_httpx_send = httpx.AsyncClient.send

async def _intercept_httpx_send(self, request, *args, **kwargs):
    print("\n" + "🔥"*30)
    print(f"👉 [HTTPX REQUEST] {request.method} {request.url}")
    print(f"📦 [HEADERS]: {dict(request.headers)}")
    
    # 🔴 LECTURA DE PAYLOAD MEJORADA Y A PRUEBA DE FALLOS
    try:
        await request.aread()  # Forzamos la lectura del stream
        body_bytes = request.content
        
        if body_bytes:
            # Decodificamos reemplazando caracteres raros para que no crashee
            raw_payload = body_bytes.decode('utf-8', errors='replace')
            print(f"📄 [RAW PAYLOAD]: {raw_payload}")
            
            # Si es form-urlencoded (el estándar de OAuth2), lo parseamos bonito
            content_type = request.headers.get("content-type", "")
            if "application/x-www-form-urlencoded" in content_type:
                parsed_data = urllib.parse.parse_qs(raw_payload)
                print(f"🧩 [FORM DATA PARSEADA]:")
                for key, value in parsed_data.items():
                    print(f"   - {key}: {value}")
        else:
            print("📄 [BODY PAYLOAD]: (Cuerpo vacío)")
            
    except Exception as e:
        print(f"📄 [BODY PAYLOAD RAW]: {request.content} (Error al decodificar: {e})")
        
    # Ejecutamos la petición real
    response = await _original_httpx_send(self, request, *args, **kwargs)
    
    print(f"\n👈 [HTTPX RESPONSE] CODE: {response.status_code}")
    try:
        await response.aread()
        print(f"📄 [RESPONSE BODY]: {response.text}")
    except Exception as e:
        print(f"📄 [RESPONSE BODY RAW]: Error leyendo body {e}")
    print("🔥"*30 + "\n")
    return response

httpx.AsyncClient.send = _intercept_httpx_send
# =====================================================================

# SDKs Oficiales
from asgardeo import AsgardeoConfig
from asgardeo_ai import AgentConfig, AgentAuthManager

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

IDENTITY_SERVER_CONFIG = AsgardeoConfig(
    base_url=os.getenv("IDENTITY_SERVER_BASE_URL"),
    client_id=os.getenv("CLIENT_ID"),
    client_secret=os.getenv("CLIENT_SECRET"),
    redirect_uri=os.getenv("REDIRECT_URI").strip()
)

AGENT_CONFIG = AgentConfig(
    agent_id=os.getenv("AGENT_ID"),
    agent_secret=os.getenv("AGENT_SECRET")
)

FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:1234/v1")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "hermes-2-pro-llama-3-8b")

# --- HERRAMIENTAS DEL AGENTE ---

@tool
async def consultar_clima_seguro(ciudad: str) -> str:
    """Consulta el clima usando la autenticación nativa de Agente de WSO2 Identity Server."""
    try:
        print(f"\n[🤖 AGENT AUTH] Iniciando secuencia de autenticación con AgentAuthManager...")
        print(f"App Client ID: {IDENTITY_SERVER_CONFIG.client_id}")
        print(f"Agent ID: {AGENT_CONFIG.agent_id}")
        
        async with AgentAuthManager(IDENTITY_SERVER_CONFIG, AGENT_CONFIG) as auth_manager:
            agent_token = await auth_manager.get_agent_token(["weather:read"])
            
        print("✅ [WSO2] Token de Agente obtenido con éxito.")
        headers = {"Authorization": f"Bearer {agent_token.access_token}"}
        
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(f"{FASTAPI_BASE_URL}/api/weather", headers=headers, params={"ciudad": ciudad})
            resp.raise_for_status()
            datos = resp.json()
            
        return f"En {ciudad} hace {datos['temp']}°C y está {datos['condicion']}."
    except Exception as e:
        print(f"❌ [ERROR DE AUTENTICACIÓN DE AGENTE]: {str(e)}")
        return f"Error en la autenticación federada del Agente: {str(e)}"

@tool
def conocimiento_general(pregunta: str) -> str:
    """Responde preguntas generales."""
    llm = ChatOpenAI(
        base_url=LLM_BASE_URL, 
        api_key="lm-studio", 
        model=LOCAL_LLM_MODEL, 
        temperature=0.7
    )
    return llm.invoke(pregunta).content

# --- CONSTRUCTOR DEL AGENTE ---
def get_agent():
    llm = ChatOpenAI(
        base_url=LLM_BASE_URL, 
        api_key="lm-studio", 
        model=LOCAL_LLM_MODEL, 
        temperature=0.0
    )
    
    tools = [consultar_clima_seguro, conocimiento_general]
    memory = MemorySaver()
    
    instrucciones = (
        "Eres un asistente virtual eficiente conectado a WSO2 Identity Server.\n"
        "1. Usa OBLIGATORIAMENTE 'consultar_clima_seguro' para preguntas sobre el clima.\n"
        "2. Usa 'conocimiento_general' para cualquier otra duda o tema."
    )
    
    return create_react_agent(llm, tools, checkpointer=memory, prompt=instrucciones)