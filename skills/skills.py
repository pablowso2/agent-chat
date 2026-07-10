from database import get_order
from database import get_all_orders

def consultar_orden(order_number):

    order = get_order(order_number)

    if order is None:
        return {
            "found": False,
            "message": f"No existe la orden {order_number}"
        }

    return {
        "found": True,
        "order_number": order["order_number"],
        "customer_name": order["customer_name"],
        "status": order["status"],
        "amount": order["amount"]
    }

def listar_ordenes():

    orders = get_all_orders()

    return {
        "total": len(orders),
        "orders": orders
    }
