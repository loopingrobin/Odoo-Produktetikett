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