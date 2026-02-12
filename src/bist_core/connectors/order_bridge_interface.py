"""
FAZ116: OrderBridgeInterface (abstract base for order routing) + Flask arayüzü.
OrderBridgeInterface is defined in order_bridge_base; re-exported here. DLL, FIX ve diğer backends bu arayüzü uygular.
Bekleyen emirler listesi; /confirm/<id> ile onaylanınca bridge.send_order çağrılır.
Flask gerekir (pip install flask).
"""
from __future__ import annotations

import importlib
from typing import Any, Dict, List

from bist_core.connectors.order_bridge_base import OrderBridgeInterface
from bist_core.connectors.order_bridge_dll import OrderBridge, OrderBridgeDLL

try:
    _flask = importlib.import_module("flask")
    Flask = getattr(_flask, "Flask")
except ImportError:
    raise ImportError("Flask is not installed") from None

app = Flask(__name__)
order_bridge: Any = OrderBridge()
pending_orders: List[Dict[str, Any]] = []


@app.route("/")
def index() -> str:
    html = "<h3>Bekleyen Emirler</h3>"
    if not pending_orders:
        html += "<p>Bekleyen emir yok.</p>"
    else:
        for order in pending_orders:
            oid = order.get("id")
            otype = order.get("type", "").upper()
            html += f"<div>Emir {oid}: {otype} - <a href='/confirm/{oid}'>Onayla</a></div>"
    return html


@app.route("/confirm/<int:order_id>")
def confirm_order(order_id: int) -> tuple[str, int]:
    order = next((o for o in pending_orders if o.get("id") == order_id), None)
    if not order:
        return "Order not found", 404
    try:
        order_bridge.send_order(order["type"])
    except Exception as e:
        return f"Order send failed: {e}", 500
    pending_orders.remove(order)
    return "Order confirmed", 200
