from datetime import datetime
import re
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import ImageTk
import threading

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

        # Letzte Druckerauswahl aus den Settings laden.
        printer_settings = self.settings_manager.get_printer_settings()
        last_id = printer_settings["last_printer_id"]

        self.printer_map = {}  # Name -> ID

        if last_id in self.printer_map.values():
            name = [k for k, v in self.printer_map.items() if v == last_id][0]
            self.printer_var.set(name)
        else:
            self.printer_var = tk.StringVar()

        # Letzte 'PDF speichern'-Auswahl aus den Settings laden.
        self.save_pdf_var = tk.BooleanVar(value=False)
        self.save_pdf_var.set(printer_settings["save_pdf"])

        self.build_ui()
        self.load_printers()
        # self.winfo_toplevel().minsize(1000, 600)
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
            values=["Auftragsetikett", "Produktetikett"],
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

        self.tree_products = ttk.Treeview(right_frame, columns=("reference", "designation", "quantity"), show="headings", height=8)

        # Spaltenbreite
        self.tree_products.column("reference", width=50, anchor="w", stretch=False)
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
        ttk.Label(preview_frame, text="Etikett-Vorschau").grid(row=0, column=0, sticky="w", padx=(0, 10))

        # QR-Code rechts von der Überschrift
        self.qr_label = ttk.Label(preview_frame)
        self.qr_label.grid(row=1, column=1, rowspan=2, padx=10, sticky="n")

        # Etikett-Vorschau (Textfeld)
        self.name_preview = tk.Text(preview_frame, height=4, wrap="word")
        self.name_preview.grid(row=1, column=0, sticky="nsew", pady=(5, 0))
        self.label_preview = tk.Text(preview_frame, height=8, wrap="word")
        self.label_preview.grid(row=2, column=0, sticky="nsew", pady=(5, 0))

        # Grid-Konfiguration für saubere Größenanpassung
        preview_frame.columnconfigure(0, weight=1)   # Textfeld dehnt sich
        preview_frame.columnconfigure(1, weight=0)   # QR-Code behält feste Größe


        # Stückzahl
        # Eingabefeld für aktuelle Stückzahl
        ttk.Label(right_frame, text="Aktuelle Stückzahl:").pack(anchor="w", pady=(5, 2))
        self.current_qty_var = tk.StringVar()   # StringVar, damit Eingabe leer bleiben kann
        self.current_qty_entry = ttk.Entry(right_frame, textvariable=self.current_qty_var)
        self.current_qty_entry.pack(anchor="w", pady=(0, 10))

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

        # Checkbutton "PDF speichern"
        self.save_pdf_check = ttk.Checkbutton(
            printer_frame,
            text="als PDF speichern",
            variable=self.save_pdf_var
        )
        self.save_pdf_check.grid(row=1, column=1, sticky="w")

        # Button "Etiketten drucken".
        ttk.Button(printer_frame, text="Etikett drucken", command=self.print_label).grid(row=1, column=2)
# ----------------------------------------------------------------------------
    def load_printers(self):
        printers = self.label_printer.get_printers()  # deine API
        names = []

        self.printer_map.clear()
        for printer in printers:
            name = printer["name"]
            self.printer_map[name] = printer["id"]
            names.append(name)

        self.printer_select["values"] = names
        if names:
            self.printer_var.set(names[0])  # Ersten Drucker standardmäßig auswählen
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region Gesamtübersicht
# ----------------------------------------------------------------------------
    def on_mode_change(self, event=None):
        """
        Bei Auswahländerung im Dropdown werden die Daten für das ausgewählte
        Etikettenformat in das Treeview 'Gesamtübersicht' geladen.
        """
        # self.load_overview_data()
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
            # Auftragsetikett
            if mode == "Auftragsetikett":
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

        except Exception as e:
            messagebox.showerror("Fehler", f"Produkte konnten nicht geladen werden:\n{str(e)}")
