from dataclasses import replace
from datetime import datetime
import os
import re
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import threading

try:
    import pymupdf  # für die Etiketten-Vorschau; ohne das Paket wird der QR-Code angezeigt
except ImportError:
    pymupdf = None

from odoo_client import Invoice

# Größte Anzeigegröße der Etiketten-Vorschau (Pixel)
PREVIEW_MAX_WIDTH = 320
PREVIEW_MAX_HEIGHT = 220
# Wartezeit nach der letzten Eingabe, bevor die Vorschau neu erzeugt wird (ms)
PREVIEW_DELAY_MS = 300
# Höchstzahl der Kopien pro Druck
MAX_COPIES = 99

# Bearbeitbare Felder des Etiketts je Etikett-Typ (Schlüssel → Beschriftung).
# Die Eingaben gelten nur für das gerade angezeigte Etikett und werden nicht gespeichert.
FIELD_LABELS = {
    "Produktetikett": {
        "code": "Referenz", "udi": "UDI", "lot": "Charge (LOT)",
        "date": "Datum (JJJJ-MM-TT)", "total": "Menge gesamt",
    },
    "Lageretikett": {
        "code": "Artikelnummer", "lot": "Chargennummer",
        "supplier": "Lieferant", "total": "Menge gesamt",
    },
}
# Ankreuzfelder des Produktetiketts (Schlüssel → Beschriftung)
FLAG_LABELS = {
    "ce": "CE-Kennzeichnung", "manual": "Gebrauchsanweisung",
    "md": "Medizinprodukt", "single": "Einmalverwendung",
}
DATE_FORMAT = "%Y-%m-%d"

class LoadingPopup(tk.Toplevel):
    def __init__(self, parent, message="Lade Daten...", on_cancel=None):
        super().__init__(parent)
        self.title("Bitte warten")
        self.resizable(False, False)
        self.transient(parent)  # Immer im Vordergrund
        self.grab_set()  # Blockiere Interaktionen mit Hauptfenster
        self.protocol("WM_DELETE_WINDOW", self.cancel)  # Verhindert manuelles Schließen

        self.on_cancel = on_cancel
        self.cancelled = False

        # Nachricht
        ttk.Label(self, text=message).pack(pady=(10, 5))

        # Ladebalken
        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill="x", padx=20, pady=5)
        self.progress.start(10)

        # Abbrechen-Button
        ttk.Button(self, text="Abbrechen", command=self.cancel).pack(pady=(0, 10))


        # Fenstergröße ermitteln und zentrieren
        self.update_idletasks()
        width = 300
        height = 100
        self.geometry(f"{width}x{height}")

        # Zentrierung mit Verzögerung
        self.after(10, self.center_popup)

    def center_popup(self):
        if not self.winfo_exists():  # schon wieder geschlossen (z. B. bei sehr schnellem Laden)
            return
        width = self.winfo_width()
        height = self.winfo_height()

        parent = self.master  # oder self.master

        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (width // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (height // 2)
        self.geometry(f"+{x}+{y}")
# ----------------------------------------------------------------------------
    def cancel(self):
        self.cancelled = True
        if self.on_cancel:
            self.on_cancel()
        self.close()
# ----------------------------------------------------------------------------
    def close(self):
        if self.winfo_exists():
            self.destroy()
# ----------------------------------------------------------------------------

class ProductPage(ttk.Frame):
# ----------------------------------------------------------------------------
# region Konstruktor
# ----------------------------------------------------------------------------
    def __init__(self, parent, app, odoo_client, label_printer, settings_manager):
        super().__init__(parent)

        self.app = app
        self.odoo_client = odoo_client
        self.label_printer = label_printer
        self.settings_manager = settings_manager

        self.overview_data = None
        self.product = None
        self.components_data = None
        self.component = None
        self.mode_var = tk.StringVar(value="Produktetikett")
        self.limit_var = tk.StringVar(value=20)

        # Suchtext: filtert die geladenen Einträge während der Eingabe
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.write_overview_data())
        # Optional: Suchtext zusätzlich direkt in Odoo suchen (findet auch ältere Einträge)
        self.search_in_odoo_var = tk.BooleanVar(value=False)
        self.server_search = ""  # Suchtext, mit dem die aktuellen Daten in Odoo gefiltert wurden

        # Anzahl der Kopien beim Drucken und gewählte Charge (bei mehreren Chargen)
        self.copies_var = tk.StringVar(value="1")
        self.lot_var = tk.StringVar()

        # Bearbeitbarer Etiketteninhalt: nur temporär, wird nirgends gespeichert und beim
        # Wechsel auf einen anderen Eintrag wieder mit den Odoo-Daten gefüllt.
        self.field_vars = {key: tk.StringVar() for key in ("code", "udi", "lot", "date", "supplier", "total")}
        self.flag_vars = {key: tk.BooleanVar() for key in FLAG_LABELS}
        self._loading_fields = False  # True, solange die Felder programmatisch gefüllt werden

        # Vorschau-Aktualisierung (verzögert, damit nicht bei jedem Tastendruck neu gerendert wird)
        self._preview_job = None
        self.preview_image = None

        # Eingabe Chargennummer bei fehlender Rechnung
        self.chargennr_var = tk.StringVar()

        # Default: 80 + Jahr zweistellig + 000
        year_short = datetime.now().strftime("%y")
        default_charge = f"80{year_short}000"
        self.chargennr_var.set(default_charge)

        # Letzte Druckerauswahl aus den Settings laden.
        printer_settings = self.settings_manager.get_printer_settings()

        # Letzte 'PDF speichern'-Auswahl aus den Settings laden.
        self.save_pdf_var = tk.BooleanVar(value=False)
        self.save_pdf_var.set(printer_settings["save_pdf"])

        # Zuletzt verwendeten Drucker aus Settings laden.
        last_id = printer_settings["last_printer_id"]
        
        # Druckerliste aus PrintNode laden.
        self.printer_map = {}  # Name -> ID
        self.printer_names = []
        self.printer_var = tk.StringVar()
        self.load_printers()

        # Zuletzt verwendeten Drucker für Dropdown auswählen.
        if last_id in self.printer_map.values():
            name = [k for k, v in self.printer_map.items() if v == last_id][0]
            self.printer_var.set(name)
        elif self.printer_names:
            self.printer_var.set(self.printer_names[0])
            
        # Grafische Oberfläche laden.
        self.build_ui()
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region Initialisierung
# ----------------------------------------------------------------------------
    def on_show(self):
        """
        Wird beim öffnen der Produktseite ausgeführt und lässt die Daten der
        Gesamtübersicht laden.
        """
        # self.load_overview_data()
