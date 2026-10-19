import os
import ssl
import warnings
import json
from dotenv import load_dotenv

# ☢️ BYPASS SSL (Para desarrollo local)
ssl.create_default_context = ssl._create_unverified_context
ssl._create_default_https_context = ssl._create_unverified_context

warnings.filterwarnings("ignore")
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_API_KEY"] = ""

# Cargar las variables del .env
load_dotenv()

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

# ==========================================
# BASES DE DATOS EN MEMORIA (ARRAYS)
# ==========================================
# Estos arrays guardarán los datos generados durante la ejecución del servidor
db_incidencias = []
db_tramites = []
db_informacion = []

# ==========================================
# MUNICIPAL TOOLS (LANGGRAPH)
# ==========================================

@tool
async def tool_incidencias(tipo_incidencia: str, ubicacion: str, descripcion: str, config: RunnableConfig) -> str:
    """ÚSALA PARA: Reportar desperfectos físicos en la ciudad (baches, farolas, limpieza, mobiliario roto)."""
    ticket_id = f"INC-{abs(hash(descripcion)) % 100000}"
    
    # Guardamos en nuestro array (memoria temporal)
    registro = {
        "ticket_id": ticket_id,
        "tipo": tipo_incidencia,
        "ubicacion": ubicacion,
        "descripcion": descripcion,
        "estado": "Registrado"
    }
    db_incidencias.append(registro)
    
    return f"RESULTADO: Incidencia de '{tipo_incidencia}' en '{ubicacion}' registrada correctamente. Número de seguimiento: {ticket_id}."

@tool
async def tool_tramites(tipo_tramite: str, dni_ciudadano: str, config: RunnableConfig) -> str:
    """ÚSALA PARA: Gestionar papeleo oficial, certificados de empadronamiento, y expedientes. Si no tienes el DNI, envia 'SIN_DNI'."""
    if dni_ciudadano == "SIN_DNI" or not dni_ciudadano:
        return "INSTRUCCIÓN: Faltan datos. Pide al usuario que te facilite su DNI para poder tramitar su solicitud."
    
    # Guardamos en nuestro array (memoria temporal)
    registro = {
        "dni": dni_ciudadano,
        "tramite": tipo_tramite,
        "estado": "En proceso"
    }
    db_tramites.append(registro)
    
    return f"RESULTADO: Trámite de '{tipo_tramite}' iniciado para el DNI {dni_ciudadano}. El documento estará disponible en su carpeta ciudadana."

@tool
async def tool_informacion(consulta_usuario: str, config: RunnableConfig) -> str:
    """ÚSALA PARA: Responder preguntas generales, dudas sobre horarios de instalaciones, eventos, fiestas y FAQ."""
    # Guardamos la consulta en nuestro array para analítica
    db_informacion.append({"consulta": consulta_usuario})
    
    consulta = consulta_usuario.lower()
    if "piscina" in consulta:
        return "RESULTADO: La piscina municipal abre de lunes a domingo de 09:00 a 21:00."
    elif "fiestas" in consulta:
        return "RESULTADO: Las fiestas patronales se celebran la última semana de septiembre."
    elif "punto limpio" in consulta:
        return "RESULTADO: El punto limpio municipal está abierto de martes a sábado de 10:00 a 14:00 y de 17:00 a 20:00."
    
    return "RESULTADO: No he encontrado esa información exacta. Deriva al usuario al teléfono 010 de atención ciudadana."

@tool
async def tool_ver_registros(config: RunnableConfig) -> str:
    """ÚSALA PARA: Consultar los registros de todo lo que el usuario ha solicitado o guardado en el sistema hasta el momento (incidencias, trámites, consultas)."""
    # Devolvemos un resumen de los 3 arrays en formato JSON
    resumen = {
        "incidencias_reportadas": db_incidencias,
        "tramites_solicitados": db_tramites,
        "consultas_realizadas": db_informacion
    }
    return f"RESULTADO REGISTROS DEL SISTEMA: {json.dumps(resumen, ensure_ascii=False)}"

# ==========================================
# CREACIÓN DEL AGENTE 
# ==========================================

def get_agent():
    llm = ChatOpenAI(
        base_url=os.getenv("LOCAL_LLM_BASE_URL"), 
        api_key=os.getenv("LOCAL_LLM_API_KEY"),
        model=os.getenv("LOCAL_LLM_MODEL"),
        temperature=0.0
    )
    
    herramientas = [
        tool_incidencias, 
        tool_tramites, 
        tool_informacion,
        tool_ver_registros # Añadimos la nueva herramienta
    ]
    
    memory = MemorySaver()

    instrucciones = (
        "Eres el Agente Municipal de Atención Ciudadana. Habla SIEMPRE en español.\n"
        "REGLA 1: Para problemas físicos en la vía pública o cosas rotas -> usa 'tool_incidencias'.\n"
        "REGLA 2: Para pedir certificados, padrón o documentos -> usa 'tool_tramites'.\n"
        "REGLA 3: Para dudas sobre horarios, eventos o instalaciones -> usa 'tool_informacion'.\n"
        "REGLA 4: Para usar 'tool_tramites' necesitas un DNI. Si el usuario no lo da, usa 'SIN_DNI' en la herramienta y pídeselo educadamente en tu respuesta.\n"
        "REGLA 5: Si el usuario te pide ver su historial, resumen, qué cosas ha pedido, o comprobar los registros -> usa 'tool_ver_registros' y formatea la respuesta de forma amigable para el usuario.\n"
        "REGLA 6 (ANTI-ALUCINACIÓN MÁXIMA): TIENES ESTRICTAMENTE PROHIBIDO inventar información municipal, fechas u horarios. Solo puedes responder usando EXACTAMENTE la información que te devuelve la herramienta."
    )
    
    # Mantenemos prompt= para que sea compatible con tu versión instalada de LangGraph
    return create_react_agent(llm, herramientas, checkpointer=memory, prompt=instrucciones)