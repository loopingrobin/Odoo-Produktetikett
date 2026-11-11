import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from odoo_client import OdooClient
from label_printer import LabelPrinter
from settings_manager import MIN_LABEL_SIZE_MM, MAX_LABEL_SIZE_MM

class SettingsPage(ttk.Frame):
    def __init__(self, parent, app, odoo_client, label_printer, settings_manager):
        super().__init__(parent)

        self.app = app
        self.odoo_client = odoo_client
        self.label_printer = label_printer
        self.settings_manager = settings_manager

        self.build_ui()

        # Nur anzeigen; verbunden wird beim Programmstart bzw. über die Buttons "Verbinden".
        self.load_settings()
# ----------------------------------------------------------------------------
    def build_ui(self):
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)
        container.rowconfigure(2, weight=0)
        container.rowconfigure(3, weight=0)
        
        # ---------------------------------------------------------
        # Odoo Einstellungen
        # ---------------------------------------------------------
        odoo_frame = ttk.LabelFrame(container, text="Odoo Einstellungen", padding=10)
        odoo_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        ttk.Label(odoo_frame, text="URL:").grid(row=0, column=0, sticky="w")
        self.odoo_url = ttk.Entry(odoo_frame)
        self.odoo_url.grid(row=0, column=1, sticky="ew", padx=5, pady=2)

        ttk.Label(odoo_frame, text="Datenbank:").grid(row=1, column=0, sticky="w")
        self.odoo_db = ttk.Entry(odoo_frame)
        self.odoo_db.grid(row=1, column=1, sticky="ew", padx=5, pady=2)

        ttk.Label(odoo_frame, text="Benutzername:").grid(row=2, column=0, sticky="w")
        self.odoo_user = ttk.Entry(odoo_frame)
        self.odoo_user.grid(row=2, column=1, sticky="ew", padx=5, pady=2)

        ttk.Label(odoo_frame, text="API-Key / Passwort:").grid(row=3, column=0, sticky="w")
        self.odoo_pass = ttk.Entry(odoo_frame, show="*")
        self.odoo_pass.grid(row=3, column=1, sticky="ew", padx=5, pady=2)

        ttk.Label(
            odoo_frame,
            text="Odoo 19: API-Key eintragen (Benutzername wird dann nicht benötigt).\n"
                 "Ältere Versionen: Benutzername und Passwort.",
            foreground="gray"
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 0))

        ttk.Button(odoo_frame, text="Verbinden", command=self.connect_odoo).grid(row=5, column=0, columnspan=2, pady=5)

        odoo_frame.columnconfigure(1, weight=1)

        # ---------------------------------------------------------
        # PrintNode Einstellungen
        # ---------------------------------------------------------
        print_frame = ttk.LabelFrame(container, text="PrintNode Einstellungen", padding=10)
        print_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

        ttk.Label(print_frame, text="API Key:").grid(row=0, column=0, sticky="w")
        self.printnode_api = ttk.Entry(print_frame, show="*")
        self.printnode_api.grid(row=0, column=1, sticky="ew", padx=5, pady=2)

        ttk.Button(print_frame, text="Verbinden", command=self.connect_printnode).grid(row=1, column=0, columnspan=2, pady=5)

        print_frame.columnconfigure(1, weight=1)

        # ---------------------------------------------------------
        # Adresseinstellungen für Produktetikett
        # ---------------------------------------------------------
        address_frame = ttk.LabelFrame(container, text="Adressinformationen (für Produktetikett)", padding=10)
        address_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        self.address_lines = []
        for i in range(5):
            ttk.Label(address_frame, text=f"Zeile {i+1}:").grid(row=i, column=0, sticky="w")
            entry = ttk.Entry(address_frame)
            entry.grid(row=i, column=1, sticky="ew", padx=5, pady=2)
            self.address_lines.append(entry)

        address_frame.columnconfigure(1, weight=1)

        # ---------------------------------------------------------
        # PDF Speicherpfad
        # ---------------------------------------------------------
        pdf_frame = ttk.LabelFrame(container, text="PDF Speicherort", padding=10)
        pdf_frame.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)

        ttk.Label(pdf_frame, text="Speicherpfad:").grid(row=0, column=0, sticky="w")
        self.pdf_path_entry = ttk.Entry(pdf_frame)
        self.pdf_path_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)

        ttk.Button(
            pdf_frame,
            text="Ordner auswählen",
            command=self.select_pdf_folder
        ).grid(row=1, column=0, columnspan=2, pady=5)

        pdf_frame.columnconfigure(1, weight=1)

        # ---------------------------------------------------------
        # Etikettenformat
        # ---------------------------------------------------------
        format_frame = ttk.LabelFrame(container, text="Etikettenformat", padding=10)
        format_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        ttk.Label(format_frame, text="Breite (mm):").grid(row=0, column=0, sticky="w")
        self.label_width = ttk.Spinbox(format_frame, from_=MIN_LABEL_SIZE_MM, to=MAX_LABEL_SIZE_MM, width=8)
        self.label_width.grid(row=0, column=1, sticky="w", padx=(5, 20), pady=2)

        ttk.Label(format_frame, text="Höhe (mm):").grid(row=0, column=2, sticky="w")
        self.label_height = ttk.Spinbox(format_frame, from_=MIN_LABEL_SIZE_MM, to=MAX_LABEL_SIZE_MM, width=8)
        self.label_height.grid(row=0, column=3, sticky="w", padx=5, pady=2)

        ttk.Label(
            format_frame,
            text="Das Etikett-Layout ist für 100 x 50 mm entworfen und wird auf andere Formate\n"
                 "proportional skaliert und zentriert. Bei stark abweichendem Seitenverhältnis bleibt Rand.",
            foreground="gray"
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(5, 0))

        # ---------------------------------------------------------
        # Speichern-Button
        # ---------------------------------------------------------
        save_frame = ttk.Frame(container)
        save_frame.grid(row=3, column=0, columnspan=2, pady=20)

        save_button = ttk.Button(
            save_frame,
            text="Alle Einstellungen speichern",
            command=self.save_settings
        )
        save_button.pack()
