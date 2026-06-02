import ballerina/http;
import ballerina/io;
import ballerina/time;
import ballerina/uuid;

// ==========================================
// 1. DEFINICIÓN DE TIPOS (RECORDS)
// ==========================================
type Cliente record {| string id; string nombre; string apellido; |};
type Cuenta record {| string cuentaId; string clienteId; decimal saldo; |};
type CuentaRequest record {| string cuentaId; string clienteId; |};
type Movimiento record {| string id; string fecha; string tipo; decimal monto; string descripcion; string cuentaId; |};
type Servicio record {| string codigoServicio; string nombre; decimal monto; string vencimiento; |};
type MontoRequest record {| decimal monto; |};
type TransferenciaRequest record {| string cuentaDestino; decimal monto; string concepto; |};
type PagoServicioRequest record {| string cuentaOrigen; string codigoServicio; decimal monto; |};

// ==========================================
// 2. SISTEMA DE PERSISTENCIA (db.data)
// ==========================================
type Database record {|
    Cliente[] clientes = [];
    Cuenta[] cuentas = [];
    Movimiento[] movimientos = [];
    Servicio[] servicios = [];
|};

Database db = {};
final string DB_FILE = "db.data";

function init() returns error? {
    json|error j = io:fileReadJson(DB_FILE);
    if j is json {
        Database|error parsed = j.cloneWithType(Database);
        if parsed is Database {
            db = parsed;
            io:println("✅ Base de datos cargada desde db.data");
            return;
        }
    }
    io:println("⚠️ Archivo db.data no encontrado o inválido. Iniciando DB vacía.");
    check saveDb();
}

function saveDb() returns error? {
    check io:fileWriteJson(DB_FILE, db.toJson());
}

// ==========================================
// 3. SERVICIO REST API
// ==========================================
configurable int port = 8000;

