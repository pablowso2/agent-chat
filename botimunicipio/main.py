import os
import asyncio

from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import ToolException
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

# ---------------------------------------------------------
# Cargar variables de entorno desde el archivo .env
# ---------------------------------------------------------
load_dotenv()

# ==========================================
# 1. HERRAMIENTAS MCP (servidor municipal)
# ==========================================
# Las tools viven en mcp_server.py y se descubren vía tools/list.
MUNICIPAL_SERVER_URL = os.getenv("MUNICIPAL_SERVER_URL", "http://127.0.0.1:8000/mcp")
# Si el MCP server se consume a través del gateway (WSO2 API Manager), la API key va en este header
MUNICIPAL_SERVER_API_KEY = os.getenv("MUNICIPAL_SERVER_API_KEY", "")
MUNICIPAL_SERVER_API_KEY_HEADER = os.getenv("MUNICIPAL_SERVER_API_KEY_HEADER", "apikey")
# Segundos máximos por request al MCP server (los túneles a veces se cuelgan ~100s antes de dar 504)
MUNICIPAL_SERVER_TIMEOUT = float(os.getenv("MUNICIPAL_SERVER_TIMEOUT", "20"))
# Reintentos por llamada fallida. Ojo: si el primer intento sí llegó al servidor, una
# operación como registrar_incidencia puede quedar duplicada.
MUNICIPAL_SERVER_RETRIES = int(os.getenv("MUNICIPAL_SERVER_RETRIES", "1"))

def _conexion_mcp() -> dict:
    conexion = {"url": MUNICIPAL_SERVER_URL, "transport": "streamable_http",
                "timeout": MUNICIPAL_SERVER_TIMEOUT}
    if MUNICIPAL_SERVER_API_KEY:
        conexion["headers"] = {MUNICIPAL_SERVER_API_KEY_HEADER: MUNICIPAL_SERVER_API_KEY}
    return conexion

mcp_client = MultiServerMCPClient({"municipal": _conexion_mcp()})

def _con_limite(tool):
    """Pone un tiempo máximo a cada llamada MCP y reintenta si falla.

    El timeout de httpx no alcanza: si el túnel se cuelga, la sesión MCP se queda
    esperando para siempre. Si se agotan los intentos, la ToolException vuelve al
    modelo como ToolMessage (handle_tool_errors) y el bot responde en vez de dar 500.
    """
    original = tool.coroutine

    async def envuelta(*args, **kwargs):
        ultimo_error = None
        for _ in range(MUNICIPAL_SERVER_RETRIES + 1):
            try:
                return await asyncio.wait_for(original(*args, **kwargs), MUNICIPAL_SERVER_TIMEOUT)
            except Exception as e:
                ultimo_error = e
        raise ToolException(
            f"El servidor municipal no respondió ({type(ultimo_error).__name__}). "
            "Dile al usuario que hay un problema técnico y que lo intente de nuevo en unos minutos."
        )

    tool.coroutine = envuelta
    return tool

# ==========================================
# 2. CONFIGURACIÓN DEL GRAFO Y AGENTE
# ==========================================

# Leer configuración del modelo desde el .env (mismos nombres que boti-bank; LOCAL_LLM_* por compatibilidad)
LLM_API_KEY = os.getenv("MODEL_API_KEY", os.getenv("LOCAL_LLM_API_KEY", "sk-mi-clave-secreta-123"))
LLM_BASE_URL = os.getenv("MODEL_BASE_URL", os.getenv("LOCAL_LLM_BASE_URL", "https://macos.tailcc45b1.ts.net/v1"))
LLM_MODEL_NAME = os.getenv("MODEL_NAME", os.getenv("LOCAL_LLM_MODEL", "hermes-2-pro-llama3-8b"))

llm = ChatOpenAI(
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY,
    model=LLM_MODEL_NAME,
    temperature=0.0
)

