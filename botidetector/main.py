"""
main.py — Agente de visión: cámara + YOLO + LLM local (qwen3-vl-2b-it) + voz.

YOLO detecta objetos y manos levantadas, MediaPipe detecta la cara (cabeza,
ojos, pestañeos, boca) y qué dedos mostrás; todo se anuncia en voz alta. Además
podés hacerle preguntas al LLM, que recibe el frame actual + lo detectado, así
que también describe la escena y lee texto (carteles, etiquetas, pantallas).

Toda la configuración está en .env:
    LOCAL_LLM_BASE_URL=https://macos.tailcc45b1.ts.net/v1
    LOCAL_LLM_API_KEY=...
    LOCAL_LLM_MODEL=qwen3-vl-2b-it
Si LOCAL_LLM_BASE_URL está vacío, funciona solo con YOLO + voz.

Uso:  python main.py
En la ventana:   q salir · espacio repetir · d describir/leer escena · m silenciar
                 c recalibrar la posición neutra de la cabeza (mirando al frente)
En la terminal:  escribí una pregunta y Enter (p. ej. "¿qué dice el cartel?")
"""
from __future__ import annotations

import base64
import json
import math
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
POSE = env("POSE", "true").lower() in ("1", "true", "si", "sí", "yes")
POSE_MODEL = env("POSE_MODEL", "yolo26n-pose.pt")
FACE = env("FACE", "true").lower() in ("1", "true", "si", "sí", "yes")
FACE_EXPRESSIONS = env("FACE_EXPRESSIONS", "true").lower() in ("1", "true", "si", "sí", "yes")
FINGERS = env("FINGERS", "true").lower() in ("1", "true", "si", "sí", "yes")
HEAD_TURN_DEG = float(env("HEAD_TURN_DEG", "20"))
HEAD_TILT_DEG = float(env("HEAD_TILT_DEG", "15"))
EYES_CLOSED_SECONDS = float(env("EYES_CLOSED_SECONDS", "1.0"))
DOUBLE_BLINK = env("DOUBLE_BLINK", "decir").lower()  # decir | describir | nada
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


# --- Pose: manos levantadas -----------------------------------------------------
# Índices de los 17 keypoints COCO. Izquierda/derecha son del cuerpo de la
# persona (su mano derecha), no del lado de la imagen.
NOSE = 0
ARMS = {"derecha": (6, 8, 10), "izquierda": (5, 7, 9)}  # (hombro, codo, muñeca)
KP_CONF = float(env("POSE_KP_CONF", "0.3"))  # con la cámara cerca, hombros y muñecas salen con poca confianza
POSE_DEBUG = env("POSE_DEBUG").lower() in ("1", "true", "si", "sí", "yes")


def arms_up(xy: list, cf: list) -> dict[str, bool]:
    """Un brazo está levantado si la muñeca o el codo quedan claramente por encima
    del hombro. Si no se ve el hombro (cámara muy cerca), se compara con la nariz."""
    (rs, _, _), (ls, _, _) = ARMS["derecha"], ARMS["izquierda"]
    shoulders_ok = cf[rs] >= KP_CONF and cf[ls] >= KP_CONF
    # margen proporcional al ancho de hombros: tolera la mano a la altura del hombro
    margin = 0.15 * abs(xy[rs][0] - xy[ls][0]) if shoulders_ok else 0
    out = {}
    for side, (sh, el, wr) in ARMS.items():
        if cf[sh] >= KP_CONF:
            ref = xy[sh][1] - margin
        elif cf[NOSE] >= KP_CONF:
            ref = xy[NOSE][1]
        else:
            out[side] = False
            continue
        out[side] = any(cf[k] >= KP_CONF and xy[k][1] < ref for k in (wr, el))
    return out


def raised_hands(p) -> list[str]:
    """Por persona: 'derecha', 'izquierda', 'ambas' o ''."""
    if p.keypoints is None or p.keypoints.conf is None:
        return []
    states = []
    for xy, cf in zip(p.keypoints.xy.tolist(), p.keypoints.conf.tolist()):
        up = arms_up(xy, cf)
        if POSE_DEBUG:
            print("pose " + " · ".join(
                f"{side}: hombro {cf[sh]:.2f}@{xy[sh][1]:.0f} codo {cf[el]:.2f}@{xy[el][1]:.0f} "
                f"muñeca {cf[wr]:.2f}@{xy[wr][1]:.0f} -> {'ARRIBA' if up[side] else '-'}"
                for side, (sh, el, wr) in ARMS.items()) + f" · nariz {cf[NOSE]:.2f}@{xy[NOSE][1]:.0f}")
        r, l = up["derecha"], up["izquierda"]
        states.append("ambas" if r and l else "derecha" if r else "izquierda" if l else "")
    return states


