from fastapi import FastAPI
from fastapi import HTTPException

from pydantic import BaseModel

from openai import OpenAI

from skills import consultar_orden
from skills import listar_ordenes
from config_loader import load_config

import json

# ----------------------------------
# Configuración
# ----------------------------------

config = load_config()

MODEL_NAME = config["llm"]["model"]

client = OpenAI(
    base_url=config["llm"]["base_url"],
    api_key=config["llm"]["api_key"]
)

SYSTEM_PROMPT = config["agent"]["system_prompt"]

app = FastAPI(
    title="Order Agent",
    description="Agente local con LM Studio + Skills",
    version="1.0.0"
)

# ----------------------------------
# DTOs
# ----------------------------------

class ChatRequest(BaseModel):
    message: str


# ----------------------------------
# Skills
# ----------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "consultar_orden",
            "description": "Obtiene información de una orden",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_number": {
                        "type": "string",
                        "description": "Número de orden"
                    }
                },
                "required": ["order_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "listar_ordenes",
            "description": "Obtiene todas las órdenes registradas",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

AVAILABLE_FUNCTIONS = {
    "consultar_orden": consultar_orden,
    "listar_ordenes": listar_ordenes
}

# ----------------------------------
# Root
# ----------------------------------

@app.get("/")
def root():

    return {
        "application": "Order Agent",
        "model": MODEL_NAME,
        "status": "running"
    }


# ----------------------------------
# Chat
# ----------------------------------

@app.post("/chat")
def chat(request: ChatRequest):

    try:

        user_message = request.message

        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            tools=TOOLS,
            tool_choice="auto"
        )

        response_message = completion.choices[0].message

        # ----------------------------------
        # Tool Calling
        # ----------------------------------

        if response_message.tool_calls:

            tool_call = response_message.tool_calls[0]

            function_name = tool_call.function.name

            function_args = json.loads(
                tool_call.function.arguments
            )

            function_to_call = AVAILABLE_FUNCTIONS[
                function_name
            ]

            tool_result = function_to_call(
                **function_args
            )

            final_completion = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "system",
                        "content": """
                        Responde de forma clara,
                        profesional y amigable.
                        """
                    },
                    {
                        "role": "user",
                        "content": user_message
                    },
                    {
                        "role": "assistant",
                        "content": response_message.content or ""
                    },
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(
                            tool_result,
                            ensure_ascii=False
                        )
                    }
                ]
            )

            answer = (
                final_completion
                .choices[0]
                .message
                .content
            )

            return {
                "answer": answer,
                "tool_used": function_name,
                "tool_result": tool_result
            }

        return {
            "answer": response_message.content,
            "tool_used": None
        }

    except Exception as ex:

        raise HTTPException(
            status_code=500,
            detail=str(ex)
        )