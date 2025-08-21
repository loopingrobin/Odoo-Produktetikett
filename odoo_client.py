# odoo_client.py
import xmlrpc.client
from dataclasses import dataclass
from typing import List
from typing import Optional

@dataclass
class SaleOrderLine:
    product_id: int
    product_name: str
    quantity: float
    price: float
    default_code: str

    # Benutzerdefinierte Felder
    ce: bool = False  # aus x_studio_ce
    user_manual: bool = False  # aus x_studio_gebrauchsanweisung
    udi: Optional[str] = None  # aus x_studio_udi
    medical_device: bool = False  # aus x_studio_medizinprodukt
    single_use: bool = False  # aus x_studio_single_use

@dataclass
class Invoice:
    id: int
    name: str
    date: Optional[str]
    total: float
    state: str

@dataclass
class SaleOrder:
    id: int
    name: str
    customer: str
    date: str
    total: float
    lines: List[SaleOrderLine]
    invoices: list 

@dataclass
class ManufacturingOrder:
    id: int
    name: str
    product_name: str
    quantity: float
    date_planned: str
    components: list

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
                [[['invoice_ids', '!=', False]]],
                {
                    'fields': ['name', 'partner_id', 'date_order', 'amount_total', 'order_line', 'invoice_ids'],
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
                    lines= self.get_order_lines(sale.get("order_line",[])),
                    invoices=self.get_invoices_by_ids(sale.get("invoice_ids", []))
                ) for sale in sales_raw
            ]

            # Liste mit Verkaufsdaten wird zurückgegeben.
            return sales
        
        except Exception as e:
            raise Exception(f"Fehler beim Abrufen der Verkaufsdaten: {str(e)}")
# ----------------------------------------------------------------------------
    def get_order_lines(self, order_line_ids: list[int]):
        if not order_line_ids:
            return []

        try:
            # Bestellungsdaten werden aus Odoo gelesen.
            lines_raw = self.models.execute_kw(
                self.db, self.uid, self.password,
                "sale.order.line", "read",
                [order_line_ids],
                {"fields": ["product_id", "product_uom_qty", "price_unit"]}
            )

            # Zusätzliche Produktdetails holen
            product_ids = [line["product_id"][0] for line in lines_raw if isinstance(line.get("product_id"), list)]
            products_raw = self.models.execute_kw(
                self.db, self.uid, self.password,
                "product.product", "read",
                [product_ids],
                {
                    "fields": [
                        "id", "name", 
                        "default_code",
                        "x_studio_ce",
                        "x_studio_gebrauchsanweisung",
                        "x_studio_udi",
                        "x_studio_medizinprodukt",
                        "x_studio_singel_use"
                    ]
                }
            )
            product_map = {p["id"]: p for p in products_raw}

            # Zusammenbau und Rückgabe der Bestellungsdaten.
            return [
                SaleOrderLine(
                    product_id=line["product_id"][0],
                    product_name=product_map.get(line["product_id"][0], {}).get("name", "Unbekannt"),
                    quantity=line.get("product_uom_qty", 0),
                    price=line.get("price_unit", 0.0),
                    default_code=product_map.get(line["product_id"][0], {}).get("default_code"),
                    ce=product_map.get(line["product_id"][0], {}).get("x_studio_ce", False),
                    user_manual=product_map.get(line["product_id"][0], {}).get("x_studio_gebrauchsanweisung", False),
                    udi=product_map.get(line["product_id"][0], {}).get("x_studio_udi"),
                    medical_device=product_map.get(line["product_id"][0], {}).get("x_studio_medizinprodukt", False),
                    single_use=product_map.get(line["product_id"][0], {}).get("x_studio_singel_use", False)
                ) for line in lines_raw if isinstance(line.get("product_id"), list)
            ]
        
        except Exception as e:
            raise Exception(f"Fehler beim Abrufen der Rechnungsdaten: {str(e)}")
# ----------------------------------------------------------------------------
    def get_invoices_by_ids(self, invoice_ids: list[int]):
        if not invoice_ids:
            return []

        try:
            invoice_data = self.models.execute_kw(
                self.db, self.uid, self.password,
                "account.move", "read",
                [invoice_ids],
                {"fields": ["id", "name", "invoice_date", "amount_total", "state"]}
            )

            return [
                Invoice(
                    id=inv["id"],
                    name=inv.get("name", "Unbekannt"),
                    date=inv.get("invoice_date"),
                    total=inv.get("amount_total", 0.0),
                    state=inv.get("state", "unknown")
                )
                for inv in invoice_data
            ]

        except Exception as e:
            raise Exception(f"Fehler beim Abrufen der Rechnungsdaten: {str(e)}")
# ----------------------------------------------------------------------------
    #TODO: Methode get_income_by_id
# ----------------------------------------------------------------------------
    #TODO: Methode get_manufacturing_order_by_id
# ----------------------------------------------------------------------------
def get_manufacturing_orders(self, limit=20):
    if not self.isConnected:
        raise Exception("Nicht verbunden mit Odoo.")

    try:
        orders_raw = self.models.execute_kw(
            self.db, self.uid, self.password,
            'mrp.production', 'search_read',
            [[]],  # alle Fertigungsaufträge
            {
                'fields': [
                    'name',
                    'product_id',
                    'product_qty',
                    'date_planned_start',
                    'raw_material_move_ids'
                ],
                'limit': limit,
                'order': 'date_planned_start desc'
            }
        )

        orders = []
        for order in orders_raw:
            components_ids = order.get("raw_material_move_ids", [])

            # Verwende get_order_lines für Komponenten
            components = self.get_order_lines(components_ids)

            orders.append(ManufacturingOrder(
                id=order.get("id"),
                name=order.get("name", "Unbekannt"),
                product_name=order.get("product_id", ["", "Unbekannt"])[1],
                quantity=order.get("product_qty", 0.0),
                date_planned=order.get("date_planned_start", "")[:10],
                components=components
            ))

        return orders

    except Exception as e:
        raise Exception(f"Fehler beim Abrufen der Fertigungsdaten: {str(e)}")
# ----------------------------------------------------------------------------
def get_components(self, move_ids: list[int]) -> list[SaleOrderLine]:
    if not move_ids:
        return []

    try:
        move_data = self.models.execute_kw(
            self.db, self.uid, self.password,
            'stock.move', 'read',
            [move_ids],
            {
                'fields': [
                    'product_id',
                    'product_uom_qty',
                    # ggf. Custom-Felder, falls auf `stock.move` gemappt
                    'x_studio_ce',
                    'x_studio_gebrauchsanweisung',
                    'x_studio_udi',
                    'x_studio_medizinprodukt',
                    'x_studio_single_use',
                ]
            }
        )

        components = []
        for move in move_data:
            product = move.get("product_id")
            product_name = product[1] if isinstance(product, list) else "Unbekannt"

            components.append(SaleOrderLine(
                id=move.get("id"),
                product_name=product_name,
                qty=move.get("product_uom_qty", 0.0),
                price=0.0,  # keine Preisangabe bei Komponenten

                ce=move.get("x_studio_ce", False),
                user_manual=move.get("x_studio_gebrauchsanweisung", False),
                udi=move.get("x_studio_udi", ""),
                medical_device=move.get("x_studio_medizinprodukt", False),
                single_use=move.get("x_studio_single_use", False),
            ))

        return components

    except Exception as e:
        raise Exception(f"Fehler beim Abrufen der Komponenten: {str(e)}")
# ----------------------------------------------------------------------------