# ----------------------------------------------------------------------------
    def connect_odoo(self):
        self.odoo_client.url = self.odoo_url.get().strip()
        self.odoo_client.db = self.odoo_db.get().strip()
        self.odoo_client.username = self.odoo_user.get().strip()
        self.odoo_client.password = self.odoo_pass.get()

        try:
            self.settings_manager.update_odoo_settings(
                self.odoo_client.url,
                self.odoo_client.db,
                self.odoo_client.username,
                self.odoo_client.password
            )
        except ValueError as e:
            messagebox.showerror("Odoo-Einstellungen", str(e))
            return

        try:
            self.odoo_client.connect()
            if self.odoo_client.transport == "json2":
                messagebox.showinfo("Odoo", "Verbindung erfolgreich (JSON-2).")
            else:
                messagebox.showinfo(
                    "Odoo",
                    "Verbindung erfolgreich (XML-RPC).\n\n"
                    "Hinweis: XML-RPC ist veraltet und wird in Odoo 20 entfernt. "
                    "Bitte in Odoo einen API-Key erzeugen und hier statt des Passworts eintragen."
                )
        except Exception as e:
            self.odoo_client.isConnected = False
            messagebox.showerror("Odoo Fehler", str(e))

        self.app.update_footer()
# ----------------------------------------------------------------------------
    def connect_printnode(self):
        self.label_printer.api_key = self.printnode_api.get().strip()
        self.settings_manager.update_printnode_settings(self.label_printer.api_key)

        success, message = self.label_printer.connect()
        if success:
            messagebox.showinfo("PrintNode", message)
        else:
            messagebox.showerror("PrintNode Fehler", message)

        self.app.update_footer()
# ----------------------------------------------------------------------------  
    def select_pdf_folder(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory()

        if folder:
            self.pdf_path_entry.delete(0, tk.END)
            self.pdf_path_entry.insert(0, folder)
# ----------------------------------------------------------------------------  
    def load_settings(self):
        # Odoo laden
        odoo = self.settings_manager.get_odoo_settings()
        self.odoo_url.insert(0, odoo["url"])
        self.odoo_db.insert(0, odoo["db"])
        self.odoo_user.insert(0, odoo["username"])
        self.odoo_pass.insert(0, odoo["password"])

        # PrintNode laden
        pn = self.settings_manager.get_printnode_settings()
        self.printnode_api.insert(0, pn["api_key"])

        # Adresse laden
        label = self.settings_manager.get_label_settings()
        for entry, value in zip(self.address_lines, label["address_lines"]):
            entry.delete(0, tk.END)
            entry.insert(0, value)

        # Etikettenformat laden
        self.label_width.set(self._format_mm(label["width_mm"]))
        self.label_height.set(self._format_mm(label["height_mm"]))

        # PDF Pfad laden
        pdf_path = label["pdf_path"]
        if pdf_path:
            self.pdf_path_entry.delete(0, tk.END)
            self.pdf_path_entry.insert(0, pdf_path)
# ----------------------------------------------------------------------------  
    @staticmethod
    def _format_mm(value) -> str:
        """100.0 → '100', 62.5 → '62.5'"""
        return f"{float(value):g}"
# ----------------------------------------------------------------------------
    def save_settings(self):

        # PDF Pfad speichern
        pdf_path = self.pdf_path_entry.get()

        # Adresse speichern
        address_data = [e.get() for e in self.address_lines]

        # Etikettenformat prüfen (Komma als Dezimaltrenner erlaubt)
        try:
            width_mm = float(self.label_width.get().replace(",", "."))
            height_mm = float(self.label_height.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Etikettenformat", "Breite und Höhe müssen Zahlen sein (in mm).")
            return

        try:
            self.settings_manager.update_label_settings(pdf_path, address_data, width_mm, height_mm)
        except ValueError as e:
            messagebox.showerror("Etikettenformat", str(e))
            return
        self.label_printer.load_settings()

        tk.messagebox.showinfo("Gespeichert", "Einstellungen erfolgreich gespeichert!")
# ----------------------------------------------------------------------------  