def draw_arms(frame, p) -> None:
    """Dibuja solo hombros y brazos (verde = levantado), sin las líneas de la cara."""
    if p.keypoints is None or p.keypoints.conf is None:
        return
    for xy, cf in zip(p.keypoints.xy.tolist(), p.keypoints.conf.tolist()):
        up = arms_up(xy, cf)
        pt = lambda k: (int(xy[k][0]), int(xy[k][1]))
        rs, ls = ARMS["derecha"][0], ARMS["izquierda"][0]
        if cf[rs] >= KP_CONF and cf[ls] >= KP_CONF:
            cv2.line(frame, pt(rs), pt(ls), (200, 200, 200), 2)
        for side, chain in ARMS.items():
            color = (0, 255, 0) if up[side] else (200, 200, 200)
            seen = [k for k in chain if cf[k] >= KP_CONF]
            for a, b in zip(seen, seen[1:]):
                cv2.line(frame, pt(a), pt(b), color, 3)
            for k in seen:
                cv2.circle(frame, pt(k), 5, color, -1)


def hands_phrase(states: list[str]) -> str:
    up = [s for s in states if s]
    if not up:
        return ""
    if len(up) > 1:
        return f"{NUM.get(len(up), len(up))} personas levantaron la mano.".capitalize()
    hand = "las dos manos" if up[0] == "ambas" else f"la mano {up[0]}"
    return f"Levantaste {hand}." if len(states) == 1 else f"Una persona levantó {hand}."


class Stable:
    """Un valor que cambió y se mantuvo en ≥75% de los últimos N frames (tolera parpadeos)."""

    def __init__(self, n: int = STABLE_FRAMES, initial=None):
        self.window: deque = deque(maxlen=n)
        self.value = initial

    def update(self, v) -> bool:
        self.window.append(v)
        top, c = Counter(self.window).most_common(1)[0]
        if len(self.window) == self.window.maxlen and c >= 0.75 * self.window.maxlen \
                and top != self.value:
            self.value = top
            return True
        return False


# --- MediaPipe: cara (cabeza, ojos, boca) y dedos -------------------------------
MP_MODELS = {
    "face": "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
            "face_landmarker/float16/latest/face_landmarker.task",
    "hand": "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
            "hand_landmarker/float16/latest/hand_landmarker.task",
}
MODELS_DIR = Path(__file__).with_name("models")


def mp_model(name: str) -> str:
    """Ruta al modelo .task de MediaPipe; lo descarga la primera vez."""
    path = MODELS_DIR / f"{name}_landmarker.task"
    if not path.exists():
        MODELS_DIR.mkdir(exist_ok=True)
        print(f"Descargando {path.name}…")
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(MP_MODELS[name], tmp)
        tmp.rename(path)
    return str(path)


# Dedos: 21 puntos por mano (0 = muñeca). Un dedo está extendido si su punta queda
# bastante más lejos de la muñeca que su articulación media (en 3D, así no depende
# del ángulo de la mano). Umbrales medidos con fotos de pulgar arriba, V e índice.
FINGERS_ES = ["el pulgar", "el índice", "el dedo medio", "el anular", "el meñique"]
FINGER_JOINTS = [(6, 8), (10, 12), (14, 16), (18, 20)]  # (articulación media, punta)
FINGERTIPS = [4, 8, 12, 16, 20]


def fingers_up(world) -> list[bool]:
    d = lambda a, b: math.dist((world[a].x, world[a].y, world[a].z),
                               (world[b].x, world[b].y, world[b].z))
    # pulgar: su punta se aleja de la base del meñique y del medio
    thumb = (d(4, 17) / d(2, 17) + d(4, 9) / d(2, 9)) / 2 > 1.35
    return [thumb] + [d(0, tip) / d(0, pip) > 1.2 for pip, tip in FINGER_JOINTS]


