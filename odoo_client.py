# odoo_client.py
import xmlrpc.client
from dataclasses import dataclass, field
from typing import List, Optional

import requests

# Timeout in Sekunden: (Verbindungsaufbau, Antwort)
REQUEST_TIMEOUT = (5, 60)
XMLRPC_TIMEOUT = 60
# Max. IDs pro read-Aufruf (hält die einzelnen Anfragen klein)
READ_CHUNK_SIZE = 500

PRODUCT_FIELDS = [
    "id", "name",
    "default_code",
    "x_studio_ce",
    "x_studio_gebrauchsanweisung",
    "x_studio_udi",
    "x_studio_medizinprodukt",
    "x_studio_singel_use",
]


@dataclass
class ProductItem:
    """
    Basisdaten für ein Produkt, unabhängig davon,
    ob es aus einem Einkauf oder einer Fertigung kommt.
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
class Component(ProductItem):
    """
    Erweiterung für Fertigungskomponenten (Stock Move).
    """
    move_id: Optional[int] = None

@dataclass
class ManufacturingOrder(ProductItem):
    """
    Basisdaten für einen Fertigungsauftrag.
    """
    product_id: int = 0
    manufacturing_name: str = ""
    date_start: str = ""
    # Alle Chargen/Seriennummern des Auftrags als [id, name]
    lots: list = field(default_factory=list)
    # Aktuell gewählte Charge als [id, name] oder False (anfangs die erste von 'lots')
    lot_producing_id: object = False
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
    amount_total: float
    lines: list[PurchaseOrderLine]
    invoices: list[Invoice]


def _make_xmlrpc_transport(url: str, timeout: float):
    """XML-RPC-Transport mit Timeout (ServerProxy hat von sich aus keinen)."""
    base = xmlrpc.client.SafeTransport if url.lower().startswith("https") else xmlrpc.client.Transport

    class _TimeoutTransport(base):
        def make_connection(self, host):
            conn = super().make_connection(host)
            conn.timeout = timeout
            return conn

    return _TimeoutTransport()


class OdooClient:
    """
    Client für Odoo.

    Verbindungsart (wird beim Verbinden automatisch gewählt):
      1. JSON-2-API (Odoo 19+): Anmeldung mit API-Key im Feld 'password'.
      2. XML-RPC (ältere Versionen / Fallback): Anmeldung mit Benutzername und
         Passwort oder API-Key. In Odoo 19 veraltet, in Odoo 20 entfernt.
    """
# ----------------------------------------------------------------------------
# region Konstruktor
# ----------------------------------------------------------------------------
    def __init__(self, url="", db="", username="", password=""):
        self.url = url
        self.db = db
        self.username = username
        self.password = password  # API-Key (JSON-2) oder Passwort (XML-RPC)

        self.uid = None
        self.models = None
        self.transport = None  # "json2" oder "xmlrpc"
        self.isConnected = False
        self.last_error = ""
        self._product_cache: dict[int, ProductItem] = {}
        self._searchable_cache: dict[str, set[str]] = {}

        # Beim Start verbinden, aber nie das Programm abstürzen lassen.
        if url and db and password:
            try:
                self.connect()
            except Exception as e:
                self.last_error = str(e)
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region Verbindung
# ----------------------------------------------------------------------------
    @property
    def base_url(self) -> str:
        return self.url.strip().rstrip("/")
# ----------------------------------------------------------------------------
    def _json_headers(self) -> dict:
        return {
            "Authorization": f"bearer {self.password}",
            "X-Odoo-Database": self.db,
            "Content-Type": "application/json; charset=utf-8",
        }
# ----------------------------------------------------------------------------
    @staticmethod
    def _error_message(response: requests.Response) -> str:
        """Verständliche Fehlermeldung aus einer JSON-2-Antwort."""
        if response.status_code == 401:
            return "Anmeldung fehlgeschlagen (401): API-Key ungültig oder abgelaufen."
        try:
            data = response.json()
            detail = data.get("message") or data.get("name") or response.text[:300]
        except ValueError:
            detail = response.text[:300]
        return f"Odoo-Fehler {response.status_code}: {detail}"
# ----------------------------------------------------------------------------
    def connect(self) -> bool:
        """
        Verbindet mit Odoo und wählt die Verbindungsart.
        Gibt bei Erfolg True zurück, sonst wird eine Exception mit
        verständlicher Meldung geworfen.
        """
        self.isConnected = False
        self.transport = None
        self.last_error = ""
        self._product_cache.clear()
        self._searchable_cache.clear()

        if not (self.url and self.db and self.password):
            raise Exception("URL, Datenbank und API-Key/Passwort müssen angegeben werden.")

        # 1. JSON-2 (Odoo 19+). context_get funktioniert für jeden Benutzer.
        try:
            response = requests.post(
                f"{self.base_url}/json/2/res.users/context_get",
                headers=self._json_headers(), json={}, timeout=REQUEST_TIMEOUT
            )
        except requests.exceptions.RequestException as e:
            raise Exception(f"Verbindung zu Odoo fehlgeschlagen: {e}")

        if response.ok:
            self.transport = "json2"
            self.isConnected = True
            return True

        if response.status_code not in (401, 403, 404):
            raise Exception(self._error_message(response))

        # 2. Fallback: XML-RPC (ältere Odoo-Version oder Passwort statt API-Key)
        json2_error = self._error_message(response)
        if not self.username:
            raise Exception(json2_error)

        try:
            proxy_opts = {"transport": _make_xmlrpc_transport(self.base_url, XMLRPC_TIMEOUT)}
            common = xmlrpc.client.ServerProxy(f"{self.base_url}/xmlrpc/2/common", **proxy_opts)
            uid = common.authenticate(self.db, self.username, self.password, {})
        except (xmlrpc.client.Error, OSError) as e:
            raise Exception(f"Verbindung zu Odoo fehlgeschlagen: {e}")

        if not uid:
            raise Exception(
                "Login fehlgeschlagen: Bitte Zugangsdaten prüfen.\n"
                f"(JSON-2: {json2_error})"
            )

        self.uid = uid
        self.models = xmlrpc.client.ServerProxy(f"{self.base_url}/xmlrpc/2/object", **proxy_opts)
        self.transport = "xmlrpc"
        self.isConnected = True
        return True
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region Zugriff auf Odoo
# ----------------------------------------------------------------------------
    def _call(self, model: str, method: str, ids=None, **kwargs):
        """
        Ruft eine Odoo-Methode auf, unabhängig von der Verbindungsart.
        ids  → Datensätze, auf denen die Methode läuft (z. B. für 'read').
        kwargs → benannte Argumente (z. B. domain, fields, limit, order).
        """
        if not self.isConnected:
            raise Exception("Nicht verbunden mit Odoo.")

        if self.transport == "json2":
            body = dict(kwargs)
            if ids is not None:
                body["ids"] = list(ids)
            try:
                response = requests.post(
                    f"{self.base_url}/json/2/{model}/{method}",
                    headers=self._json_headers(), json=body, timeout=REQUEST_TIMEOUT
                )
            except requests.exceptions.RequestException as e:
                raise Exception(f"Verbindungsfehler: {e}")
            if not response.ok:
                raise Exception(self._error_message(response))
            return response.json()

        # XML-RPC
        kwargs = dict(kwargs)
        args = []
        if ids is not None:
            args = [list(ids)]
        elif "domain" in kwargs:
            args = [kwargs.pop("domain")]
        try:
            return self.models.execute_kw(
                self.db, self.uid, self.password, model, method, args, kwargs
            )
        except xmlrpc.client.Fault as e:
            raise Exception(e.faultString.strip().splitlines()[-1] if e.faultString else str(e))
        except OSError as e:
            raise Exception(f"Verbindungsfehler: {e}")
# ----------------------------------------------------------------------------
    def _search_read(self, model, domain, fields, limit=None, order=None):
        kwargs = {"domain": domain, "fields": fields}
        if limit:
            kwargs["limit"] = limit
        if order:
            kwargs["order"] = order
        return self._call(model, "search_read", **kwargs)
# ----------------------------------------------------------------------------
    def _read(self, model, ids, fields) -> list[dict]:
        """Liest Datensätze gesammelt (in Blöcken), doppelte/leere IDs werden ignoriert."""
        unique_ids = list(dict.fromkeys(i for i in ids if i))
        result = []
        for start in range(0, len(unique_ids), READ_CHUNK_SIZE):
            chunk = unique_ids[start:start + READ_CHUNK_SIZE]
            result.extend(self._call(model, "read", ids=chunk, fields=fields))
        return result
# ----------------------------------------------------------------------------
    def _searchable_fields(self, model: str) -> set[str]:
        """
        Namen der in Odoo durchsuchbaren Felder eines Modells (fields_get, je
        Modell einmal). Bei einem Fehler: leere Menge → keine Serversuche.
        """
        if model not in self._searchable_cache:
            try:
                info = self._call(model, "fields_get", attributes=["searchable"])
                self._searchable_cache[model] = {n for n, a in info.items() if a.get("searchable")}
            except Exception:
                self._searchable_cache[model] = set()
        return self._searchable_cache[model]
# ----------------------------------------------------------------------------
    def _build_search_domain(self, model: str, text: str, candidate_fields: list[str]) -> list:
        """
        Baut einen Odoo-Filter aus dem Suchtext: Jedes Wort muss in mindestens
        einem der Felder vorkommen (Wörter UND-verknüpft, Felder ODER-verknüpft,
        Groß-/Kleinschreibung egal). Felder, die Odoo nicht durchsuchen kann
        (auch Pfade wie 'order_line.product_id'), werden übersprungen.
        """
        words = text.split()
        if not words:
            return []

        searchable = self._searchable_fields(model)
        fields = [f for f in candidate_fields if f.split(".")[0] in searchable]
        if not fields:
            raise Exception("Die Suche in Odoo ist für diese Daten nicht möglich.")

        domain = []
        for word in words:
            domain += ["|"] * (len(fields) - 1)
            domain += [[f, "ilike", word] for f in fields]
        return domain
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region Produkte und Rechnungen
# ----------------------------------------------------------------------------
    def get_product_details(self, product_ids: list[int]) -> dict[int, ProductItem]:
        """
        Lädt Produktdetails (nur noch nicht bekannte, in einem Aufruf) und gibt
        eine Map von Produkt-ID → ProductItem zurück.
        """
        wanted = [i for i in dict.fromkeys(product_ids) if i]
        missing = [i for i in wanted if i not in self._product_cache]

        for p in self._read("product.product", missing, PRODUCT_FIELDS):
            self._product_cache[p["id"]] = ProductItem(
                id=p["id"],
                name=p.get("name") or "Unbekannt",
                default_code=p.get("default_code") or None,
                ce=bool(p.get("x_studio_ce")),
                user_manual=bool(p.get("x_studio_gebrauchsanweisung")),
                udi=p.get("x_studio_udi") or None,
                medical_device=bool(p.get("x_studio_medizinprodukt")),
                single_use=bool(p.get("x_studio_singel_use")),
            )

        return {i: self._product_cache[i] for i in wanted if i in self._product_cache}
# ----------------------------------------------------------------------------
    @staticmethod
    def _item_fields(product: Optional[ProductItem]) -> dict:
        """Gemeinsame Produktfelder für Zeilen/Komponenten (auch wenn das Produkt fehlt)."""
        if product is None:
            return {"name": "Unbekannt"}
        return {
            "name": product.name,
            "default_code": product.default_code,
            "ce": product.ce,
            "user_manual": product.user_manual,
            "udi": product.udi,
            "medical_device": product.medical_device,
            "single_use": product.single_use,
        }
# ----------------------------------------------------------------------------
    def _read_invoices(self, invoice_ids: list[int]) -> dict[int, Invoice]:
        """Lädt Rechnungen gesammelt und gibt eine Map ID → Invoice zurück."""
        rows = self._read(
            "account.move", invoice_ids,
            ["id", "name", "invoice_date", "amount_total", "state"]
        )
        return {
            inv["id"]: Invoice(
                id=inv["id"],
                name=inv.get("name") or "Unbekannt",
                date=inv.get("invoice_date") or None,
                total=inv.get("amount_total", 0.0),
                state=inv.get("state", "unknown"),
            )
            for inv in rows
        }
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region Fertigung
# ----------------------------------------------------------------------------
    def get_manufacturing_orders(self, limit: int = 20, search: str = "") -> list[ManufacturingOrder]:
        """
        Holt Fertigungsaufträge mit Hauptprodukt, Chargen und Komponenten.
        Alle abhängigen Daten werden mit je einem Aufruf pro Modell geladen.
        search: optionaler Suchtext, der direkt in Odoo gefiltert wird.
        """
        if not self.isConnected:
            raise Exception("Nicht verbunden mit Odoo.")

        try:
            self._product_cache.clear()

            domain = self._build_search_domain(
                "mrp.production", search,
                ["name", "product_id", "lot_producing_ids", "move_raw_ids.product_id"]
            )
            orders_raw = self._search_read(
                "mrp.production", domain,
                ["id", "name", "product_id", "product_qty", "date_start",
                 "lot_producing_ids",  # Odoo 19: Many2many (früher lot_producing_id)
                 "move_raw_ids"],
                limit=limit, order="date_start desc"
            )

            # Komponenten (Lagerbewegungen) aller Aufträge auf einmal laden
            move_ids = [i for o in orders_raw for i in o.get("move_raw_ids", [])]
            moves = {
                m["id"]: m for m in self._read(
                    "stock.move", move_ids, ["id", "product_id", "product_uom_qty"]
                )
            }

            # Alle Chargen aller Aufträge auf einmal laden
            lot_ids = [i for o in orders_raw for i in o.get("lot_producing_ids", [])]
            lot_names = {
                lot["id"]: [lot["id"], lot.get("name", "")]
                for lot in self._read("stock.lot", lot_ids, ["id", "name"])
            }

            # Alle Produkte (Hauptprodukte + Komponenten) auf einmal laden
            product_ids = [o["product_id"][0] for o in orders_raw if o.get("product_id")]
            product_ids += [m["product_id"][0] for m in moves.values() if m.get("product_id")]
            products = self.get_product_details(product_ids)

            orders: list[ManufacturingOrder] = []
            for order in orders_raw:
                product_id = order["product_id"][0] if order.get("product_id") else None

                components = [
                    Component(
                        id=moves[i]["product_id"][0],
                        quantity=moves[i].get("product_uom_qty", 0.0),
                        move_id=moves[i]["id"],
                        **self._item_fields(products.get(moves[i]["product_id"][0])),
                    )
                    for i in order.get("move_raw_ids", [])
                    if i in moves and moves[i].get("product_id")
                ]

                order_lots = [lot_names[i] for i in order.get("lot_producing_ids", []) if i in lot_names]

                orders.append(
                    ManufacturingOrder(
                        id=order["id"],
                        manufacturing_name=order.get("name") or "Unbekannt",
                        product_id=product_id,
                        quantity=order.get("product_qty", 0.0),
                        date_start=(order.get("date_start") or "")[:10],
                        lots=order_lots,
                        lot_producing_id=order_lots[0] if order_lots else False,
                        components=components,
                        **self._item_fields(products.get(product_id)),
                    )
                )

            return orders

        except Exception as e:
            raise Exception(f"Fehler beim Abrufen der Fertigungsdaten: {e}")
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region Einkäufe
# ----------------------------------------------------------------------------
    def get_purchases(self, limit=20, search: str = "") -> list[PurchaseOrder]:
        """
        Lädt Einkaufsbestellungen (purchase.order) mit Positionen und Rechnungen.
        Alle abhängigen Daten werden mit je einem Aufruf pro Modell geladen.
        search: optionaler Suchtext, der direkt in Odoo gefiltert wird.
        """
        if not self.isConnected:
            raise Exception("Nicht verbunden mit Odoo.")

        try:
            self._product_cache.clear()

            domain = self._build_search_domain(
                "purchase.order", search,
                ["name", "partner_id", "invoice_ids", "order_line.product_id"]
            )
            orders_raw = self._search_read(
                "purchase.order", domain,
                ["id", "name", "date_order", "partner_id", "order_line",
                 "invoice_ids", "amount_total"],
                limit=limit, order="date_order desc"
            )

            line_ids = [i for o in orders_raw for i in o.get("order_line", [])]
            lines = {
                line["id"]: line for line in self._read(
                    "purchase.order.line", line_ids,
                    ["id", "order_id", "product_id", "product_qty", "price_unit"]
                )
            }

            invoice_ids = [i for o in orders_raw for i in o.get("invoice_ids", [])]
            invoices = self._read_invoices(invoice_ids)

            products = self.get_product_details(
                [line["product_id"][0] for line in lines.values() if line.get("product_id")]
            )

            purchases = []
            for order in orders_raw:
                order_lines = [
                    PurchaseOrderLine(
                        id=lines[i]["product_id"][0],
                        quantity=lines[i].get("product_qty", 0.0),
                        price=lines[i].get("price_unit", 0.0),
                        order_id=order["id"],
                        **self._item_fields(products.get(lines[i]["product_id"][0])),
                    )
                    for i in order.get("order_line", [])
                    if i in lines and lines[i].get("product_id")
                ]

                purchases.append(
                    PurchaseOrder(
                        id=order["id"],
                        name=order.get("name") or "Unbekannt",
                        partner_name=(order.get("partner_id") or ["", "Unbekannt"])[1],
                        date_order=(order.get("date_order") or "")[:10],
                        amount_total=order.get("amount_total", 0.0),
                        lines=order_lines,
                        invoices=[invoices[i] for i in order.get("invoice_ids", []) if i in invoices],
                    )
                )

            return purchases

        except Exception as e:
            raise Exception(f"Fehler beim Abrufen der Einkaufsbestellungen: {e}")
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
