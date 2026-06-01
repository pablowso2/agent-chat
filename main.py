import os
import requests
import dotenv
import re
from fastapi import FastAPI, Depends, Security, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel

# Importamos la inicialización del agente
from agent import create_agent

# Cargar variables de entorno
dotenv.load_dotenv()

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

# Configuración de WSO2 para validación (Introspection)
WSO2_INTROSPECT_URL = os.getenv("WSO2_INTROSPECT_URL", "https://127.0.0.1:9446/oauth2/introspect")
WSO2_CLIENT_ID = os.getenv("WSO2_CLIENT_ID")
WSO2_CLIENT_SECRET = os.getenv("WSO2_CLIENT_SECRET")
WSO2_TOKEN_URL = os.getenv("WSO2_TOKEN_URL", "https://127.0.0.1:9446/oauth2/token")

app = FastAPI(title="Resource Server & Agent API")

# Inicializamos el grafo del agente
agent_graph = create_agent()

# Almacén temporal en memoria para los tokens de usuario en base a su session_id
TOKEN_STORE = {}

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
                        // Enviamos señal de éxito a la pestaña del chat principal
                        window.opener.postMessage({{ type: "WSO2_AUTH_SUCCESS", sessionId: "{state}" }}, "*");
                        // Nos cerramos automáticamente de inmediato
                        window.close();
                    }}
                </script>
            </head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding-top: 60px; background-color: #f4f6f9;">
                <div style="background: white; max-width: 500px; margin: 0 auto; padding: 30px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #2e7d32; margin-bottom: 10px;">🔓 ¡Autenticación Completada!</h1>
                    <p style="color: #555; font-size: 16px;">Has iniciado sesión correctamente en WSO2 Identity Server.</p>
                    <p style="font-weight: bold; color: #1e3a8a; margin-top: 20px;">Volviendo al chat automáticamente...</p>
                </div>
            </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    except Exception as e:
        print(f"❌ [ERROR CALLBACK EXCHANGE]: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Fallo al procesar login de WSO2: {str(e)}")


# --- INTERFAZ GRÁFICA DEL CHAT (FRONTEND) ---