def join_es(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1]


def hand_desc(up: list[bool], lm) -> str:
    n = sum(up)
    if n == 0:
        return "el puño cerrado"
    if n == 5:
        return "la mano abierta"
    if up == [True, False, False, False, False]:  # pulgar solo: ¿arriba o abajo?
        if lm[4].y < lm[2].y and lm[4].y < lm[0].y:
            return "el pulgar arriba"
        if lm[4].y > lm[2].y and lm[4].y > lm[0].y:
            return "el pulgar abajo"
    names = [f for f, u in zip(FINGERS_ES, up) if u]
    return join_es(names) if n == 1 else f"{NUM[n]} dedos: {join_es(names)}"


def fingers_phrase(res) -> str:
    hands = []
    for lm, world, handed in zip(res.hand_landmarks, res.hand_world_landmarks, res.handedness):
        # MediaPipe asume imagen espejada (selfie); la cámara no lo está, así que se invierte
        side = "izquierda" if handed[0].category_name == "Right" else "derecha"
        hands.append((side, hand_desc(fingers_up(world), lm)))
    if not hands:
        return ""
    if len(hands) == 1:
        return f"Mostrás {hands[0][1]}."
    hands.sort()  # derecha primero
    return f"Mostrás {hands[0][1]} con la mano derecha y {hands[1][1]} con la izquierda."


def draw_hands(frame, res) -> None:
    """Puntas de los dedos: verde = extendido, gris = doblado."""
    h, w = frame.shape[:2]
    for lm, world in zip(res.hand_landmarks, res.hand_world_landmarks):
        for tip, up in zip(FINGERTIPS, fingers_up(world)):
            cv2.circle(frame, (int(lm[tip].x * w), int(lm[tip].y * h)), 7,
                       (0, 255, 0) if up else (160, 160, 160), -1)


def head_angles(matrix) -> tuple[float, float, float]:
    """(yaw, pitch, roll) en grados desde la matriz de MediaPipe. Signos verificados:
    yaw > 0 = gira a SU izquierda, pitch > 0 = mira abajo, roll > 0 = inclina a SU derecha."""
    m = [list(row) for row in matrix]
    yaw = math.degrees(math.asin(max(-1.0, min(1.0, -m[2][0]))))
    pitch = math.degrees(math.atan2(m[2][1], m[2][2]))
    roll = math.degrees(math.atan2(m[1][0], m[0][0]))
    return yaw, pitch, roll


def oscillates(values: list[float], amp: float) -> bool:
    """¿Fue y vino al menos dos veces (ida-vuelta-ida) con amplitud ≥ amp?"""
    if len(values) < 6 or max(values) - min(values) < amp:
        return False
    mid = (max(values) + min(values)) / 2
    sides = []
    for v in values:
        if abs(v - mid) > amp / 3:
            s = v > mid
            if not sides or sides[-1] != s:
                sides.append(s)
    return len(sides) >= 3


HEAD_PHRASES = {
    "izquierda": "Giraste la cabeza a la izquierda.", "derecha": "Giraste la cabeza a la derecha.",
    "arriba": "Miraste hacia arriba.", "abajo": "Miraste hacia abajo.",
    "incl_izq": "Inclinaste la cabeza a la izquierda.", "incl_der": "Inclinaste la cabeza a la derecha.",
}
HEAD_SHORT = {"": "al frente", "izquierda": "izquierda", "derecha": "derecha", "arriba": "arriba",
              "abajo": "abajo", "incl_izq": "inclinada izq", "incl_der": "inclinada der"}
EYE_CLOSED = 0.5  # score de eyeBlink a partir del cual el ojo está cerrado


