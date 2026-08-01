#!/bin/bash

# ==========================================
# 1. Configuración de credenciales y variables
# ==========================================
# Credenciales Usuario Admin
ADMIN_CLIENT_ID="wpd8x7vCxP6XbdgI0ZP86ggOGyoa"
ADMIN_CLIENT_SECRET="fmIXWEvJLFIXQNTKSHqUXW6gTEEa"

# Credenciales Usuario Pablo
PABLO_CLIENT_ID="ZV2ruvBjBWEyWGZmKnJwHIawQxca"
PABLO_CLIENT_SECRET="79W5c9O06AQqOf5EVhJRW93nahwa"

TOKEN_URL="https://localhost:9443/oauth2/token"
API_URL_MISTRAL="https://localhost:8243/mistralaiapi/0.0.2/v1/chat/completions"
API_URL_QWEN="https://localhost:8243/iaopenaiapi/2.3.0/chat/completions"

# ==========================================
# 2. Menú 1: Selección de Usuario
# ==========================================
echo "=========================================="
echo "      MENÚ 1: SELECCIÓN DE USUARIO        "
echo "=========================================="
echo "  1 - Usuario Admin"
echo "  2 - Usuario Pablo"
echo "  3 - Todos los usuarios (Alternando)"
echo "=========================================="
read -p "Elige una opción (1, 2 o 3): " OPCION_USUARIO

if [[ ! "$OPCION_USUARIO" =~ ^[1-3]$ ]]; then
    echo "❌ Opción de usuario inválida. Saliendo..."
    exit 1
fi

# ==========================================
# 3. Menú 2: Selección de API / Lógica
# ==========================================
echo ""
echo "=========================================="
echo "      MENÚ 2: SELECCIÓN DE LÓGICA API     "
echo "=========================================="
echo "  1 - Todos (Failover: Mistral -> Si falla -> Qwen)"
echo "  2 - Solo Mistral"
echo "  3 - Solo Qwen"
echo "=========================================="
read -p "Elige una opción (1, 2 o 3): " MODO_API

if [[ ! "$MODO_API" =~ ^[1-3]$ ]]; then
    echo "❌ Opción de API inválida. Saliendo..."
    exit 1
fi

# ==========================================
# 4. Menú 3: Cantidad de Peticiones
# ==========================================
echo ""
echo "=========================================="
echo "      MENÚ 3: CANTIDAD DE PETICIONES      "
echo "=========================================="
read -p "Ingresa el número total de iteraciones a realizar (ej. 10): " TOTAL_PETICIONES

# Validar que sea un número entero mayor que cero
if ! [[ "$TOTAL_PETICIONES" =~ ^[0-9]+$ ]] || [ "$TOTAL_PETICIONES" -le 0 ]; then
    echo "❌ Cantidad inválida. Debe ser un número entero mayor que 0. Saliendo..."
    exit 1
fi

# ==========================================
# 5. Función para obtener Token
# ==========================================
obtener_token() {
    local CID=$1
    local CSECRET=$2
    local RESPONSE=$(curl -k -s -X POST "$TOKEN_URL" \
      -u "$CID:$CSECRET" \
      -d "grant_type=client_credentials")
    
    local TOKEN=$(echo "$RESPONSE" | jq -r '.access_token')
    
    if [ "$TOKEN" == "null" ] || [ -z "$TOKEN" ]; then
        echo "ERROR"
    else
        echo "$TOKEN"
    fi
}

echo -e "\n⏳ Solicitando tokens OAuth2..."

# Generar tokens según la elección
TOKEN_ADMIN=""
TOKEN_PABLO=""

if [ "$OPCION_USUARIO" -eq 1 ] || [ "$OPCION_USUARIO" -eq 3 ]; then
    TOKEN_ADMIN=$(obtener_token "$ADMIN_CLIENT_ID" "$ADMIN_CLIENT_SECRET")
    if [ "$TOKEN_ADMIN" == "ERROR" ]; then echo "❌ Error obteniendo token de Admin."; exit 1; fi
    echo "✅ Token de Admin obtenido."
