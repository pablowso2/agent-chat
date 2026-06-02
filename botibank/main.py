from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import asyncio

app = FastAPI(title="BotiBank Frontend")

# ==========================================
# 1. DATA MODELS
# ==========================================
class ChatRequest(BaseModel):
    message: str

# ==========================================
# 2. CHAT ENDPOINT
# ==========================================
@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    await asyncio.sleep(1.2)  # Simulate BotiBank thinking
    
    msg = req.message.lower()
    respuesta = ""
    
    if "balance" in msg or "transaction" in msg or "transactions" in msg:
        respuesta = "Your latest transactions are synced. You have an available balance of **$1,500.50**. Would you like to make a transfer?"
    elif "transfer" in msg or "send" in msg:
        respuesta = "Understood! Please provide the amount and the destination account number to process the transfer immediately."
    elif "pay" in msg or "bill" in msg or "electricity" in msg or "utility" in msg:
        respuesta = "I have scanned your bills. You have an **Electricity (ELESUR-1234)** bill for $45.20 about to expire. Shall I proceed with the payment?"
    else:
        respuesta = "Hello! I am your BotiBank assistant 🤖. I am connected to the WSO2 engine. I can check your balance, transfer funds, or pay bills. What do you need?"

    return {"response": respuesta}

# ==========================================
# 3. GRAPHICAL INTERFACE (LANDING PAGE + CHAT)
# ==========================================
@app.get("/", response_class=HTMLResponse)
def get_ui():
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>BotiBank | AI-Powered Banking</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
        
        <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='20' fill='%233b82f6'/><path d='M30 30h40v40H30z' fill='none' stroke='white' stroke-width='8'/><circle cx='50' cy='50' r='10' fill='white'/></svg>" />
        
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&display=swap');
            
            body { 
                font-family: 'Space Grotesk', sans-serif; 
                background-color: #020617; /* Slate 950 */
                color: #f8fafc;
                overflow-x: hidden;
            }
            
            /* Mesh Gradient + Grid Tech Background */
            .bg-tech-pattern {
                background-color: #020617;
                background-image: 
                    radial-gradient(at 0% 0%, rgba(59, 130, 246, 0.25) 0px, transparent 50%),
                    radial-gradient(at 100% 100%, rgba(6, 182, 212, 0.25) 0px, transparent 50%),
                    linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
                background-size: 100% 100%, 100% 100%, 40px 40px, 40px 40px;
            }

            tailwind.config = {
                theme: {
                    extend: {
                        colors: {
                            boti: {
                                blue: '#3b82f6',
                                cyan: '#06b6d4',
                                dark: '#0f172a',
                                panel: '#1e293b'
                            }
                        }
                    }
                }
            }
            
            /* Typing Animation */
            .typing-indicator span {
                display: inline-block; width: 6px; height: 6px;
                background-color: #94a3b8; border-radius: 50%;
                animation: typing 1.4s infinite ease-in-out both; margin-right: 3px;
            }
            .typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
            .typing-indicator span:nth-child(2) { animation-delay: -0.16s; }
            @keyframes typing {
                0%, 80%, 100% { transform: scale(0); opacity: 0.4; }
                40% { transform: scale(1); opacity: 1; }
            }

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
                        <svg viewBox="0 0 512 512" fill="none" xmlns="http://www.w3.org/2000/svg" class="w-10 h-10 shadow-lg shadow-blue-500/20 rounded-xl">
                            <rect width="512" height="512" rx="128" fill="url(#boti-grad)"/>
                            <path d="M160 160h110c45 0 75 25 75 60 0 25-15 45-35 55 25 10 50 35 50 70 0 45-40 75-95 75H160V160z" fill="white"/>
                            <circle cx="230" cy="220" r="18" fill="#0f172a"/>
                            <circle cx="230" cy="345" r="18" fill="#0f172a"/>
                            <rect x="230" y="275" width="40" height="10" rx="5" fill="#0f172a"/>
                            <defs>
                                <linearGradient id="boti-grad" x1="0" y1="0" x2="512" y2="512" gradientUnits="userSpaceOnUse">
                                    <stop stop-color="#3b82f6"/>
                                    <stop offset="1" stop-color="#06b6d4"/>
                                </linearGradient>
                            </defs>
                        </svg>
                        <h1 class="text-2xl font-bold tracking-tight text-white">Boti<span class="text-boti-cyan">Bank</span></h1>
                    </div>
                    <div class="hidden md:flex space-x-8 items-center">
                        <a href="#" class="text-gray-400 hover:text-white transition-colors font-medium text-sm">Accounts</a>
                        <a href="#" class="text-gray-400 hover:text-white transition-colors font-medium text-sm">Cards</a>
                        <a href="#" class="text-gray-400 hover:text-white transition-colors font-medium text-sm">WSO2 API</a>
                    </div>
                </div>
            </div>
        </nav>

        <div class="relative pt-40 pb-20 sm:pt-48 sm:pb-32 overflow-hidden">
            <div class="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
                <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-900/30 border border-blue-500/30 text-boti-cyan text-xs font-semibold uppercase tracking-wider mb-8">
                    <span class="relative flex h-2 w-2">
                        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                        <span class="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
                    </span>
                    AI Agent Online
                </div>
                <h1 class="text-5xl sm:text-7xl font-bold tracking-tight mb-8 leading-tight">
                    The future of banking <br>
                    <span class="text-transparent bg-clip-text bg-gradient-to-r from-boti-blue to-boti-cyan">
                        is now conversational.
                    </span>
                </h1>
                <p class="mt-4 text-lg text-gray-400 max-w-2xl mx-auto mb-10">
                    BotiBank uses advanced artificial intelligence to process your transfers, payments, and inquiries through a secure integrated chat.
                </p>
                <div class="flex justify-center gap-4">
                    <button class="bg-white text-slate-900 px-8 py-3.5 rounded-full font-bold hover:bg-gray-100 transition-colors shadow-xl flex items-center gap-2">
                        <i class="fa-solid fa-bolt text-yellow-500"></i> Open a Zero Account
                    </button>
                </div>
            </div>
        </div>

        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-32">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div class="bg-boti-dark/50 backdrop-blur-sm p-8 rounded-3xl border border-white/10 hover:border-boti-blue/50 transition-colors">
                    <i class="fa-solid fa-microchip text-3xl text-boti-blue mb-4"></i>
                    <h3 class="text-lg font-bold mb-2">AI Engine</h3>
                    <p class="text-gray-400 text-sm">Connected to next-gen LLMs to perfectly understand your natural language.</p>
                </div>
                <div class="bg-boti-dark/50 backdrop-blur-sm p-8 rounded-3xl border border-white/10 hover:border-boti-cyan/50 transition-colors">
                    <i class="fa-solid fa-money-bill-transfer text-3xl text-boti-cyan mb-4"></i>
                    <h3 class="text-lg font-bold mb-2">Ballerina Backend</h3>
                    <p class="text-gray-400 text-sm">Ultra-fast and secure transactions processed by our Ballerina architecture.</p>
                </div>
                <div class="bg-boti-dark/50 backdrop-blur-sm p-8 rounded-3xl border border-white/10 hover:border-blue-400/50 transition-colors">
                    <i class="fa-solid fa-shield-halved text-3xl text-blue-400 mb-4"></i>
                    <h3 class="text-lg font-bold mb-2">WSO2 Security</h3>
                    <p class="text-gray-400 text-sm">Federated identity and access control managed by WSO2 Identity Server.</p>
                </div>
            </div>
        </div>

        <button id="chat-toggle" onclick="toggleChat()" class="fixed bottom-6 right-6 w-16 h-16 bg-gradient-to-r from-boti-blue to-boti-cyan rounded-full shadow-[0_0_20px_rgba(6,182,212,0.4)] flex items-center justify-center text-white text-2xl hover:scale-110 transition-transform z-50">
            <i class="fa-solid fa-robot"></i>
        </button>

        <div id="chat-panel" class="fixed bottom-28 right-4 md:right-6 w-[90vw] md:w-[450px] h-[750px] max-h-[85vh] bg-boti-panel/95 backdrop-blur-xl border border-white/10 rounded-3xl shadow-2xl flex flex-col overflow-hidden z-50 transform scale-0 origin-bottom-right transition-transform duration-300 opacity-0 pointer-events-none">
            
            <div class="bg-boti-dark p-5 border-b border-white/10 flex justify-between items-center">
                <div class="flex items-center gap-3">
                    <div class="w-12 h-12 bg-gradient-to-br from-boti-blue to-boti-cyan rounded-xl flex items-center justify-center text-white">
                        <i class="fa-solid fa-bolt text-xl"></i>
                    </div>
                    <div>
                        <h3 class="font-bold text-white text-base">BotiBank AI</h3>
                        <p class="text-xs text-gray-400 flex items-center gap-1">Your virtual executive</p>
                    </div>
                </div>
                <button onclick="toggleChat()" class="text-gray-400 hover:text-white transition-colors w-10 h-10 flex justify-center items-center rounded-full hover:bg-white/10">
                    <i class="fa-solid fa-chevron-down text-lg"></i>
                </button>
            </div>

            <div id="chat-box" class="flex-1 p-5 overflow-y-auto flex flex-col gap-5 bg-[#0f172a]/40">
                <div class="flex gap-3 max-w-[90%]">
                    <div class="w-10 h-10 rounded-full bg-gradient-to-r from-boti-blue to-boti-cyan flex items-center justify-center flex-shrink-0 mt-1 shadow-md shadow-blue-500/20">
                        <i class="fa-solid fa-robot text-white text-sm"></i>
                    </div>
                    <div class="bg-boti-dark border border-white/5 p-4 rounded-2xl rounded-tl-none text-sm text-gray-200">
                        Hello! Welcome to BotiBank. My neural system is ready to manage your finances. What would you like to do today?
                    </div>
                </div>
            </div>

            <div class="p-5 bg-boti-dark border-t border-white/10">
                <div class="flex gap-2 mb-4 overflow-x-auto pb-1 scrollbar-hide">
                    <button onclick="sendSuggestion('View balance')" class="whitespace-nowrap px-4 py-2 text-xs font-medium text-gray-300 bg-white/5 border border-white/10 hover:bg-boti-blue/20 hover:text-boti-cyan hover:border-boti-blue/50 rounded-lg transition-colors">
                        <i class="fa-solid fa-wallet mr-1"></i> Balance
                    </button>
                    <button onclick="sendSuggestion('Transfer money')" class="whitespace-nowrap px-4 py-2 text-xs font-medium text-gray-300 bg-white/5 border border-white/10 hover:bg-boti-blue/20 hover:text-boti-cyan hover:border-boti-blue/50 rounded-lg transition-colors">
                        <i class="fa-solid fa-money-bill-transfer mr-1"></i> Transfer
                    </button>
                </div>
                
                <div class="relative flex items-center">
                <input id="user-input" type="text" placeholder="Type a command..." 
                    class="w-full bg-white border border-gray-300 focus:border-boti-blue focus:ring-2 focus:ring-boti-blue/20 rounded-xl pl-4 pr-12 py-4 text-sm text-black placeholder-gray-400 focus:outline-none transition-all shadow-inner"
                    onkeypress="if(event.key === 'Enter') sendMessage()">
                    <button onclick="sendMessage()" class="absolute right-2 top-2 bottom-2 aspect-square bg-boti-blue hover:bg-blue-400 text-white rounded-lg flex items-center justify-center transition-colors">
                        <i class="fa-solid fa-paper-plane text-sm"></i>
                    </button>
                </div>
            </div>
        </div>

        <script>
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

            function sendSuggestion(text) {
                userInput.value = text;
                sendMessage();
            }

            function appendMessage(text, isUser) {
                const msgDiv = document.createElement("div");
                msgDiv.className = `flex gap-3 max-w-[90%] ${isUser ? 'ml-auto flex-row-reverse' : ''}`;
                
                const avatar = isUser
                    ? `<div class="w-10 h-10 rounded-full bg-slate-700 flex items-center justify-center flex-shrink-0 mt-1"><i class="fa-solid fa-user text-white text-sm"></i></div>`
                    : `<div class="w-10 h-10 rounded-full bg-gradient-to-r from-boti-blue to-boti-cyan flex items-center justify-center flex-shrink-0 mt-1 shadow-md shadow-blue-500/20"><i class="fa-solid fa-robot text-white text-sm"></i></div>`;

                const bubbleClass = isUser 
                    ? `bg-boti-blue text-white rounded-2xl rounded-tr-none font-medium shadow-md shadow-blue-500/20`
                    : `bg-boti-dark border border-white/5 text-gray-200 rounded-2xl rounded-tl-none`;

                const formattedText = text.replace(/\\*\\*(.*?)\\*\\*/g, "<b>$1</b>");

                msgDiv.innerHTML = `
                    ${avatar}
                    <div class="p-4 text-sm ${bubbleClass}">
                        ${formattedText}
                    </div>
                `;
                chatBox.appendChild(msgDiv);
                chatBox.scrollTop = chatBox.scrollHeight;
            }

            function showTyping() {
                const typingId = "typing-" + Date.now();
                const msgDiv = document.createElement("div");
                msgDiv.id = typingId;
                msgDiv.className = `flex gap-3 max-w-[90%]`;
                msgDiv.innerHTML = `
                    <div class="w-10 h-10 rounded-full bg-gradient-to-r from-boti-blue to-boti-cyan flex items-center justify-center flex-shrink-0 mt-1"><i class="fa-solid fa-robot text-white text-sm"></i></div>
                    <div class="bg-boti-dark border border-white/5 p-4 rounded-2xl rounded-tl-none flex items-center">
                        <div class="typing-indicator"><span></span><span></span><span></span></div>
                    </div>
                `;
                chatBox.appendChild(msgDiv);
                chatBox.scrollTop = chatBox.scrollHeight;
                return typingId;
            }

            function hideTyping(id) {
                const el = document.getElementById(id);
                if(el) el.remove();
            }

            async function sendMessage() {
                const text = userInput.value.trim();
                if (!text) return;

                appendMessage(text, true);
                userInput.value = "";
                const typingId = showTyping();

                try {
                    const res = await fetch("/api/chat", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ message: text })
                    });
                    const data = await res.json();
                    hideTyping(typingId);
                    appendMessage(data.response, false);
                } catch (error) {
                    hideTyping(typingId);
                    appendMessage("⚠️ BotiBank systems offline. Please try again later.", false);
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