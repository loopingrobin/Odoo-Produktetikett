import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import qrcode
from PIL import Image, ImageTk
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
    def __init__(self, parent, app, odoo_client, label_printer):
        super().__init__(parent)

        self.app = app
        self.odoo_client = odoo_client
        self.label_printer = label_printer

        self.overview_data = None
        self.product = None
        self.components_data = None
        self.component = None
        self.mode_var = tk.StringVar(value="Produktetikett") # Default

        self.build_ui()
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
        self.load_overview_data()
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
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        # Dropdown für Auswahl
        ttk.Label(left_frame, text="Etikett-Typ:").pack(anchor="w", pady=(5, 2))
        self.mode_select = ttk.Combobox(
            left_frame,
            textvariable=self.mode_var,
            values=["Produktetikett", "Auftragsetikett"],
            state="readonly"
        )
        self.mode_select.pack(anchor="w", pady=(0, 10))
        self.mode_select.bind("<<ComboboxSelected>>", self.on_mode_change)

        # Gesamtsübersicht
        self.tree = ttk.Treeview(
            left_frame,
            columns=("reference1", "reference2", "designation", "total"),
            show="headings"
        )

        # Spaltenbreite in Pixeln definieren (stretch=True erlaubt Anpassung durch Benutzer)
        self.tree.column("reference1", width=100, anchor="w", stretch=False)
        self.tree.column("reference2", width=100, anchor="w", stretch=False)
        self.tree.column("designation", width=230, anchor="w", stretch=True)
        self.tree.column("total", width=80, anchor="e", stretch=False)

        self.tree.bind("<<TreeviewSelect>>", self.on_overview_selected)  # Eventbindung

        self.tree.pack(fill="both", expand=True)

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

        # Etikett-Vorschau
        ttk.Label(right_frame, text="Etikett-Vorschau").pack(pady=(15, 5), anchor="w")
        self.label_preview = tk.Text(right_frame, height=10, wrap="word")
        self.label_preview.pack(fill="both", expand=True)
        
        self.qr_label = ttk.Label(right_frame)
        self.qr_label.pack(pady=5)

        ttk.Button(right_frame, text="Etikett drucken", command=self.print_label).pack(fill="x", pady=5)
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
        # mode = self.mode_var.get()
        # if mode == "Produktetikett":
        #     self.load_manufacturing_data()
        # elif mode == "Auftragsetikett":
        self.load_overview_data()
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
                            f"{component.quantity:.2f} Stück"
                        )
                    )

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
                    self.overview_data = self.odoo_client.get_purchases(limit=20)
                elif mode == "Produktetikett":
                    self.overview_data = self.odoo_client.get_manufacturing_orders(limit=20)

                # GUI-Aktualisierung im Hauptthread
                self.tree.after(0, lambda: self.write_overview_data())
                if not loading_popup.cancelled:
                    print("Laden abgeschlossen.")

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
                        f"{purchase.lines[i].price:.2f} €"
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
                        f"{component.components[i].quantity} Stück"
                    )
                )
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
        preview = ""

        mode = self.mode_var.get()
        # Auftragsetikett
        if mode == "Auftragsetikett":
            # Text vorbereiten.
            preview = (
                f"Bezeichnung: {self.component.name}\n"
                f"Artikelnummer: {self.component.default_code}\n"
                f"Chargennummer: {getattr(self.component, 'lot_producing_id', ['','Unbekannt'])[1]}\n"
                f"Menge: {self.component.quantity}\n"
                f"Lieferant: {self.product.partner_name}\n"
            )

        # Produktetikett
        elif mode == "Produktetikett":
            preview = (
                f"Produkt: {self.product.name}\n"
                f"Referenz: {self.product.default_code}\n"
                f"UDI: {self.product.udi if self.product.udi else ''}\n"
                f"CE-Kennzeichnung: {'Ja' if self.product.ce else 'Nein'}\n"
                f"Gebrauchsanweisung: {'Ja' if self.product.user_manual else 'Nein'}\n"
                f"Medizinprodukt: {'Ja' if self.product.medical_device else 'Nein'}\n"
                f"Einmalverwendung: {'Ja' if self.product.single_use else 'Nein'}"
            )

        # Text anzeigen.
        self.label_preview.delete("1.0", tk.END)
        self.label_preview.insert("1.0", preview)

        # QR-Code vorbereiten.
        qr = qrcode.QRCode(box_size=4, border=2)
        qr.add_data(self.product.udi)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img = img.resize((150, 150), Image.Resampling.LANCZOS)

        # QR-Code anzeigen.
        self.qr_image = ImageTk.PhotoImage(img)
        self.qr_label.configure(image=self.qr_image)
# ----------------------------------------------------------------------------
    def print_label(self):
        """
        Erstellt das Label und sendet es an den Drucker.
        """
        # Etikett drucken
        # zpl = printer.generate_zpl(product)
        # printer.print_label(zpl)
        pfad = "etikett.pdf"
        self.label_printer.create_pdf(pfad, self.component)
        self.label_printer.send_pdf_to_printnode(pfad)

        print("Etikett wurde gesendet.")
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