# ----------------------------------------------------------------------------
    def build_ui(self):
        """
        Läd die grafische Oberfläche der Produktseite.
        """
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        # Zwei Spalten im Container anlegen
        container.columnconfigure(0, weight=1, minsize=520)  # linke Spalte (Verkaufsliste)
        container.columnconfigure(1, weight=1)  # rechte Spalte (Suchfeld etc.)

        # Linke Spalte
        left_frame = ttk.Frame(container)
        left_frame.config(height=500)
        left_frame.pack_propagate(False)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        # Frame für die Controls
        controls_frame = ttk.Frame(left_frame)
        controls_frame.pack(anchor="nw", pady=(5, 10), fill="x")

        # Dropdown Etikett-Typ
        ttk.Label(controls_frame, text="Etikett-Typ:").grid(row=0, column=0, sticky="w")
        self.mode_select = ttk.Combobox(
            controls_frame,
            textvariable=self.mode_var,
            values=["Lageretikett", "Produktetikett"],
            state="readonly",
            width=15
        )
        self.mode_select.grid(row=1, column=0, padx=5, pady=(0, 5), sticky="w")
        self.mode_select.bind("<<ComboboxSelected>>", self.on_mode_change)

        # Dropdown Limit
        ttk.Label(controls_frame, text="Anzahl Einträge:").grid(row=0, column=1, sticky="w")
        self.limit_select = ttk.Combobox(
            controls_frame,
            textvariable=self.limit_var,
            values=[20, 50, 100, 200, 500],
            state="readonly",
            width=10
        )
        self.limit_select.grid(row=1, column=1, padx=5, pady=(0, 5), sticky="w")

        # Button "Daten laden"
        button = ttk.Button(
            controls_frame, 
            text="Daten laden", 
            command=self.load_overview_data
        )
        button.grid(row=1, column=2, padx=10, pady=(0, 5), sticky="w")

        # Suchfeld
        ttk.Label(
            controls_frame,
            text="Suche (Nummer, Rechnung, Lieferant, Artikel, Charge):"
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(5, 0))

        self.search_entry = ttk.Entry(controls_frame, textvariable=self.search_var)
        self.search_entry.grid(row=3, column=0, columnspan=2, padx=5, sticky="ew")
        self.search_entry.bind("<Escape>", lambda e: self.search_var.set(""))
        self.search_entry.bind("<Return>", self.on_search_enter)

        ttk.Button(
            controls_frame,
            text="Zurücksetzen",
            command=lambda: self.search_var.set("")
        ).grid(row=3, column=2, padx=10, sticky="w")

        ttk.Checkbutton(
            controls_frame,
            text="Auch in Odoo suchen (Enter oder 'Daten laden') – findet ältere Einträge",
            variable=self.search_in_odoo_var
        ).grid(row=4, column=0, columnspan=3, sticky="w", padx=5, pady=(3, 0))

        # Optional: gleichmäßige Spaltenverteilung
        controls_frame.grid_columnconfigure(0, weight=1)
        controls_frame.grid_columnconfigure(1, weight=1)
        controls_frame.grid_columnconfigure(2, weight=0)

        # Gesamtsübersicht
        self.tree = ttk.Treeview(
            left_frame,
            columns=("reference1", "reference2", "designation", "total"),
            show="headings",
            height=20
        )

        # Spaltenbreite in Pixeln definieren (stretch=True erlaubt Anpassung durch Benutzer)
        self.tree.column("reference1", width=100, anchor="w", stretch=False)
        self.tree.column("reference2", width=100, anchor="w", stretch=False)
        self.tree.column("designation", width=230, anchor="w", stretch=True)
        self.tree.column("total", width=80, anchor="e", stretch=False)

        self.tree.bind("<<TreeviewSelect>>", self.on_overview_selected)  # Eventbindung

        self.tree.pack(fill="both", expand=True)

        # Anzeige der Anzahl der geladenen Einträge
        self.entries_tree = ttk.Label(left_frame, text="0 Einträge")
        self.entries_tree.pack(fill="both", expand=True)

        # Rechte Spalte
        right_frame = ttk.Frame(container)
        right_frame.grid(row=0, column=1, sticky="nsew")

        # Einzelteilübersicht
        ttk.Label(right_frame, text="Produktübersicht").pack(pady=5, anchor="w")

        self.tree_products = ttk.Treeview(right_frame, columns=("reference", "designation", "quantity"), show="headings", height=5)

        # Spaltenbreite
        self.tree_products.column("reference", width=90, anchor="w", stretch=False)
        self.tree_products.column("designation", width=200, anchor="w", stretch=True)
        self.tree_products.column("quantity", width=80, anchor="e", stretch=False)

        # Überschriften im Treeview werden gesetzt.
        self.tree_products.heading('reference', text='Kennzeichen')
        self.tree_products.heading('designation', text='Bezeichnung')
        self.tree_products.heading('quantity', text='Menge')

        self.tree_products.pack(fill="both", expand=True)
        self.tree_products.bind("<<TreeviewSelect>>", self.on_component_selected)

        # Vorschau
        preview_frame = ttk.Frame(right_frame)
        preview_frame.pack(anchor="nw", pady=(5, 10), fill="x")

        # Überschrift
        ttk.Label(
            preview_frame, text="Etikett-Vorschau (Änderungen gelten nur für dieses Etikett)"
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=(0, 10))

        # Bild rechts von der Überschrift: Vorschau des fertigen Etiketts
        # (ohne pymupdf nur der QR-Code)
        self.qr_label = ttk.Label(preview_frame, relief="solid", borderwidth=1)
        self.qr_label.grid(row=1, column=1, rowspan=2, padx=10, sticky="n")

        # Etikett-Vorschau (Textfeld); der Text dient zugleich als Bezeichnung auf dem Etikett
        self.name_preview = tk.Text(preview_frame, height=3, wrap="word")
        self.name_preview.grid(row=1, column=0, sticky="nsew", pady=(5, 0))
        self.name_preview.bind("<KeyRelease>", self.schedule_preview_update)

        # Bearbeitbare Felder des Etiketts: Sie fließen in Vorschau und Druck ein, werden aber
        # nirgends gespeichert (auch nicht in Odoo).
        self.fields_frame = ttk.Frame(preview_frame)
        self.fields_frame.grid(row=2, column=0, sticky="nsew", pady=(5, 0))
        self.fields_frame.columnconfigure(1, weight=1)

        self.field_widgets = {}  # Schlüssel → (Beschriftung, Eingabefeld)
        for row, key in enumerate(("code", "udi", "lot", "date", "supplier", "total")):
            label = ttk.Label(self.fields_frame, text="")
            label.grid(row=row, column=0, sticky="w")
            entry = ttk.Entry(self.fields_frame, textvariable=self.field_vars[key], width=24)
            entry.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=1)
            self.field_widgets[key] = (label, entry)
            self.field_vars[key].trace_add("write", self.schedule_preview_update)

        # Ankreuzfelder (nur Produktetikett)
        self.flags_frame = ttk.Frame(self.fields_frame)
        self.flags_frame.grid(row=6, column=0, columnspan=2, sticky="w", pady=(3, 0))
        for i, (key, text) in enumerate(FLAG_LABELS.items()):
            ttk.Checkbutton(
                self.flags_frame, text=text, variable=self.flag_vars[key],
                command=self.schedule_preview_update
            ).grid(row=i, column=0, sticky="w")

        self.update_form_for_mode()

        # Grid-Konfiguration für saubere Größenanpassung
        preview_frame.columnconfigure(0, weight=1)   # Textfeld dehnt sich
        preview_frame.columnconfigure(1, weight=0)   # QR-Code behält feste Größe


        # Stückzahl und Chargennummer
        number_frame = ttk.Frame(right_frame)
        number_frame.pack(anchor="w", pady=(5, 10), fill="x")

        # Eingabefeld für aktuelle Stückzahl
        ttk.Label(number_frame, text="Aktuelle Stückzahl:").grid(row=0, column=0, sticky="w")
        self.current_qty_var = tk.StringVar()   # StringVar, damit Eingabe leer bleiben kann
        self.current_qty_entry = ttk.Entry(number_frame, textvariable=self.current_qty_var)
        self.current_qty_entry.grid(row=1, column=0, padx=(0, 10), sticky="w")

        # Auswahl der Charge (nur sichtbar, wenn ein Fertigungsauftrag mehrere Chargen hat)
        self.lot_label = ttk.Label(number_frame, text="Charge:")
        self.lot_label.grid(row=0, column=1, sticky="w")
        self.lot_select = ttk.Combobox(number_frame, textvariable=self.lot_var, state="readonly", width=22)
        self.lot_select.grid(row=1, column=1, sticky="w")
        self.lot_select.bind("<<ComboboxSelected>>", self.on_lot_selected)
        self.hide_lot_select()

        # Anzahl der Kopien
        ttk.Label(number_frame, text="Kopien:").grid(row=0, column=2, sticky="w", padx=(10, 0))
        self.copies_spinbox = ttk.Spinbox(number_frame, from_=1, to=MAX_COPIES, width=5, textvariable=self.copies_var)
        self.copies_spinbox.grid(row=1, column=2, sticky="w", padx=(10, 0))

        # Verwirft alle Änderungen am Etikett und lädt wieder die Daten aus Odoo
        ttk.Button(
            number_frame, text="Änderungen zurücksetzen", command=self.reset_label_edits
        ).grid(row=1, column=3, sticky="w", padx=(10, 0))

        # Vorschau aktualisieren, wenn die Stückzahl geändert wird
        self.current_qty_var.trace_add("write", self.schedule_preview_update)


        # Druckerauswahl
        printer_frame = ttk.Frame(right_frame)
        printer_frame.pack(anchor="w", pady=(5, 10), fill="x")

        # Label für Drucker
        ttk.Label(printer_frame, text="Drucker:").grid(row=0, column=0, sticky="w")

        # Dropdown
        self.printer_select = ttk.Combobox(
            printer_frame,
            textvariable=self.printer_var,
            state="readonly",
            width=25
        )
        self.printer_select.grid(row=1, column=0, padx=(0, 10), sticky="w")
        self.printer_select["values"] = self.printer_names

        # Checkbutton "PDF speichern"
        self.save_pdf_check = ttk.Checkbutton(
            printer_frame,
            text="als PDF speichern",
            variable=self.save_pdf_var
        )
        self.save_pdf_check.grid(row=1, column=1, sticky="w")

        # Button "Etiketten drucken".
        ttk.Button(printer_frame, text="Etikett drucken", command=self.print_label).grid(row=1, column=2)

        # Rückmeldung nach dem Drucken
        self.print_status = ttk.Label(printer_frame, text="")
        self.print_status.grid(row=2, column=0, columnspan=3, sticky="w", pady=(5, 0))
