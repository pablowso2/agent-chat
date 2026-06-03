import os
import requests
import json
import urllib.parse
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
import warnings

# Limpieza de consola
warnings.filterwarnings("ignore")
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_API_KEY"] = ""

load_dotenv()

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

# --- CONFIGURACIONES ---
WSO2_MCP_URL = os.getenv("WSO2_MCP_URL", "https://localhost:8243/botibank/1.0/mcp")
WSO2_APIM_TOKEN_URL = os.getenv("WSO2_APIM_TOKEN_URL")
WSO2_CONSUMER_KEY = os.getenv("WSO2_CONSUMER_KEY")
WSO2_CONSUMER_SECRET = os.getenv("WSO2_CONSUMER_SECRET")

WSO2_CLIENT_ID = os.getenv("WSO2_CLIENT_ID")
FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "http://127.0.0.1:5000")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "hermes-2-pro-llama-3-8b")


# ==========================================
# FUNCIONES AUXILIARES (AUTH Y MCP)
# ==========================================

def get_mcp_m2m_token() -> str:
    """Solicita un Access Token M2M al API Manager para consultar el MCP en operaciones de lectura."""
    resp = requests.post(
        WSO2_APIM_TOKEN_URL,
        auth=HTTPBasicAuth(WSO2_CONSUMER_KEY, WSO2_CONSUMER_SECRET),
        data={'grant_type': 'client_credentials'},
        verify=False 
    )
    resp.raise_for_status()
    return resp.json().get("access_token")

def check_user_auth(config: RunnableConfig, scope: str = "default"):
    """Interceptor de Seguridad: Verifica si hay token, si no, devuelve la instrucción obligatoria de Login."""
    configurable = config.get("configurable", {})
    user_token = configurable.get("user_token")
    session_id = configurable.get("session_id", "default_session")
    
    if not user_token:
        print(f"[🔐 AUTH REQUIRED] Solicitando WSO2 Login para el scope: {scope}...")
        safe_client_id = WSO2_CLIENT_ID.strip() if WSO2_CLIENT_ID else ""
        safe_redirect_uri = urllib.parse.quote(f"{FASTAPI_BASE_URL.strip()}/callback", safe='')
        auth_link = f"https://127.0.0.1:9446/oauth2/authorize?response_type=code&client_id={safe_client_id}&redirect_uri={safe_redirect_uri}&scope={scope}&state={session_id}"
        
        instruccion = f"INSTRUCCIÓN OBLIGATORIA: Copia y pega EXACTAMENTE este texto en tu respuesta final:\nFor security reasons, I need your authorization to proceed. Please log in here: <{auth_link}>"
        return None, instruccion
    
    return user_token, None

