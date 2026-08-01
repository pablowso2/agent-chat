#!/bin/bash

# ==========================================
# 1. Configuración de credenciales y variables
# ==========================================
# Credenciales Usuario Admin (AIAPP)
ADMIN_CLIENT_ID="wpd8x7vCxP6XbdgI0ZP86ggOGyoa"
ADMIN_CLIENT_SECRET="jBWuyMmLkyY6GvonfsLkU_CgrP8a"

# Credenciales Usuario Pablo (AI MCP)
PABLO_CLIENT_ID="ZV2ruvBjBWEyWGZmKnJwHIawQxca"
PABLO_CLIENT_SECRET="lXwY5mmyEiAT_YSaUH5gluwly4Qa"

TOKEN_URL="https://localhost:9443/oauth2/token"
API_URL="https://localhost:8243/botibankmcp/1.0/mcp"

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
# 3. Menú 2: Cantidad de Corridas
# ==========================================
echo ""
echo "=========================================="
echo "      MENÚ 2: CANTIDAD DE CORRIDAS        "
echo "=========================================="
read -p "Ingresa el número total de iteraciones a realizar (ej. 1): " TOTAL_PETICIONES

if ! [[ "$TOTAL_PETICIONES" =~ ^[0-9]+$ ]] || [ "$TOTAL_PETICIONES" -le 0 ]; then
    echo "❌ Cantidad inválida. Debe ser un número entero mayor que 0. Saliendo..."
    exit 1
fi

# ==========================================
# 4. Función para obtener Token
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
# 5. Función para llamar a MCP (Retorna JSON crudo)
# ==========================================
llamar_mcp() {
    local TOKEN=$1
    local TOOL_NAME=$2
    local PARAMS_JSON=$3

    # ¡AQUÍ ESTÁ LA CORRECCIÓN! Cambiado "call_tool" por "tools/call"
    local PAYLOAD="{\"jsonrpc\": \"2.0\", \"id\": $RANDOM, \"method\": \"tools/call\""
    
    # Formato estándar MCP para llamar herramientas
    local ARGUMENTS="{}"
    if [ "$PARAMS_JSON" != "{}" ]; then
        ARGUMENTS="$PARAMS_JSON"
    fi
    PAYLOAD="$PAYLOAD, \"params\": {\"name\": \"$TOOL_NAME\", \"arguments\": $ARGUMENTS}}"

    curl -k -s -X POST "$API_URL" \
      -H "accept: application/json" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN" \
      -d "$PAYLOAD"
}

# ==========================================
# 6. Bucle Principal (Flujo de Lectura)
# ==========================================
for i in $(seq 1 $TOTAL_PETICIONES); do
    echo -e "\n🔥 === INICIANDO CORRIDA $i DE $TOTAL_PETICIONES === 🔥"
    
    CURRENT_TOKEN=""
    CURRENT_USER=""
    
    if [ "$OPCION_USUARIO" -eq 1 ]; then
        CURRENT_TOKEN=$TOKEN_ADMIN
        CURRENT_USER="Admin"
    elif [ "$OPCION_USUARIO" -eq 2 ]; then
        CURRENT_TOKEN=$TOKEN_PABLO
        CURRENT_USER="Pablo"
    elif [ "$OPCION_USUARIO" -eq 3 ]; then
        if [ $((i % 2)) -eq 0 ]; then
            CURRENT_TOKEN=$TOKEN_PABLO
            CURRENT_USER="Pablo"
        else
            CURRENT_TOKEN=$TOKEN_ADMIN
            CURRENT_USER="Admin"
        fi
    fi

    echo "👉 [$CURRENT_USER] 1. Consultando lista de clientes (get_clientes)..."
    RES_CLIENTES=$(llamar_mcp "$CURRENT_TOKEN" "get_clientes" "{}")
    echo "$RES_CLIENTES" | jq .
    
    # ---------------------------------------------------------
    # Extracción de IDs de Clientes
    # (Asume que MCP devuelve un JSON string en result.content[0].text con una propiedad "id")
    # ---------------------------------------------------------
    CLIENTES_IDS=$(echo "$RES_CLIENTES" | jq -r '.result.content[0].text | fromjson? | .[]?.id // empty')

    if [ -z "$CLIENTES_IDS" ]; then
        echo "⚠️ No se encontraron clientes o el formato de respuesta requiere ajustar el filtro 'jq'."
        continue
    fi

    # Bucle por cada cliente encontrado
    for CLIENTE_ID in $CLIENTES_IDS; do
        echo -e "\n   👤 CLIENTE ENCONTRADO: $CLIENTE_ID"
        echo "   👉 [$CURRENT_USER] 2. Consultando cuentas de $CLIENTE_ID (get_cuentas)..."
        
        RES_CUENTAS=$(llamar_mcp "$CURRENT_TOKEN" "get_cuentas" "{\"clienteId\": \"$CLIENTE_ID\"}")
        echo "$RES_CUENTAS" | jq .

        # ---------------------------------------------------------
        # Extracción de IDs de Cuentas
        # (Asume que devuelve una propiedad "cuentaId" o "id")
        # ---------------------------------------------------------
        CUENTAS_IDS=$(echo "$RES_CUENTAS" | jq -r '.result.content[0].text | fromjson? | .[]?.cuentaId // empty')
        
        # Si no lo encuentra como cuentaId, intenta buscarlo como id
        if [ -z "$CUENTAS_IDS" ]; then
            CUENTAS_IDS=$(echo "$RES_CUENTAS" | jq -r '.result.content[0].text | fromjson? | .[]?.id // empty')
        fi

        if [ -z "$CUENTAS_IDS" ]; then
            echo "   ⚠️ El cliente $CLIENTE_ID no tiene cuentas asociadas."
            continue
        fi

        # Bucle por cada cuenta del cliente
        for CUENTA_ID in $CUENTAS_IDS; do
            echo -e "\n      💳 CUENTA ENCONTRADA: $CUENTA_ID"
            echo "      👉 [$CURRENT_USER] 3. Consultando movimientos de $CUENTA_ID (get_cuentas_by_cuentaId_movimientos)..."
            
            RES_MOVIMIENTOS=$(llamar_mcp "$CURRENT_TOKEN" "get_cuentas_by_cuentaId_movimientos" "{\"cuentaId\": \"$CUENTA_ID\"}")
            echo "$RES_MOVIMIENTOS" | jq .
            sleep 1
        done
        
    done
done

echo -e "\n\n✅ Prueba de lectura anidada completada."