"""
main.py — Agente de visión: cámara + YOLO + LLM local (qwen3-vl-2b-it) + voz.

YOLO detecta objetos en vivo y los anuncia en voz alta. Además podés hacerle
preguntas al LLM, que recibe el frame actual + las detecciones de YOLO, así que
también describe la escena y lee texto (carteles, etiquetas, pantallas).

Toda la configuración está en .env:
    LOCAL_LLM_BASE_URL=https://macos.tailcc45b1.ts.net/v1
    LOCAL_LLM_API_KEY=...
    LOCAL_LLM_MODEL=qwen3-vl-2b-it
Si LOCAL_LLM_BASE_URL está vacío, funciona solo con YOLO + voz.

Uso:  python main.py
En la ventana:   q salir · espacio repetir · d describir/leer escena · m silenciar
En la terminal:  escribí una pregunta y Enter (p. ej. "¿qué dice el cartel?")
"""
from __future__ import annotations

import base64
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter, deque
from pathlib import Path

import cv2
from ultralytics import YOLO


# --- Configuración (.env) ------------------------------------------------------
def load_dotenv(path: Path = Path(__file__).with_name(".env")) -> None:
    """Carga KEY=valor en os.environ sin pisar variables ya exportadas."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        value = value.strip()
        if value[:1] in "\"'" and value[-1:] == value[:1]:
            value = value[1:-1]
        elif value.startswith("#"):                   # KEY=   # comentario  -> vacío
            value = ""
        else:
            value = value.split(" #", 1)[0].strip()  # comentario al final de línea
        os.environ.setdefault(key.strip(), value)


load_dotenv()


def env(key: str, default: str = "") -> str:
    return os.getenv(key) or default


CAMERA = int(env("CAMERA", "0"))
YOLO_MODEL = env("YOLO_MODEL", "yolo26n.pt")
YOLO_CONF = float(env("YOLO_CONF", "0.45"))
YOLO_DEVICE = env("YOLO_DEVICE")              # vacío = automático
STABLE_FRAMES = int(env("STABLE_FRAMES", "8"))
ANNOUNCE_COOLDOWN = float(env("ANNOUNCE_COOLDOWN", "3.0"))
VOICE = env("VOICE", "Paulina")

LLM_BASE_URL = env("LOCAL_LLM_BASE_URL").rstrip("/")
LLM_API_KEY = env("LOCAL_LLM_API_KEY")
LLM_MODEL = env("LOCAL_LLM_MODEL", "qwen3-vl-2b-it")
LLM_MAX_TOKENS = int(env("LLM_MAX_TOKENS", "400"))
LLM_TEMPERATURE = float(env("LLM_TEMPERATURE", "0.3"))
LLM_TIMEOUT = float(env("LLM_TIMEOUT", "120"))
LLM_HISTORY_TURNS = int(env("LLM_HISTORY_TURNS", "6"))
IMAGE_MAX_SIDE = int(env("IMAGE_MAX_SIDE", "1024"))

# --- Clases COCO en español: (singular, plural, género) ----------------------
ES = {
    "person": ("persona", "personas", "f"), "bicycle": ("bicicleta", "bicicletas", "f"),
    "car": ("auto", "autos", "m"), "motorcycle": ("moto", "motos", "f"),
    "airplane": ("avión", "aviones", "m"), "bus": ("colectivo", "colectivos", "m"),
    "train": ("tren", "trenes", "m"), "truck": ("camión", "camiones", "m"),
    "boat": ("barco", "barcos", "m"), "traffic light": ("semáforo", "semáforos", "m"),
    "fire hydrant": ("hidrante", "hidrantes", "m"),
    "stop sign": ("señal de pare", "señales de pare", "f"),
    "parking meter": ("parquímetro", "parquímetros", "m"), "bench": ("banco", "bancos", "m"),
    "bird": ("pájaro", "pájaros", "m"), "cat": ("gato", "gatos", "m"),
    "dog": ("perro", "perros", "m"), "horse": ("caballo", "caballos", "m"),
    "sheep": ("oveja", "ovejas", "f"), "cow": ("vaca", "vacas", "f"),
    "elephant": ("elefante", "elefantes", "m"), "bear": ("oso", "osos", "m"),
    "zebra": ("cebra", "cebras", "f"), "giraffe": ("jirafa", "jirafas", "f"),
    "backpack": ("mochila", "mochilas", "f"), "umbrella": ("paraguas", "paraguas", "m"),
    "handbag": ("cartera", "carteras", "f"), "tie": ("corbata", "corbatas", "f"),
    "suitcase": ("valija", "valijas", "f"), "frisbee": ("frisbee", "frisbees", "m"),
    "skis": ("esquí", "esquís", "m"), "snowboard": ("tabla de snow", "tablas de snow", "f"),
    "sports ball": ("pelota", "pelotas", "f"), "kite": ("barrilete", "barriletes", "m"),
    "baseball bat": ("bate", "bates", "m"),
    "baseball glove": ("guante de béisbol", "guantes de béisbol", "m"),
    "skateboard": ("skate", "skates", "m"), "surfboard": ("tabla de surf", "tablas de surf", "f"),
    "tennis racket": ("raqueta", "raquetas", "f"), "bottle": ("botella", "botellas", "f"),
    "wine glass": ("copa", "copas", "f"), "cup": ("taza", "tazas", "f"),
    "fork": ("tenedor", "tenedores", "m"), "knife": ("cuchillo", "cuchillos", "m"),
    "spoon": ("cuchara", "cucharas", "f"), "bowl": ("bol", "boles", "m"),
    "banana": ("banana", "bananas", "f"), "apple": ("manzana", "manzanas", "f"),
    "sandwich": ("sándwich", "sándwiches", "m"), "orange": ("naranja", "naranjas", "f"),
    "broccoli": ("brócoli", "brócolis", "m"), "carrot": ("zanahoria", "zanahorias", "f"),
    "hot dog": ("pancho", "panchos", "m"), "pizza": ("pizza", "pizzas", "f"),
    "donut": ("dona", "donas", "f"), "cake": ("torta", "tortas", "f"),
    "chair": ("silla", "sillas", "f"), "couch": ("sillón", "sillones", "m"),
    "potted plant": ("planta", "plantas", "f"), "bed": ("cama", "camas", "f"),
    "dining table": ("mesa", "mesas", "f"), "toilet": ("inodoro", "inodoros", "m"),
    "tv": ("televisor", "televisores", "m"), "laptop": ("notebook", "notebooks", "f"),
    "mouse": ("mouse", "mouses", "m"), "remote": ("control remoto", "controles remotos", "m"),
    "keyboard": ("teclado", "teclados", "m"), "cell phone": ("celular", "celulares", "m"),
    "microwave": ("microondas", "microondas", "m"), "oven": ("horno", "hornos", "m"),
    "toaster": ("tostadora", "tostadoras", "f"), "sink": ("pileta", "piletas", "f"),
    "refrigerator": ("heladera", "heladeras", "f"), "book": ("libro", "libros", "m"),
    "clock": ("reloj", "relojes", "m"), "vase": ("florero", "floreros", "m"),
    "scissors": ("tijera", "tijeras", "f"),
    "teddy bear": ("oso de peluche", "osos de peluche", "m"),
    "hair drier": ("secador de pelo", "secadores de pelo", "m"),
    "toothbrush": ("cepillo de dientes", "cepillos de dientes", "m"),
}
NUM = {2: "dos", 3: "tres", 4: "cuatro", 5: "cinco",
       6: "seis", 7: "siete", 8: "ocho", 9: "nueve", 10: "diez"}


def to_phrase(counts: dict[str, int]) -> str:
    if not counts:
        return "No detecto nada."
    parts = []
    for label, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        sing, plur, g = ES.get(label, (label, label + "s", "m"))
        if n == 1:
            parts.append(f"{'una' if g == 'f' else 'un'} {sing}")
        else:
            parts.append(f"{NUM.get(n, n)} {plur}")
    body = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " y " + parts[-1]
    return f"Veo {body}."


def ascii_only(text: str) -> str:
    """cv2.putText no dibuja acentos ni ñ: 'camión' -> 'camion'."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def describe_detections(r) -> str:
    """Resumen de YOLO en texto para el LLM, con posición aproximada."""
    h, w = r.orig_shape
    lines = []
    for box, c, p in zip(r.boxes.xyxy, r.boxes.cls, r.boxes.conf):
        x1, y1, x2, y2 = (float(v) for v in box)
        cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
        horiz = "izquierda" if cx < 0.33 else "derecha" if cx > 0.66 else "centro"
        vert = "arriba" if cy < 0.33 else "abajo" if cy > 0.66 else "medio"
        lines.append(f"- {r.names[int(c)]} (conf {float(p):.2f}) en {horiz}/{vert}")
    return "\n".join(lines) or "(YOLO no detectó objetos)"