class FaceTracker:
    """Convierte cada resultado de MediaPipe en eventos ('Pestañeaste dos veces'…)."""

    def __init__(self):
        self.recalibrate()
        self.head = Stable(initial="")
        self.wink = Stable(n=5, initial="")
        self.expr = Stable(initial="")
        self.motion: deque[tuple[float, float, float]] = deque()  # (t, yaw, pitch)
        self.last_nod = 0.0
        self.closed_since: float | None = None
        self.closed_said = False
        self.blink_times: deque[float] = deque(maxlen=2)
        self.blinks = 0
        self.summary = ""

    def recalibrate(self) -> None:
        """La posición neutra se toma de los primeros frames con cara (mirando al frente)."""
        self.base: tuple[float, float, float] | None = None
        self.calib: list[tuple[float, float, float]] = []

    def update(self, res, now: float) -> list[str]:
        if not res.face_landmarks:
            self.closed_since, self.closed_said, self.summary = None, False, ""
            return []
        events: list[str] = []
        bs = {c.category_name: c.score for c in res.face_blendshapes[0]}
        raw = head_angles(res.facial_transformation_matrixes[0])

        if self.base is None:
            self.calib.append(raw)
            if len(self.calib) < 15:
                self.summary = "Cara: calibrando, mira al frente"
                return []
            self.base = tuple(sorted(v)[len(v) // 2] for v in zip(*self.calib))  # mediana
        yaw, pitch, roll = (r - b for r, b in zip(raw, self.base))

        # Asentir (sí) / negar (no): ida y vuelta en el último segundo y medio
        self.motion.append((now, yaw, pitch))
        while self.motion and now - self.motion[0][0] > 1.5:
            self.motion.popleft()
        if now - self.last_nod > 2.0:
            yaws = [m[1] for m in self.motion]
            pitches = [m[2] for m in self.motion]
            gesture = ("Dijiste que no con la cabeza." if oscillates(yaws, 12) else
                       "Dijiste que sí con la cabeza." if oscillates(pitches, 8) else "")
            if gesture:
                events.append(gesture)
                self.last_nod = now
                self.motion.clear()

        # Dirección de la cabeza
        if abs(yaw) > HEAD_TURN_DEG:
            head = "izquierda" if yaw > 0 else "derecha"
        elif abs(pitch) > HEAD_TILT_DEG:
            head = "abajo" if pitch > 0 else "arriba"
        elif abs(roll) > HEAD_TILT_DEG:
            head = "incl_der" if roll > 0 else "incl_izq"
        else:
            head = ""
        if self.head.update(head) and head and now - self.last_nod > 1.0:
            events.append(HEAD_PHRASES[head])

        # Ojos (eyeBlinkLeft = ojo izquierdo de la persona)
        left, right = bs.get("eyeBlinkLeft", 0), bs.get("eyeBlinkRight", 0)
        both_closed = left > EYE_CLOSED and right > EYE_CLOSED
        if both_closed:
            if self.closed_since is None:
                self.closed_since = now
            elif now - self.closed_since >= EYES_CLOSED_SECONDS and not self.closed_said:
                events.append("Cerraste los ojos.")
                self.closed_said = True
        elif self.closed_since is not None:
            if self.closed_said:
                events.append("Abriste los ojos.")
            elif now - self.closed_since < 0.5:  # cierre corto = pestañeo
                self.blinks += 1
                self.blink_times.append(now)
                if len(self.blink_times) == 2 and self.blink_times[1] - self.blink_times[0] < 0.7:
                    events.append("DOBLE_PESTAÑEO")
                    self.blink_times.clear()
            self.closed_since, self.closed_said = None, False

        wink = ("derecho" if right > EYE_CLOSED and left < 0.3 else
                "izquierdo" if left > EYE_CLOSED and right < 0.3 else "")
        if self.wink.update(wink) and wink:
            events.append(f"Guiñaste el ojo {wink}.")

        if FACE_EXPRESSIONS:
            smile = (bs.get("mouthSmileLeft", 0) + bs.get("mouthSmileRight", 0)) / 2
            expr = "sonrisa" if smile > 0.6 else "boca" if bs.get("jawOpen", 0) > 0.6 else ""
            if self.expr.update(expr) and expr:
                events.append("Estás sonriendo." if expr == "sonrisa" else "Abriste la boca.")

        eyes = "cerrados" if both_closed else "abiertos"
        self.summary = (f"Cabeza: {HEAD_SHORT[head]} | ojos {eyes} | pestaneos: {self.blinks}"
                        f" (yaw {yaw:+.0f} pitch {pitch:+.0f} roll {roll:+.0f})")
        return events


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
    pose = YOLO(POSE_MODEL) if POSE else None
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

    face_lm = hand_lm = None
    if FACE or FINGERS:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
        video = vision.RunningMode.VIDEO
        if FACE:
            face_lm = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=mp_model("face")), running_mode=video,
                output_face_blendshapes=True, output_facial_transformation_matrixes=True))
        if FINGERS:
            hand_lm = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=mp_model("hand")), running_mode=video,
                num_hands=2))
    face = FaceTracker()
    fingers = Stable(initial="")
    last_ts = 0

    window: deque[tuple] = deque(maxlen=STABLE_FRAMES)
    last_said: tuple | None = None
    last_time = 0.0
    raised = Stable(initial=())
    title = "Detector (q salir, espacio repetir, d describir, m silenciar, c calibrar)"

    speaker.say("Cámara activada.")
    extras = [m for m, on in ((POSE_MODEL, pose), ("cara", face_lm), ("dedos", hand_lm)) if on]
    print(f"YOLO: {YOLO_MODEL} en {device or 'auto'}" + (f" + {', '.join(extras)}" if extras else ""))
    # stream=True devuelve un generador: no acumula frames en memoria
    for r in yolo.predict(source=CAMERA, conf=YOLO_CONF, device=device,
                          stream=True, verbose=False):
        now = time.time()
        counts = Counter(r.names[int(c)] for c in r.boxes.cls)
        hands, hands_text, p = [], "", None
        if pose:
            p = pose.predict(r.orig_img, conf=YOLO_CONF, device=device, verbose=False)[0]
            hands = raised_hands(p)
            hands_text = hands_phrase(hands)

        face_events, fingers_text, hres = [], "", None
        if face_lm or hand_lm:
            image = mp.Image(image_format=mp.ImageFormat.SRGB,
                             data=cv2.cvtColor(r.orig_img, cv2.COLOR_BGR2RGB))
            last_ts = max(int(time.monotonic() * 1000), last_ts + 1)  # VIDEO exige ts crecientes
            if face_lm:
                face_events = face.update(face_lm.detect_for_video(image, last_ts), now)
            if hand_lm:
                hres = hand_lm.detect_for_video(image, last_ts)
                fingers_text = fingers_phrase(hres)

        dets = describe_detections(r)
        for label, text in (("pose", hands_text), ("cara", face.summary if face_lm else ""),
                            ("dedos", fingers_text)):
            if text:
                dets += f"\n- {label}: {text}"
        latest.set(r.orig_img, dets)
        window.append(tuple(sorted(counts.items())))

        # Gestos: se dicen al aparecer (no mientras se mantienen)
        if not busy.is_set():
            for ev in face_events:
                if ev == "DOBLE_PESTAÑEO":
                    if DOUBLE_BLINK == "describir" and llm_on:
                        questions.put(DESCRIBE)
                    elif DOUBLE_BLINK != "nada":
                        speaker.say("Pestañeaste dos veces.")
                else:
                    speaker.say(ev)
            if fingers.update(fingers_text) and fingers_text:
                speaker.say(fingers_text)

        # Escena estable = la misma composición en ≥75% de la ventana (tolera parpadeos)
        key, n = Counter(window).most_common(1)[0]
        stable = len(window) == window.maxlen and n >= 0.75 * window.maxlen
        if stable and key != last_said and now - last_time > ANNOUNCE_COOLDOWN and not busy.is_set():
            speaker.say(to_phrase(dict(key)))
            last_said, last_time = key, now

        # Manos: se anuncia al levantarlas; al bajarlas se rearma en silencio
        if pose and raised.update(tuple(sorted(h for h in hands if h))) \
                and raised.value and not busy.is_set():
            speaker.say(hands_phrase(list(raised.value)))

        frame = r.plot()
        if p is not None:  # brazos encima de las cajas de objetos
            draw_arms(frame, p)
        if hres is not None:
            draw_hands(frame, hres)
        lines = [("pensando..." if busy.is_set() else to_phrase(counts), (0, 255, 0)),
                 (hands_text, (0, 200, 255)),
                 (face.summary if face_lm else "", (255, 200, 0)),
                 (fingers_text, (255, 0, 255))]
        y = 30
        for text, color in lines:
            if text:
                cv2.putText(frame, ascii_only(text), (10, y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                y += 28
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
        if k == ord("c") and face_lm:
            face.recalibrate()
            speaker.say("Mirá al frente, calibrando.", important=True)
        if k == ord("m"):
            speaker.toggle_mute()
            print("🔇 silenciado" if speaker.muted else "🔊 activo")

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