# ----------------------------------------------------------------------------
    def load_printers(self):
        try:
            printers = self.label_printer.get_printers()
        except Exception as e:
            # z. B. ungültiger API-Key (401) oder keine Verbindung: Programm soll trotzdem starten.
            print(f"⚠️ Drucker konnten nicht geladen werden: {e}")
            printers = []

        self.printer_map.clear()
        for printer in printers:
            name = printer["name"]
            self.printer_map[name] = printer["id"]
            self.printer_names.append(name)
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region Gesamtübersicht
# ----------------------------------------------------------------------------
    def on_mode_change(self, event=None):
        """
        Bei Auswahländerung im Dropdown wird die Übersicht geleert, weil die
        geladenen Daten zum anderen Etikett-Typ gehören. Neu laden mit 'Daten laden'.
        """
        self.overview_data = None
        self.server_search = ""
        self.product = None
        self.component = None
        self.tree.delete(*self.tree.get_children())
        self.tree_products.delete(*self.tree_products.get_children())
        self.entries_tree.configure(text="0 Einträge")
        self.hide_lot_select()
        self.clear_preview()
        self.update_form_for_mode()
# ----------------------------------------------------------------------------
    def clear_preview(self):
        """Leert die Etiketten-Vorschau (Bezeichnung, Felder und Bild), z. B. bei Wechsel des Etikett-Typs."""
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
            self._preview_job = None
        self.name_preview.delete("1.0", tk.END)
        self.clear_fields()
        self.preview_image = None
        self.qr_label.configure(image="")