# ----------------------------------------------------------------------------
    def load_overview_data(self):
        """
        Läd die Einträge aus der im Dropdown-Menü ausgewählten Datenbank.
        """
        mode = self.mode_var.get()
        if mode == "Auftragsetikett":
            loading_popup = LoadingPopup(self, "Einkäufe werden geladen...", on_cancel=lambda: loading_popup.cancel)
        elif mode == "Produktetikett":
            loading_popup = LoadingPopup(self, "Gefertigte Produkte werden geladen...", on_cancel=lambda: loading_popup.cancel)

        def load():
            try:
                if mode == "Auftragsetikett":
                    self.overview_data = self.odoo_client.get_purchases(limit=int(self.limit_var.get()))
                elif mode == "Produktetikett":
                    self.overview_data = self.odoo_client.get_manufacturing_orders(limit=int(self.limit_var.get()))

                # GUI-Aktualisierung im Hauptthread
                self.tree.after(0, lambda: self.write_overview_data())
                if not loading_popup.cancelled:
                    print("Laden abgeschlossen.")

                # Anzahl Einträge wird nach dem laden dargestellt.
                self.entries_tree.configure(text=f"{len(self.overview_data)} Einträge")

            except Exception as e:
                error_context = "Fertigungsdaten" if mode == "Produktetikett" else "Einkaufsdaten"
                self.tree.after(
                    0,
                    lambda err=e: messagebox.showerror("Fehler", f"{error_context} konnten nicht geladen werden:\n{err}")
    )
                
            finally:
                if not loading_popup.cancelled:
                    loading_popup.destroy()

        threading.Thread(target=load, daemon=True).start()
# ----------------------------------------------------------------------------
    def write_overview_data(self):
        """
        Schreibt die geladenen Einträge in das Treeview 'Gesamtübersicht'.
        """
        self.tree.delete(*self.tree.get_children())  # vorherige Zeilen löschen
        
        mode = self.mode_var.get()
        # Auftragsetikett
        if mode == "Auftragsetikett":
            # Überschriften im Treeview werden gesetzt.
            self.tree.heading('reference1', text='Bestellnr.')
            self.tree.heading('reference2', text='Rechnungsnr.')
            self.tree.heading('designation', text='Lieferant')
            self.tree.heading('total', text='Kosten')

            for i, purchase in enumerate(self.overview_data):
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

            for i, component in enumerate(self.overview_data):
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
            # Auftragsetikett
            if mode == "Auftragsetikett":
                self.component = self.product.lines[component_index]

            # Produktetikett
            elif mode == "Produktetikett":
                self.component = self.product.components[component_index]

            self.load_label_data()

        except Exception as e:
            messagebox.showerror("Fehler", f"Produktdetails konnten nicht angezeigt werden:\n{str(e)}")
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region Etikettenvorschau / -druck
# ----------------------------------------------------------------------------
    def load_label_data(self):
        """
        Läd die Einzelteildaten in die Etikettenvorschau.
        """
        name_preview = ""

        preview = ""

        mode = self.mode_var.get()
        # Auftragsetikett
        if mode == "Auftragsetikett" and self.product:
            invoices = getattr(self.product, "invoices", [])
            name_preview = getattr(self.component, 'name', 'Unbekannt')
            preview = (
                f"Chargennummer: {invoices[0].name if invoices else 'Keine Rechnung'}\n"
                f"Artikelnummer: {getattr(self.component, 'default_code', '')}\n"
                f"Menge: {getattr(self.component, 'quantity', 0)}\n"
                f"Lieferant: {getattr(self.product, 'partner_name', 'Unbekannt')}\n"
                f"Rechnung vom {invoices[0].date if invoices else 'Keine Rechnung'}"
            )

        # Produktetikett
        elif mode == "Produktetikett" and self.product:
            name_preview = getattr(self.product, 'name', 'Unbekannt')
            lot = getattr(self.product, "lot_producing_id", None)

            # LOT sicher extrahieren
            if isinstance(lot, (list, tuple)) and len(lot) > 1:
                lot_value = lot[1]
            elif isinstance(lot, str):
                lot_value = lot
            else:
                lot_value = "—"
            preview = (
                f"Referenz: {getattr(self.product, 'default_code', '')}\n"
                f"LOT: {lot_value}\n"
                f"UDI: {getattr(self.product, 'udi', '')}\n"
                f"CE-Kennzeichnung: {'Ja' if getattr(self.product, 'ce', False) else 'Nein'}\n"
                f"Gebrauchsanweisung: {'Ja' if getattr(self.product, 'user_manual', False) else 'Nein'}\n"
                f"Medizinprodukt: {'Ja' if getattr(self.product, 'medical_device', False) else 'Nein'}\n"
                f"Einmalverwendung: {'Ja' if getattr(self.product, 'single_use', False) else 'Nein'}"
            )

        # Text anzeigen.
        self.name_preview.delete("1.0", tk.END)
        self.name_preview.insert("1.0", name_preview)
        self.label_preview.delete("1.0", tk.END)
        self.label_preview.insert("1.0", preview)

        # QR-Code vorbereiten.
        img = None
        if self.product:
            if mode == "Produktetikett":
                # QR-String für Produktetikett
                parts = []
                udi = getattr(self.product, "udi", None)
                lot = getattr(self.product, "lot_producing_id", None)
                if udi:
                    parts.append(f"(01){udi}")
                if lot and len(lot) > 1:
                    parts.append(f"(10){lot[1]}")
                qr_string = "".join(parts) if parts else "NO DATA"

            elif mode == "Auftragsetikett":
                # QR-String für Auftragsetikett
                default_code = getattr(self.component, "default_code", None)
                invoice_name = getattr(self.product.invoices[0], "name", None) if getattr(self.product, "invoices", []) else None
                if default_code and invoice_name:
                    qr_string = f"{default_code}-{invoice_name}"
                else:
                    qr_string = "NO DATA"

            img = self.label_printer.generate_qr_pil(qr_string, 100)

            # Anzeige in Tkinter
            self.qr_image = ImageTk.PhotoImage(img)
            self.qr_label.configure(image=self.qr_image)
