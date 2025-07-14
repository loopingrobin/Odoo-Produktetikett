# odoo_client.py
import xmlrpc.client

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
        if not self.isConnected:
            raise Exception("Nicht verbunden mit Odoo.")

        try:
            sales = self.models.execute_kw(
                self.db, self.uid, self.password,
                'sale.order', 'search_read',
                [[]],  # keine Filter – alle Bestellungen
                {
                    'fields': ['name', 'partner_id', 'date_order', 'amount_total', 'order_line'],
                    'limit': limit,
                    'order': 'date_order desc'
                }
            )
            return sales
        except Exception as e:
            raise Exception(f"Fehler beim Abrufen der Verkaufsdaten: {str(e)}")
# ----------------------------------------------------------------------------