# ----------------------------------------------------------------------------
    def clear_fields(self):
        """Leert die bearbeitbaren Etikettenfelder."""
        previous = self._loading_fields  # kann schon von load_label_data gesetzt sein
        self._loading_fields = True
        try:
            for var in self.field_vars.values():
                var.set("")
            for var in self.flag_vars.values():
                var.set(False)
        finally:
            self._loading_fields = previous
# ----------------------------------------------------------------------------
    def update_form_for_mode(self):
        """Zeigt nur die Felder an, die zum gewählten Etikett-Typ gehören."""
        mode = self.mode_var.get()
        labels = FIELD_LABELS.get(mode, {})
        for key, (label, entry) in self.field_widgets.items():
            if key in labels:
                label.configure(text=f"{labels[key]}:")
                label.grid()
                entry.grid()
            else:
                label.grid_remove()
                entry.grid_remove()
        if mode == "Produktetikett":
            self.flags_frame.grid()
        else:
            self.flags_frame.grid_remove()
# ----------------------------------------------------------------------------
    def on_overview_selected(self, event):
        """
        Bei Auswahländerung im Treeview 'Gesamtübersicht' werden die Produkt-
        daten des ausgewählten Datensatzes ins Treeview 'Einzelteilübersicht'
        geladen.
        """
        selected = self.tree.selection()
        if not selected:
            return

        index = int(selected[0])
        self.product = self.overview_data[index]

        try:
            # Produkte anzeigen
            self.tree_products.delete(*self.tree_products.get_children())
            mode = self.mode_var.get()
            # Lageretikett
            if mode == "Lageretikett":
                # Neue Bestellung gewählt: Die Vorschau der vorherigen Position passt nicht
                # mehr und bleibt leer, bis eine Position ausgewählt wird.
                self.component = None
                self.clear_preview()
                for line in self.product.lines:
                    self.tree_products.insert(
                        "", "end", 
                        values=(
                            line.default_code, 
                            line.name, 
                            f"{line.quantity:.2f} Stück"
                        )
                    )

            # Produktetikett
            elif mode == "Produktetikett":
                for component in self.product.components:
                    self.tree_products.insert(
                        "", "end", 
                        values=(
                            component.default_code, 
                            component.name, 
                            f"{component.quantity:.0f} Stück"
                        )
                    )
                self.load_label_data()

            self.tree_products.event_generate("<<TreeviewSelect>>")

            # Chargenauswahl gibt es nur beim Produktetikett (bei mehreren Chargen).
            if mode == "Lageretikett":
                self.hide_lot_select()
            else:
                self.update_lot_select()

        except Exception as e:
            messagebox.showerror("Fehler", f"Produkte konnten nicht geladen werden:\n{str(e)}")