fi

if [ "$OPCION_USUARIO" -eq 2 ] || [ "$OPCION_USUARIO" -eq 3 ]; then
    TOKEN_PABLO=$(obtener_token "$PABLO_CLIENT_ID" "$PABLO_CLIENT_SECRET")
    if [ "$TOKEN_PABLO" == "ERROR" ]; then echo "❌ Error obteniendo token de Pablo."; exit 1; fi
    echo "✅ Token de Pablo obtenido."
fi

echo "=========================================="

# ==========================================
# 6. Funciones de Petición
# ==========================================
llamar_mistral() {
    local TOKEN=$1
    local USER=$2
    echo "👉 [MISTRAL] Enviando petición con usuario: $USER..."
    
    HTTP_CODE=$(curl -k -s -w "%{http_code}" -o mistral_temp.json -X POST "$API_URL_MISTRAL" \
      -H "accept: application/json" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN" \
      -d '{
      "model": "mistral-small-latest",
      "temperature": 0.7,
      "messages": [
        {
          "role": "user",
          "content": "Who is the best Spanish painter? Answer in one short sentence."
        }
      ]
    }')
    
    cat mistral_temp.json
    echo "" # Salto de línea
    return $HTTP_CODE
}

llamar_qwen() {
    local TOKEN=$1
    local USER=$2
    echo "👉 [QWEN] Enviando petición con usuario: $USER..."
    
    curl -k -s -X POST "$API_URL_QWEN" \
      -H "accept: application/json" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN" \
      -d '{
        "model": "qwen2.5-coder-1.5b",
        "messages": [
          {"role": "user", "content": "¿Cómo se hace un bucle for en Python?"}
        ],
        "temperature": 0.3
      }'
    echo "" # Salto de línea
}

# ==========================================
# 7. Bucle Principal
# ==========================================
for i in $(seq 1 $TOTAL_PETICIONES); do
    echo -e "\n🔥 --- Iteración $i de $TOTAL_PETICIONES ---"
    
    # Determinar qué token/usuario usar en esta iteración
    CURRENT_TOKEN=""
    CURRENT_USER=""
    
    if [ "$OPCION_USUARIO" -eq 1 ]; then
        CURRENT_TOKEN=$TOKEN_ADMIN
        CURRENT_USER="Admin"
    elif [ "$OPCION_USUARIO" -eq 2 ]; then
        CURRENT_TOKEN=$TOKEN_PABLO
        CURRENT_USER="Pablo"
    elif [ "$OPCION_USUARIO" -eq 3 ]; then
        # Alternar entre Pablo y Admin en cada iteración (par/impar)
        if [ $((i % 2)) -eq 0 ]; then
            CURRENT_TOKEN=$TOKEN_PABLO
            CURRENT_USER="Pablo"
        else
            CURRENT_TOKEN=$TOKEN_ADMIN
            CURRENT_USER="Admin"
        fi
    fi

    # Ejecutar la lógica de API elegida
    case $MODO_API in
        1)
            llamar_mistral "$CURRENT_TOKEN" "$CURRENT_USER"
            CODIGO=$?
            if [ "$CODIGO" -ne 200 ] || grep -q "throttled" mistral_temp.json; then
                echo "⚠️ Mistral falló para $CURRENT_USER (HTTP $CODIGO o Throttled). Disparando respaldo (Failover)..."
                llamar_qwen "$CURRENT_TOKEN" "$CURRENT_USER"
            else
                echo "✅ Mistral respondió OK. Omitiendo a Qwen."
            fi
            ;;
        2)
            llamar_mistral "$CURRENT_TOKEN" "$CURRENT_USER"
            ;;
        3)
            llamar_qwen "$CURRENT_TOKEN" "$CURRENT_USER"
            ;;
    esac
    
    sleep 1 
done

# Limpieza final
rm -f mistral_temp.json

echo -e "\n\n✅ Prueba de $TOTAL_PETICIONES iteraciones completada."