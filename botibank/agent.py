import os
import ssl
import json
import base64
import urllib.parse
from dotenv import load_dotenv
import warnings
import httpx

# ☢️ BYPASS SSL (Para desarrollo local)
ssl.create_default_context = ssl._create_unverified_context
ssl._create_default_https_context = ssl._create_unverified_context

warnings.filterwarnings("ignore")
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_API_KEY"] = ""

load_dotenv()

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

# --- CONFIGURACIONES IDENTITY SERVER ---
WSO2_CLIENT_ID = os.getenv("WSO2_CLIENT_ID", "").strip()
WSO2_TOKEN_URL = os.getenv("WSO2_TOKEN_URL", "")
IDENTITY_SERVER_BASE_URL = WSO2_TOKEN_URL.replace("/oauth2/token", "") if WSO2_TOKEN_URL else "https://127.0.0.1:9446"
REDIRECT_URI = "http://127.0.0.1:5000/callback" 

# --- CONFIGURACIONES WSO2 API MANAGER (MCP & LLM Gateway) ---
WSO2_CONSUMER_KEY = os.getenv("WSO2_CONSUMER_KEY", "").strip()
WSO2_CONSUMER_SECRET = os.getenv("WSO2_CONSUMER_SECRET", "").strip()
WSO2_APIM_TOKEN_URL = os.getenv("WSO2_APIM_TOKEN_URL", "https://localhost:9443/oauth2/token").strip()
WSO2_MCP_URL = os.getenv("WSO2_MCP_URL", "https://localhost:8243/botibankmcp/1.0/mcp").strip()

FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "http://127.0.0.1:5000")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "hermes-2-pro-llama-3-8b")
LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:1234/v1")

# ==========================================
# FUNCIONES AUXILIARES (LOGIN Y JWT)
# ==========================================

def generar_instruccion_login(session_id: str, scopes: str) -> str:
    """Genera el enlace de Login usando el patrón ganador <URL>."""
    safe_client_id = WSO2_CLIENT_ID
    safe_redirect_uri = urllib.parse.quote(REDIRECT_URI, safe='')
    
    auth_link = (
        f"{IDENTITY_SERVER_BASE_URL}/oauth2/authorize?response_type=code"
        f"&client_id={safe_client_id}"
        f"&redirect_uri={safe_redirect_uri}"
        f"&scope={urllib.parse.quote(scopes)}"
        f"&state={session_id}"
    )
    
    return f"INSTRUCCIÓN OBLIGATORIA: Copia y pega EXACTAMENTE este texto en tu respuesta final, no lo resumas ni cambies una sola letra:\nPor favor, inicia sesión de forma segura para autorizar esta operación: <{auth_link}>"

def get_username_from_token(token: str) -> str:
    """Decodifica el JWT de usuario de IS para extraer la identidad."""
    try:
        payload_b64 = token.split('.')[1]
        padded = payload_b64 + '=' * (4 - len(payload_b64) % 4)
        claims = json.loads(base64.b64decode(padded).decode('utf-8'))
        username = claims.get("username", claims.get("sub", ""))
        if "@carbon.super" in username:
            username = username.split("@carbon.super")[0]
        return username
    except Exception as e:
        print(f"⚠️ Error extrayendo identidad del token: {e}")
        return "usuario_anonimo"

# ==========================================
# SEGURIDAD WSO2 API MANAGER (APIM)
# ==========================================

async def get_apim_access_token(scope: str = "") -> str:
    """Obtiene un Bearer Token de APIM usando Client Credentials para el Gateway."""
    credentials = f"{WSO2_CONSUMER_KEY}:{WSO2_CONSUMER_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"grant_type": "client_credentials"}
    if scope:
        data["scope"] = scope

    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.post(WSO2_APIM_TOKEN_URL, headers=headers, data=data)
        if resp.status_code != 200:
            raise Exception(f"APIM Token Rejected: {resp.text}")
        return resp.json().get("access_token")