# ----------------------------------------------------------------------------
    def load_overview_data(self):
        """
        Läd die Einträge aus der im Dropdown-Menü ausgewählten Datenbank.
        Das Laden läuft im Hintergrund; die Oberfläche wird danach im Hauptthread
        aktualisiert (Tkinter ist nicht thread-sicher).
        """
        mode = self.mode_var.get()
        if mode == "Lageretikett":
            message = "Einkäufe werden geladen..."
            loader = self.odoo_client.get_purchases
            error_context = "Einkaufsdaten"
        elif mode == "Produktetikett":
            message = "Gefertigte Produkte werden geladen..."
            loader = self.odoo_client.get_manufacturing_orders
            error_context = "Fertigungsdaten"
        else:
            return

        try:
            limit = int(self.limit_var.get())
        except ValueError:
            limit = 20

        # Mit gesetztem Haken wird der Suchtext direkt in Odoo gesucht.
        search = self.search_var.get().strip() if self.search_in_odoo_var.get() else ""
        if search:
            message = "Suche in Odoo läuft..."

        loading_popup = LoadingPopup(self, message)

        def load():
            data, error = None, None
            try:
                data = loader(limit=limit, search=search)
            except Exception as e:
                error = e
            self.after(0, lambda: self.on_data_loaded(loading_popup, data, error, error_context, search))

        threading.Thread(target=load, daemon=True).start()
# ----------------------------------------------------------------------------
    def on_search_enter(self, event=None):
        """Enter im Suchfeld: bei gesetztem Haken wird in Odoo gesucht, sonst gefiltert wird ohnehin sofort."""
        if self.search_in_odoo_var.get():
            self.load_overview_data()
# ----------------------------------------------------------------------------
    def on_data_loaded(self, loading_popup, data, error, error_context, search=""):
        """
        Wird im Hauptthread aufgerufen, wenn das Laden fertig ist.
        Wurde das Laden abgebrochen, werden die Daten verworfen.
        search: Suchtext, mit dem die Daten in Odoo gefiltert wurden (leer = alle).
        """
        if loading_popup.cancelled:
            return
        loading_popup.close()

        if error is not None:
            messagebox.showerror("Fehler", f"{error_context} konnten nicht geladen werden:\n{error}")
            return

        self.server_search = search
        self.overview_data = data
        self.product = None
        self.component = None
        self.tree_products.delete(*self.tree_products.get_children())
        self.clear_preview()
        self.hide_lot_select()
        self.write_overview_data()
# ----------------------------------------------------------------------------
    @staticmethod
    def build_search_text(item, mode) -> str:
        """Alle durchsuchbaren Texte eines Eintrags (klein geschrieben, durch Leerzeichen getrennt)."""
        if mode == "Lageretikett":
            parts = [item.name, item.partner_name, item.date_order]
            parts += [invoice.name for invoice in item.invoices]
            parts += [f"{line.default_code or ''} {line.name}" for line in item.lines]
        else:
            parts = [item.manufacturing_name, item.default_code, item.name, item.udi, item.date_start]
            parts += [lot[1] for lot in item.lots]
            parts += [f"{comp.default_code or ''} {comp.name}" for comp in item.components]
        return " ".join(str(p) for p in parts if p).lower()
# ----------------------------------------------------------------------------
    def matches_search(self, item, mode, terms: list[str]) -> bool:
        """Alle Suchbegriffe müssen vorkommen (UND), Groß-/Kleinschreibung egal."""
        if not terms:
            return True
        text = self.build_search_text(item, mode)
        return all(term in text for term in terms)
# ----------------------------------------------------------------------------
    def write_overview_data(self):
        """
        Schreibt die geladenen Einträge in das Treeview 'Gesamtübersicht'.
        Ist ein Suchtext eingegeben, werden nur passende Einträge angezeigt.
        Die iid jeder Zeile bleibt der Index in self.overview_data.
        """
        self.tree.delete(*self.tree.get_children())  # vorherige Zeilen löschen
        if not self.overview_data:
            self.entries_tree.configure(text="0 Einträge")
            return

        mode = self.mode_var.get()
        search_text = self.search_var.get().strip()
        # Wurde genau dieser Text bereits in Odoo gesucht, sind alle geladenen Einträge Treffer
        # und müssen nicht noch einmal lokal gefiltert werden.
        searched_in_odoo = bool(self.server_search) and search_text.lower() == self.server_search.lower()
        terms = [] if searched_in_odoo else search_text.lower().split()
        visible = [
            (i, item) for i, item in enumerate(self.overview_data)
            if self.matches_search(item, mode, terms)
        ]
        total = len(self.overview_data)
        if searched_in_odoo:
            count_text = f"{total} Einträge (Suche in Odoo: \"{self.server_search}\")"
        elif terms:
            count_text = f"{len(visible)} von {total} Einträgen"
        else:
            count_text = f"{total} Einträge"
        self.entries_tree.configure(text=count_text)

        # Lageretikett
        if mode == "Lageretikett":
            # Überschriften im Treeview werden gesetzt.
            self.tree.heading('reference1', text='Bestellnr.')
            self.tree.heading('reference2', text='Rechnungsnr.')
            self.tree.heading('designation', text='Lieferant')
            self.tree.heading('total', text='Kosten')

            for i, purchase in visible:
                self.tree.insert(
                    "", "end", iid=i, 
                    values=(
                        purchase.name,
                        purchase.invoices[0].name if purchase.invoices else "Keine Rechnung",
                        purchase.partner_name,
                        f"{purchase.amount_total:.2f} €"
                    )
                )

        # Produktetikett
        elif mode == "Produktetikett":
            # Überschriften im Treeview werden gesetzt.
            self.tree.heading('reference1', text='Fertigungsnr.')
            self.tree.heading('reference2', text='Kennzeichen')
            self.tree.heading('designation', text='Bezeichnung')
            self.tree.heading('total', text='Menge')

            for i, component in visible:
                self.tree.insert(
                    "", "end", iid=i, 
                    values=(
                        component.manufacturing_name,
                        component.default_code,
                        component.name,
                        f"{component.quantity:.0f} Stück"
                    )
                )

        self.tree.event_generate("<<TreeviewSelect>>")
