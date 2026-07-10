import sqlite3
import os

os.makedirs("data", exist_ok=True)

conn = sqlite3.connect("data/orders.db")

cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS orders (
    order_number TEXT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    status TEXT NOT NULL,
    amount REAL NOT NULL
)
""")

orders = [
    ("1001", "Juan Perez", "En preparación", 120.50),
    ("1002", "Maria Gomez", "Despachada", 250.00),
    ("1003", "Carlos Ruiz", "Entregada", 90.30),
    ("1004", "Ana Torres", "Facturada", 500.00),
    ("1005", "Luis Sanchez", "Pendiente", 80.00)
]

cursor.executemany("""
INSERT OR REPLACE INTO orders
(order_number, customer_name, status, amount)
VALUES (?, ?, ?, ?)
""", orders)

conn.commit()
conn.close()

print("Base de datos creada correctamente")