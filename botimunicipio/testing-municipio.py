import os
import sys
import json
import time
import uuid
import random
import argparse
import requests
from collections import Counter, defaultdict
from dotenv import load_dotenv

# ==========================================
# Cargar variables de entorno (.env)
# ==========================================
load_dotenv()

# ==========================================
# CONFIGURACIÓN
# ==========================================
URL_LOCAL = os.getenv("LOCAL_AGENT_URL", "http://127.0.0.1:8000/chat")
URL_PLATAFORMA = os.getenv(
    "AGENT_URL",
    "https://development-wc-019e6383-b65fad2b.us-east-2.cloud.wso2.com:443/botiayuntamiento-botiayuntamiento-endpoint/chat"
)
AGENT_API_KEY = os.getenv("AGENT_API_KEY", "")
TIMEOUT = int(os.getenv("TEST_TIMEOUT", "120"))

# ==========================================
# 1. TEMAS PARA registrar_incidencia
# ==========================================
INCIDENCIAS = [
    "un bache enorme", "una farola que no enciende", "una farola que parpadea toda la noche",
    "un contenedor de basura desbordado", "un contenedor quemado", "basura acumulada en la acera",
    "un banco roto", "una papelera arrancada", "un semáforo que no funciona",
    "un semáforo en ámbar fijo", "una señal de stop caída", "un paso de peatones borrado",
    "una alcantarilla sin tapa", "una alcantarilla atascada que inunda la calle", "una fuga de agua en la acera",
    "un árbol con ramas a punto de caer", "un árbol que necesita poda", "raíces que levantaron la acera",
    "un columpio roto en el parque", "un tobogán con astillas", "una fuente pública que no para de perder agua",
    "pintadas en la fachada del colegio", "excrementos de perro en el parque infantil", "un coche abandonado",
    "una baldosa suelta", "una barandilla doblada", "un cable eléctrico colgando",
    "un nido de avispas en un árbol del parque", "ratas en el solar", "un muro con riesgo de derrumbe",
    "una boca de riego rota", "un aparcamiento de bicis destrozado", "una marquesina de autobús con el cristal roto",
    "hojas acumuladas que tapan los desagües", "un charco permanente que no drena", "ruido de una obra fuera de horario",
]
CALLES = [
    "la calle Cramer", "la calle Sol", "la avenida de la Constitución", "la plaza Mayor", "la calle Real",
    "la calle de la Iglesia", "el paseo del Prado", "la calle San Juan", "la avenida de Andalucía",
    "la calle Cervantes", "la ronda Norte", "la calle del Río", "la plaza de España", "la calle Mayor",
    "la calle Alcalá", "la avenida del Puerto", "el camino de la Ermita", "la calle Lope de Vega",
    "el parque del Oeste", "la calle de los Olivos", "la calle Goya", "la travesía del Molino",
]
PLANTILLAS_INCIDENCIA = [
    "Quiero crear una incidencia: hay {inc} en {calle} al {num}.",
    "Hay {inc} en {calle} {num}, ¿lo pueden arreglar?",
    "Vengo a reportar {inc} en {calle}, a la altura del número {num}.",
    "Buenas, en {calle} {num} hay {inc}. Registradlo por favor.",
    "Aviso de desperfecto: {inc} frente al portal {num} de {calle}.",
    "Necesito dar parte de {inc} en {calle} número {num}.",
]

def generar_incidencia():
    return random.choice(PLANTILLAS_INCIDENCIA).format(
        inc=random.choice(INCIDENCIAS), calle=random.choice(CALLES), num=random.randint(1, 250)
    )

