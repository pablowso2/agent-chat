import dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# CAMBIO: Como ambos archivos están en la misma carpeta, importamos directamente de 'agent'
from agent import create_agent

# Cargar variables de entorno
dotenv.load_dotenv()

# Inicializar la aplicación y el agente
app = FastAPI(title="Weather & Music AI Agent")
agent_graph = create_agent()

# Definir la estructura del payload esperado
class ChatRequest(BaseModel):
    session_id: str
    message: str

def run_agent(thread_id: str, question: str):
    config = {
        "configurable": {
            # Los checkpoints (memoria) se acceden mediante este thread_id
            "thread_id": thread_id,
        }
    }

    # Transmitimos los eventos del grafo
    events = agent_graph.stream(
        {"messages": [("user", question)]}, config, stream_mode="values"
    )

    final_answer = None
    for event in events:
        if "messages" in event:
            final_answer = event["messages"][-1].content

    return final_answer

@app.post("/chat")
async def chat(payload: ChatRequest):
    result = {
        "response": run_agent(
            thread_id=payload.session_id,
            question=payload.message,
        )
    }
    return JSONResponse(content=result)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)