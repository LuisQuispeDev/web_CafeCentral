import os
from decimal import Decimal, InvalidOperation
import mysql.connector
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cambiar-esta-clave")


def connect():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "3306")),
        database=os.getenv("DB_NAME", "cafe_central"),
        user=os.getenv("DB_USER", "app_web"),
        password=os.getenv("DB_PASSWORD"),
        connection_timeout=10,
    )


def rows(sql, params=()):
    conn = connect()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


@app.template_filter("money")
def money(value):
    return f"S/ {Decimal(str(value)):.2f}"


@app.get("/")
def index():
    products = rows("SELECT * FROM productos ORDER BY nombre")
    orders = rows("""SELECT p.*, pr.nombre AS producto FROM pedidos p
                     JOIN productos pr ON pr.id_producto=p.id_producto
                     ORDER BY p.id_pedido DESC""")
    return render_template("index.html", products=products, orders=orders)


@app.post("/products/add")
def add_product():
    try:
        data = (request.form["nombre"].strip(), request.form["categoria"].strip(),
                Decimal(request.form["precio"]), int(request.form["stock"]))
        if not data[0] or not data[1] or data[2] < 0 or data[3] < 0:
            raise ValueError()
        conn = connect()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO productos(nombre,categoria,precio,stock) VALUES(%s,%s,%s,%s)", data)
            conn.commit()
        finally:
            cur.close(); conn.close()
        flash("Producto registrado.", "success")
    except (ValueError, InvalidOperation, KeyError):
        flash("Datos del producto inválidos.", "error")
    except mysql.connector.Error as exc:
        flash(f"Error MySQL: {exc.msg}", "error")
    return redirect(url_for("index"))


@app.post("/products/<int:pid>/edit")
def edit_product(pid):
    try:
        data = (request.form["nombre"].strip(), request.form["categoria"].strip(),
                Decimal(request.form["precio"]), int(request.form["stock"]), pid)
        if not data[0] or not data[1] or data[2] < 0 or data[3] < 0:
            raise ValueError()
        conn = connect()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE productos SET nombre=%s,categoria=%s,precio=%s,stock=%s WHERE id_producto=%s", data)
            conn.commit()
        finally:
            cur.close(); conn.close()
        flash("Producto actualizado.", "success")
    except (ValueError, InvalidOperation, KeyError):
        flash("Datos inválidos.", "error")
    except mysql.connector.Error as exc:
        flash(f"No se pudo actualizar: {exc.msg}", "error")
    return redirect(url_for("index"))


@app.post("/products/<int:pid>/delete")
def delete_product(pid):
    try:
        conn = connect()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM productos WHERE id_producto=%s", (pid,))
            conn.commit()
        finally:
            cur.close(); conn.close()
        flash("Producto eliminado si no tiene pedidos asociados.", "success")
    except mysql.connector.Error:
        flash("No se puede eliminar un producto que tenga pedidos asociados.", "error")
    return redirect(url_for("index"))


@app.post("/orders/add")
def add_order():
    try:
        customer = request.form["cliente"].strip()
        pid, qty = int(request.form["id_producto"]), int(request.form["cantidad"])
        status = request.form["estado"]
        if not customer or qty <= 0 or status not in ("Pendiente", "En preparación", "Entregado", "Cancelado"):
            raise ValueError()
        conn = connect()
        try:
            conn.start_transaction()
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT precio,stock FROM productos WHERE id_producto=%s FOR UPDATE", (pid,))
            product = cur.fetchone()
            if not product or qty > product["stock"]:
                raise ValueError("Producto inexistente o stock insuficiente.")
            total = Decimal(str(product["precio"])) * qty
            cur.execute("INSERT INTO pedidos(cliente,id_producto,cantidad,total,estado) VALUES(%s,%s,%s,%s,%s)",
                        (customer, pid, qty, total, status))
            cur.execute("UPDATE productos SET stock=stock-%s WHERE id_producto=%s", (qty, pid))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close(); conn.close()
        flash("Pedido registrado.", "success")
    except (ValueError, KeyError) as exc:
        flash(str(exc) or "Datos del pedido inválidos.", "error")
    except mysql.connector.Error as exc:
        flash(f"Error MySQL: {exc.msg}", "error")
    return redirect(url_for("index"))


@app.post("/orders/<int:oid>/edit")
def edit_order(oid):
    try:
        customer = request.form["cliente"].strip()
        pid, qty = int(request.form["id_producto"]), int(request.form["cantidad"])
        status = request.form["estado"]
        if not customer or qty <= 0 or status not in ("Pendiente", "En preparación", "Entregado", "Cancelado"):
            raise ValueError()
        product = rows("SELECT precio FROM productos WHERE id_producto=%s", (pid,))
        if not product:
            raise ValueError("Producto no encontrado.")
        total = Decimal(str(product[0]["precio"])) * qty
        conn = connect()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE pedidos SET cliente=%s,id_producto=%s,cantidad=%s,total=%s,estado=%s WHERE id_pedido=%s",
                        (customer, pid, qty, total, status, oid))
            conn.commit()
        finally:
            cur.close(); conn.close()
        flash("Pedido actualizado. Revisa el stock si cambiaste producto o cantidad.", "success")
    except (ValueError, KeyError):
        flash("Datos del pedido inválidos.", "error")
    except mysql.connector.Error as exc:
        flash(f"Error MySQL: {exc.msg}", "error")
    return redirect(url_for("index"))


@app.post("/orders/<int:oid>/delete")
def delete_order(oid):
    try:
        conn = connect()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM pedidos WHERE id_pedido=%s", (oid,))
            conn.commit()
        finally:
            cur.close(); conn.close()
        flash("Pedido eliminado.", "success")
    except mysql.connector.Error as exc:
        flash(f"No se pudo eliminar: {exc.msg}", "error")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