# ==========================================
# 2. TEMAS PARA iniciar_tramite
# ==========================================
TRAMITES = [
    "el certificado de empadronamiento", "el volante de empadronamiento", "el padrón histórico",
    "el certificado de convivencia", "una licencia de obra menor", "una licencia de apertura de negocio",
    "la tarjeta de aparcamiento para residentes", "la tarjeta de estacionamiento para discapacidad",
    "el alta en el padrón", "el cambio de domicilio en el padrón", "la baja del padrón",
    "una bonificación del IBI", "el fraccionamiento del IBI", "la exención del impuesto de circulación",
    "la licencia para tener un perro potencialmente peligroso", "el registro de pareja de hecho",
    "la solicitud de vado permanente", "una ayuda de emergencia social", "la inscripción en la escuela de verano",
    "la reserva de una pista polideportiva", "el permiso para terraza de bar", "la cita para la cédula de habitabilidad",
    "la devolución de una multa pagada dos veces", "el certificado de bienes", "el abono del bono-bus municipal",
]
PLANTILLAS_TRAMITE_DNI = [
    "Necesito {tram}, mi DNI es {dni}.",
    "Quiero solicitar {tram}. DNI {dni}.",
    "Hola, ¿me tramitas {tram}? Mi documento es {dni}.",
    "Inicia por favor este trámite: {tram}, para el DNI {dni}.",
]
PLANTILLAS_TRAMITE_SIN_DNI = [
    "Necesito {tram}.",
    "Quiero pedir {tram}, ¿cómo lo hago?",
    "¿Me puedes iniciar {tram}?",
    "Tengo que sacar {tram} cuanto antes.",
]
LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"

def _dni_valido():
    numero = random.randint(10000000, 99999999)
    return f"{numero}{LETRAS_DNI[numero % 23]}"

def generar_tramite():
    tram = random.choice(TRAMITES)
    if random.random() < 0.7:
        dni = _dni_valido()
        return random.choice(PLANTILLAS_TRAMITE_DNI).format(tram=tram, dni=dni), {"dni": dni}
    return random.choice(PLANTILLAS_TRAMITE_SIN_DNI).format(tram=tram), {"dni": None}

# ==========================================
# 3. TEMAS PARA consultar_informacion
# ==========================================
# (pregunta, texto que debería aparecer en la respuesta). Los tres primeros grupos tienen
# respuesta en mcp_server.py; el resto debería derivar al 010.
CONSULTAS = [
    ("¿A qué hora abre la piscina municipal?", "09:00"),
    ("¿Cuál es el horario de la piscina este verano?", "09:00"),
    ("¿Hasta qué hora puedo ir a la piscina?", "21:00"),
    ("¿Cuándo son las fiestas del pueblo?", "septiembre"),
    ("¿Qué semana caen las fiestas patronales?", "septiembre"),
    ("¿Cuándo empiezan las fiestas este año?", "septiembre"),
    ("¿Qué horario tiene el punto limpio?", "10:00"),
    ("¿El punto limpio abre los sábados?", "10:00"),
    ("¿Dónde y cuándo puedo llevar un colchón viejo al punto limpio?", "10:00"),
    ("¿A qué hora abre la biblioteca municipal?", "010"),
    ("¿Qué horario tiene el ayuntamiento para atención presencial?", "010"),
    ("¿Cuándo pasa el camión de recogida de muebles?", "010"),
    ("¿Hay cursos de natación para niños?", "010"),
    ("¿Dónde está el centro de salud más cercano?", "010"),
    ("¿Qué días hay mercadillo?", "010"),
    ("¿Cuánto cuesta el abono del polideportivo?", "010"),
    ("¿A qué hora cierra el cementerio?", "010"),
    ("¿Hay alguna exposición en la casa de cultura?", "010"),
    ("¿Cuándo es el próximo pleno municipal?", "010"),
    ("¿Dónde puedo aparcar gratis cerca del centro?", "010"),
    ("¿Qué autobús va al hospital?", "010"),
    ("¿Hay wifi gratis en la plaza Mayor?", "010"),
    ("¿Cuándo abre el plazo de inscripción en las escuelas infantiles?", "010"),
    ("¿Hay huertos urbanos disponibles para alquilar?", "010"),
]

def generar_consulta():
    pregunta, esperado = random.choice(CONSULTAS)
    return pregunta, {"esperado": esperado}