# ----------------------------------------------------------------------------
    def hide_lot_select(self):
        """ Versteckt die Chargenauswahl """
        self.lot_label.grid_remove()
        self.lot_select.grid_remove()
# ----------------------------------------------------------------------------
    def update_lot_select(self):
        """
        Füllt die Chargenauswahl mit den Chargen des gewählten Fertigungsauftrags.
        Sie ist nur sichtbar, wenn es mehrere Chargen gibt.
        """
        lots = getattr(self.product, "lots", []) or []
        if len(lots) > 1:
            self.lot_select["values"] = [lot[1] for lot in lots]
            current = self.product.lot_producing_id
            self.lot_var.set(current[1] if current else lots[0][1])
            self.lot_label.grid()
            self.lot_select.grid()
        else:
            self.hide_lot_select()
# ----------------------------------------------------------------------------
    def on_lot_selected(self, event=None):
        """
        Die gewählte Charge wird ins Feld 'Charge' übernommen (und gilt damit für Vorschau,
        QR-Code, Dateiname und Druck). Andere Änderungen am Etikett bleiben erhalten.
        """
        self.field_vars["lot"].set(self.lot_var.get())
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region Einzelteilübersicht
# ----------------------------------------------------------------------------
    def on_component_selected(self, event):
        """
        Bei Auswahländerung im Treeview 'Einzelteilübersicht' werden die Detail-
        daten des ausgewählten Einzelteils in die Etikettenvorschau geladen.
        """
        selected_component_index = self.tree_products.selection()
        if not selected_component_index:
            return
        component_iid = selected_component_index[0]
        components = self.tree_products.get_children()
        component_index = components.index(component_iid)

        try:
            mode = self.mode_var.get()
            # Lageretikett
            if mode == "Lageretikett":
                self.component = self.product.lines[component_index]

                self.load_label_data()

            # Produktetikett: Die Komponente ändert das Etikett nicht, deshalb bleiben
            # bereits vorgenommene Änderungen erhalten.
            elif mode == "Produktetikett":
                self.component = self.product.components[component_index]

        except Exception as e:
            messagebox.showerror("Fehler", f"Produktdetails konnten nicht angezeigt werden:\n{str(e)}")
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region Etikettenvorschau / -druck
# ----------------------------------------------------------------------------
    @staticmethod
    def format_number(value) -> str:
        """5.0 → '5', 2.5 → '2.5' (für das Feld 'Menge gesamt')."""
        value = float(value or 0)
        return str(int(value)) if value.is_integer() else str(value)
# ----------------------------------------------------------------------------
    @staticmethod
    def default_lot_for_invoice(invoice) -> str:
        """Chargennummer aus der Rechnungsnummer: ohne das Präfix 'RG'."""
        return (invoice.name or "NOCHARGE").removeprefix("RG")
# ----------------------------------------------------------------------------
    def load_label_data(self):
        """
        Füllt Bezeichnung und Felder des Etiketts mit den Daten des gewählten Eintrags.
        Dabei werden alle bisherigen Änderungen überschrieben. Danach wird die
        Vorschau aktualisiert.
        """
        mode = self.mode_var.get()
        ready = bool(self.product) and (mode == "Produktetikett" or bool(self.component))

        name = ""
        self._loading_fields = True
        try:
            self.clear_fields()

            # Lageretikett: Daten der gewählten Position
            if ready and mode == "Lageretikett":
                product, component = self.product, self.component
                name = component.name or ""
                if product.invoices:
                    lot = self.default_lot_for_invoice(product.invoices[0])
                else:
                    lot = self.chargennr_var.get()  # zuletzt verwendete manuelle Charge
                self.field_vars["code"].set(component.default_code or "")
                self.field_vars["lot"].set(lot)
                self.field_vars["supplier"].set(product.partner_name or "")
                self.field_vars["total"].set(self.format_number(component.quantity))

            # Produktetikett: Daten des Fertigungsauftrags
            elif ready:
                product = self.product
                name = product.name or ""
                lot = product.lot_producing_id
                self.field_vars["code"].set(product.default_code or "")
                self.field_vars["udi"].set(product.udi or "")
                self.field_vars["lot"].set(lot[1] if lot else "")
                self.field_vars["date"].set(product.date_start or "")
                self.field_vars["total"].set(self.format_number(product.quantity))
                self.flag_vars["ce"].set(bool(product.ce))
                self.flag_vars["manual"].set(bool(product.user_manual))
                self.flag_vars["md"].set(bool(product.medical_device))
                self.flag_vars["single"].set(bool(product.single_use))
        finally:
            self._loading_fields = False

        self.name_preview.delete("1.0", tk.END)
        self.name_preview.insert("1.0", name)

        if not ready:
            return

        # QR-Code (wird angezeigt, wenn keine PDF-Vorschau möglich ist).
        qr_image = self.label_printer.generate_qr_pil(self.preview_qr_string(), 100)
        self.preview_image = ImageTk.PhotoImage(qr_image)
        self.qr_label.configure(image=self.preview_image)

        # Vorschau des fertigen Etiketts ersetzt den QR-Code (wenn pymupdf vorhanden ist).
        self.update_pdf_preview()