service /api/v1 on new http:Listener(port) {

    // ----------------------------------------
    // CLIENTES
    // ----------------------------------------
    resource function get clientes() returns Cliente[] {
        io:println("\n========================================");
        io:println("📥 [REQUEST] GET /clientes");
        Cliente[] res = db.clientes;
        io:println("📤 [RESPONSE] 200 OK | Body: ", res);
        return res;
    }

    resource function post clientes(@http:Payload Cliente cliente) returns http:Created|error {
        io:println("\n========================================");
        io:println("📥 [REQUEST] POST /clientes | Payload: ", cliente);
        db.clientes.push(cliente);
        check saveDb();
        io:println("📤 [RESPONSE] 201 Created");
        // 🔴 FIX: Ahora devolvemos el cliente creado en el body
        return <http:Created> { body: cliente };
    }

    resource function delete clientes/[string clienteId]() returns http:Ok|http:NotFound|error {
        io:println("\n========================================");
        io:println("📥 [REQUEST] DELETE /clientes/", clienteId);
        int? index = db.clientes.indexOf(let var c = db.clientes.filter(cl => cl.id == clienteId)[0] in c);
        if index is int {
            _ = db.clientes.remove(index);
            check saveDb();
            io:println("📤 [RESPONSE] 200 OK");
            return <http:Ok> { body: { "mensaje": "Cliente eliminado con éxito" } };
        }
        io:println("📤 [RESPONSE] 404 Not Found");
        return <http:NotFound> { body: { "error": "Cliente no encontrado" } };
    }

    // ----------------------------------------
    // CUENTAS
    // ----------------------------------------
    resource function post cuentas(@http:Payload CuentaRequest req) returns http:Created|error {
        io:println("\n========================================");
        io:println("📥 [REQUEST] POST /cuentas | Payload: ", req);
        Cuenta nuevaCuenta = { cuentaId: req.cuentaId, clienteId: req.clienteId, saldo: 0.0 };
        db.cuentas.push(nuevaCuenta);
        check saveDb();
        io:println("📤 [RESPONSE] 201 Created");
        return <http:Created> { body: nuevaCuenta };
    }

    resource function delete cuentas/[string cuentaId](string clienteId) returns http:Ok|http:NotFound|error {
        io:println("\n========================================");
        io:println("📥 [REQUEST] DELETE /cuentas/", cuentaId, " | Params: clienteId=", clienteId);
        Cuenta[] filtradas = db.cuentas.filter(c => c.cuentaId == cuentaId && c.clienteId == clienteId);
        if filtradas.length() > 0 {
            int? index = db.cuentas.indexOf(filtradas[0]);
            if index is int {
                _ = db.cuentas.remove(index);
                check saveDb();
                io:println("📤 [RESPONSE] 200 OK");
                return <http:Ok> { body: { "mensaje": "Cuenta eliminada con éxito" } };
            }
        }
        io:println("📤 [RESPONSE] 404 Not Found");
        return <http:NotFound> { body: { "error": "Cuenta no encontrada o no pertenece al cliente" } };
    }

    resource function get cuentas/[string cuentaId]/movimientos() returns Movimiento[] {
        io:println("\n========================================");
        io:println("📥 [REQUEST] GET /cuentas/", cuentaId, "/movimientos");
        Movimiento[] res = db.movimientos.filter(m => m.cuentaId == cuentaId);
        io:println("📤 [RESPONSE] 200 OK | Body: ", res);
        return res;
    }

    // ----------------------------------------
    // OPERACIONES BANCARIAS
    // ----------------------------------------
    resource function post cuentas/[string cuentaId]/ingresar(@http:Payload MontoRequest req) returns http:Ok|http:NotFound|error {
        io:println("\n========================================");
        io:println("📥 [REQUEST] POST /cuentas/", cuentaId, "/ingresar | Payload: ", req);
        foreach var cuenta in db.cuentas {
            if cuenta.cuentaId == cuentaId {
                cuenta.saldo += req.monto;
                check registrarMovimiento(cuentaId, "INGRESO", req.monto, "Ingreso por ventanilla/cajero");
                check saveDb();
                io:println("📤 [RESPONSE] 200 OK | Nuevo Saldo: ", cuenta.saldo);
                return <http:Ok> { body: { "mensaje": "Ingreso exitoso", "nuevoSaldo": cuenta.saldo } };
            }
        }
        io:println("📤 [RESPONSE] 404 Not Found");
        return <http:NotFound> { body: { "error": "Cuenta no encontrada" } };
    }

    resource function post cuentas/[string cuentaId]/sacar(@http:Payload MontoRequest req) returns http:Ok|http:BadRequest|http:NotFound|error {
        io:println("\n========================================");
        io:println("📥 [REQUEST] POST /cuentas/", cuentaId, "/sacar | Payload: ", req);
        foreach var cuenta in db.cuentas {
            if cuenta.cuentaId == cuentaId {
                if cuenta.saldo < req.monto {
                    io:println("📤 [RESPONSE] 400 Bad Request | Saldo insuficiente");
                    return <http:BadRequest> { body: { "error": "Saldo insuficiente" } };
                }
                cuenta.saldo -= req.monto;
                check registrarMovimiento(cuentaId, "RETIRO", req.monto, "Retiro de efectivo");
                check saveDb();
                io:println("📤 [RESPONSE] 200 OK | Nuevo Saldo: ", cuenta.saldo);
                return <http:Ok> { body: { "mensaje": "Retiro exitoso", "nuevoSaldo": cuenta.saldo } };
            }
        }
        io:println("📤 [RESPONSE] 404 Not Found");
        return <http:NotFound> { body: { "error": "Cuenta no encontrada" } };
    }

    resource function post cuentas/[string cuentaId]/transferir(@http:Payload TransferenciaRequest req) returns http:Ok|http:BadRequest|http:NotFound|error {
        io:println("\n========================================");
        io:println("📥 [REQUEST] POST /cuentas/", cuentaId, "/transferir | Payload: ", req);
        Cuenta? origen = ();
        Cuenta? destino = ();

        foreach var c in db.cuentas {
            if c.cuentaId == cuentaId { origen = c; }
            if c.cuentaId == req.cuentaDestino { destino = c; }
        }

        if origen is () || destino is () { 
            io:println("📤 [RESPONSE] 404 Not Found | Cuentas no encontradas");
            return <http:NotFound> { body: { "error": "Cuenta de origen o destino no encontrada" } }; 
        }
        if origen.saldo < req.monto { 
            io:println("📤 [RESPONSE] 400 Bad Request | Saldo insuficiente");
            return <http:BadRequest> { body: { "error": "Saldo insuficiente para transferir" } }; 
        }

        origen.saldo -= req.monto;
        destino.saldo += req.monto;

        check registrarMovimiento(cuentaId, "TRANSFERENCIA_ENVIADA", req.monto, req.concepto);
        check registrarMovimiento(req.cuentaDestino, "TRANSFERENCIA_RECIBIDA", req.monto, req.concepto);
        check saveDb();

        io:println("📤 [RESPONSE] 200 OK | Transferencia realizada");
        return <http:Ok> { body: { "mensaje": "Transferencia realizada con éxito", "saldoRestante": origen.saldo } };
    }

    // ----------------------------------------
    // SERVICIOS
    // ----------------------------------------
    resource function get servicios() returns Servicio[] {
        io:println("\n========================================");
        io:println("📥 [REQUEST] GET /servicios");
        Servicio[] res = db.servicios;
        io:println("📤 [RESPONSE] 200 OK | Body: ", res);
        return res;
    }

    resource function post servicios(@http:Payload Servicio srv) returns http:Created|error {
        io:println("\n========================================");
        io:println("📥 [REQUEST] POST /servicios | Payload: ", srv);
        db.servicios.push(srv);
        check saveDb();
        io:println("📤 [RESPONSE] 201 Created");
        return <http:Created> { body: srv };
    }

    resource function delete servicios/[string codigoServicio]() returns http:Ok|http:NotFound|error {
        io:println("\n========================================");
        io:println("📥 [REQUEST] DELETE /servicios/", codigoServicio);
        Servicio[] filtrados = db.servicios.filter(s => s.codigoServicio == codigoServicio);
        if filtrados.length() > 0 {
            int? index = db.servicios.indexOf(filtrados[0]);
            if index is int {
                _ = db.servicios.remove(index);
                check saveDb();
                io:println("📤 [RESPONSE] 200 OK");
                return <http:Ok> { body: { "mensaje": "Servicio eliminado con éxito" } };
            }
        }
        io:println("📤 [RESPONSE] 404 Not Found");
        return <http:NotFound> { body: { "error": "Servicio no encontrado" } };
    }

    resource function post servicios/pagar(@http:Payload PagoServicioRequest req) returns http:Ok|http:BadRequest|http:NotFound|error {
        io:println("\n========================================");
        io:println("📥 [REQUEST] POST /servicios/pagar | Payload: ", req);
        Servicio[] srv = db.servicios.filter(s => s.codigoServicio == req.codigoServicio);
        if srv.length() == 0 { 
            io:println("📤 [RESPONSE] 404 Not Found | Servicio no encontrado");
            return <http:NotFound> { body: { "error": "Servicio no encontrado" } }; 
        }
        
        if srv[0].monto != req.monto { 
            io:println("📤 [RESPONSE] 400 Bad Request | Monto incorrecto");
            return <http:BadRequest> { body: { "error": "El monto enviado no coincide con el valor de la factura" } }; 
        }

        foreach var cuenta in db.cuentas {
            if cuenta.cuentaId == req.cuentaOrigen {
                if cuenta.saldo < req.monto {
                    io:println("📤 [RESPONSE] 400 Bad Request | Saldo insuficiente");
                    return <http:BadRequest> { body: { "error": "Saldo insuficiente en la cuenta" } };
                }
                cuenta.saldo -= req.monto;
                check registrarMovimiento(req.cuentaOrigen, "PAGO_SERVICIO", req.monto, "Pago de servicio: " + srv[0].nombre);
                
                int? idx = db.servicios.indexOf(srv[0]);
                if idx is int { _ = db.servicios.remove(idx); }

                check saveDb();
                io:println("📤 [RESPONSE] 200 OK | Pago realizado");
                return <http:Ok> { body: { "mensaje": "Servicio pagado con éxito", "nuevoSaldo": cuenta.saldo } };
            }
        }
        io:println("📤 [RESPONSE] 404 Not Found | Cuenta no encontrada");
        return <http:NotFound> { body: { "error": "Cuenta de origen no encontrada" } };
    }
}

// ==========================================
// 4. FUNCIONES AUXILIARES
// ==========================================
function registrarMovimiento(string cuentaId, string tipo, decimal monto, string descripcion) returns error? {
    Movimiento mov = {
        id: uuid:createType1AsString(),
        fecha: time:utcToString(time:utcNow()),
        tipo: tipo,
        monto: monto,
        descripcion: descripcion,
        cuentaId: cuentaId
    };
    db.movimientos.push(mov);
}