# ==========================================
# 4. TEMAS PARA ver_registros
# ==========================================
PREGUNTAS_REGISTROS = [
    "Muéstrame mis registros.",
    "Quiero ver el historial de todo lo que he pedido.",
    "¿Qué incidencias hay registradas?",
    "Enséñame la lista de incidencias y trámites.",
    "¿Puedes listar los trámites que están en proceso?",
    "Dame un resumen de mis solicitudes.",
    "¿Qué consultas se han hecho hasta ahora?",
    "Ver mis registros, por favor.",
    "¿Cuál es el estado de mis incidencias?",
    "Necesito ver el historial completo del ayuntamiento.",
]

def generar_registros():
    return random.choice(PREGUNTAS_REGISTROS), {}

# ==========================================
# GENERADORES Y VALIDACIÓN (heurística sobre el texto de la respuesta)
# ==========================================
GENERADORES = {
    "registrar_incidencia": lambda: (generar_incidencia(), {}),
    "iniciar_tramite": generar_tramite,
    "consultar_informacion": generar_consulta,
    "ver_registros": generar_registros,
}

def validar(tool: str, respuesta: str, datos: dict) -> bool:
    r = respuesta.lower()
    if tool == "registrar_incidencia":
        return "inc-" in r
    if tool == "iniciar_tramite":
        if datos.get("dni"):
            return datos["dni"].lower() in r or "iniciado" in r
        return "dni" in r
    if tool == "consultar_informacion":
        return datos["esperado"].lower() in r
    if tool == "ver_registros":
        return any(p in r for p in ("incidencia", "trámite", "tramite", "registro", "consulta", "inc-"))
    return False

def planificar(cantidad: int) -> list:
    """Las primeras peticiones cubren cada tool una vez (en orden aleatorio); el resto es al azar."""
    tools = list(GENERADORES)
    cobertura = random.sample(tools, len(tools))
    plan = cobertura[:cantidad] + [random.choice(tools) for _ in range(cantidad - len(cobertura))]
    random.shuffle(plan)
    return plan

# ==========================================
# EJECUCIÓN
# ==========================================
def ejecutar_peticiones(url: str, cantidad: int, pausa: float, misma_sesion: bool, verbose: bool):
    headers = {"Content-Type": "application/json"}
    if AGENT_API_KEY and "127.0.0.1" not in url and "localhost" not in url:
        headers["x-api-key"] = AGENT_API_KEY

    if cantidad < len(GENERADORES):
        print(f"⚠️  Con {cantidad} petición(es) no se cubren las {len(GENERADORES)} tools.")

    plan = planificar(cantidad)
    sesion_fija = f"test-municipio-{uuid.uuid4().hex[:8]}"
    resultados = defaultdict(Counter)
    tiempos = []

    print(f"\n🚀 Iniciando batería de {cantidad} petición(es) contra {url}")
    print(f"   Reparto: {dict(Counter(plan))}")
    print("-" * 60)

    for i, tool in enumerate(plan, start=1):
        mensaje, datos = GENERADORES[tool]()
        session_id = sesion_fija if misma_sesion else f"test-municipio-{uuid.uuid4().hex[:8]}"
        payload = {"message": mensaje, "session_id": session_id}

        print(f"\n▶ PETICIÓN {i} DE {cantidad}  [tool esperada: {tool}]")
        print(f"✍️  Enviando: {mensaje}")
        if verbose:
            print(f"Body    : {json.dumps(payload, ensure_ascii=False)}")

        inicio = time.time()
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
            duracion = time.time() - inicio
            tiempos.append(duracion)
            if verbose:
                print(f"Status  : {response.status_code}  ({duracion:.1f}s)")
                print(f"Raw     : {response.text[:500]}")
            response.raise_for_status()

            respuesta_agente = response.json().get("response", "")
            ok = validar(tool, respuesta_agente, datos)
            resultados[tool]["ok" if ok else "dudosa"] += 1
            print(f"🤖 Agente ({duracion:.1f}s): {respuesta_agente}")
            print("✅ Respuesta coherente con la tool" if ok else "⚠️  La respuesta no parece venir de la tool esperada")

        except (requests.exceptions.RequestException, ValueError) as e:
            resultados[tool]["error"] += 1
            print(f"❌ ERROR EN LA COMUNICACIÓN: {e}")

        print("-" * 60)
        if i < cantidad:
            time.sleep(pausa)

    imprimir_resumen(resultados, tiempos, cantidad)

