import os
# ☢️ EL BOTÓN NUCLEAR: Apagado maestro de OpenTelemetry y LangSmith
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["OTEL_TRACES_EXPORTER"] = "none"
os.environ["OTEL_METRICS_EXPORTER"] = "none"
os.environ["OTEL_LOGS_EXPORTER"] = "none"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_API_KEY"] = ""

import requests
import dotenv

# Cargar variables de entorno
dotenv.load_dotenv()
import re
import httpx
import json
import base64
from fastapi import FastAPI, Depends, Security, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel

# Importamos la inicialización del agente
from agent import create_agent

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

# Configuración de WSO2 para validación (Introspection)
WSO2_INTROSPECT_URL = os.getenv("WSO2_INTROSPECT_URL")
WSO2_CLIENT_ID = os.getenv("WSO2_CLIENT_ID")
WSO2_CLIENT_SECRET = os.getenv("WSO2_CLIENT_SECRET")
WSO2_TOKEN_URL = os.getenv("WSO2_TOKEN_URL")

app = FastAPI(title="Resource Server & Agent API")

# Inicializamos el grafo del agente
agent_graph = create_agent()

# Almacén temporal en memoria para los tokens de usuario y LOGS
TOKEN_STORE = {}
# 🔴 HISTORIAL COMPLETO: Guardará el historial de llamadas para el APIM Monitor
SESSION_LOGS = [] 

# Define el esquema de seguridad (extrae el Bearer token del Header)
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="https://127.0.0.1:9446/oauth2/token",
    scopes={"weather:read": "Leer el clima", "music:read": "Buscar música"}
)

def validar_token_y_scopes(security_scopes: SecurityScopes, token: str = Depends(oauth2_scheme)):
    if security_scopes.scopes:
        authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
    else:
        authenticate_value = "Bearer"

    try:
        resp = requests.post(
            WSO2_INTROSPECT_URL,
            auth=(WSO2_CLIENT_ID, WSO2_CLIENT_SECRET), 
            data={"token": token},
            verify=False 
        )
        resp.raise_for_status()
        token_data = resp.json()
    except Exception as e:
        print(f"\n❌ [ERROR INTROSPECCIÓN WSO2]: {str(e)}") 
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al conectar con WSO2 Identity Server: {str(e)}"
        )

    if not token_data.get("active"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": authenticate_value},
        )

    token_scopes = token_data.get("scope", "").split()
    print(f"🔑 [WSO2 -> INTROSPECCIÓN] Scopes reales dentro de este token: {token_scopes}")

    for scope in security_scopes.scopes:
        if scope not in token_scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No tienes los permisos necesarios. Scope requerido: {scope}",
                headers={"WWW-Authenticate": authenticate_value},
            )
            
    return token_data


# --- ENDPOINTS PROTEGIDOS (SERVIDORES DE RECURSOS) ---

@app.get("/weather", dependencies=[Security(validar_token_y_scopes, scopes=["weather:read"])])
def get_weather(ciudad: str):  
    url = "http://api.weatherapi.com/v1/current.json"
    params = {"key": WEATHER_API_KEY, "q": ciudad, "lang": "es"}
    
    resp = requests.get(url, params=params)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="Error en WeatherAPI")
    return resp.json()

@app.get("/music", dependencies=[Security(validar_token_y_scopes, scopes=["music:read"])])
def get_music(animo: str):  
    url = "https://itunes.apple.com/search"
    params = {"term": animo, "media": "music", "entity": "song", "limit": 1}
    
    resp = requests.get(url, params=params)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="Error en iTunes API")
    return resp.json()


# --- INTERCEPTOR ENDPOINT: CALLBACK PARA EL ENLACE DEL NAVEGADOR ---