# --- Voz: hilo dedicado para no bloquear el video -----------------------------
class Speaker:
    """Cola de una sola frase. Las respuestas del LLM ('important') no las pisan
    los anuncios automáticos de YOLO."""

    def __init__(self, voice: str):
        self.q: queue.Queue[tuple[str, bool]] = queue.Queue(maxsize=1)
        self.voice = voice
        self.muted = False
        self.system = platform.system()
        self.lock = threading.Lock()
        self.important_pending = 0
        threading.Thread(target=self._loop, daemon=True).start()

    def _drain(self) -> None:
        try:
            _, important = self.q.get_nowait()
            self.important_pending -= important
        except queue.Empty:
            pass

    def say(self, text: str, important: bool = False) -> None:
        with self.lock:
            if self.muted or (not important and self.important_pending):
                return
            self._drain()
            self.important_pending += important
            self.q.put_nowait((text, important))

    def toggle_mute(self) -> None:
        with self.lock:
            self.muted = not self.muted
            if self.muted:
                self._drain()

    def _loop(self) -> None:
        engine = None
        if self.system != "Darwin" and not shutil.which("espeak-ng"):
            import pyttsx3  # Windows / Linux sin espeak-ng
            engine = pyttsx3.init()
            for v in engine.getProperty("voices"):
                if "es" in (v.id + str(v.languages)).lower():
                    engine.setProperty("voice", v.id)
                    break
        while True:
            text, important = self.q.get()
            print(f"🔊 {text}")
            if self.system == "Darwin":           # macOS: voz nativa
                subprocess.run(["say", "-v", self.voice, text])
            elif engine is None:                   # Linux con espeak-ng
                subprocess.run(["espeak-ng", "-v", "es-419", text])
            else:
                engine.say(text)
                engine.runAndWait()
            if important:
                with self.lock:
                    self.important_pending -= 1