def invoke_mcp_tool(tool_name: str, arguments: dict, token: str) -> str:
    """Función central (Core) que ejecuta llamadas JSON-RPC al servidor MCP de WSO2."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    try:
        print(f"   [📡 MCP REQUEST] Llamando a {tool_name}...")
        resp = requests.post(WSO2_MCP_URL, json=payload, headers=headers, verify=False)
        resp.raise_for_status()
        data = resp.json()
        
        if "result" in data and "content" in data["result"]:
            content_list = data["result"]["content"]
            text_outputs = [item.get("text", "") for item in content_list if item.get("type") == "text"]
            return "\n".join(text_outputs)
        elif "error" in data:
            return f"MCP Error: {data['error']}"
            
        return json.dumps(data.get("result", data))
    except Exception as e:
        return f"Error conectando al servidor MCP: {str(e)}"

# ==========================================
# WSO2 MCP TOOLS (ADAPTADORES LANGCHAIN)
# ==========================================

# --- CLIENTES ---
@tool
def get_clientes() -> str:
    """Listar todos los clientes."""
    token = get_mcp_m2m_token()
    return invoke_mcp_tool("get_clientes", {}, token)

@tool
def post_clientes(id: str, nombre: str, apellido: str, config: RunnableConfig) -> str:
    """Agregar un cliente nuevo."""
    token, auth_msg = check_user_auth(config, "clientes:write")
    if auth_msg: return auth_msg
    args = {"requestBody": {"id": id, "nombre": nombre, "apellido": apellido}}
    return invoke_mcp_tool("post_clientes", args, token)

@tool
def delete_clientes_by_clienteId(clienteId: str, config: RunnableConfig) -> str:
    """Eliminar un cliente."""
    token, auth_msg = check_user_auth(config, "clientes:write")
    if auth_msg: return auth_msg
    args = {"clienteId": clienteId}
    return invoke_mcp_tool("delete_clientes_by_clienteId", args, token)

# --- CUENTAS ---
@tool
def post_cuentas(cuentaId: str, clienteId: str, config: RunnableConfig) -> str:
    """Agregar una cuenta nueva."""
    token, auth_msg = check_user_auth(config, "cuentas:write")
    if auth_msg: return auth_msg
    args = {"requestBody": {"cuentaId": cuentaId, "clienteId": clienteId}}
    return invoke_mcp_tool("post_cuentas", args, token)

@tool
def delete_cuentas_by_cuentaId(cuentaId: str, clienteId: str, config: RunnableConfig) -> str:
    """Eliminar una cuenta."""
    token, auth_msg = check_user_auth(config, "cuentas:write")
    if auth_msg: return auth_msg
    args = {"cuentaId": cuentaId, "clienteId": clienteId}
    return invoke_mcp_tool("delete_cuentas_by_cuentaId", args, token)

@tool
def get_cuentas_by_cuentaId_movimientos(cuentaId: str) -> str:
    """Ver los movimientos y saldo de la cuenta."""
    token = get_mcp_m2m_token()
    args = {"cuentaId": cuentaId}
    return invoke_mcp_tool("get_cuentas_by_cuentaId_movimientos", args, token)

@tool
def post_cuentas_by_cuentaId_ingresar(cuentaId: str, monto: float, config: RunnableConfig) -> str:
    """Ingresar dinero a la cuenta por ventanilla."""
    token, auth_msg = check_user_auth(config, "cuentas:write")
    if auth_msg: return auth_msg
    args = {"cuentaId": cuentaId, "requestBody": {"monto": monto}}
    return invoke_mcp_tool("post_cuentas_by_cuentaId_ingresar", args, token)

@tool
def post_cuentas_by_cuentaId_sacar(cuentaId: str, monto: float, config: RunnableConfig) -> str:
    """Sacar dinero de la cuenta."""
    token, auth_msg = check_user_auth(config, "cuentas:write")
    if auth_msg: return auth_msg
    args = {"cuentaId": cuentaId, "requestBody": {"monto": monto}}
    return invoke_mcp_tool("post_cuentas_by_cuentaId_sacar", args, token)

@tool
def post_cuentas_by_cuentaId_transferir(cuentaId: str, cuentaDestino: str, monto: float, concepto: str, config: RunnableConfig) -> str:
    """Hacer una transferencia a otra cuenta. REQUIERE AUTENTICACIÓN."""
    token, auth_msg = check_user_auth(config, "transfer:write")
    if auth_msg: return auth_msg
    args = {"cuentaId": cuentaId, "requestBody": {"cuentaDestino": cuentaDestino, "monto": monto, "concepto": concepto}}
    return invoke_mcp_tool("post_cuentas_by_cuentaId_transferir", args, token)

# --- SERVICIOS ---
@tool
def get_servicios() -> str:
    """Listar servicios disponibles para pagar (luz, agua, etc)."""
    token = get_mcp_m2m_token()
    return invoke_mcp_tool("get_servicios", {}, token)

@tool
def post_servicios(codigoServicio: str, nombre: str, monto: float, vencimiento: str, config: RunnableConfig) -> str:
    """Agregar un servicio nuevo al sistema."""
    token, auth_msg = check_user_auth(config, "servicios:write")
    if auth_msg: return auth_msg
    args = {"requestBody": {"codigoServicio": codigoServicio, "nombre": nombre, "monto": monto, "vencimiento": vencimiento}}
    return invoke_mcp_tool("post_servicios", args, token)

@tool
def delete_servicios_by_codigoServicio(codigoServicio: str, config: RunnableConfig) -> str:
    """Eliminar un servicio del sistema."""
    token, auth_msg = check_user_auth(config, "servicios:write")
    if auth_msg: return auth_msg
    args = {"codigoServicio": codigoServicio}
    return invoke_mcp_tool("delete_servicios_by_codigoServicio", args, token)

@tool
def post_servicios_pagar(cuentaOrigen: str, codigoServicio: str, monto: float, config: RunnableConfig) -> str:
    """Pagar un servicio. REQUIERE AUTENTICACIÓN."""
    token, auth_msg = check_user_auth(config, "service:pay")
    if auth_msg: return auth_msg
    args = {"requestBody": {"cuentaOrigen": cuentaOrigen, "codigoServicio": codigoServicio, "monto": monto}}
    return invoke_mcp_tool("post_servicios_pagar", args, token)

# --- HIPOTECAS ---
@tool
def get_hipotecas(clienteId: str) -> str:
    """Listar hipotecas de un cliente."""
    token = get_mcp_m2m_token()
    args = {"clienteId": clienteId}
    return invoke_mcp_tool("get_hipotecas", args, token)

@tool
def get_hipotecas_by_idHipoteca(idHipoteca: str) -> str:
    """Consultar el balance y detalle de una hipoteca específica."""
    token = get_mcp_m2m_token()
    args = {"idHipoteca": idHipoteca}
    return invoke_mcp_tool("get_hipotecas_by_idHipoteca", args, token)

@tool
def post_hipotecas(id: str, clienteId: str, monto: float, vencimiento: str, pagoParcial: float, config: RunnableConfig) -> str:
    """Otorgar (crear) una nueva hipoteca."""
    token, auth_msg = check_user_auth(config, "hipotecas:write")
    if auth_msg: return auth_msg
    args = {"requestBody": {"id": id, "clienteId": clienteId, "monto": monto, "vencimiento": vencimiento, "pagoParcial": pagoParcial}}
    return invoke_mcp_tool("post_hipotecas", args, token)

@tool
def post_hipotecas_by_idHipoteca_pagar(idHipoteca: str, cuentaOrigen: str, monto: float, config: RunnableConfig) -> str:
    """Pagar cuota parcial de la hipoteca. REQUIERE AUTENTICACIÓN."""
    token, auth_msg = check_user_auth(config, "mortgage:pay")
    if auth_msg: return auth_msg
    args = {"idHipoteca": idHipoteca, "requestBody": {"cuentaOrigen": cuentaOrigen, "monto": monto}}
    return invoke_mcp_tool("post_hipotecas_by_idHipoteca_pagar", args, token)

# --- CONOCIMIENTO GENERAL ---
@tool
def conocimiento_general(mensaje_literal_usuario: str) -> str:
    """ÚSALA SIEMPRE para preguntas generales. Enruta al proxy de WSO2 APIM Guardrails."""
    print(f"\n[🧠 PROXY TOOL] Enrutando al Proxy APIM...")
    try:
        url = f"{FASTAPI_BASE_URL.strip()}/proxy/chat/completions"
        payload = {
            "model": LOCAL_LLM_MODEL,
            "messages": [{"role": "user", "content": mensaje_literal_usuario}],
            "temperature": 0.7
        }
        resp = requests.post(url, json=payload)
        resp.raise_for_status()
        datos = resp.json()
        
        if isinstance(datos, dict) and datos.get("type") == "SEMANTIC_PROMPT_GUARD":
            return "INSTRUCCIÓN OBLIGATORIA: Copia y pega EXACTAMENTE este texto en tu respuesta final:\n🛡️ **Security Block (WSO2 APIM):** My corporate policies strictly prohibit discussing that topic."
            
        respuesta = datos["choices"][0]["message"]["content"]
        if "🛡️" in respuesta:
            return f"INSTRUCCIÓN OBLIGATORIA: Copia y pega EXACTAMENTE este texto en tu respuesta final:\n{respuesta}"
            
        return respuesta
    except Exception as e:
        return f"Error conectando al AI Gateway: {str(e)}"

# ==========================================
# CONSTRUCTOR DEL AGENTE LANGGRAPH
# ==========================================
def create_agent():
    llm = ChatOpenAI(
        base_url=f"{FASTAPI_BASE_URL.strip()}/proxy", 
        api_key="wso2-apim-proxy", 
        model=LOCAL_LLM_MODEL.strip(),
        temperature=0.0
    )
    
    # Cargamos el arsenal COMPLETO de herramientas
    herramientas = [
        get_clientes,
        post_clientes,
        delete_clientes_by_clienteId,
        post_cuentas,
        delete_cuentas_by_cuentaId,
        get_cuentas_by_cuentaId_movimientos,
        post_cuentas_by_cuentaId_transferir,
        post_cuentas_by_cuentaId_ingresar,
        post_cuentas_by_cuentaId_sacar,
        get_servicios,
        post_servicios,
        delete_servicios_by_codigoServicio,
        post_servicios_pagar,
        get_hipotecas,
        get_hipotecas_by_idHipoteca,
        post_hipotecas,
        post_hipotecas_by_idHipoteca_pagar,
        conocimiento_general
    ]
    
    memory = MemorySaver()

    instrucciones = (
        "You are the BotiBank AI Executive Assistant. Speak ALWAYS in English.\n"
        "RULE 1: For balances/movements -> use 'get_cuentas_by_cuentaId_movimientos'.\n"
        "RULE 2: For transfers -> use 'post_cuentas_by_cuentaId_transferir'.\n"
        "RULE 3: For listing mortgages -> use 'get_hipotecas'. For paying mortgages -> use 'post_hipotecas_by_idHipoteca_pagar'.\n"
        "RULE 4: For paying services -> use 'post_servicios_pagar'.\n"
        "RULE 5 (CRITICAL): If a tool returns 'INSTRUCCIÓN OBLIGATORIA', stop thinking and EXACTLY COPY AND PASTE that text into your final response, including the '<' and '>' symbols.\n"
        "RULE 6: NEVER ask for auth codes manually. If the user says they logged in, immediately execute the pending transaction tool.\n"
        "RULE 7 (MAX PRIORITY): For general questions (greeting, history, sports, dangerous topics) use 'conocimiento_general' sending the exact user prompt."
    )
    
    agent_graph = create_react_agent(
        model=llm,
        tools=herramientas,
        checkpointer=memory,
        prompt=instrucciones # Changed state_modifier back to prompt
    )
    
    return agent_graph