# ----------------------------------------------------------------------------
    def print_label(self):
        """
        Erstellt das Label und sendet es an den Drucker.
        """
        # Auswahl des Druckers wird geladen
        selected_name = self.printer_var.get()
        printer_id = self.printer_map.get(selected_name)

        if not printer_id:
            messagebox.showwarning("Kein Drucker", "Bitte einen Drucker auswählen!")
            return
        
        self.label_printer.printer_id = printer_id
        
        # Auswahl des Modus wird geladen
        mode = self.mode_var.get()

        # Zeitstempel generieren (z. B. 20250827_153012)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")

        file_name = "test.pdf"
        pdf_data = ""

        # Auftragsetikett
        if mode == "Auftragsetikett" and self.product:
            if self.product.invoices:
                invoice = self.product.invoices[0]

                # Chargennummer ohne "RG"
                chargenr = invoice.name.removeprefix("RG") if invoice.name else "NOCHARGE"

                # Default Code sauber machen (nur Buchstaben/Zahlen)
                default_code = getattr(self.component, "default_code", "NODEFAULT")
                # default_code = re.sub(r"[^A-Za-z0-9_-]", "_", default_code)

                file_name = self.sanitize_filename(f"{default_code}_{chargenr}_{timestamp}.pdf")
                
                current_qty = self.current_qty_var.get().strip()
                edited_name = self.name_preview.get("1.0", "end-1c").strip()
                if not edited_name:
                    edited_name = getattr(self.product, "name", "Unbekannt")
                pdf_data = self.label_printer.create_order_label_pdf(
                    self.product, self.component, invoice, current_qty, edited_name
                )
            else:
                messagebox.showinfo("Fehlende Daten", "Keine Rechnung vorhanden, bitte Datensatz mit Rechnung auswählen!")
        
        # Produktetikett
        elif mode == "Produktetikett" and self.product:
            lot = getattr(self.product, "lot_producing_id", None)
            if isinstance(lot, list) and len(lot) > 1:
                lot = lot[1]
            lot = lot or "NOLOT"

            default_code = getattr(self.product, "default_code", "NODEFAULT")
            # default_code = re.sub(r"[^A-Za-z0-9_-]", "_", default_code)

            file_name = self.sanitize_filename(f"{default_code}_{lot}_{timestamp}.pdf")

            current_qty = self.current_qty_var.get().strip()
            edited_name = self.name_preview.get("1.0", "end-1c").strip()
            if not edited_name:
                edited_name = getattr(self.product, "name", "Unbekannt")
            pdf_data = self.label_printer.create_product_label_pdf(self.product, current_qty, edited_name)

        self.label_printer.send_pdf_to_printnode(pdf_data)

        # Optional speichern
        if self.save_pdf_var.get():
            file_path = self.label_printer.file_path + file_name

            with open(file_path, "wb") as pdf:
                pdf.write(pdf_data)

            print(f"Etikett gespeichert als: {file_path}")

        # Druckauswahl in den Settings speichern.
        self.settings_manager.update_printer_settings(
            printer_id,
            self.save_pdf_var.get()
        )
# ----------------------------------------------------------------------------
    def sanitize_filename(self, name: str) -> str:
        # Alles außer Buchstaben, Zahlen, Unterstrich und Bindestrich durch "_" ersetzen
        return re.sub(r'[\\/*?:"<>|]', "_", name)
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