# ----------------------------------------------------------------------------
    def reset_label_edits(self):
        """Verwirft alle Änderungen am Etikett und lädt die Daten des gewählten Eintrags neu."""
        if not self.product or (self.mode_var.get() == "Lageretikett" and not self.component):
            return
        if self.mode_var.get() == "Produktetikett":
            self.update_lot_select()  # Auswahl zurück auf die erste Charge
        self.load_label_data()
# ----------------------------------------------------------------------------
    def preview_qr_string(self) -> str:
        """Inhalt des QR-Codes für die einfache Anzeige (ohne PDF-Vorschau)."""
        try:
            product, component, invoice, _, lot = self.collect_label_objects()
        except ValueError:
            return "NO DATA"

        if self.mode_var.get() == "Lageretikett":
            code = component.default_code
            return f"{code}-{invoice.name}" if code and invoice.name else "NO DATA"

        parts = []
        if product.udi:
            parts.append(f"(01){product.udi}")
        if lot:
            parts.append(f"(10){lot}")
        return "".join(parts) or "NO DATA"
# ----------------------------------------------------------------------------
    def schedule_preview_update(self, *args):
        """Aktualisiert die Etiketten-Vorschau kurz nach der letzten Eingabe."""
        if self._loading_fields:  # Felder werden gerade programmatisch gefüllt
            return
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(PREVIEW_DELAY_MS, self.update_pdf_preview)
# ----------------------------------------------------------------------------
    def update_pdf_preview(self):
        """
        Zeigt das fertige Etikett (so, wie es gedruckt wird) als Bild an.
        Ohne pymupdf oder bei unvollständigen Angaben bleibt der QR-Code sichtbar.
        """
        self._preview_job = None
        if pymupdf is None or not self.winfo_exists() or not self.product:
            return

        try:
            pdf_data, _ = self.build_label()
            with pymupdf.open(stream=pdf_data, filetype="pdf") as doc:
                page = doc[0]
                zoom = min(PREVIEW_MAX_WIDTH / page.rect.width, PREVIEW_MAX_HEIGHT / page.rect.height)
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        except Exception:
            return  # unvollständige Angaben: die QR-Anzeige bleibt

        self.preview_image = ImageTk.PhotoImage(image)
        self.qr_label.configure(image=self.preview_image)
# ----------------------------------------------------------------------------
    @staticmethod
    def parse_quantity(text: str) -> float:
        """Zahl aus dem Feld 'Menge gesamt' (Komma als Dezimaltrenner erlaubt)."""
        try:
            value = float(text.strip().replace(",", "."))
        except ValueError:
            raise ValueError("'Menge gesamt' muss eine Zahl sein.")
        if value < 0:
            raise ValueError("'Menge gesamt' darf nicht negativ sein.")
        return value
# ----------------------------------------------------------------------------
    @staticmethod
    def parse_date(text: str) -> str:
        """Datum im Format JJJJ-MM-TT; ein leeres Feld bedeutet: kein Datum auf dem Etikett."""
        text = text.strip()
        if text:
            try:
                datetime.strptime(text, DATE_FORMAT)
            except ValueError:
                raise ValueError("Das Datum bitte als JJJJ-MM-TT eingeben (z. B. 2026-11-02).")
        return text
# ----------------------------------------------------------------------------
    def collect_label_objects(self):
        """
        Baut aus den Odoo-Daten und den (ggf. vom Benutzer geänderten) Feldern die
        Objekte für das Etikett. Es werden Kopien erzeugt: Die geladenen Daten bleiben
        unverändert, und nichts wird gespeichert (auch nicht in Odoo).

        Rückgabe: (Eintrag, Position, Rechnung, Bezeichnung, Charge)
        Wirft ValueError mit einem Hinweis für den Benutzer, wenn Angaben fehlen oder ungültig sind.
        """
        mode = self.mode_var.get()

        if not self.product:
            raise ValueError("Bitte zuerst einen Eintrag in der Gesamtübersicht auswählen!")
        if mode == "Lageretikett" and not self.component:
            raise ValueError("Bitte eine Position in der Produktübersicht auswählen!")

        fields = {key: var.get().strip() for key, var in self.field_vars.items()}
        edited_name = self.name_preview.get("1.0", "end-1c").strip()
        total = self.parse_quantity(fields["total"])

        # Lageretikett
        if mode == "Lageretikett":
            if not fields["lot"]:
                raise ValueError("Bitte eine Chargennummer eingeben!")

            component = replace(self.component, default_code=fields["code"] or None, quantity=total)
            order = replace(self.product, partner_name=fields["supplier"])

            invoices = self.product.invoices
            if invoices and fields["lot"] == self.default_lot_for_invoice(invoices[0]):
                # Charge unverändert: Die Rechnung bleibt wie sie ist (Rechnungsnummer im QR-Code).
                invoice = invoices[0]
            else:
                # Keine Rechnung oder Charge geändert: künstliche Rechnung mit dieser Charge.
                invoice = Invoice(id=0, name=fields["lot"], date=None, total=0.0, state="manual")

            return order, component, invoice, edited_name or component.name, fields["lot"]

        # Produktetikett
        product = replace(
            self.product,
            name=edited_name or self.product.name,
            default_code=fields["code"] or None,
            udi=fields["udi"] or None,
            date_start=self.parse_date(fields["date"]),
            quantity=total,
            lot_producing_id=[0, fields["lot"]] if fields["lot"] else False,
            ce=self.flag_vars["ce"].get(),
            user_manual=self.flag_vars["manual"].get(),
            medical_device=self.flag_vars["md"].get(),
            single_use=self.flag_vars["single"].get(),
        )
        return product, None, None, product.name, fields["lot"]