# --- LLM local (API /v1/chat/completions) -------------------------------------
SYSTEM = """Sos un asistente de visión que mira por una cámara en tiempo real.
Recibís el frame actual y la lista de objetos que detectó YOLO (puede tener errores
o faltar cosas: priorizá lo que ves en la imagen).
- Respondé en español, en 1 a 3 frases cortas: tu respuesta se lee en voz alta.
- Si hay texto visible y te lo piden (o es relevante), leelo textualmente.
- Si no se ve bien o no estás seguro, decilo. No inventes.
- Sin markdown, listas ni emojis."""

DESCRIBE = "Describí brevemente lo que ves. Si hay texto visible, leelo."


class Brain:
    def __init__(self):
        self.vision = True  # se apaga sola si el modelo rechaza imágenes
        self.history: list[tuple[str, str]] = []  # (pregunta, respuesta), solo texto

    def ask(self, question: str, jpeg: bytes, detections: str) -> str:
        prompt = f"Detecciones de YOLO:\n{detections}\n\nPregunta: {question}"
        image = base64.b64encode(jpeg).decode() if self.vision else None
        try:
            raw = self._chat(prompt, image)
        except urllib.error.HTTPError as e:
            if image is None or e.code not in (400, 415, 422, 500, 501):
                raise
            # El servidor no acepta imágenes (falta el mmproj): seguimos solo con YOLO
            print(f"⚠️  {LLM_MODEL} no aceptó la imagen (HTTP {e.code}); uso solo YOLO.")
            self.vision = False
            raw = self._chat(prompt, None)
        answer = re.sub(r"[*_#`]", "", raw).strip()  # sin markdown: se lee en voz alta
        if not answer:
            raise RuntimeError("el modelo devolvió una respuesta vacía")
        # Guardamos solo texto: reenviar imágenes viejas gasta tokens y no aporta
        if LLM_HISTORY_TURNS:
            self.history = (self.history + [(question, answer)])[-LLM_HISTORY_TURNS:]
        return answer

    def _chat(self, prompt: str, image_b64: str | None) -> str:
        messages = [{"role": "system", "content": SYSTEM}]
        for q, a in self.history:
            messages += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
        if image_b64:
            messages.append({"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                {"type": "text", "text": prompt},
            ]})
        else:
            messages.append({"role": "user", "content": prompt})

        payload = {"model": LLM_MODEL, "messages": messages,
                   "max_tokens": LLM_MAX_TOKENS, "temperature": LLM_TEMPERATURE}
        headers = {"Content-Type": "application/json"}
        if LLM_API_KEY:
            headers["Authorization"] = f"Bearer {LLM_API_KEY}"

        req = urllib.request.Request(f"{LLM_BASE_URL}/chat/completions",
                                     data=json.dumps(payload).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
            return json.load(resp)["choices"][0]["message"]["content"] or ""


# --- Estado compartido entre el loop de video y el hilo del LLM --------------
class Latest:
    def __init__(self):
        self.lock = threading.Lock()
        self.frame = None
        self.detections = ""

    def set(self, frame, detections: str) -> None:
        with self.lock:
            self.frame, self.detections = frame, detections

    def jpeg(self, max_side: int) -> tuple[bytes, str] | None:
        with self.lock:
            if self.frame is None:
                return None
            frame, dets = self.frame.copy(), self.detections
        h, w = frame.shape[:2]
        if max(h, w) > max_side:  # imágenes más chicas = menos tokens y más rápido
            s = max_side / max(h, w)
            frame = cv2.resize(frame, (int(w * s), int(h * s)))
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return (buf.tobytes(), dets) if ok else None


def brain_worker(brain: Brain, latest: Latest, questions: queue.Queue,
                 speaker: Speaker, busy: threading.Event) -> None:
    while True:
        question = questions.get()
        snap = latest.jpeg(IMAGE_MAX_SIDE)
        if snap is None:
            continue
        busy.set()
        print(f"🤔 ({LLM_MODEL}) {question}")
        try:
            answer = brain.ask(question, *snap)
        except Exception as e:  # no tiramos abajo el video por un error de red/API
            answer = "No pude consultar al modelo."
            print(f"⚠️  {type(e).__name__}: {e}")
        finally:
            busy.clear()
        print(f"💬 {answer}")
        speaker.say(answer, important=True)


def stdin_reader(questions: queue.Queue, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            q = input().strip()
        except EOFError:
            return
        if q.lower() in ("salir", "exit", "quit"):
            stop.set()
        elif q:
            questions.put(q)


# --- Bucle principal ----------------------------------------------------------
def main() -> None:
    yolo = YOLO(YOLO_MODEL)  # descarga los pesos la primera vez
    device = YOLO_DEVICE or None
    if not device:  # Ultralytics no elige MPS solo: en Mac Apple Silicon lo pedimos
        import torch
        device = "mps" if torch.backends.mps.is_available() else None

    # Probamos la cámara antes que YOLO para dar un error entendible (en macOS
    # este primer acceso es el que dispara el pedido de permiso)
    cap = cv2.VideoCapture(CAMERA)
    ok = cap.isOpened() and cap.read()[0]
    cap.release()
    if not ok:
        raise SystemExit(
            f"❌ No pude abrir la cámara {CAMERA}.\n"
            "   macOS: Ajustes del Sistema → Privacidad y seguridad → Cámara → activá tu\n"
            "   terminal (Terminal, iTerm, VS Code…), cerrala del todo (Cmd+Q) y volvé a abrirla.\n"
            "   Si tenés varias cámaras, probá otro CAMERA en .env.")

    speaker = Speaker(VOICE)
    latest = Latest()
    questions: queue.Queue[str] = queue.Queue()
    busy = threading.Event()
    stop = threading.Event()

    llm_on = bool(LLM_BASE_URL)
    if llm_on:
        threading.Thread(target=brain_worker, daemon=True,
                         args=(Brain(), latest, questions, speaker, busy)).start()
        threading.Thread(target=stdin_reader, args=(questions, stop), daemon=True).start()
        print(f"LLM: {LLM_MODEL} @ {LLM_BASE_URL}. Escribí una pregunta y Enter, o 'salir'.")
    else:
        print("LLM desactivado (LOCAL_LLM_BASE_URL vacío): solo YOLO + voz.")

    window: deque[tuple] = deque(maxlen=STABLE_FRAMES)
    last_said: tuple | None = None
    last_time = 0.0
    title = "Detector (q salir, espacio repetir, d describir, m silenciar)"

    speaker.say("Cámara activada.")
    print(f"YOLO: {YOLO_MODEL} en {device or 'auto'}")
    # stream=True devuelve un generador: no acumula frames en memoria
    for r in yolo.predict(source=CAMERA, conf=YOLO_CONF, device=device,
                          stream=True, verbose=False):
        counts = Counter(r.names[int(c)] for c in r.boxes.cls)
        latest.set(r.orig_img, describe_detections(r))
        window.append(tuple(sorted(counts.items())))

        # Escena estable = la misma composición en ≥75% de la ventana (tolera parpadeos)
        key, n = Counter(window).most_common(1)[0]
        stable = len(window) == window.maxlen and n >= 0.75 * window.maxlen
        now = time.time()
        if stable and key != last_said and now - last_time > ANNOUNCE_COOLDOWN and not busy.is_set():
            speaker.say(to_phrase(dict(key)))
            last_said, last_time = key, now

        frame = r.plot()
        status = "pensando..." if busy.is_set() else to_phrase(counts)
        cv2.putText(frame, ascii_only(status), (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow(title, frame)

        k = cv2.waitKey(1) & 0xFF
        if k == ord("q") or stop.is_set():
            break
        if k == ord(" "):
            speaker.say(to_phrase(counts), important=True)
        if k == ord("d"):
            if llm_on:
                questions.put(DESCRIBE)
            else:
                print("LLM desactivado: configurá LOCAL_LLM_BASE_URL en .env para usar 'd'.")
        if k == ord("m"):
            speaker.toggle_mute()
            print("🔇 silenciado" if speaker.muted else "🔊 activo")

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
