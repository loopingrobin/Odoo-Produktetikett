# odoo_client.py
import xmlrpc.client
from dataclasses import dataclass, field
from typing import List
from typing import Optional
    
@dataclass
class ProductItem:
    """
    Basisdaten für ein Produkt, unabhängig davon,
    ob es aus einem Verkauf oder einer Fertigung kommt.
    """
    id: int
    name: str
    default_code: Optional[str] = None
    quantity: float = 0.0
    price: float = 0.0
    ce: bool = False
    user_manual: bool = False
    udi: Optional[str] = None
    medical_device: bool = False
    single_use: bool = False

@dataclass
class SaleOrderLine(ProductItem):
    """
    Erweiterung für Verkaufszeilen (Sale Order Line).
    """
    order_id: Optional[int] = None

@dataclass
class Invoice:
    """
    Basisdaten für eine Rechnung.
    """
    id: int
    name: str
    date: Optional[str]
    total: float
    state: str

@dataclass
class SaleOrder:
    """
    Basisdaten für einen Verkauf.
    """
    id: int
    name: str
    customer: str
    date: str
    total: float
    lines: list[SaleOrderLine]
    invoices: list[Invoice]

@dataclass
class Component(ProductItem):
    """
    Erweiterung für Fertigungskomponenten (Stock Move).
    """
    move_id: Optional[int] = None

@dataclass
class ManufacturingOrder(ProductItem):
    """
    Basisdaten für eine Fertigungskomponente.
    """
    product_id: int = 0
    manufacturing_name: str = ""
    date_start: str = ""
    lot_producing_id: str = ""
    components: List[Component] = field(default_factory=list)

@dataclass
class PurchaseOrderLine(ProductItem):
    """
    Erweiterung für die Einkaufszeilen (Purchase Order Line).
    """
    order_id: int | None = None

@dataclass
class PurchaseOrder:
    """
    Basisdaten für einen Einkauf.
    """
    id: int
    name: str
    partner_name: str
    date_order: str
    amount_total:float
    lines: list[PurchaseOrderLine]
    invoices: list[Invoice]

class OdooClient:
# ----------------------------------------------------------------------------
# region Konstruktor
# ----------------------------------------------------------------------------
    def __init__(self, url="", db="", username="", password=""):
        """
        Konstruktor mit Anmeldedaten.
        Parameter:
            url
        """
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
# endregion
# ----------------------------------------------------------------------------
# region Initialisierung
# ----------------------------------------------------------------------------
    def login(self):
        """
        Meldet den Odoo-Client mit den Anmeldedaten an.
        """
        self.common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self.uid = self.common.authenticate(self.db, self.username, self.password, {})
        if not self.uid:
            raise Exception("Login fehlgeschlagen: Bitte Zugangsdaten prüfen.")
        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
        return True
# ----------------------------------------------------------------------------
    def connect(self):
        """
        """
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self.uid = common.authenticate(self.db, self.username, self.password, {})
        if not self.uid:
            return False

        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
        return True
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region Produkte
# ----------------------------------------------------------------------------
    def search_read_products_by_code(self, code):
        """
        Holt Produkte (product.template) und filtert nach Kennzeichen.
        """
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            'product.template', 'search_read',
            [[['default_code', '=', code]]],
            {'fields': ['name', 'list_price', 'barcode']}
        )
# ----------------------------------------------------------------------------
    def get_product_details(self, product_ids: list[int]) -> dict[int, ProductItem]:
        """
        Lädt Produktdetails aus Odoo und gibt eine Map von Produkt-ID → ProductItem zurück.
        """
        if not product_ids:
            return {}

        try:
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
            return {
                p["id"]: ProductItem(
                    id=p["id"],
                    name=p.get("name", "Unbekannt"),
                    default_code=p.get("default_code"),
                    ce=p.get("x_studio_ce", False),
                    user_manual=p.get("x_studio_gebrauchsanweisung", False),
                    udi=p.get("x_studio_udi"),
                    medical_device=p.get("x_studio_medizinprodukt", False),
                    single_use=p.get("x_studio_singel_use", False),
                )
                for p in products_raw
            }

        except Exception as e:
            raise Exception(f"Fehler beim Abrufen der Produktdetails: {str(e)}")
# ----------------------------------------------------------------------------
    def get_invoices_by_id_list(self, invoice_ids: list[int]) -> list[Invoice]:
        """
        Läd Details der Rechnungen.
        """
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
# endregion
# ----------------------------------------------------------------------------
# region Verkäufe
# ----------------------------------------------------------------------------
    def get_sales(self, limit: int = 20) -> list[SaleOrder]:
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
                    invoices=self.get_invoices_by_id_list(sale.get("invoice_ids", []))
                ) for sale in sales_raw
            ]

            # Liste mit Verkaufsdaten wird zurückgegeben.
            return sales
        
        except Exception as e:
            raise Exception(f"Fehler beim Abrufen der Verkaufsdaten: {str(e)}")
