import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from odoo_client import OdooClient
from label_printer import LabelPrinter

class SettingsPage(ttk.Frame):
    def __init__(self, parent, app, odoo_client, label_printer, settings_manager):
        super().__init__(parent)

        self.app = app
        self.odoo_client = odoo_client
        self.label_printer = label_printer
        self.settings_manager = settings_manager

        self.build_ui()

        self.load_settings()
        self.connect_odoo()
        self.connect_printnode()
# ----------------------------------------------------------------------------
    def build_ui(self):
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Odoo Einstellungen
        odoo_frame = ttk.LabelFrame(container, text="Odoo Einstellungen", padding=10)
        odoo_frame.pack(side="left", fill="both", expand=True, padx=5)

        ttk.Label(odoo_frame, text="URL:").grid(row=0, column=0, sticky="w")
        self.odoo_url = ttk.Entry(odoo_frame)
        self.odoo_url.grid(row=0, column=1, sticky="ew", padx=5, pady=2)

        ttk.Label(odoo_frame, text="Datenbank:").grid(row=1, column=0, sticky="w")
        self.odoo_db = ttk.Entry(odoo_frame)
        self.odoo_db.grid(row=1, column=1, sticky="ew", padx=5, pady=2)

        ttk.Label(odoo_frame, text="Benutzername:").grid(row=2, column=0, sticky="w")
        self.odoo_user = ttk.Entry(odoo_frame)
        self.odoo_user.grid(row=2, column=1, sticky="ew", padx=5, pady=2)

        ttk.Label(odoo_frame, text="Passwort:").grid(row=3, column=0, sticky="w")
        self.odoo_pass = ttk.Entry(odoo_frame, show="*")
        self.odoo_pass.grid(row=3, column=1, sticky="ew", padx=5, pady=2)

        ttk.Button(odoo_frame, text="Verbinden", command=self.connect_odoo).grid(row=4, column=0, columnspan=2, pady=5)

        odoo_frame.columnconfigure(1, weight=1)

        # PrintNode Einstellungen
        print_frame = ttk.LabelFrame(container, text="PrintNode Einstellungen", padding=10)
        print_frame.pack(side="left", fill="both", expand=True, padx=5)

        ttk.Label(print_frame, text="API Key:").grid(row=0, column=0, sticky="w")
        self.printnode_api = ttk.Entry(print_frame)
        self.printnode_api.grid(row=0, column=1, sticky="ew", padx=5, pady=2)

        ttk.Button(print_frame, text="Verbinden", command=self.connect_printnode).grid(row=1, column=0, columnspan=2, pady=5)

        print_frame.columnconfigure(1, weight=1)
# ----------------------------------------------------------------------------
    def connect_odoo(self):
        self.odoo_client.url = self.odoo_url.get()
        self.odoo_client.db = self.odoo_db.get()
        self.odoo_client.username = self.odoo_user.get()
        self.odoo_client.password = self.odoo_pass.get()

        try:
            self.settings_manager.update_odoo_settings(
                self.odoo_client.url, 
                self.odoo_client.db, 
                self.odoo_client.username, 
                self.odoo_client.password
            )

            try:
                if self.odoo_client.login() and self.odoo_client.connect():
                    self.odoo_client.isConnected = True
                    # messagebox.showinfo("Odoo", "Verbindung erfolgreich!")
                else:
                    self.odoo_client.isConnected = False
                    # messagebox.showerror("Odoo", "Verbindung fehlgeschlagen.")
            except Exception as e:
                self.odoo_client.isConnected = False
                messagebox.showerror("Odoo Fehler", str(e))

            self.app.update_footer()
        except Exception as e:
            messagebox.showerror("Odoo-Einstellungen", str(e))
# ----------------------------------------------------------------------------
    def connect_printnode(self):
        self.label_printer.api_key = self.printnode_api.get()
        self.settings_manager.update_printnode_settings(self.label_printer.api_key)

        try:
            if self.label_printer.connect():
                self.label_printer.isConnected = True
                # messagebox.showinfo("PrintNode", "Verbindung erfolgreich!")
            else:
                self.label_printer.isConnected = False
                # messagebox.showerror("PrintNode", "Verbindung fehlgeschlagen.")
        except Exception as e:
            self.label_printer.isConnected = False
            messagebox.showerror("PrintNode Fehler", str(e))
        self.app.update_footer()
# ----------------------------------------------------------------------------  
    def load_settings(self):
        odoo = self.settings_manager.get_odoo_settings()
        self.odoo_url.insert(0, odoo["url"])
        self.odoo_db.insert(0, odoo["db"])
        self.odoo_user.insert(0, odoo["username"])
        self.odoo_pass.insert(0, odoo["password"])

        pn = self.settings_manager.get_printnode_settings()
        self.printnode_api.insert(0, pn["api_key"])
# ----------------------------------------------------------------------------  