# ----------------------------------------------------------------------------
    def build_label(self) -> tuple[bytes, str]:
        """
        Erstellt das PDF für den gewählten Eintrag und die aktuellen Eingaben
        (einschließlich der temporären Änderungen an den Feldern).
        Rückgabe: (PDF-Bytes, vorgeschlagener Dateiname).
        Wirft ValueError mit einem Hinweis für den Benutzer, wenn Angaben fehlen.
        """
        product, component, invoice, name, lot = self.collect_label_objects()

        timestamp = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
        current_qty = self.current_qty_var.get().strip()

        # Lageretikett
        if self.mode_var.get() == "Lageretikett":
            default_code = component.default_code or "NODEFAULT"
            file_name = self.sanitize_filename(f"{default_code}_{lot}_{timestamp}.pdf")
            pdf_data = self.label_printer.create_order_label_pdf(
                product, component, invoice, current_qty, name
            )

        # Produktetikett
        else:
            default_code = product.default_code or "NODEFAULT"
            file_name = self.sanitize_filename(f"{default_code}_{lot or 'NOLOT'}_{timestamp}.pdf")
            pdf_data = self.label_printer.create_product_label_pdf(product, current_qty, name)

        return pdf_data, file_name
# ----------------------------------------------------------------------------
    def print_label(self):
        """
        Erstellt das Label und sendet es an den Drucker.
        Fehler werden dem Benutzer angezeigt; gespeichert wird nur nach erfolgreichem Druck.
        """
        # Auswahl des Druckers wird geladen
        selected_name = self.printer_var.get()
        printer_id = self.printer_map.get(selected_name)

        if not printer_id:
            messagebox.showwarning("Kein Drucker", "Bitte einen Drucker auswählen!")
            return

        # Anzahl der Kopien prüfen
        try:
            copies = int(self.copies_var.get())
        except ValueError:
            copies = 0
        if not 1 <= copies <= MAX_COPIES:
            messagebox.showwarning("Kopien", f"Bitte eine Anzahl von 1 bis {MAX_COPIES} Kopien eingeben!")
            return

        if self.save_pdf_var.get() and not self.label_printer.file_path:
            messagebox.showwarning(
                "Kein Speicherort",
                "Für 'als PDF speichern' ist noch kein Speicherort festgelegt (siehe Einstellungen)."
            )
            return

        # Etikett erstellen
        try:
            pdf_data, file_name = self.build_label()
        except ValueError as e:
            messagebox.showwarning("Hinweis", str(e))
            return
        except Exception as e:
            messagebox.showerror("Fehler", f"Das Etikett konnte nicht erstellt werden:\n{e}")
            return

        # An den Drucker senden
        self.label_printer.printer_id = printer_id
        try:
            self.label_printer.send_pdf_to_printnode(pdf_data, copies=copies)
        except Exception as e:
            messagebox.showerror("Druck fehlgeschlagen", str(e))
            return

        status = "✅ Etikett an den Drucker gesendet." if copies == 1 else f"✅ {copies} Etiketten an den Drucker gesendet."

        # Ohne Rechnung wird die Charge von Hand eingegeben: für die nächste Position merken
        # (nur bis zum Programmende; es wird nichts gespeichert).
        if self.mode_var.get() == "Lageretikett" and not self.product.invoices:
            self.chargennr_var.set(self.field_vars["lot"].get().strip())

        # Optional als PDF speichern
        if self.save_pdf_var.get():
            try:
                os.makedirs(self.label_printer.file_path, exist_ok=True)
                file_path = os.path.join(self.label_printer.file_path, file_name)
                with open(file_path, "wb") as pdf:
                    pdf.write(pdf_data)
                print(f"Etikett gespeichert als: {file_path}")
            except OSError as e:
                messagebox.showerror("PDF nicht gespeichert", f"Das Etikett wurde gedruckt, aber das PDF konnte nicht gespeichert werden:\n{e}")
                status = "⚠️ Gedruckt, PDF aber nicht gespeichert."

        # Druckauswahl in den Settings speichern.
        self.settings_manager.update_printer_settings(
            printer_id,
            self.save_pdf_var.get()
        )

        self.show_print_status(status)
# ----------------------------------------------------------------------------
    def show_print_status(self, text: str):
        """Zeigt eine Rückmeldung neben dem Druckbutton und blendet sie nach 5 s aus."""
        self.print_status.configure(text=text)
        self.after(5000, lambda: self.print_status.configure(text=""))
# ----------------------------------------------------------------------------
    def sanitize_filename(self, name: str) -> str:
        # Alles außer Buchstaben, Zahlen, Unterstrich und Bindestrich durch "_" ersetzen
        return re.sub(r'[\\/*?:"<>|]', "_", name)
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
