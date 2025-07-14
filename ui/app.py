import tkinter as tk
from tkinter import ttk
from odoo_client import OdooClient
from label_printer import LabelPrinter
from settings_manager import SettingsManager
from .product_page import ProductPage
from .settings_page import SettingsPage

class EtikettApp(tk.Tk):
    def __init__(self, app_version=""):
        super().__init__()

        self.title("Etikettendrucker")
        self.geometry("800x600")

        self.app_version = app_version
        self.odoo_client = OdooClient()
        self.label_printer = LabelPrinter()
        self.settings_manager = SettingsManager()

        # Einstellungen laden und direkt setzen
        odoo_settings = self.settings_manager.get_odoo_settings()
        if all(odoo_settings.values()):
            self.odoo_client = OdooClient(**odoo_settings)

        # Menü
        self.create_menu()

        # Inhalt
        self.panel = ttk.Frame(self)
        self.panel.pack(fill="both", expand=True)

        # Footer
        self.create_footer()

        self.pages = {
            "Einstellungen": lambda parent: SettingsPage(
                parent, self, self.odoo_client, self.label_printer, self.settings_manager
            ),
            "Produktseite": lambda parent: ProductPage(
                parent, self, self.odoo_client, self.label_printer
            )
        }

        self.current_page = None
        self.load_page("Produktseite")
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
