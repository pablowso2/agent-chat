import os
import json
import base64
import warnings
from dotenv import load_dotenv
import traceback

# Limpieza de consola
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=SyntaxWarning)

load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
import httpx
import requests

# 🔴 IMPORTAMOS EL AGENTE DESDE agent.py
from agent import get_agent

# --- CONFIGURACIONES ---
WSO2_TOKEN_URL = os.getenv("WSO2_TOKEN_URL", "")
IDENTITY_SERVER_BASE_URL = WSO2_TOKEN_URL.replace("/oauth2/token", "") if WSO2_TOKEN_URL else "https://127.0.0.1:9446"

WSO2_CLIENT_ID = os.getenv("WSO2_CLIENT_ID", "")
WSO2_CLIENT_SECRET = os.getenv("WSO2_CLIENT_SECRET", "")
FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "http://127.0.0.1:5000")
# 🔴 Forzamos el puerto 5000 para evitar el invalid_callback
REDIRECT_URI = "http://127.0.0.1:5000/callback"

app = FastAPI(title="BotiBank Frontend")

# Memoria de la aplicación
TOKEN_STORE = {}
SESSION_LOGS = []

# Inicializamos el grafo del agente
agent_graph = get_agent()

# ==========================================
# ENDPOINTS DE FASTAPI
# ==========================================
class ChatRequestSchema(BaseModel):
    session_id: str
    message: str

@app.post("/chat")
async def chat(payload: ChatRequestSchema):
    config = {
        "configurable": {
            "thread_id": payload.session_id,
            "session_id": payload.session_id,
            "user_token": TOKEN_STORE.get(payload.session_id) 
        }
    }
    try:
        result = await agent_graph.ainvoke({"messages": [("user", payload.message)]}, config)
        final_answer = result["messages"][-1].content
        return JSONResponse(content={"response": final_answer})
    except Exception as e:
        print("\n❌ DETALLE DEL ERROR 500:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Agent internal error: {str(e)}")

# --- WSO2 APIM PROXY ---
async def get_apim_access_token():
    consumer_key = os.getenv("WSO2_CONSUMER_KEY")
    consumer_secret = os.getenv("WSO2_CONSUMER_SECRET")
    token_url = os.getenv("WSO2_APIM_TOKEN_URL", f"{IDENTITY_SERVER_BASE_URL}/oauth2/token") 
    
    credentials = f"{consumer_key}:{consumer_secret}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    headers = {"Authorization": f"Basic {encoded_credentials}", "Content-Type": "application/x-www-form-urlencoded"}
    
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.post(token_url, headers=headers, data={"grant_type": "client_credentials"})
        if response.status_code == 200:
            return response.json().get("access_token")
        raise Exception(f"APIM Token Failed: {response.text}")

@app.post("/proxy/chat/completions")
async def wso2_proxy(request: Request):
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
        
    wso2_url = os.getenv("WSO2_CHAT_URL", "https://localhost:8243/openaiapi/2.3.0/chat/completions")
    try:
        access_token = await get_apim_access_token()
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        
        async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
            response = await client.post(wso2_url, json=payload, headers=headers)
            resp_data = response.json()
            
            if isinstance(resp_data, dict) and resp_data.get("type") == "SEMANTIC_PROMPT_GUARD":
                regla = resp_data.get("message", {}).get("assessments", {}).get("deniedRule", "this topic")
                resp_data = {
                    "choices": [{
                        "message": {"role": "assistant", "content": f"🛡️ **Security Block (WSO2 APIM):** My corporate policies strictly prohibit discussing **'{regla}'**."}
                    }]
                }
            
            SESSION_LOGS.append({"request": payload, "response": resp_data})
            return resp_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Proxy error: {str(e)}")

