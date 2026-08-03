# Weather & Music AI Agent

Este es un agente conversacional inteligente construido con FastAPI, LangChain y LangGraph. Utiliza el modelo de **Mistral AI** para procesar lenguaje natural y tiene acceso a herramientas para consultar el clima actual y buscar recomendaciones musicales basadas en el estado de ánimo o el clima.

## Configuración de Variables de Entorno

Para que el proyecto funcione correctamente, es **estrictamente necesario** configurar las siguientes dos variables de entorno. Al desplegar la aplicación, asegúrate de añadirlas en la sección de **Environment Variables (Optional)** de tu plataforma de despliegue:

- `WEATHER_API_KEY`: Clave de la API del clima. Puedes obtenerla registrándote de forma gratuita en [https://www.weatherapi.com](https://www.weatherapi.com).
- `MISTRAL_API_KEY`: Clave de la API de Mistral AI. Puedes generarla desde tu panel de control en [https://admin.mistral.ai/](https://admin.mistral.ai/).

### Uso en local
Si vas a ejecutar el proyecto en tu máquina local, crea un archivo llamado `.env` en la raíz del proyecto con el siguiente contenido:

```env
WEATHER_API_KEY=tu_clave_de_weatherapi_aqui
MISTRAL_API_KEY=tu_clave_de_mistral_aqui
```

## Ejecución local

Asegúrate de tener instaladas las dependencias (FastAPI, uvicorn, langchain, langgraph, langchain_mistralai, requests, python-dotenv).
Luego, inicia el servidor:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Uso de la API

El servidor expone un endpoint principal para interactuar con el agente:

**Endpoint:** `POST /chat`

**Cuerpo de la petición (JSON):**
```json
{
  "session_id": "12345",
  "message": "¿Qué clima hace en Madrid y qué música me recomiendas para este tiempo?"
}
```

El `session_id` se utiliza como identificador de hilo (`thread_id`) para mantener la memoria y el contexto de la conversación de cada 