system_prompt = SystemMessage(content="""
Eres el Agente Municipal de Atención Ciudadana. Habla SIEMPRE en español.
TIENES HERRAMIENTAS (TOOLS) DISPONIBLES. ESTÁS OBLIGADO a usarlas.
REGLA 1: Si el usuario quiere reportar algo roto (bache, farola, basura), EJECUTA 'registrar_incidencia'.
REGLA 2: Si el usuario quiere un certificado o trámite, EJECUTA 'iniciar_tramite' (si no da el DNI, envíalo como 'SIN_DNI' y pídeselo).
REGLA 3: Si el usuario pregunta horarios o información, EJECUTA 'consultar_informacion'.
REGLA 4 (CRÍTICA): Si el usuario te pide ver la lista de incidencias, sus registros o historial, TIENES QUE EJECUTAR OBLIGATORIAMENTE la herramienta 'ver_registros'. NUNCA digas que no tienes acceso.
REGLA 5: NO inventes excusas ni alucines información.
REGLA 6: CADA PEDIDO NUEVO NECESITA SU PROPIA HERRAMIENTA: haber usado una herramienta antes en la
conversación no te da la respuesta a la pregunta siguiente.
""")

# Cuantos turnos de usuario viajan al modelo (mismo motivo que en boti-bank: con el
# historial completo el modelo chico deja de llamar tools y repite el turno anterior).
MAX_TURNOS = int(os.getenv("AGENT_MAX_TURNOS", "3"))


def _recortar(messages):
    """Deja los ultimos MAX_TURNOS turnos del usuario.

    Corta siempre en un HumanMessage: cortar en cualquier otro sitio separaria
    una tool_call de su ToolMessage y el request saldria invalido.
    """
    inicios = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    if len(inicios) <= MAX_TURNOS:
        return messages
    return messages[inicios[-MAX_TURNOS]:]


def _construir_agente(tools):
    llm_with_tools = llm.bind_tools(tools)

    async def agent_node(state: MessagesState):
        messages = _recortar(state["messages"])
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [system_prompt] + messages
        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    def should_continue(state: MessagesState):
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "tools"
        return END

    workflow = StateGraph(MessagesState)
    workflow.add_node("agent", agent_node)
    # Si el MCP server falla (timeout, 504...), el error vuelve al modelo como ToolMessage
    # y el bot responde en vez de devolver un 500.
    workflow.add_node("tools", ToolNode(tools, handle_tool_errors=True))

    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", should_continue, ["tools", END])
    workflow.add_edge("tools", "agent")

    return workflow.compile(checkpointer=checkpointer)

checkpointer = MemorySaver()
_municipal_agent = None
_lock_agente = asyncio.Lock()

async def obtener_agente():
    """Construye el grafo la primera vez que se usa: las tools se piden al MCP server
    en ese momento, así el contenedor arranca aunque el MCP server todavía no responda."""
    global _municipal_agent
    async with _lock_agente:
        if _municipal_agent is None:
            tools = [_con_limite(t) for t in await asyncio.wait_for(
                mcp_client.get_tools(), MUNICIPAL_SERVER_TIMEOUT)]
            _municipal_agent = _construir_agente(tools)
    return _municipal_agent

# ==========================================
# 3. FASTAPI ENDPOINTS
# ==========================================

app = FastAPI(title="Sede Virtual Municipal", version="1.0.0")

# NOTE: field names/requiredness here must match the OpenAPI schema
# registered for this component's /chat endpoint in Agent Manager
# (message + session_id required, context optional) — otherwise the
# gateway's requests get rejected with 422 before they ever reach the graph.
class ChatRequest(BaseModel):
    message: str = Field(..., description="El mensaje o instrucción del usuario")
    session_id: str = Field(..., description="ID de sesión para mantener el historial")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Contexto opcional en formato JSON")

class ChatResponse(BaseModel):
    response: str

def _respuesta_final(messages) -> str:
    """Lo que se le devuelve al usuario: la ultima respuesta REDACTADA.

    Coger messages[-1] a ciegas devuelve el ToolMessage tal cual cuando el grafo
    termina justo despues de una herramienta. Aqui se busca hacia atras el ultimo
    AIMessage con texto.
    """
    ultimo_tool = next((m.content for m in reversed(messages)
                        if isinstance(m, ToolMessage) and isinstance(m.content, str)), None)

    for m in reversed(messages):
        if not isinstance(m, AIMessage):
            continue
        texto = m.content if isinstance(m.content, str) else ""
        texto = texto.strip()
        if not texto:
            continue
        if ultimo_tool and texto == ultimo_tool.strip():
            return ("No pude redactar la respuesta: el modelo devolvio el resultado "
                    "de la herramienta sin elaborar. Vuelve a preguntarlo, por favor.")
        return texto

    return "No obtuve una respuesta del modelo para este pedido."


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    run_config = {"configurable": {"thread_id": req.session_id}}

    input_message = HumanMessage(content=req.message)

    try:
        municipal_agent = await obtener_agente()
        final_state = await municipal_agent.ainvoke(
            {"messages": [input_message]},
            config=run_config
        )

        return ChatResponse(response=_respuesta_final(final_state["messages"]))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# FRONTEND UI