# --- WSO2 IS CALLBACK ---
@app.get("/callback")
def callback(code: str, state: str):
    print(f"\n[🌐 CALLBACK] Intercambiando código OAuth2 para la sesión: '{state}'...")
    try:
        resp = requests.post(
            WSO2_TOKEN_URL,
            auth=(WSO2_CLIENT_ID, WSO2_CLIENT_SECRET),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI  # 🔴 Hardcodeado al puerto 5000
            },
            verify=False
        )
        
        if resp.status_code != 200:
            print(f"❌ [WSO2 RECHAZÓ EL TOKEN]: {resp.text}")
            
        resp.raise_for_status()
        TOKEN_STORE[state] = resp.json().get("access_token")
        print(f"✅ [CALLBACK] Token guardado exitosamente para '{state}'")

        html_content = f"""
        <html>
            <script>
                if (window.opener) {{
                    window.opener.postMessage({{ type: "WSO2_AUTH_SUCCESS", sessionId: "{state}" }}, "*");
                    window.close();
                }}
            </script>
            <body style="background: #020617; color: #06b6d4; font-family: sans-serif; text-align: center; padding-top: 20%;">
                <h2>✅ Autenticación Exitosa</h2>
                <p>Volviendo al chat automáticamente...</p>
            </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Login failed: {str(e)}")
    
# ==========================================
# FRONTEND UI (BOTIBANK)
# ==========================================
@app.get("/", response_class=HTMLResponse)
def get_ui():
    html = r"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>BotiBank | AI-Powered Banking</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&display=swap');
            body { font-family: 'Space Grotesk', sans-serif; background-color: #020617; color: #f8fafc; overflow-x: hidden; }
            .bg-tech-pattern {
                background-image: 
                    radial-gradient(at 0% 0%, rgba(59, 130, 246, 0.25) 0px, transparent 50%),
                    radial-gradient(at 100% 100%, rgba(6, 182, 212, 0.25) 0px, transparent 50%),
                    linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
                background-size: 100% 100%, 100% 100%, 40px 40px, 40px 40px;
            }
            tailwind.config = { theme: { extend: { colors: { boti: { blue: '#3b82f6', cyan: '#06b6d4', dark: '#0f172a', panel: '#1e293b' } } } } }
            .typing-indicator span { display: inline-block; width: 6px; height: 6px; background-color: #94a3b8; border-radius: 50%; animation: typing 1.4s infinite ease-in-out both; margin-right: 3px; }
            .typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
            .typing-indicator span:nth-child(2) { animation-delay: -0.16s; }
            @keyframes typing { 0%, 80%, 100% { transform: scale(0); opacity: 0.4; } 40% { transform: scale(1); opacity: 1; } }
            #chat-box::-webkit-scrollbar { width: 4px; }
            #chat-box::-webkit-scrollbar-track { background: transparent; }
            #chat-box::-webkit-scrollbar-thumb { background: #334155; border-radius: 10px; }
        </style>
    </head>
    <body class="antialiased bg-tech-pattern min-h-screen">
        <nav class="fixed w-full z-40 top-0 bg-boti-dark/70 backdrop-blur-xl border-b border-white/10">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div class="flex justify-between items-center h-20">
                    <div class="flex items-center gap-3">
                        <svg viewBox="0 0 512 512" fill="none" class="w-10 h-10 shadow-lg shadow-blue-500/20 rounded-xl">
                            <rect width="512" height="512" rx="128" fill="url(#boti-grad)"/><path d="M160 160h110c45 0 75 25 75 60 0 25-15 45-35 55 25 10 50 35 50 70 0 45-40 75-95 75H160V160z" fill="white"/>
                            <circle cx="230" cy="220" r="18" fill="#0f172a"/><circle cx="230" cy="345" r="18" fill="#0f172a"/><rect x="230" y="275" width="40" height="10" rx="5" fill="#0f172a"/>
                            <defs><linearGradient id="boti-grad" x1="0" y1="0" x2="512" y2="512" gradientUnits="userSpaceOnUse"><stop stop-color="#3b82f6"/><stop offset="1" stop-color="#06b6d4"/></linearGradient></defs>
                        </svg>
                        <h1 class="text-2xl font-bold tracking-tight text-white">Boti<span class="text-boti-cyan">Bank</span></h1>
                    </div>
                </div>
            </div>
        </nav>

        <div class="relative pt-40 pb-20 sm:pt-48 sm:pb-32 text-center">
            <h1 class="text-5xl sm:text-7xl font-bold tracking-tight mb-8">The future of banking <br><span class="text-transparent bg-clip-text bg-gradient-to-r from-boti-blue to-boti-cyan">is now conversational.</span></h1>
        </div>

        <button id="chat-toggle" onclick="toggleChat()" class="fixed bottom-6 right-6 w-16 h-16 bg-gradient-to-r from-boti-blue to-boti-cyan rounded-full shadow-[0_0_20px_rgba(6,182,212,0.4)] flex items-center justify-center text-white text-2xl hover:scale-110 transition-transform z-50">
            <i class="fa-solid fa-robot"></i>
        </button>

        <div id="chat-panel" class="fixed bottom-28 right-4 md:right-6 w-[90vw] md:w-[450px] h-[750px] max-h-[85vh] bg-boti-panel/95 backdrop-blur-xl border border-white/10 rounded-3xl shadow-2xl flex flex-col overflow-hidden z-50 transform scale-0 origin-bottom-right transition-transform duration-300 opacity-0 pointer-events-none">
            
            <div class="bg-boti-dark p-5 border-b border-white/10 flex justify-between items-center">
                <div class="flex items-center gap-3">
                    <div class="w-12 h-12 bg-gradient-to-br from-boti-blue to-boti-cyan rounded-xl flex items-center justify-center text-white"><i class="fa-solid fa-bolt text-xl"></i></div>
                    <div><h3 class="font-bold text-white text-base">BotiBank AI</h3><p class="text-xs text-emerald-400 font-medium"><i class="fa-solid fa-shield-check"></i> Agent Auth Active</p></div>
                </div>
                <button onclick="toggleChat()" class="text-gray-400 hover:text-white transition-colors w-10 h-10 rounded-full hover:bg-white/10"><i class="fa-solid fa-chevron-down text-lg"></i></button>
            </div>

            <div id="chat-box" class="flex-1 p-5 overflow-y-auto flex flex-col gap-5 bg-[#0f172a]/40">
                <div class="flex gap-3 max-w-[90%]">
                    <div class="w-10 h-10 rounded-full bg-gradient-to-r from-boti-blue to-boti-cyan flex items-center justify-center flex-shrink-0 shadow-md"><i class="fa-solid fa-robot text-white text-sm"></i></div>
                    <div class="bg-boti-dark border border-white/5 p-4 rounded-2xl rounded-tl-none text-sm text-gray-200">Hello! I am ready to manage your finances. Try typing: <b>"Transfer $50 to CTA-999"</b> or <b>"Pay my mortgage HIP-001"</b></div>
                </div>
            </div>

            <div class="p-5 bg-boti-dark border-t border-white/10">
                <div class="relative flex items-center">
                    <input id="user-input" type="text" placeholder="Type a command..." class="w-full bg-white border border-gray-300 focus:border-boti-blue focus:ring-2 focus:ring-boti-blue/20 rounded-xl pl-4 pr-12 py-4 text-sm text-black placeholder-gray-400 focus:outline-none transition-all shadow-inner" onkeypress="if(event.key === 'Enter') sendMessage()">
                    <button onclick="sendMessage()" class="absolute right-2 top-2 bottom-2 aspect-square bg-boti-blue hover:bg-blue-400 text-white rounded-lg flex items-center justify-center"><i class="fa-solid fa-paper-plane text-sm"></i></button>
                </div>
            </div>
        </div>

        <script>
            const sessionId = "session-" + Math.random().toString(36).substr(2, 9);
            const chatPanel = document.getElementById("chat-panel");
            const chatToggleBtn = document.getElementById("chat-toggle");
            const chatBox = document.getElementById("chat-box");
            const userInput = document.getElementById("user-input");
            let chatOpen = false;

            function toggleChat() {
                chatOpen = !chatOpen;
                if(chatOpen) {
                    chatPanel.classList.remove("scale-0", "opacity-0", "pointer-events-none");
                    chatPanel.classList.add("scale-100", "opacity-100", "pointer-events-auto");
                    chatToggleBtn.innerHTML = '<i class="fa-solid fa-xmark"></i>';
                    userInput.focus();
                } else {
                    chatPanel.classList.remove("scale-100", "opacity-100", "pointer-events-auto");
                    chatPanel.classList.add("scale-0", "opacity-0", "pointer-events-none");
                    chatToggleBtn.innerHTML = '<i class="fa-solid fa-robot"></i>';
                }
            }

            function appendMessage(text, isUser) {
                const msgDiv = document.createElement("div");
                msgDiv.className = `flex gap-3 max-w-[90%] ${isUser ? 'ml-auto flex-row-reverse' : ''}`;
                
                let formattedText = text;
                
                // 🔴 MICRO-CIRUGÍA: La expresión regular exacta del ejemplo Aura AI
                const urlRegex = /<(https?:\/\/[^>]+)>/g;
                
                if (urlRegex.test(text)) {
                    formattedText = text.replace(urlRegex, function(match, url) {
                        if (url.includes("oauth2/authorize")) {
                            return `<div class="mt-4 mb-2"><a href="${url}" target="_blank" rel="opener" class="inline-flex items-center gap-2 bg-gradient-to-r from-boti-blue to-boti-cyan hover:opacity-90 text-white font-semibold py-2.5 px-5 rounded-xl shadow-lg transition-all"><i class="fa-solid fa-shield-halved"></i> Secure Bank Login</a></div>`;
                        } else {
                            return `<a href="${url}" target="_blank" class="text-boti-cyan underline">${url}</a>`;
                        }
                    });
                }
                
                formattedText = formattedText.replace(/\*\*(.*?)\*\*/g, "<b>$1</b>");

                const avatar = isUser
                    ? `<div class="w-10 h-10 rounded-full bg-slate-700 flex items-center justify-center flex-shrink-0 mt-1"><i class="fa-solid fa-user text-white text-sm"></i></div>`
                    : `<div class="w-10 h-10 rounded-full bg-gradient-to-r from-boti-blue to-boti-cyan flex items-center justify-center flex-shrink-0 mt-1 shadow-md shadow-blue-500/20"><i class="fa-solid fa-robot text-white text-sm"></i></div>`;
                const bubbleClass = isUser ? `bg-boti-blue text-white rounded-2xl rounded-tr-none font-medium` : `bg-boti-dark border border-white/5 text-gray-200 rounded-2xl rounded-tl-none`;

                msgDiv.innerHTML = `${avatar}<div class="p-4 text-sm ${bubbleClass} leading-relaxed">${formattedText}</div>`;
                chatBox.appendChild(msgDiv);
                chatBox.scrollTop = chatBox.scrollHeight;
            }

            function showTyping() {
                const typingId = "typing-" + Date.now();
                const msgDiv = document.createElement("div");
                msgDiv.id = typingId;
                msgDiv.className = `flex gap-3 max-w-[90%]`;
                msgDiv.innerHTML = `<div class="w-10 h-10 rounded-full bg-gradient-to-r from-boti-blue to-boti-cyan flex items-center justify-center flex-shrink-0 mt-1"><i class="fa-solid fa-robot text-white text-sm"></i></div><div class="bg-boti-dark border border-white/5 p-4 rounded-2xl rounded-tl-none flex items-center"><div class="typing-indicator"><span></span><span></span><span></span></div></div>`;
                chatBox.appendChild(msgDiv);
                chatBox.scrollTop = chatBox.scrollHeight;
                return typingId;
            }

            function hideTyping(id) {
                const el = document.getElementById(id);
                if(el) el.remove();
            }

            // Continuación automática
            window.addEventListener("message", async function(event) {
                if (event.data && event.data.type === "WSO2_AUTH_SUCCESS" && event.data.sessionId === sessionId) {
                    const alertDiv = document.createElement("div");
                    alertDiv.className = "flex justify-center my-4 w-full";
                    alertDiv.innerHTML = `<div class="bg-boti-blue/20 border border-boti-blue/50 px-4 py-2 rounded-full text-xs text-boti-cyan font-medium shadow-lg backdrop-blur-sm"><i class="fa-solid fa-shield-check"></i> Identity Verified. Resuming operation...</div>`;
                    chatBox.appendChild(alertDiv);
                    chatBox.scrollTop = chatBox.scrollHeight;
                    
                    const typingId = showTyping();
                    try {
                        const response = await fetch("/chat", {
                            method: "POST", headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ session_id: sessionId, message: "I have securely logged in. Please execute the pending transaction." })
                        });
                        const data = await response.json();
                        hideTyping(typingId);
                        appendMessage(data.response, false);
                    } catch (error) {
                        hideTyping(typingId);
                    }
                }
            });

            async function sendMessage() {
                const text = userInput.value.trim();
                if (!text) return;

                appendMessage(text, true);
                userInput.value = "";
                const typingId = showTyping();

                try {
                    const res = await fetch("/chat", {
                        method: "POST", headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ session_id: sessionId, message: text })
                    });
                    const data = await res.json();
                    hideTyping(typingId);
                    appendMessage(data.response, false);
                } catch (error) {
                    hideTyping(typingId);
                    appendMessage("⚠️ BotiBank systems offline.", false);
                }
            }
        </script>
    </body>
    </html>
    """
    return html

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)