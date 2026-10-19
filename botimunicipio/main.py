import os
import traceback
from dotenv import load_dotenv

# Limpieza de consola
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel

# 🔴 IMPORTAMOS EL AGENTE DESDE agent.py
from agent import get_agent

app = FastAPI(title="Sede Virtual Municipal")

# Inicializamos el grafo del agente tal como en el ejemplo
agent_graph = get_agent()

# ==========================================
# ENDPOINTS DE FASTAPI
# ==========================================
class ChatRequestSchema(BaseModel):
    session_id: str
    message: str

@app.post("/chat")
async def chat(payload: ChatRequestSchema):
    # Configuramos el hilo de la conversación (thread_id) para la memoria de LangGraph
    config = {
        "configurable": {
            "thread_id": payload.session_id,
            "session_id": payload.session_id
        }
    }
    
    try:
        # Ejecutamos el grafo con ainvoke usando el formato de mensajes de LangGraph
        result = await agent_graph.ainvoke({"messages": [("user", payload.message)]}, config)
        
        # Extraemos la respuesta final generada por el asistente
        final_answer = result["messages"][-1].content
        
        return JSONResponse(content={"response": final_answer})
    except Exception as e:
        print("\n❌ DETALLE DEL ERROR 500:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Agent internal error: {str(e)}")

# ==========================================
# FRONTEND UI (MUNICIPAL)
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
                <p class="text-slate-600 mb-8">Pide certificados, reporta incidencias o consulta horarios con nuestro asistente inteligente.</p>
                <button onclick="toggleChat()" class="bg-green-600 text-white px-6 py-3 rounded-full font-bold shadow-lg hover:bg-green-700 transition-all">
                    Abrir Chat Asistente
                </button>
            </div>
        </main>

        <button id="chat-toggle" onclick="toggleChat()" class="fixed bottom-6 right-6 w-14 h-14 bg-green-600 rounded-full shadow-xl flex items-center justify-center text-white text-xl hover:scale-105 z-50">
            <i class="fa-solid fa-comment-dots"></i>
        </button>

        <div id="chat-panel" class="fixed bottom-24 right-4 md:right-6 w-[90vw] md:w-[400px] h-[600px] bg-white border border-slate-200 rounded-2xl shadow-2xl flex flex-col overflow-hidden z-50 transform scale-0 origin-bottom-right transition-transform duration-300 pointer-events-none">            
            <div class="bg-slate-900 p-4 flex justify-between items-center text-white">
                <div class="flex items-center gap-3">
                    <i class="fa-solid fa-robot text-green-400"></i>
                    <div><h3 class="font-bold text-sm">Agente Municipal</h3></div>
                </div>
                <button onclick="toggleChat()" class="text-gray-400 hover:text-white"><i class="fa-solid fa-xmark"></i></button>
            </div>

            <div id="chat-box" class="flex-1 p-4 overflow-y-auto flex flex-col gap-4 bg-slate-50">
                <div class="flex gap-3 max-w-[90%]">
                    <div class="w-8 h-8 rounded-full bg-green-600 flex items-center justify-center flex-shrink-0 text-white"><i class="fa-solid fa-robot text-xs"></i></div>
                    <div class="bg-white border border-slate-200 p-3 rounded-xl rounded-tl-none text-sm text-slate-700 shadow-sm">
                        ¡Hola! Soy el asistente virtual. ¿En qué te puedo ayudar hoy?
                    </div>
                </div>
            </div>

            <div class="p-4 bg-white border-t border-slate-200">
                <div class="flex gap-2 mb-3 overflow-x-auto pb-2 scrollbar-hide">
                    <button onclick="sendSuggestion('Farola rota')" class="whitespace-nowrap px-3 py-1.5 text-xs bg-slate-100 hover:bg-green-50 rounded-full">🚧 Incidencia</button>
                    <button onclick="sendSuggestion('Necesito el padrón')" class="whitespace-nowrap px-3 py-1.5 text-xs bg-slate-100 hover:bg-green-50 rounded-full">📄 Trámite</button>
                    <button onclick="sendSuggestion('Horario piscina')" class="whitespace-nowrap px-3 py-1.5 text-xs bg-slate-100 hover:bg-green-50 rounded-full">ℹ️ Información</button>
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

            function toggleChat() {
                chatOpen = !chatOpen;
                if(chatOpen) {
                    chatPanel.classList.remove("scale-0", "pointer-events-none");
                    chatPanel.classList.add("scale-100", "pointer-events-auto");
                    userInput.focus();
                } else {
                    chatPanel.classList.remove("scale-100", "pointer-events-auto");
                    chatPanel.classList.add("scale-0", "pointer-events-none");
                }
            }

            function sendSuggestion(text) { userInput.value = text; sendMessage(); }

            function appendMessage(text, isUser) {
                const msgDiv = document.createElement("div");
                msgDiv.className = `flex gap-3 max-w-[90%] ${isUser ? 'ml-auto flex-row-reverse' : ''}`;
                const avatar = isUser ? `<div class="w-8 h-8 rounded-full bg-slate-300 flex items-center justify-center flex-shrink-0 text-slate-600"><i class="fa-solid fa-user text-xs"></i></div>` : `<div class="w-8 h-8 rounded-full bg-green-600 flex items-center justify-center flex-shrink-0 text-white"><i class="fa-solid fa-robot text-xs"></i></div>`;
                const bubbleClass = isUser ? `bg-green-600 text-white rounded-xl rounded-tr-none` : `bg-white border border-slate-200 text-slate-700 rounded-xl rounded-tl-none`;
                msgDiv.innerHTML = `${avatar}<div class="p-3 text-sm ${bubbleClass} shadow-sm">${text}</div>`;
                chatBox.appendChild(msgDiv);
                chatBox.scrollTop = chatBox.scrollHeight;
            }

            function showTyping() {
                const typingId = "typing-" + Date.now();
                const msgDiv = document.createElement("div");
                msgDiv.id = typingId;
                msgDiv.className = `flex gap-3 max-w-[90%]`;
                msgDiv.innerHTML = `<div class="w-8 h-8 rounded-full bg-green-600 flex items-center justify-center flex-shrink-0 text-white"><i class="fa-solid fa-robot text-xs"></i></div><div class="bg-white border border-slate-200 p-3 rounded-xl rounded-tl-none flex items-center shadow-sm"><div class="typing-indicator"><span></span><span></span><span></span></div></div>`;
                chatBox.appendChild(msgDiv);
                chatBox.scrollTop = chatBox.scrollHeight;
                return typingId;
            }

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
                    document.getElementById(typingId).remove();
                    appendMessage(data.response, false);
                } catch (error) {
                    document.getElementById(typingId).remove();
                    appendMessage("⚠️ Error de conexión.", false);
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