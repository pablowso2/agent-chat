┌─────────────────────────────────────────────────────────────────────┐
│                        Usuario (HTTP)                               │
│               POST /chat  { session_id, message }                   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│              FastAPI Server (main.py)                               │
│   1. get_or_create_session(thread_id)                               │
│   2. try_poll_auth(thread_id)  ← polling automático Device Flow     │
│   3. run_agent(thread_id, message)                                  │
└──────────┬──────────────────────┬──────────────────────────────────-┘
           │                      │
  ┌────────▼──────────┐  ┌────────▼───────────────────────┐
  │ consultar_clima   │  │   LangGraph ReAct Agent         │
  │ WeatherAPI (M2M)  │  │   (agent.py)                    │
  └────────-──────────┘  └───────┬────────────┬────────────┘
                                 │            │
                    ┌────────────▼──┐  ┌──────▼──────────────────┐
                    │iniciar_       │  │buscar_musica_por_tiempo  │
                    │autenticacion  │  │(requiere auth)           │
                    └────────┬──────┘  └──────┬───────────────────┘
                             │                │
                    ┌────────▼──────────────--▼────────────────────┐
                    │          wso2_auth.py (WSO2Auth)             │
                    │                                               │
                    │  ① Device Authorization Grant (RFC 8628)     │
                    │     POST /oauth2/device_authorize             │
                    │     → device_code, user_code, verify_uri     │
                    │                                               │
                    │  ② Polling token                             │
                    │     POST /oauth2/token                        │
                    │     grant_type=device_code                    │
                    │     → access_token (user)                     │
                    │                                               │
                    │  ③ On Behalf Of / Token Exchange (RFC 8693)  │
                    │     POST /oauth2/token                        │
                    │     grant_type=token-exchange                 │
                    │     subject_token=<user_access_token>         │
                    │     → obo_token (agente actúa x el usuario)  │
                    │                                               │
                    │  ④ M2M Client Credentials                    │
                    │     POST /oauth2/token                        │
                    │     grant_type=client_credentials             │
                    │     → m2m_token (agente a servicios)          │
                    └───────────────────────────────────────────────┘

FLUJO DE AUTENTICACIÓN (Device Flow + OBO)
==========================================

1. Usuario pide: "busca música relajante a 70 bpm"
2. Agente llama buscar_musica_por_tiempo → AUTH_REQUIRED
3. Agente llama iniciar_autenticacion
   → POST /oauth2/device_authorize → { device_code, user_code, url }
4. Agente responde: "Ve a <url> e ingresa el código XXXX-YYYY"
5. Usuario abre navegador → inicia sesión en WSO2 IS
6. En el siguiente mensaje del usuario, main.py llama try_poll_auth()
   → POST /oauth2/token (device_code grant) → access_token del usuario
7. Agente llama buscar_musica_por_tiempo de nuevo (ahora autenticado)
   → POST /oauth2/token (token-exchange) → OBO token
   → GET iTunes API (con contexto de identidad del usuario)
8. Agente responde con recomendaciones personalizadas

ENDPOINTS
=========
POST   /chat                      Chat principal
GET    /auth/status/{session_id}  Estado de autenticación de la sesión
DELETE /auth/{session_id}         Logout (limpia tokens locales)

VARIABLES DE ENTORNO (.env)
============================
WEATHER_API_KEY=...
MISTRAL_API_KEY=...
WSO2_IS_BASE_URL=https://localhost:9443
WSO2_CLIENT_ID=...
WSO2_CLIENT_SECRET=...
WSO2_SCOPE=openid profile email
WSO2_VERIFY_SSL=false

CONFIGURACIÓN EN WSO2 IS
=========================
1. Crear aplicación OAuth2 con:
   - Grant types: Device Code, Client Credentials, Token Exchange
   - Allowed scopes: openid, profile, email
2. Copiar Client ID y Client Secret al .env
3. Habilitar Token Exchange en la consola de IS





curl -k -X POST https://localhost:9443/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -u "MlExdlfmufiNf62QdwqZI98182Ea:wboTRoEgLHDANBlBUAG8kyFcxBwCsmU2Y0g8fwJUEgoa" \
  -d "grant_type=client_credentials&scope=weather:read"


  curl "http://api.weatherapi.com/v1/current.json?key=5355b7ec82b04b8389f155930252404&q=Madrid&lang=es"



  curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "sesion-combinada-1", "message": "Quiero que me recomiendes musica en base al tiempo que hace en Madrid hoy"}'