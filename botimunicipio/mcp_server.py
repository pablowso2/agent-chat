import os
import json
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

load_dotenv()

MCP_PORT = int(os.getenv("MCP_PORT", 8000))

# Hosts públicos extra (túneles, gateway) separados por comas, p.ej. "mw98grj3-7000.uks1.devtunnels.ms"
HOSTS_EXTRA = [h.strip() for h in os.getenv("MCP_ALLOWED_HOSTS", f"mw98grj3-{MCP_PORT}.uks1.devtunnels.ms").split(",") if h.strip()]

# Servidor MCP real (JSON-RPC 2.0 sobre Streamable HTTP) expuesto en http://127.0.0.1:<MCP_PORT>/mcp
mcp = FastMCP(
    "API Municipal (Backend de Herramientas)",
    host="127.0.0.1",
    port=MCP_PORT,
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*", *HOSTS_EXTRA],
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*", *[f"https://{h}" for h in HOSTS_EXTRA]],
    ),
)

# ==========================================
# BASES DE DATOS EN MEMORIA
# ==========================================
db_incidencias = []
db_tramites = []
db_informacion = []

# ==========================================
# HERRAMIENTAS MCP
# ==========================================
@mcp.tool()
def registrar_incidencia(tipo_incidencia: str, ubicacion: str, descripcion: str) -> str:
    """ÚSALA PARA: Reportar desperfectos físicos en la ciudad (baches, farolas, limpieza, mobiliario roto)."""
    ticket_id = f"INC-{abs(hash(descripcion)) % 100000}"
    db_incidencias.append({
        "ticket_id": ticket_id,
        "tipo": tipo_incidencia,
        "ubicacion": ubicacion,
        "estado": "Registrado"
    })
    return f"RESULTADO: Incidencia en '{ubicacion}' registrada. Ticket: {ticket_id}."

@mcp.tool()
def iniciar_tramite(tipo_tramite: str, dni_ciudadano: str) -> str:
    """ÚSALA PARA: Gestionar papeleo oficial, certificados de empadronamiento. Si no tienes DNI, envía 'SIN_DNI'."""
    if dni_ciudadano == "SIN_DNI" or not dni_ciudadano:
        return "INSTRUCCIÓN: Faltan datos. Pide al usuario que te facilite su DNI para tramitarlo."

    db_tramites.append({"dni": dni_ciudadano, "tramite": tipo_tramite, "estado": "En proceso"})
    return f"RESULTADO: Trámite de '{tipo_tramite}' iniciado para el DNI {dni_ciudadano}."

@mcp.tool()
def consultar_informacion(consulta_usuario: str) -> str:
    """ÚSALA PARA: Responder preguntas generales, dudas sobre horarios de instalaciones, eventos y FAQ."""
    consulta = consulta_usuario.lower()
    db_informacion.append({"consulta": consulta})

    if "piscina" in consulta: return "RESULTADO: La piscina abre de 09:00 a 21:00."
    if "fiestas" in consulta: return "RESULTADO: Las fiestas son la última semana de septiembre."
    if "punto limpio" in consulta: return "RESULTADO: El punto limpio abre M-S de 10:00 a 14:00."

    return "RESULTADO: No he encontrado esa información. Deriva al usuario al teléfono 010."

@mcp.tool()
def ver_registros() -> str:
    """ÚSALA PARA: Consultar el historial y los registros de todo lo que el usuario ha solicitado."""
    resumen = {"incidencias": db_incidencias, "tramites": db_tramites, "consultas": db_informacion}
    return f"RESULTADO REGISTROS: {json.dumps(resumen, ensure_ascii=False)}"

if __name__ == "__main__":
    print(f"🚀 Arrancando Servidor MCP (Streamable HTTP) en http://127.0.0.1:{MCP_PORT}/mcp")
    mcp.run(transport="streamable-http")