# ----------------------------------------------------------------------------
    def get_order_lines(self, order_line_ids: list[int]) -> list[SaleOrderLine]:
        """
        Lädt Verkaufszeilen inkl. Produktdetails.
        """
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

            # Produkt-IDs extrahieren
            product_ids = [
                line["product_id"][0] for line in lines_raw 
                if isinstance(line.get("product_id"), list)
            ]

            # Produktdetails laden
            product_map = self.get_product_details(product_ids)

            # Zusammenbau und Rückgabe der Bestellungsdaten.
            return [
                SaleOrderLine(
                    id=line["product_id"][0],
                    name=product_map.get(line["product_id"][0], ProductItem(0, "Unbekannt")).name,
                    default_code=product_map.get(line["product_id"][0], {}).default_code,
                    ce=product_map.get(line["product_id"][0], {}).ce,
                    user_manual=product_map.get(line["product_id"][0], {}).user_manual,
                    udi=product_map.get(line["product_id"][0], {}).udi,
                    medical_device=product_map.get(line["product_id"][0], {}).medical_device,
                    single_use=product_map.get(line["product_id"][0], {}).single_use,
                    quantity=line.get("product_uom_qty", 0.0),
                    price=line.get("price_unit", 0.0),
                    order_id=line.get("order_id", [None])[0],
                )
                for line in lines_raw if isinstance(line.get("product_id"), list)
            ]
        
        except Exception as e:
            raise Exception(f"Fehler beim Abrufen der Bestelldaten: {str(e)}")
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region Fertigung
# ----------------------------------------------------------------------------
    #TODO: Methode get_income_by_id
# ----------------------------------------------------------------------------
    #TODO: Methode get_manufacturing_order_by_id
# ----------------------------------------------------------------------------
    def get_manufacturing_orders(self, limit: int = 20) -> list[ManufacturingOrder]:
        """
        Holt Fertigungsaufträge mit Hauptprodukt und Komponenten.
        """
        if not self.isConnected:
            raise Exception("Nicht verbunden mit Odoo.")

        try:
            # Fertigungsaufträge aus Odoo holen
            orders_raw = self.models.execute_kw(
                self.db, self.uid, self.password,
                'mrp.production', 'search_read',
                [[]],  # alle Fertigungsaufträge
                {
                    'fields': [
                        'id',
                        'name',
                        'product_id',
                        'product_qty',
                        'date_start',
                        'lot_producing_id',
                        'move_raw_ids'
                    ],
                    'limit': limit,
                    'order': 'date_start desc'
                }
            )

            orders: list[ManufacturingOrder] = []

            for order in orders_raw:
                product_id = order.get("product_id", [None])[0]
                product_data = None

                if product_id:
                    # Produktdetails über die neue Hilfsmethode laden
                    product_data = self.get_product_details(product_id)

                # Komponenten holen (z. B. Rohmaterialien)
                component_ids = order.get("move_raw_ids", [])
                components = self.get_components(component_ids)

                # ManufacturingOrder-Instanz aufbauen
                orders.append(
                    ManufacturingOrder(
                        id=order.get("id"),
                        manufacturing_name=order.get("name", "Unbekannt"),
                        product_id=product_data.get(product_id, {}).id if product_data else None,
                        name=product_data.get(product_id, {}).name if product_data else "Unbekannt",
                        default_code=product_data.get(product_id, {}).default_code,
                        quantity=order.get("product_qty", 0.0),
                        date_start=order.get("date_start", "")[:10],
                        lot_producing_id=order.get("lot_producing_id", ""),
                        ce=product_data.get(product_id, {}).ce if product_data else False,
                        user_manual=product_data.get(product_id, {}).user_manual if product_data else False,
                        udi=product_data.get(product_id, {}).udi if product_data else None,
                        medical_device=product_data.get(product_id, {}).medical_device if product_data else False,
                        single_use=product_data.get(product_id, {}).single_use if product_data else False,
                        components=components
                    )
                )

            return orders

        except Exception as e:
            raise Exception(f"Fehler beim Abrufen der Fertigungsdaten: {str(e)}")
