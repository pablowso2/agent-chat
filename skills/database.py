import sqlite3

DB_PATH = "data/orders.db"


def get_order(order_number):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM orders
        WHERE order_number = ?
    """, (order_number,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def get_all_orders():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM orders
        ORDER BY order_number
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]