@app.get("/callback")
def callback(code: str, state: str):
    print(f"\n[🌐 CALLBACK] Código recibido desde WSO2. Intercambiando para sesión: '{state}'...")
    try:
        resp = requests.post(
            WSO2_TOKEN_URL,
            auth=(WSO2_CLIENT_ID, WSO2_CLIENT_SECRET),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://127.0.0.1:8000/callback"
            },
            verify=False
        )
        resp.raise_for_status()
        token_data = resp.json()
        
        TOKEN_STORE[state] = token_data.get("access_token")
        print(f"✅ [CALLBACK] Token de usuario guardado con éxito para la sesión '{state}'")

        html_content = f"""
        <html>
            <head>
                <title>Autenticación Exitosa</title>
                <script>
                    if (window.opener) {{
                        window.opener.postMessage({{ type: "WSO2_AUTH_SUCCESS", sessionId: "{state}" }}, "*");
                        window.close();
                    }}
                </script>
            </head>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; text-align: center; padding-top: 80px; background: linear-gradient(135deg, #1e293b, #0f172a); color: white;">
                <div style="background: rgba(255, 255, 255, 0.1); backdrop-filter: blur(10px); max-width: 500px; margin: 0 auto; padding: 40px; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.2);">
                    <div style="font-size: 48px; margin-bottom: 20px;">✅</div>
                    <h1 style="color: #4ade80; margin-bottom: 10px; font-weight: 600;">Autenticación Completada</h1>
                    <p style="color: #cbd5e1; font-size: 16px; margin-bottom: 20px;">Conexión segura establecida con WSO2 Identity Server.</p>
                    <div style="display: inline-block; width: 30px; height: 30px; border: 3px solid rgba(255,255,255,0.3); border-radius: 50%; border-top-color: #fff; animation: spin 1s ease-in-out infinite;"></div>
                    <p style="color: #94a3b8; font-size: 14px; margin-top: 15px;">Volviendo al chat automáticamente...</p>
                </div>
                <style>@keyframes spin {{ to {{ transform: rotate(360deg); }} }}</style>
            </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    except Exception as e:
        print(f"❌ [ERROR CALLBACK EXCHANGE]: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Fallo al procesar login de WSO2: {str(e)}")


# --- INTERFAZ GRÁFICA DEL CHAT ---

@app.get("/", response_class=HTMLResponse)
def get_chat_ui():
    html_content = r"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Weather & Music AI</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
        <style>
            @keyframes gradientBG {
                0% { background-position: 0% 50%; }
                50% { background-position: 100% 50%; }
                100% { background-position: 0% 50%; }
            }
            body {
                background: linear-gradient(-45deg, #0f172a, #1e1b4b, #0f172a, #020617);
                background-size: 400% 400%;
                animation: gradientBG 20s ease infinite;
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            .glass {
                background: rgba(15, 23, 42, 0.6);
                backdrop-filter: blur(16px);
                -webkit-backdrop-filter: blur(16px);
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
            .glass-header {
                background: rgba(15, 23, 42, 0.8);
                backdrop-filter: blur(12px);
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            /* Scrollbars técnicos */
            ::-webkit-scrollbar { width: 6px; height: 6px; }
            ::-webkit-scrollbar-track { background: transparent; }
            ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.2); border-radius: 10px; }
            ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.3); }
            
            .typing-dot {
                animation: typing 1.4s infinite ease-in-out both;
            }
            .typing-dot:nth-child(1) { animation-delay: -0.32s; }
            .typing-dot:nth-child(2) { animation-delay: -0.16s; }
            @keyframes typing {
                0%, 80%, 100% { transform: scale(0); opacity: 0.5; }
                40% { transform: scale(1); opacity: 1; }
            }
            /* Pre para código */
            pre {
                white-space: pre-wrap;       /* CSS3 */   
                white-space: -moz-pre-wrap;  /* Mozilla */
                word-wrap: break-word;       /* IE */
            }
        </style>
    </head>
    <body class="text-gray-100 h-screen flex flex-col justify-center items-center p-0 md:p-6 overflow-hidden">
        
        <div class="w-full max-w-7xl h-full md:h-[95vh] flex flex-col md:flex-row gap-4 relative">
            
            <div class="absolute top-0 left-0 w-64 h-64 bg-indigo-600 rounded-full mix-blend-multiply filter blur-3xl opacity-20 pointer-events-none transform -translate-x-1/2 -translate-y-1/2"></div>
            <div class="absolute bottom-0 right-0 w-80 h-80 bg-blue-600 rounded-full mix-blend-multiply filter blur-3xl opacity-20 pointer-events-none transform translate-x-1/3 translate-y-1/3"></div>

            <div class="glass w-full md:w-2/3 h-full md:rounded-3xl shadow-2xl flex flex-col overflow-hidden z-10">
                <header class="glass-header p-5 flex items-center justify-between">
                    <div class="flex items-center gap-3">
                        <div class="w-10 h-10 rounded-full bg-gradient-to-tr from-indigo-500 to-blue-500 flex items-center justify-center shadow-lg">
                            <i class="fa-solid fa-cloud-bolt text-white text-lg"></i>
                        </div>
                        <div>
                            <h1 class="text-xl font-bold text-white tracking-wide">Aura AI</h1>
                            <p class="text-xs text-indigo-300">Clima, Música & Traductor</p>
                        </div>
                    </div>
                    <div class="hidden sm:flex items-center gap-2 bg-black/30 px-3 py-1.5 rounded-full border border-white/10">
                        <div class="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
                        <span class="text-xs text-gray-300 font-medium">WSO2 Secured</span>
                    </div>
                </header>

                <main id="chat-box" class="flex-1 p-4 sm:p-6 overflow-y-auto space-y-6 scroll-smooth">
                    <div class="flex justify-center my-4">
                        <div class="bg-indigo-900/40 border border-indigo-500/30 px-5 py-3 rounded-2xl text-sm text-indigo-200 text-center max-w-md shadow-lg backdrop-blur-sm">
                            <i class="fa-solid fa-music mr-2"></i><b>Sistema:</b> Bienvenido. Intenta preguntar:<br><i>"¿Cómo está el clima en Madrid y qué música me recomiendas?"</i> o usa la traducción.
                        </div>
                    </div>
                </main>

                <footer class="p-4 sm:p-6 bg-gray-900/50 backdrop-blur-md border-t border-white/5">
                    <div class="relative flex items-center">
                        <input id="user-input" type="text" placeholder="Pregúntale al agente sobre el clima y la música..." 
                               class="w-full bg-gray-800/80 border border-gray-600/50 rounded-2xl pl-5 pr-16 py-4 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent shadow-inner transition-all"
                               onkeypress="if(event.key === 'Enter') sendMessage()">
                        <button onclick="sendMessage()" class="absolute right-2 bg-gradient-to-r from-indigo-500 to-blue-600 hover:from-indigo-400 hover:to-blue-500 text-white w-10 h-10 rounded-xl flex items-center justify-center transition-all transform hover:scale-105 shadow-lg">
                            <i class="fa-solid fa-paper-plane text-sm"></i>
                        </button>
                    </div>
                </footer>
            </div>

            <div class="glass hidden md:flex flex-col w-1/3 h-full md:rounded-3xl shadow-2xl overflow-hidden z-10 border-l border-white/10">
                <header class="glass-header p-5 flex items-center gap-3">
                    <i class="fa-solid fa-terminal text-emerald-400"></i>
                    <div>
                        <h2 class="text-sm font-bold text-white tracking-wide">APIM Monitor</h2>
                        <p class="text-[10px] text-gray-400">Live Payload Inspector</p>
                    </div>
                </header>
                <div id="logs-container" class="flex-1 p-4 overflow-y-auto bg-[#0a0f1d]/80 text-[11px] font-mono leading-relaxed space-y-6">
                    <div class="text-gray-500 italic text-center mt-10" id="waiting-msg">Esperando interceptar tráfico LLM...</div>
                </div>
            </div>

        </div>

        <script>
            const sessionId = "session-" + Math.random().toString(36).substr(2, 9);
            const chatBox = document.getElementById("chat-box");
            const userInput = document.getElementById("user-input");
            
            // Variable para llevar la cuenta de los logs pintados y no duplicarlos
            let renderedLogsCount = 0;
            
            async function fetchLogs() {
                try {
                    const res = await fetch("/debug/logs");
                    const data = await res.json();
                    
                    const logsContainer = document.getElementById("logs-container");
                    
                    // Si hay logs nuevos en la lista del backend
                    if (data.logs && data.logs.length > renderedLogsCount) {
                        
                        // Quitar el mensaje de espera la primera vez
                        const waitingMsg = document.getElementById("waiting-msg");
                        if (waitingMsg) waitingMsg.remove();
                        
                        // Pintar solo los logs nuevos
                        for (let i = renderedLogsCount; i < data.logs.length; i++) {
                            const logItem = data.logs[i];
                            const logGroup = document.createElement("div");
                            logGroup.className = "border-b border-white/10 pb-5 mb-5 space-y-4 last:border-0";
                            
                            let html = '';
                            if (logItem.request) {
                                html += `
                                    <div>
                                        <div class="flex items-center gap-2 mb-2">
                                            <i class="fa-solid fa-arrow-right-to-bracket text-blue-400"></i>
                                            <span class="text-blue-400 font-bold uppercase">Req #${i + 1}</span>
                                        </div>
                                        <pre class="text-gray-300 bg-black/40 p-3 rounded-lg border border-white/5 overflow-x-auto max-h-[300px] overflow-y-auto">${JSON.stringify(logItem.request, null, 2)}</pre>
                                    </div>`;
                            }
                            if (logItem.response) {
                                html += `
                                    <div>
                                        <div class="flex items-center gap-2 mb-2">
                                            <i class="fa-solid fa-arrow-right-from-bracket text-emerald-400"></i>
                                            <span class="text-emerald-400 font-bold uppercase">Res #${i + 1}</span>
                                        </div>
                                        <pre class="text-gray-300 bg-black/40 p-3 rounded-lg border border-white/5 overflow-x-auto max-h-[300px] overflow-y-auto">${JSON.stringify(logItem.response, null, 2)}</pre>
                                    </div>`;
                            }
                            
                            logGroup.innerHTML = html;
                            logsContainer.appendChild(logGroup);
                        }
                        
                        // Actualizar el contador y hacer scroll abajo automáticamente
                        renderedLogsCount = data.logs.length;
                        logsContainer.scrollTop = logsContainer.scrollHeight;
                    }
                } catch (e) {
                    console.error("Error fetching logs", e);
                }
            }

            window.addEventListener("message", async function(event) {
                if (event.data && event.data.type === "WSO2_AUTH_SUCCESS" && event.data.sessionId === sessionId) {
                    const alertDiv = document.createElement("div");
                    alertDiv.className = "flex justify-center my-4";
                    alertDiv.innerHTML = `
                        <div class="bg-emerald-900/40 border border-emerald-500/30 px-4 py-2 rounded-full text-xs text-emerald-300 font-medium flex items-center gap-2 shadow-lg backdrop-blur-sm">
                            <i class="fa-solid fa-check-circle"></i> Autenticación detectada. Procesando música...
                        </div>
                    `;
                    chatBox.appendChild(alertDiv);
                    chatBox.scrollTop = chatBox.scrollHeight;

                    await sendAutomatedContinuation();
                }
            });

            async function sendAutomatedContinuation() {
                showLoading();
                const logInterval = setInterval(fetchLogs, 1000);
                
                try {
                    const response = await fetch("/chat", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ 
                            session_id: sessionId, 
                            message: "Ya inicié sesión de forma segura. Continúa con la recomendación de música de inmediato." 
                        })
                    });
                    const data = await response.json();
                    removeLoading();
                    clearInterval(logInterval);
                    fetchLogs(); 
                    appendMessage("Aura AI", data.response, true);
                } catch (error) {
                    removeLoading();
                    clearInterval(logInterval);
                    appendMessage("Sistema", "❌ Error al continuar el flujo automáticamente.", true);
                }
            }

            function appendMessage(sender, text, isBot = false) {
                const msgDiv = document.createElement("div");
                msgDiv.className = isBot ? "flex justify-start w-full" : "flex justify-end w-full";
                
                let formattedText = text;
                const urlRegex = /<(https?:\/\/[^>]+)>/g;
                
                if (urlRegex.test(text)) {
                    formattedText = text.replace(urlRegex, function(match, url) {
                        if (url.includes("oauth2/authorize")) {
                            return `<div class="mt-4 mb-2"><a href="${url}" target="_blank" rel="opener" class="inline-flex items-center gap-2 bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-bold py-2.5 px-5 rounded-xl shadow-lg transition-all transform hover:-translate-y-0.5"><i class="fa-solid fa-lock"></i> Iniciar Sesión en WSO2</a></div>`;
                        } else {
                            return `<div class="mt-4 mb-2"><a href="${url}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-2 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-400 hover:to-purple-500 text-white font-bold py-2.5 px-5 rounded-xl shadow-lg transition-all transform hover:-translate-y-0.5"><i class="fa-solid fa-play"></i> Escuchar en iTunes</a></div>`;
                        }
                    });
                }

                const avatar = isBot 
                    ? `<div class="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center shadow-md flex-shrink-0 mt-1"><i class="fa-solid fa-robot text-xs text-white"></i></div>`
                    : `<div class="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center shadow-md flex-shrink-0 mt-1"><i class="fa-solid fa-user text-xs text-white"></i></div>`;

                const bubbleStyle = isBot 
                    ? `bg-gray-800/80 border border-gray-700/50 text-gray-100 rounded-2xl rounded-tl-sm shadow-md` 
                    : `bg-blue-600 text-white rounded-2xl rounded-tr-sm shadow-md`;

                msgDiv.innerHTML = `
                    <div class="flex gap-3 max-w-[85%] sm:max-w-[75%] ${isBot ? 'flex-row' : 'flex-row-reverse'}">
                        ${avatar}
                        <div class="px-5 py-3.5 ${bubbleStyle}">
                            <p class="text-xs font-bold mb-1.5 ${isBot ? 'text-indigo-400' : 'text-blue-200'}">${sender}</p>
                            <p class="whitespace-pre-line text-[15px] leading-relaxed">${formattedText}</p>
                        </div>
                    </div>
                `;
                chatBox.appendChild(msgDiv);
                chatBox.scrollTop = chatBox.scrollHeight;
            }

            function showLoading() {
                const loadingDiv = document.createElement("div");
                loadingDiv.id = "loading-bubble";
                loadingDiv.className = "flex justify-start w-full";
                loadingDiv.innerHTML = `
                    <div class="flex gap-3 max-w-[85%] flex-row">
                        <div class="w-8 h-8 rounded-full bg-indigo-600/50 flex items-center justify-center flex-shrink-0 mt-1"><i class="fa-solid fa-robot text-xs text-white/50"></i></div>
                        <div class="px-5 py-4 bg-gray-800/50 border border-gray-700/30 rounded-2xl rounded-tl-sm flex gap-1 items-center">
                            <div class="w-2 h-2 bg-indigo-400 rounded-full typing-dot"></div>
                            <div class="w-2 h-2 bg-indigo-400 rounded-full typing-dot"></div>
                            <div class="w-2 h-2 bg-indigo-400 rounded-full typing-dot"></div>
                        </div>
                    </div>
                `;
                chatBox.appendChild(loadingDiv);
                chatBox.scrollTop = chatBox.scrollHeight;
            }

            function removeLoading() {
                const loading = document.getElementById("loading-bubble");
                if (loading) loading.remove();
            }

            async function sendMessage() {
                const text = userInput.value.trim();
                if (!text) return;

                appendMessage("Tú", text, false);
                userInput.value = "";

                showLoading();
                
                const logInterval = setInterval(fetchLogs, 1000);

                try {
                    const response = await fetch("/chat", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ session_id: sessionId, message: text })
                    });
                    
                    const data = await response.json();
                    removeLoading();
                    clearInterval(logInterval);
                    fetchLogs(); 
                    appendMessage("Aura AI", data.response, true);
                } catch (error) {
                    removeLoading();
                    clearInterval(logInterval);
                    appendMessage("Sistema", "❌ Error de conexión con el servidor.", true);
                }
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# --- ENDPOINT PÚBLICO DEL AGENTE (/chat) ---

class ChatRequest(BaseModel):
    session_id: str
    message: str

def run_agent(thread_id: str, question: str):
    config = {
        "configurable": {
            "thread_id": thread_id,
            "session_id": thread_id,
            "user_token": TOKEN_STORE.get(thread_id) 
        }
    }
    try:
        events = agent_graph.stream(
            {"messages": [("user", question)]}, config, stream_mode="values"
        )

        final_answer = None
        for event in events:
            if "messages" in event:
                final_answer = event["messages"][-1].content

        return final_answer
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del Agente: {str(e)}")

@app.post("/chat")
def chat(payload: ChatRequest):
    result = {
        "response": run_agent(
            thread_id=payload.session_id,
            question=payload.message,
        )
    }
    return JSONResponse(content=result)


# --- FUNCIONES PROXY PARA WSO2 APIM ---

async def get_apim_access_token():
    consumer_key = os.getenv("WSO2_CONSUMER_KEY")
    consumer_secret = os.getenv("WSO2_CONSUMER_SECRET")
    token_url = os.getenv("WSO2_APIM_TOKEN_URL") 
    
    credentials = f"{consumer_key}:{consumer_secret}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    data = {
        "grant_type": "client_credentials"
    }
    
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.post(token_url, headers=headers, data=data)
        
        if response.status_code == 200:
            return response.json().get("access_token")
        else:
            raise Exception(f"Fallo al obtener Token OAuth2 de APIM: {response.text}")

@app.post("/proxy/chat/completions")
async def wso2_proxy(request: Request):
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="El cuerpo de la petición no es un JSON válido")
        
    wso2_url = os.getenv("WSO2_CHAT_URL")
    
    try:
        access_token = await get_apim_access_token()
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        print("\n" + "="*50)
        print("🚀 ENVIANDO PETICIÓN A WSO2 APIM...")
        print(f"URL: {wso2_url}")
        print("="*50 + "\n")

        async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
            # Hacemos la petición a WSO2 APIM
            response = await client.post(wso2_url, json=payload, headers=headers)
            resp_data = response.json()
            
            # 🔴 MICRO-CIRUGÍA: Interceptor del Guardrail de WSO2
            # Si WSO2 APIM bloquea el prompt, devuelve este 'type' específico
            if isinstance(resp_data, dict) and resp_data.get("type") == "SEMANTIC_PROMPT_GUARD":
                
                # Extraemos qué regla fue la que disparó el bloqueo
                regla_rota = resp_data.get("message", {}).get("assessments", {}).get("deniedRule", "este tema")
                
                # Falsificamos una respuesta de modelo exitosa para que LangChain no se rompa
                # y le mostramos al usuario un mensaje elegante.
                resp_data = {
                    "id": "chatcmpl-guardrail-blocked",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "wso2-apim-guardrail",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": f"🛡️ **Bloqueo de Seguridad (WSO2 APIM):** Lo siento, mis políticas corporativas me prohíben estrictamente hablar sobre **'{regla_rota}'**. ¿Puedo ayudarte con otra cosa?"
                            },
                            "finish_reason": "stop"
                        }
                    ],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                }
            
            # Agregamos el log a la lista para el panel lateral
            SESSION_LOGS.append({
                "request": payload,
                "response": resp_data
            })
            
            return resp_data
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fallo interno en el Proxy APIM: {str(e)}")

# Endpoint para devolver la lista entera de logs al front
@app.get("/debug/logs")
def get_debug_logs():
    return JSONResponse(content={"logs": SESSION_LOGS})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)