async def invoke_mcp_tool(tool_name: str, arguments: dict, scope: str = "") -> str:
    """Ejecuta llamadas JSON-RPC al servidor MCP autenticándose primero con WSO2 APIM."""
    try:
        apim_token = await get_apim_access_token(scope)
    except Exception as e:
        return f"Error obteniendo token del APIM Gateway: {str(e)}"

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments}
    }
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {apim_token}"
    }
    
    try:
        print(f"   [📡 MCP REQUEST] Llamando a {tool_name} a través del APIM Gateway...")
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(WSO2_MCP_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            
            if "result" in data and "content" in data["result"]:
                content_list = data["result"]["content"]
                result_text = "\n".join([item.get("text", "") for item in content_list if item.get("type") == "text"])
                
                # 🔴 SEGURO ANTI-ALUCINACIÓN PARA RESULTADOS VACÍOS
                if not result_text.strip() or result_text.strip() == "[]":
                    return "RESULTADO: No hay datos registrados. El sistema devolvió una lista vacía. INFORMA AL USUARIO QUE NO TIENE CUENTAS/DATOS Y NO INVENTES NADA."
                    
                return result_text
                
            elif "error" in data:
                return f"MCP Error: {data['error']}"
            return json.dumps(data.get("result", data))
    except Exception as e:
        return f"Error conectando al servidor MCP: {str(e)}"

# ==========================================
# WSO2 MCP TOOLS
# ==========================================

@tool
async def get_clientes() -> str:
    """Listar todos los clientes."""
    return await invoke_mcp_tool("get_clientes", {}, "clientes:read")

@tool
async def post_clientes(id: str, nombre: str, apellido: str) -> str:
    """Agregar un cliente nuevo."""
    return await invoke_mcp_tool("post_clientes", {"requestBody": {"id": id, "nombre": nombre, "apellido": apellido}}, "clientes:write")

@tool
async def delete_clientes_by_clienteId(clienteId: str) -> str:
    """Eliminar un cliente."""
    return await invoke_mcp_tool("delete_clientes_by_clienteId", {"clienteId": clienteId}, "clientes:write")

@tool
async def get_cuentas(config: RunnableConfig) -> str:
    """Listar todas las cuentas del usuario autenticado."""
    configurable = config.get("configurable", {})
    user_token = configurable.get("user_token")
    session_id = configurable.get("session_id", "default")
    if not user_token:
        return generar_instruccion_login(session_id, "openid profile cuentas:read")
    
    username = get_username_from_token(user_token)
    return await invoke_mcp_tool("get_cuentas", {"clienteId": username}, "cuentas:read")

@tool
async def post_cuentas(cuentaId: str, config: RunnableConfig) -> str:
    """Agregar una cuenta nueva al sistema. El clienteId se asignará automáticamente."""
    configurable = config.get("configurable", {})
    user_token = configurable.get("user_token")
    session_id = configurable.get("session_id", "default")
    if not user_token:
        return generar_instruccion_login(session_id, "openid profile cuentas:write")
    
    username = get_username_from_token(user_token)
    return await invoke_mcp_tool("post_cuentas", {"requestBody": {"cuentaId": cuentaId, "clienteId": username}}, "cuentas:write")

@tool
async def delete_cuentas_by_cuentaId(cuentaId: str, clienteId: str) -> str:
    """Eliminar una cuenta."""
    return await invoke_mcp_tool("delete_cuentas_by_cuentaId", {"cuentaId": cuentaId, "clienteId": clienteId}, "cuentas:write")

@tool
async def get_cuentas_by_cuentaId_movimientos(cuentaId: str) -> str:
    """Ver los movimientos y saldo de la cuenta."""
    return await invoke_mcp_tool("get_cuentas_by_cuentaId_movimientos", {"cuentaId": cuentaId}, "cuentas:read")

@tool
async def post_cuentas_by_cuentaId_ingresar(cuentaId: str, monto: float) -> str:
    """Ingresar dinero a la cuenta por ventanilla."""
    return await invoke_mcp_tool("post_cuentas_by_cuentaId_ingresar", {"cuentaId": cuentaId, "requestBody": {"monto": monto}}, "cuentas:write")

@tool
async def post_cuentas_by_cuentaId_sacar(cuentaId: str, monto: float) -> str:
    """Sacar dinero de la cuenta."""
    return await invoke_mcp_tool("post_cuentas_by_cuentaId_sacar", {"cuentaId": cuentaId, "requestBody": {"monto": monto}}, "cuentas:write")

@tool
async def post_cuentas_by_cuentaId_transferir(cuentaId: str, cuentaDestino: str, monto: float, concepto: str, config: RunnableConfig) -> str:
    """Hacer una transferencia a otra cuenta."""
    configurable = config.get("configurable", {})
    user_token = configurable.get("user_token")
    session_id = configurable.get("session_id", "default")
    if not user_token:
        return generar_instruccion_login(session_id, "openid profile transfer:write")
    
    return await invoke_mcp_tool("post_cuentas_by_cuentaId_transferir", {"cuentaId": cuentaId, "requestBody": {"cuentaDestino": cuentaDestino, "monto": monto, "concepto": concepto}}, "transfer:write")

@tool
async def get_servicios() -> str:
    """Listar servicios disponibles para pagar."""
    return await invoke_mcp_tool("get_servicios", {}, "servicios:read")

@tool
async def post_servicios(codigoServicio: str, nombre: str, monto: float, vencimiento: str) -> str:
    """Agregar un servicio nuevo al sistema."""
    return await invoke_mcp_tool("post_servicios", {"requestBody": {"codigoServicio": codigoServicio, "nombre": nombre, "monto": monto, "vencimiento": vencimiento}}, "servicios:write")

@tool
async def delete_servicios_by_codigoServicio(codigoServicio: str) -> str:
    """Eliminar un servicio del sistema."""
    return await invoke_mcp_tool("delete_servicios_by_codigoServicio", {"codigoServicio": codigoServicio}, "servicios:write")

@tool
async def post_servicios_pagar(cuentaOrigen: str, codigoServicio: str, monto: float, config: RunnableConfig) -> str:
    """Pagar un servicio."""
    configurable = config.get("configurable", {})
    user_token = configurable.get("user_token")
    session_id = configurable.get("session_id", "default")
    if not user_token:
        return generar_instruccion_login(session_id, "openid profile service:pay")
    
    return await invoke_mcp_tool("post_servicios_pagar", {"requestBody": {"cuentaOrigen": cuentaOrigen, "codigoServicio": codigoServicio, "monto": monto}}, "service:pay")

@tool
async def get_hipotecas(clienteId: str) -> str:
    """Listar hipotecas de un cliente."""
    return await invoke_mcp_tool("get_hipotecas", {"clienteId": clienteId}, "hipotecas:read")

@tool
async def get_hipotecas_by_idHipoteca(idHipoteca: str) -> str:
    """Consultar el balance de una hipoteca específica."""
    return await invoke_mcp_tool("get_hipotecas_by_idHipoteca", {"idHipoteca": idHipoteca}, "hipotecas:read")

@tool
async def post_hipotecas(id: str, clienteId: str, monto: float, vencimiento: str, pagoParcial: float) -> str:
    """Otorgar (crear) una nueva hipoteca."""
    return await invoke_mcp_tool("post_hipotecas", {"requestBody": {"id": id, "clienteId": clienteId, "monto": monto, "vencimiento": vencimiento, "pagoParcial": pagoParcial}}, "hipotecas:write")

@tool
async def post_hipotecas_by_idHipoteca_pagar(idHipoteca: str, cuentaOrigen: str, monto: float, config: RunnableConfig) -> str:
    """Pagar cuota parcial de la hipoteca."""
    configurable = config.get("configurable", {})
    user_token = configurable.get("user_token")
    session_id = configurable.get("session_id", "default")
    if not user_token:
        return generar_instruccion_login(session_id, "openid profile mortgage:pay")
    
    return await invoke_mcp_tool("post_hipotecas_by_idHipoteca_pagar", {"idHipoteca": idHipoteca, "requestBody": {"cuentaOrigen": cuentaOrigen, "monto": monto}}, "mortgage:pay")

@tool
async def conocimiento_general(mensaje_literal_usuario: str) -> str:
    """ÚSALA SIEMPRE para preguntas generales. Enruta al proxy de WSO2 APIM Guardrails."""
    try:
        url = f"{FASTAPI_BASE_URL.strip()}/proxy/chat/completions"
        payload = {
            "model": LOCAL_LLM_MODEL,
            "messages": [{"role": "user", "content": mensaje_literal_usuario}],
            "temperature": 0.7
        }
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            datos = resp.json()
            if isinstance(datos, dict) and datos.get("type") == "SEMANTIC_PROMPT_GUARD":
                return "INSTRUCCIÓN OBLIGATORIA: Copia y pega EXACTAMENTE este texto en tu respuesta final, no lo resumas ni cambies una sola letra:\n🛡️ **Security Block (WSO2 APIM):** My corporate policies strictly prohibit discussing that topic."
            respuesta = datos["choices"][0]["message"]["content"]
            if "🛡️" in respuesta:
                return f"INSTRUCCIÓN OBLIGATORIA: Copia y pega EXACTAMENTE este texto en tu respuesta final, no lo resumas ni cambies una sola letra:\n{respuesta}"
            return respuesta
    except Exception as e:
        return f"Error conectando al AI Gateway: {str(e)}"

# ==========================================
def get_agent():
    llm = ChatOpenAI(
        base_url=LLM_BASE_URL, 
        api_key="lm-studio", 
        model=LOCAL_LLM_MODEL,
        temperature=0.0
    )
    
    herramientas = [
        get_clientes, post_clientes, delete_clientes_by_clienteId,
        get_cuentas, post_cuentas, delete_cuentas_by_cuentaId, get_cuentas_by_cuentaId_movimientos,
        post_cuentas_by_cuentaId_transferir, post_cuentas_by_cuentaId_ingresar, post_cuentas_by_cuentaId_sacar,
        get_servicios, post_servicios, delete_servicios_by_codigoServicio, post_servicios_pagar,
        get_hipotecas, get_hipotecas_by_idHipoteca, post_hipotecas, post_hipotecas_by_idHipoteca_pagar,
        conocimiento_general
    ]
    
    memory = MemorySaver()

    instrucciones = (
        "Eres el asistente ejecutivo de IA de BotiBank. Habla SIEMPRE en español.\n"
        "REGLA 1: Para saldos/movimientos -> usa 'get_cuentas_by_cuentaId_movimientos'. Para listar cuentas -> usa 'get_cuentas'.\n"
        "REGLA 2: Para transferencias -> usa 'post_cuentas_by_cuentaId_transferir'.\n"
        "REGLA 3: Para listar hipotecas -> usa 'get_hipotecas'. Para pagar hipotecas -> usa 'post_hipotecas_by_idHipoteca_pagar'.\n"
        "REGLA 4: Para pagar servicios -> usa 'post_servicios_pagar'.\n"
        "REGLA 5: Si el usuario dice que ya inició sesión, ejecuta el comando pendiente directamente sin pedirlo de nuevo.\n"
        "REGLA 6 (CRÍTICA): Si obtienes una 'INSTRUCCIÓN OBLIGATORIA' de una herramienta, DEBES imprimir su contenido EXACTAMENTE como se te entregó (respetando los símbolos < >), sin pensar ni modificar nada.\n"
        "REGLA 7: Para preguntas generales usa 'conocimiento_general'.\n"
        "REGLA 8 (ANTI-ALUCINACIÓN MÁXIMA): TIENES ESTRICTAMENTE PROHIBIDO inventar números de cuenta, saldos, nombres o datos. Solo puedes responder usando EXACTAMENTE la información JSON que te devuelve la herramienta (por ejemplo, debes mostrar 'CTA-122', no inventar '12345'). Si la herramienta dice que no hay datos, dile al usuario la verdad."
    )
    
    return create_react_agent(llm, herramientas, checkpointer=memory, prompt=instrucciones)