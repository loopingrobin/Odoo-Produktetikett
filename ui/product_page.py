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
    def __init__(self, parent, app, odoo_client, label_printer):
        super().__init__(parent)

        self.app = app
        self.odoo_client = odoo_client
        self.label_printer = label_printer

        self.sales_data = None
        self.tree = None

        self.build_ui()
        # self.winfo_toplevel().minsize(1000, 600)
# ----------------------------------------------------------------------------
    def on_show(self):
        self.load_sales_data()
        # self.load_sales_data_with_invoices()
# ----------------------------------------------------------------------------
    def build_ui(self):
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        # Zwei Spalten im Container anlegen
        container.columnconfigure(0, weight=1, minsize=520)  # linke Spalte (Verkaufsliste)
        container.columnconfigure(1, weight=1)  # rechte Spalte (Suchfeld etc.)

        # Verkaufsübersicht
        left_frame = ttk.Frame(container)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        self.tree = ttk.Treeview(
            left_frame,
            columns=("invoice", "customer", "date", "total"),
            show="headings"
        )

        # Spaltenüberschriften
        self.tree.heading("invoice", text="Rechnung")
        self.tree.heading("customer", text="Kunde")
        self.tree.heading("date", text="Datum")
        self.tree.heading("total", text="Gesamt")

        # Spaltenbreite in Pixeln definieren (stretch=True erlaubt Anpassung durch Benutzer)
        self.tree.column("invoice", width=100, anchor="w", stretch=False)
        self.tree.column("customer", width=250, anchor="w", stretch=True)
        self.tree.column("date", width=80, anchor="center", stretch=False)
        self.tree.column("total", width=80, anchor="e", stretch=False)

        self.tree.bind("<<TreeviewSelect>>", self.on_sale_selected)  # Eventbindung

        self.tree.pack(fill="both", expand=True)

        # Etikett-Vorschau
        right_frame = ttk.Frame(container)
        right_frame.grid(row=0, column=1, sticky="nsew")

        ttk.Label(right_frame, text="Produktübersicht").pack(pady=5, anchor="w")

        self.tree_products = ttk.Treeview(right_frame, columns=("product", "qty", "price"), show="headings", height=8)

        # Spaltenüberschriften
        self.tree_products.heading("product", text="Produkt")
        self.tree_products.heading("qty", text="Menge")
        self.tree_products.heading("price", text="Einzelpreis")

        # Spaltenbreite
        self.tree_products.column("product", width=200, anchor="w", stretch=True)
        self.tree_products.column("qty", width=50, anchor="e", stretch=False)
        self.tree_products.column("price", width=80, anchor="e", stretch=False)

        self.tree_products.pack(fill="both", expand=True)
        self.tree_products.bind("<<TreeviewSelect>>", self.on_product_selected)


        ttk.Label(right_frame, text="Etikett-Vorschau").pack(pady=(15, 5), anchor="w")
        self.label_preview = tk.Text(right_frame, height=10, wrap="word")
        self.label_preview.pack(fill="both", expand=True)
        
        self.qr_label = ttk.Label(right_frame)
        self.qr_label.pack(pady=5)

        ttk.Button(right_frame, text="Etikett drucken", command=self.print_label).pack(fill="x", pady=5)
# ----------------------------------------------------------------------------
    def print_label(self):
        # Etikett drucken
        # zpl = printer.generate_zpl(product)
        # printer.print_label(zpl)
        pfad = "etikett.pdf"
        self.label_printer.create_pdf(pfad, self.product)
        self.label_printer.send_pdf_to_printnode(pfad)

        print("Etikett wurde gesendet.")
# ----------------------------------------------------------------------------
    def on_sale_selected(self, event):
        selected = self.tree.selection()
        if not selected:
            return

        index = int(selected[0])
        sale = self.sales_data[index]

        try:
            # Produkte anzeigen
            self.tree_products.delete(*self.tree_products.get_children())
            for line in sale.lines:
                self.tree_products.insert("", "end", values=(line.product_name, line.quantity, f"{line.price:.2f} €"))

        except Exception as e:
            messagebox.showerror("Fehler", f"Produkte konnten nicht geladen werden:\n{str(e)}")
# ----------------------------------------------------------------------------
    def on_product_selected(self, event):
        selected_sale_index = self.tree.selection()
        if not selected_sale_index:
            return

        selected_product_index = self.tree_products.selection()
        if not selected_product_index:
            return

        sale_index = int(selected_sale_index[0])
        product_iid = selected_product_index[0]
        children = self.tree_products.get_children()
        product_index = children.index(product_iid)

        try:
            sale = self.sales_data[sale_index]
            line = sale.lines[product_index]

            # Text vorbereiten.
            preview = (
                f"Produkt: {line.product_name}\n"
                f"Referenz: {line.default_code}\n"
                f"Menge: {line.quantity}\n"
                f"Einzelpreis: {line.price:.2f} €\n\n"
                f"UDI: {line.udi}\n"
                f"CE-Kennzeichnung: {'Ja' if line.ce else 'Nein'}\n"
                f"Gebrauchsanweisung: {'Ja' if line.user_manual else 'Nein'}\n"
                f"Medizinprodukt: {'Ja' if line.medical_device else 'Nein'}\n"
                f"Einmalverwendung: {'Ja' if line.single_use else 'Nein'}"
            )

            # Text anzeigen.
            self.label_preview.delete("1.0", tk.END)
            self.label_preview.insert("1.0", preview)

            # QR-Code vorbereiten.
            qr = qrcode.QRCode(box_size=4, border=2)
            qr.add_data(line.udi)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img = img.resize((150, 150), Image.Resampling.LANCZOS)

            # QR-Code anzeigen.
            self.qr_image = ImageTk.PhotoImage(img)
            self.qr_label.configure(image=self.qr_image)

        except Exception as e:
            messagebox.showerror("Fehler", f"Produktdetails konnten nicht angezeigt werden:\n{str(e)}")
# ----------------------------------------------------------------------------
    def load_sales_data(self):
        loading_popup = LoadingPopup(self, "Verkäufe werden geladen...", on_cancel=lambda: loading_popup.cancel)

        def load():
            try:
                self.sales_data = self.odoo_client.get_sales(limit=20)

                # GUI-Aktualisierung im Hauptthread
                self.tree.after(0, lambda: self.update_treeview())
                if not loading_popup.cancelled:
                    print("Laden abgeschlossen.")

            except Exception as e:
                self.tree.after(0, lambda: messagebox.showerror("Fehler", f"Verkaufsdaten konnten nicht geladen werden:\n{str(e)}"))

                
            finally:
                if not loading_popup.cancelled:
                    loading_popup.destroy()

        threading.Thread(target=load, daemon=True).start()
# ----------------------------------------------------------------------------
    def update_treeview(self):
        self.tree.delete(*self.tree.get_children())  # vorherige Zeilen löschen

        for i, sale in enumerate(self.sales_data):
            self.tree.insert("", "end", iid=i, values=(sale.invoices[0].name, sale.customer, sale.date, f"{sale.total:.2f} €"))
# ----------------------------------------------------------------------------
