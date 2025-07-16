# odoo_client.py
import xmlrpc.client
from dataclasses import dataclass
from typing import List

@dataclass
class SaleOrderLine:
    product_name: str
    quantity: float
    price: float

@dataclass
class SaleOrder:
    id: int
    name: str
    customer: str
    date: str
    total: float
    lines: List[SaleOrderLine]

class OdooClient:
    def __init__(self, url="", db="", username="", password=""):
        self.url = url
        self.db = db
        self.username = username
        self.password = password
        self.common = None
        self.uid = None
        self.models = None
        self.isConnected = False

        if all([url, db, username, password]):
            if self.login() and self.connect():
                self.isConnected = True
# ----------------------------------------------------------------------------
    def login(self):
        self.common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self.uid = self.common.authenticate(self.db, self.username, self.password, {})
        if not self.uid:
            raise Exception("Login fehlgeschlagen: Bitte Zugangsdaten prüfen.")
        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
        return True
# ----------------------------------------------------------------------------
    def connect(self):
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self.uid = common.authenticate(self.db, self.username, self.password, {})
        if not self.uid:
            return False

        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
        return True
# ----------------------------------------------------------------------------
    def search_read_products_by_code(self, code):
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            'product.template', 'search_read',
            [[['default_code', '=', code]]],
            {'fields': ['name', 'list_price', 'barcode']}
        )
# ----------------------------------------------------------------------------
    def get_sales(self, limit=20):
        # Odoo-Verbindung wird geprüft.
        if not self.isConnected:
            raise Exception("Nicht verbunden mit Odoo.")

        try:
            # Verkaufsdaten werden aus Odoo gelesen.
            sales_raw = self.models.execute_kw(
                self.db, self.uid, self.password,
                'sale.order', 'search_read',
                [[]],  # keine Filter – alle Bestellungen
                {
                    'fields': ['name', 'partner_id', 'date_order', 'amount_total', 'order_line'],
                    'limit': limit,
                    'order': 'date_order desc'
                }
            )

            # Verkaufsdaten werden aufbereitet und in Liste gespeichert.
            sales = [
                SaleOrder(
                    id= sale.get("id"),
                    name= sale.get("name", "Unbekannt"),
                    customer= sale.get("partner_id", ["", "Unbekannt"])[1],
                    date= sale.get("date_order", "")[:10],
                    total= sale.get("amount_total", 0.0),
                    lines= self.get_order_lines(sale.get("order_line",[]))
                ) for sale in sales_raw
            ]

            # Liste mit Verkaufsdaten wird zurückgegeben.
            return sales
        
        except Exception as e:
            raise Exception(f"Fehler beim Abrufen der Verkaufsdaten: {str(e)}")
# ----------------------------------------------------------------------------
    def get_order_lines(self, order_line_ids):
        try:
            # Rechnungsdaten werden aus Odoo gelesen.
            lines_raw = self.models.execute_kw(
                self.db, self.uid, self.password,
                "sale.order.line", "read",
                [order_line_ids],
                {"fields": ["product_id", "product_uom_qty", "price_unit"]}
            )

            # Rechnungsdaten werden aufbereitet und in Liste gespeichert.
            lines = []
            for line in lines_raw:
                # Produktname wird überprüft.
                product_raw = line.get("product_id")
                if isinstance(product_raw, list) and len(product_raw) > 1:
                    product_name = product_raw[1]
                else:
                    product_name = "Unbekannt"

                lines.append(
                    SaleOrderLine(
                        product_name=product_name,
                        quantity=line.get("product_uom_qty", 0),
                        price=line.get("price_unit", 0.0)
                    ) 
                )

            # Liste mit Rechnungsdaten wird zurückgegeben.
            return lines
        
        except Exception as e:
            raise Exception(f"Fehler beim Abrufen der Rechnungsdaten: {str(e)}")
# ----------------------------------------------------------------------------