# ==========================================
@app.get("/", response_class=HTMLResponse)
def get_ui():
    html = r"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Sede Virtual | Ayuntamiento</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
            body { font-family: 'Inter', sans-serif; overflow-x: hidden; }
            .bg-institutional { background-color: #f8fafc; }
            #chat-box::-webkit-scrollbar { width: 6px; }
            #chat-box::-webkit-scrollbar-track { background: transparent; }
            #chat-box::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 10px; }
            .scrollbar-hide::-webkit-scrollbar { display: none; }
            .typing-indicator span { display: inline-block; width: 6px; height: 6px; background-color: #94a3b8; border-radius: 50%; animation: typing 1.4s infinite ease-in-out both; margin-right: 3px; }
            .typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
            .typing-indicator span:nth-child(2) { animation-delay: -0.16s; }
            @keyframes typing { 0%, 80%, 100% { transform: scale(0); opacity: 0.4; } 40% { transform: scale(1); opacity: 1; } }
        </style>
    </head>
    <body class="antialiased bg-institutional min-h-screen text-slate-800">
        <nav class="fixed w-full z-40 top-0 bg-white border-b border-slate-200 shadow-sm">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div class="flex items-center h-16 gap-3">
                    <div class="w-8 h-8 bg-green-600 rounded flex items-center justify-center text-white"><i class="fa-solid fa-building-columns text-sm"></i></div>
                    <h1 class="text-xl font-bold text-slate-800">Sede <span class="text-green-600">Virtual</span></h1>
                </div>
            </div>
        </nav>
        <main class="flex flex-col items-center justify-center min-h-screen pt-16 px-4">
            <div class="text-center max-w-2xl">
                <h2 class="text-4xl font-bold mb-4">Atención Ciudadana</h2>
                <p class="text-slate-600 mb-8">Pide certificados, reporta incidencias o consulta horarios. Conectado al Backend vía API REST.</p>
                <button onclick="toggleChat()" class="bg-green-600 text-white px-6 py-3 rounded-full font-bold shadow-lg hover:bg-green-700 transition-all">Abrir Chat Asistente</button>
            </div>
        </main>
        <button id="chat-toggle" onclick="toggleChat()" class="fixed bottom-6 right-6 w-14 h-14 bg-green-600 rounded-full shadow-xl flex items-center justify-center text-white text-xl hover:scale-105 z-50"><i class="fa-solid fa-comment-dots"></i></button>
        <div id="chat-panel" class="fixed bottom-24 right-4 md:right-6 w-[90vw] md:w-[400px] h-[600px] bg-white border border-slate-200 rounded-2xl shadow-2xl flex flex-col overflow-hidden z-50 transform scale-0 origin-bottom-right transition-transform duration-300 pointer-events-none">            
            <div class="bg-slate-900 p-4 flex justify-between items-center text-white">
                <div class="flex items-center gap-3">
                    <i class="fa-solid fa-robot text-green-400"></i>
                    <div><h3 class="font-bold text-sm">Agente Municipal (API REST)</h3></div>
                </div>
                <button onclick="toggleChat()" class="text-gray-400 hover:text-white"><i class="fa-solid fa-xmark"></i></button>
            </div>
            <div id="chat-box" class="flex-1 p-4 overflow-y-auto flex flex-col gap-4 bg-slate-50">
                <div class="flex gap-3 max-w-[90%]">
                    <div class="w-8 h-8 rounded-full bg-green-600 flex items-center justify-center flex-shrink-0 text-white"><i class="fa-solid fa-robot text-xs"></i></div>
                    <div class="bg-white border border-slate-200 p-3 rounded-xl rounded-tl-none text-sm text-slate-700 shadow-sm">¡Hola! Soy el asistente virtual. ¿En qué te puedo ayudar hoy?</div>
                </div>
            </div>
            <div class="p-4 bg-white border-t border-slate-200">
                <div class="flex gap-2 mb-3 overflow-x-auto pb-2 scrollbar-hide">
                    <button onclick="sendSuggestion('Farola rota en calle Sol')" class="whitespace-nowrap px-3 py-1.5 text-xs bg-slate-100 hover:bg-green-50 rounded-full">🚧 Incidencia</button>
                    <button onclick="sendSuggestion('Necesito el padrón')" class="whitespace-nowrap px-3 py-1.5 text-xs bg-slate-100 hover:bg-green-50 rounded-full">📄 Trámite</button>
                    <button onclick="sendSuggestion('Ver mis registros')" class="whitespace-nowrap px-3 py-1.5 text-xs bg-slate-100 hover:bg-green-50 rounded-full">📋 Historial</button>
                </div>
                <div class="relative flex items-center">
                    <input id="user-input" type="text" placeholder="Escribe tu consulta..." class="w-full bg-slate-100 border-none focus:ring-2 focus:ring-green-500 rounded-lg pl-3 pr-10 py-2.5 text-sm" onkeypress="if(event.key === 'Enter') sendMessage()">
                    <button onclick="sendMessage()" class="absolute right-2 text-green-600 hover:text-green-800"><i class="fa-solid fa-paper-plane"></i></button>
                </div>
            </div>
        </div>
        <script>
            const sessionId = "sesion-" + Math.random().toString(36).substr(2, 9);
            const chatPanel = document.getElementById("chat-panel");
            const chatBox = document.getElementById("chat-box");
            const userInput = document.getElementById("user-input");
            let chatOpen = false;
            function toggleChat() { chatOpen = !chatOpen; if(chatOpen) { chatPanel.classList.remove("scale-0", "pointer-events-none"); chatPanel.classList.add("scale-100", "pointer-events-auto"); userInput.focus(); } else { chatPanel.classList.remove("scale-100", "pointer-events-auto"); chatPanel.classList.add("scale-0", "pointer-events-none"); } }
            function sendSuggestion(text) { userInput.value = text; sendMessage(); }
            function appendMessage(text, isUser) { const msgDiv = document.createElement("div"); msgDiv.className = `flex gap-3 max-w-[90%] ${isUser ? 'ml-auto flex-row-reverse' : ''}`; const formattedText = text.replace(/\n/g, '<br>'); const avatar = isUser ? `<div class="w-8 h-8 rounded-full bg-slate-300 flex items-center justify-center flex-shrink-0 text-slate-600"><i class="fa-solid fa-user text-xs"></i></div>` : `<div class="w-8 h-8 rounded-full bg-green-600 flex items-center justify-center flex-shrink-0 text-white"><i class="fa-solid fa-robot text-xs"></i></div>`; const bubbleClass = isUser ? `bg-green-600 text-white rounded-xl rounded-tr-none` : `bg-white border border-slate-200 text-slate-700 rounded-xl rounded-tl-none`; msgDiv.innerHTML = `${avatar}<div class="p-3 text-sm ${bubbleClass} shadow-sm leading-relaxed">${formattedText}</div>`; chatBox.appendChild(msgDiv); chatBox.scrollTop = chatBox.scrollHeight; }
            function showTyping() { const typingId = "typing-" + Date.now(); const msgDiv = document.createElement("div"); msgDiv.id = typingId; msgDiv.className = `flex gap-3 max-w-[90%]`; msgDiv.innerHTML = `<div class="w-8 h-8 rounded-full bg-green-600 flex items-center justify-center flex-shrink-0 text-white"><i class="fa-solid fa-robot text-xs"></i></div><div class="bg-white border border-slate-200 p-3 rounded-xl rounded-tl-none flex items-center shadow-sm"><div class="typing-indicator"><span></span><span></span><span></span></div></div>`; chatBox.appendChild(msgDiv); chatBox.scrollTop = chatBox.scrollHeight; return typingId; }
            async function sendMessage() { const text = userInput.value.trim(); if (!text) return; appendMessage(text, true); userInput.value = ""; const typingId = showTyping(); try { const res = await fetch("/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: sessionId, message: text }) }); const data = await res.json(); document.getElementById(typingId).remove(); appendMessage(data.response, false); } catch (error) { document.getElementById(typingId).remove(); appendMessage("⚠️ Error de conexión con la API.", false); } }
        </script>
    </body>
    </html>
    """
    return html

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", 8000))

    uvicorn.run("main:app", host=host, port=port)