def imprimir_resumen(resultados, tiempos, cantidad):
    print("\n" + "=" * 60)
    print("📊 RESUMEN")
    print("=" * 60)
    print(f"{'tool':<24}{'total':>7}{'ok':>6}{'dudosa':>8}{'error':>7}")
    totales = Counter()
    for tool in GENERADORES:
        c = resultados[tool]
        total = sum(c.values())
        totales.update(c)
        print(f"{tool:<24}{total:>7}{c['ok']:>6}{c['dudosa']:>8}{c['error']:>7}")
    print("-" * 52)
    print(f"{'TOTAL':<24}{cantidad:>7}{totales['ok']:>6}{totales['dudosa']:>8}{totales['error']:>7}")
    if tiempos:
        print(f"\n⏱  Tiempo medio: {sum(tiempos) / len(tiempos):.1f}s  |  máx: {max(tiempos):.1f}s")
    no_cubiertas = [t for t in GENERADORES if not resultados[t]]
    if no_cubiertas:
        print(f"⚠️  Tools sin probar: {', '.join(no_cubiertas)}")
    print("\n✅ Batería de pruebas finalizada.")

def pedir_cantidad() -> int:
    while True:
        try:
            cantidad = int(input("\n¿Cuántas peticiones automáticas deseas enviar?: "))
            if cantidad > 0:
                return cantidad
            print("Por favor, ingresa un número mayor a 0.")
        except ValueError:
            print("Entrada inválida. Debes ingresar un número entero.")

def menu_destino() -> str:
    print("=" * 60)
    print("🤖 AUTOMATIZADOR DE PRUEBAS - AGENTE MUNICIPAL")
    print("=" * 60)
    print(f"1. Agente local      ({URL_LOCAL})")
    print(f"2. Agente plataforma ({URL_PLATAFORMA})")
    print("3. Salir")
    while True:
        opcion = input("\nElige una opción (1-3): ")
        if opcion == "1":
            return URL_LOCAL
        if opcion == "2":
            return URL_PLATAFORMA
        if opcion == "3":
            print("Saliendo del simulador...")
            sys.exit(0)
        print("Opción inválida. Intenta nuevamente.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batería aleatoria de pruebas para las tools del agente municipal.")
    parser.add_argument("-n", "--cantidad", type=int, help="Cantidad de peticiones (si no se indica, se pregunta)")
    parser.add_argument("--destino", choices=["local", "plataforma"], help="Agente a probar (si no se indica, se pregunta)")
    parser.add_argument("--url", help="URL del /chat a probar (tiene prioridad sobre --destino)")
    parser.add_argument("--pausa", type=float, default=2.0, help="Segundos entre peticiones (default 2)")
    parser.add_argument("--seed", type=int, help="Semilla para repetir exactamente la misma batería")
    parser.add_argument("--misma-sesion", action="store_true", help="Usar un único session_id para todas las peticiones")
    parser.add_argument("-v", "--verbose", action="store_true", help="Mostrar body, status y respuesta cruda")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    if args.url:
        url = args.url
    elif args.destino:
        url = URL_LOCAL if args.destino == "local" else URL_PLATAFORMA
    else:
        url = menu_destino()

    cantidad = args.cantidad if args.cantidad and args.cantidad > 0 else pedir_cantidad()
    ejecutar_peticiones(url, cantidad, args.pausa, args.misma_sesion, args.verbose)