# ----------------------------------------------------------------------------
    def get_components(self, move_ids: list[int]) -> list[Component]:
        """
        Lädt Fertigungskomponenten (Stock Moves) inkl. Produktdetails.
        """
        if not move_ids:
            return []

        try:
            # Moves laden (Lagerbewegungen für die Fertigung)
            move_data = self.models.execute_kw(
                self.db, self.uid, self.password,
                'stock.move', 'read',
                [move_ids],
                {"fields": ["id", "product_id", "product_uom_qty", "price_unit"]}
            )

            # Produkt-IDs aus den Moves sammeln
            product_ids = [
                move["product_id"][0] for move in move_data 
                if isinstance(move.get("product_id"), list)
            ]

            # Produktdetails laden
            product_map = self.get_product_details(product_ids)

            # Zusammenbauen
            return [
                Component(
                    id=move["product_id"][0],
                    name=product_map.get(move["product_id"][0], ProductItem(0, "Unbekannt")).name,
                    default_code=product_map.get(move["product_id"][0], {}).default_code,
                    ce=product_map.get(move["product_id"][0], {}).ce,
                    user_manual=product_map.get(move["product_id"][0], {}).user_manual,
                    udi=product_map.get(move["product_id"][0], {}).udi,
                    medical_device=product_map.get(move["product_id"][0], {}).medical_device,
                    single_use=product_map.get(move["product_id"][0], {}).single_use,
                    quantity=move.get("product_uom_qty", 0.0),
                    price=move.get("price_unit", 0.0),
                    move_id=move.get("id"),
                )
                for move in move_data if isinstance(move.get("product_id"), list)
            ]

        except Exception as e:
            raise Exception(f"Fehler beim Abrufen der Komponenten: {str(e)}")
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region Einkäufe
# ----------------------------------------------------------------------------
    def get_purchases(self, limit=20) -> list[PurchaseOrder]:
        """
        Lädt Einkaufsbestellungen (purchase.order) mit ihren Positionen.
        """
        if not self.isConnected:
            raise Exception("Nicht verbunden mit Odoo.")

        try:
            # Einkaufsaufträge holen
            orders_raw = self.models.execute_kw(
                self.db, self.uid, self.password,
                "purchase.order", "search_read",
                [[]],  # alle Bestellungen
                {
                    "fields": [
                        "id", "name", "date_order",
                        "partner_id", "order_line",
                        "invoice_ids", "amount_total"
                    ],
                    "limit": limit,
                    "order": "date_order desc",
                }
            )

            purchases = [
                PurchaseOrder(
                    id=order.get("id"),
                    name=order.get("name", "Unbekannt"),
                    partner_name=order.get("partner_id", ["", "Unbekannt"])[1],
                    date_order=order.get("date_order", "")[:10],
                    amount_total=order.get("amount_total",0.0),
                    lines= self.get_purchase_lines(order.get("order_line",[])),
                    invoices=self.get_invoices_by_id_list(order.get("invoice_ids", []))
                ) for order in orders_raw
            ]

            return purchases

        except Exception as e:
            raise Exception(f"Fehler beim Abrufen der Einkaufsbestellungen: {str(e)}")
# ----------------------------------------------------------------------------
    def get_purchase_lines(self, purchase_line_ids: list[int]) -> list[PurchaseOrderLine]:
        """
        Lädt Einkaufszeilen (purchase.order.line) inkl. Produktdetails.
        """
        if not purchase_line_ids:
            return []

        try:
            # Einkaufszeilen lesen
            lines_raw = self.models.execute_kw(
                self.db, self.uid, self.password,
                "purchase.order.line", "read",
                [purchase_line_ids],
                {"fields": ["order_id", "product_id", "product_qty", "price_unit"]}
            )

            # Produktdetails laden
            product_ids = [line["product_id"][0] for line in lines_raw if isinstance(line.get("product_id"), list)]
            product_map = self.get_product_details(product_ids)

            # Zusammenbauen
            return [
                PurchaseOrderLine(
                    id=line["product_id"][0],
                    name=product_map.get(line["product_id"][0], ProductItem(0, "Unbekannt")).name,
                    default_code=product_map.get(line["product_id"][0], {}).default_code,
                    ce=product_map.get(line["product_id"][0], {}).ce,
                    user_manual=product_map.get(line["product_id"][0], {}).user_manual,
                    udi=product_map.get(line["product_id"][0], {}).udi,
                    medical_device=product_map.get(line["product_id"][0], {}).medical_device,
                    single_use=product_map.get(line["product_id"][0], {}).single_use,
                    quantity=line.get("product_qty", 0.0),
                    price=line.get("price_unit", 0.0),
                    order_id=line.get("order_id", [None])[0],
                )
                for line in lines_raw if isinstance(line.get("product_id"), list)
            ]

        except Exception as e:
            raise Exception(f"Fehler beim Abrufen der Einkaufsdaten: {str(e)}")
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
