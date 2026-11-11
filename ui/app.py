import re
import tkinter as tk
from tkinter import ttk
from odoo_client import OdooClient
from label_printer import LabelPrinter
from settings_manager import SettingsManager
from .product_page import ProductPage
from .settings_page import SettingsPage

# Fenstergröße (Pixel): Startgröße ohne gespeicherte Größe und kleinste erlaubte Größe
DEFAULT_WIDTH, DEFAULT_HEIGHT = 1150, 800
MIN_WIDTH, MIN_HEIGHT = 1000, 680
# Platz für Taskleiste und Fensterrahmen, der von der Bildschirmhöhe abgezogen wird
SCREEN_MARGIN = 80

class EtikettApp(tk.Tk):
    def __init__(self, app_version=""):
        super().__init__()

        self.title("Etikettendrucker")
        self.minsize(MIN_WIDTH, MIN_HEIGHT)

        self.app_version = app_version
        self.settings_manager = SettingsManager()

        # Zuletzt verwendete Fenstergröße und -position wiederherstellen
        self.restore_window()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Odoo Initialisierung
        odoo_settings = self.settings_manager.get_odoo_settings()
        
        # URL, Datenbank und API-Key/Passwort müssen belegt sein (Benutzername nur für XML-RPC).
        # OdooClient wirft beim Verbinden keine Fehler; bei Problemen bleibt isConnected False.
        if all(odoo_settings.get(k) for k in ("url", "db", "password")):
            self.odoo_client = OdooClient(**odoo_settings)
            if not self.odoo_client.isConnected:
                print(f"⚠️ Odoo-Verbindung fehlgeschlagen: {self.odoo_client.last_error}")
        else:
            # Leere Version
            self.odoo_client = OdooClient()

        # PrintNode + LabelPrinter initialisieren
        printNode_settings = self.settings_manager.get_printnode_settings()
        printer_settings = self.settings_manager.get_printer_settings()

        # LabelPrinter mit SettingsManager erstellen
        self.label_printer = LabelPrinter(
            api_key = printNode_settings.get("api_key", ""),
            settings_manager = self.settings_manager,
            printer_id = printer_settings.get("last_printer_id", "")
        )

        # Wenn Printer-ID gespeichert wurde, übernehmen:
        if printer_settings.get("last_printer_id"):
            self.label_printer.printer_id = printer_settings["last_printer_id"]

        # UI aufbauen
        # Menü
        self.create_menu()

        # Footer zuerst einbauen, damit er auch bei kleinem Fenster sichtbar bleibt
        # (der Inhalt darunter wird dann beschnitten, nicht die Fußleiste).
        self.create_footer()

        # Inhalt
        self.panel = ttk.Frame(self)
        self.panel.pack(fill="both", expand=True)

        self.pages = {
            "Einstellungen": lambda parent: SettingsPage(
                parent, self, self.odoo_client, self.label_printer, self.settings_manager
            ),
            "Produktseite": lambda parent: ProductPage(
                parent, self, self.odoo_client, self.label_printer, self.settings_manager
            )
        }

        self.current_page = None
        self.load_page("Produktseite")
# ----------------------------------------------------------------------------
    def restore_window(self):
        """
        Setzt die beim letzten Beenden gespeicherte Fenstergröße (und Position,
        wenn sie sichtbar ist). Ungültige Werte oder zu große Fenster fallen auf
        eine passende Größe für den aktuellen Bildschirm zurück.
        """
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        max_w, max_h = screen_w, screen_h - SCREEN_MARGIN

        settings = self.settings_manager.get_window_settings()
        match = re.fullmatch(r"(\d+)x(\d+)(?:([+-]\d+)([+-]\d+))?", settings.get("geometry") or "")

        width, height, position = DEFAULT_WIDTH, DEFAULT_HEIGHT, ""
        if match:
            width, height = int(match.group(1)), int(match.group(2))
            if match.group(3) is not None:
                x, y = int(match.group(3)), int(match.group(4))
                # Position nur übernehmen, wenn das Fenster noch erreichbar ist
                # (z. B. nicht auf einem inzwischen getrennten Monitor).
                if -width + 100 <= x <= screen_w - 100 and 0 <= y <= screen_h - 100:
                    position = f"{x:+d}{y:+d}"

        width = max(MIN_WIDTH, min(width, max_w))
        height = max(MIN_HEIGHT, min(height, max_h))
        self.geometry(f"{width}x{height}{position}")

        if settings.get("maximized"):
            self.state("zoomed")
# ----------------------------------------------------------------------------
    def on_close(self):
        """Speichert Fenstergröße und -position, dann wird das Programm beendet."""
        try:
            maximized = self.state() == "zoomed"
            if maximized:
                # Die normale Größe merken, damit sie nach dem Verkleinern stimmt.
                self.state("normal")
                self.update_idletasks()
            self.settings_manager.update_window_settings(self.geometry(), maximized)
        except Exception as e:
            print(f"⚠️ Fenstergröße konnte nicht gespeichert werden: {e}")
        self.destroy()
# ----------------------------------------------------------------------------
    def create_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        seiten_menu = tk.Menu(menubar, tearoff=0)
        seiten_menu.add_command(label="Produktseite", command=lambda: self.load_page("Produktseite"))
        seiten_menu.add_command(label="Einstellungen", command=lambda: self.load_page("Einstellungen"))

        menubar.add_cascade(label="Seiten", menu=seiten_menu)
# ----------------------------------------------------------------------------
    def create_footer(self):
        self.footer = ttk.Frame(self, padding=5)
        self.footer.pack(side="bottom", fill="x")

        # Spaltenstruktur
        self.status_label_odoo = ttk.Label(self.footer, text=self.get_odoo_status(), anchor="w")
        self.status_label_odoo.grid(row=0, column=0, sticky="w")
        
        self.status_label_printNode = ttk.Label(self.footer, text=self.get_printnode_status(), anchor="w")
        self.status_label_printNode.grid(row=0, column=1)

        center_label = ttk.Label(self.footer, text="© 2025 LoopingRobin", anchor="center")
        center_label.grid(row=0, column=2)

        version_label = ttk.Label(self.footer, text=f"Version: {self.app_version}", anchor="e")
        version_label.grid(row=0, column=3, sticky="e")

        # Grid konfigurieren
        self.footer.columnconfigure(0, minsize=150)
        self.footer.columnconfigure(1, minsize=150)
        self.footer.columnconfigure(2, weight=1)
        self.footer.columnconfigure(3, minsize=150)
# ----------------------------------------------------------------------------
    def load_page(self, page_name):
        if self.current_page:
            self.current_page.destroy()

        page_factory = self.pages[page_name]
        self.current_page = page_factory(self.panel)
        self.current_page.pack(fill="both", expand=True)

        # Falls die Seite eine `on_show()`-Methode hat, aufrufen:
        if hasattr(self.current_page, "on_show"):
            self.current_page.on_show()
# ----------------------------------------------------------------------------
    def get_odoo_status(self):
        return "Odoo: Verbunden" if self.odoo_client.isConnected else "Odoo: Nicht verbunden"
# ----------------------------------------------------------------------------
    def get_printnode_status(self):
        return "PrintNode: Verbunden" if self.label_printer.isConnected else "PrintNode: Nicht verbunden"
# ----------------------------------------------------------------------------
    def update_footer(self):
        self.status_label_odoo.config(text=self.get_odoo_status())
        self.status_label_printNode.config(text=self.get_printnode_status())
# ----------------------------------------------------------------------------