@app.get("/", response_class=HTMLResponse)
def get_chat_ui():
    html_content = r"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI Agent Corporate Chat</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-900 text-gray-100 h-screen flex flex-col justify-between">
        <header class="bg-gray-800 p-4 border-b border-gray-700 shadow-md">
            <h1 class="text-xl font-bold text-blue-400 flex items-center gap-2">
                🤖 Agente IA Seguro <span class="text-xs bg-green-900 text-green-300 px-2 py-0.5 rounded border border-green-700">WSO2 OAuth2 Connected</span>
            </h1>
        </header>

        <main id="chat-box" class="flex-1 p-4 overflow-y-auto space-y-4 max-w-4xl w-full mx-auto">
            <div class="bg-gray-800 border border-gray-700 p-3 rounded-lg text-sm text-gray-400">
                <b>Sistema:</b> Bienvenido al chat del agente. He generado una sesión única para ti. Intenta preguntar: <i>"¿Cómo está el clima en Madrid y qué música me recomiendas?"</i>
            </div>
        </main>

        <footer class="bg-gray-800 p-4 border-t border-gray-700 w-full sticky bottom-0">
            <div class="max-w-4xl mx-auto flex gap-2">
                <input id="user-input" type="text" placeholder="Escribe tu mensaje aquí..." 
                       class="flex-1 bg-gray-700 border border-gray-600 rounded px-4 py-2 text-white focus:outline-none focus:border-blue-500"
                       onkeypress="if(event.key === 'Enter') sendMessage()">
                <button onclick="sendMessage()" class="bg-blue-600 hover:bg-blue-500 text-white font-bold px-6 py-2 rounded transition-colors">
                    Enviar
                </button>
            </div>
        </footer>

        <script>
            const sessionId = "session-" + Math.random().toString(36).substr(2, 9);
            const chatBox = document.getElementById("chat-box");
            const userInput = document.getElementById("user-input");

            // Escuchador del mensaje automático enviado por la pestaña del callback
            window.addEventListener("message", async function(event) {
                if (event.data && event.data.type === "WSO2_AUTH_SUCCESS" && event.data.sessionId === sessionId) {
                    const alertDiv = document.createElement("div");
                    alertDiv.className = "bg-green-950 border border-green-700 p-2 rounded text-xs text-green-300 text-center my-2 font-semibold animate-pulse";
                    alertDiv.innerText = "✓ Autenticación en WSO2 detectada. Continuando flujo de música de forma automática...";
                    chatBox.appendChild(alertDiv);
                    chatBox.scrollTop = chatBox.scrollHeight;

                    // Enviamos la instrucción de continuación automática oculta al endpoint /chat
                    await sendAutomatedContinuation();
                }
            });

            async function sendAutomatedContinuation() {
                const loadingDiv = document.createElement("div");
                loadingDiv.id = "loading-bubble";
                loadingDiv.className = "text-xs text-gray-500 animate-pulse italic pl-2";
                loadingDiv.innerText = "El agente está procesando los resultados...";
                chatBox.appendChild(loadingDiv);
                chatBox.scrollTop = chatBox.scrollHeight;

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
                    document.getElementById("loading-bubble").remove();
                    appendMessage("Agente", data.response, true);
                } catch (error) {
                    if (document.getElementById("loading-bubble")) document.getElementById("loading-bubble").remove();
                    appendMessage("Agente", "❌ Error al continuar el flujo de música automáticamente.", true);
                }
            }

            function appendMessage(sender, text, isBot = false) {
                const msgDiv = document.createElement("div");
                msgDiv.className = isBot ? "flex justify-start" : "flex justify-end";
                
                let formattedText = text;
                // Expresión regular para detectar enlaces envueltos en < >
                const urlRegex = /<(https?:\/\/[^>]+)>/g;
                
                if (urlRegex.test(text)) {
                    formattedText = text.replace(urlRegex, function(match, url) {
                        // 1. Si la URL es de WSO2, pintamos el botón verde de Login con rel="opener"
                        if (url.includes("oauth2/authorize")) {
                            return `<a href="${url}" target="_blank" rel="opener" class="inline-block mt-2 bg-gradient-to-r from-green-600 to-emerald-500 hover:from-green-500 hover:to-emerald-400 text-white font-bold py-2 px-4 rounded shadow-md transition-all text-center">🔐 Iniciar Sesión en WSO2</a>`;
                        } 
                        // 2. Si es cualquier otra URL (la de la música), pintamos el botón azul
                        else {
                            return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="inline-block mt-2 bg-gradient-to-r from-blue-600 to-indigo-500 hover:from-blue-500 hover:to-indigo-400 text-white font-bold py-2 px-4 rounded shadow-md transition-all text-center">🎵 Escuchar canción</a>`;
                        }
                    });
                }

                msgDiv.innerHTML = `
                    <div class="max-w-[75%] rounded-lg px-4 py-3 shadow ${isBot ? 'bg-gray-800 border border-gray-700 text-gray-100' : 'bg-blue-600 text-white'}">
                        <p class="text-xs font-semibold mb-1 opacity-60">${sender}</p>
                        <p class="whitespace-pre-line">${formattedText}</p>
                    </div>
                `;
                chatBox.appendChild(msgDiv);
                chatBox.scrollTop = chatBox.scrollHeight;
            }

            async function sendMessage() {
                const text = userInput.value.trim();
                if (!text) return;

                appendMessage("Tú", text, false);
                userInput.value = "";

                const loadingDiv = document.createElement("div");
                loadingDiv.id = "loading-bubble";
                loadingDiv.className = "text-xs text-gray-500 animate-pulse italic pl-2";
                loadingDiv.innerText = "El agente está pensando y gestionando accesos con WSO2...";
                chatBox.appendChild(loadingDiv);
                chatBox.scrollTop = chatBox.scrollHeight;

                try {
                    const response = await fetch("/chat", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ session_id: sessionId, message: text })
                    });
                    
                    const data = await response.json();
                    document.getElementById("loading-bubble").remove();
                    appendMessage("Agente", data.response, true);
                } catch (error) {
                    if (document.getElementById("loading-bubble")) document.getElementById("loading-bubble").remove();
                    appendMessage("Agente", "❌ Error de conexión con el servidor de IA.", true);
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)