import os
import ssl
from fastapi import FastAPI, Depends, Security, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

ssl._create_default_https_context = ssl._create_unverified_context

from agent import get_agent

app = FastAPI(title="WSO2 Nativo Agent API")
agent_app = get_agent()

# --- RECURSO PROTEGIDO ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="https://127.0.0.1:9446/oauth2/token")

def validar_token(token: str = Depends(oauth2_scheme)):
    if not token:
        raise HTTPException(status_code=401, detail="Token requerido por el Servidor de Recursos")
    return token

@app.get("/api/weather", dependencies=[Security(validar_token)])
def mock_weather(ciudad: str):
    return {"ciudad": ciudad, "temp": 24, "condicion": "Soleado"}


# --- ENDPOINT DEL CHAT ---
class ChatRequest(BaseModel):
    session_id: str
    message: str

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    config = {"configurable": {"thread_id": request.session_id}}
    try:
        response = await agent_app.ainvoke(
            {"messages": [("user", request.message)]}, 
            config
        )
        final_answer = response["messages"][-1].content
        return {"agente": final_answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)