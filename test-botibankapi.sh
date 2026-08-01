#!/bin/bash

# ==========================================
# 1. Configuración de credenciales y variables
# ==========================================
# Credenciales Usuario Admin
ADMIN_CLIENT_ID="eTJlLrOvUB2J5LtB33yhV_CrZWMa"
ADMIN_CLIENT_SECRET="anPGTK_l46I7Gx5432aKuSIkT_Aa"

# Credenciales Usuario Pablo
PABLO_CLIENT_ID="MO5NGRfyYv62Rx8YhUx8lqyJzYMa"
PABLO_CLIENT_SECRET="116D_2wMAvGsjWUWUuzHFwbGcAMa"

TOKEN_URL="https://localhost:9443/oauth2/token"
API_URL="https://localhost:8243/botibankapi/1.2.0/clientes"

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
# 3. Menú 2: Cantidad de Peticiones
# ==========================================
echo ""
echo "=========================================="
echo "      MENÚ 2: CANTIDAD DE PETICIONES      "
echo "=========================================="
read -p "Ingresa el número total de peticiones a realizar (ej. 10): " TOTAL_PETICIONES

# Validar que sea un número entero mayor que cero
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
# 5. Función de Petición
# ==========================================
llamar_botibank() {
    local TOKEN=$1
    local USER=$2
    echo "👉 [BOTIBANK] Solicitando /clientes con usuario: $USER..."
    
    curl -k -s -X GET "$API_URL" \
      -H "accept: application/json" \
      -H "Authorization: Bearer $TOKEN"
      
    echo "" # Salto de línea estético para separar la respuesta JSON
}

# ==========================================
# 6. Bucle Principal
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

    # Ejecutar la llamada a la API
    llamar_botibank "$CURRENT_TOKEN" "$CURRENT_USER"
    
    sleep 1 
done

echo -e "\n\n✅ Prueba de $TOTAL_PETICIONES peticiones completada."