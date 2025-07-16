import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

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

        self.entry_code = ttk.Entry(right_frame)
        self.entry_code.pack(fill="x", pady=5)

        ttk.Button(right_frame, text="Etikett anzeigen", command=self.preview_label).pack(fill="x", pady=5)
        ttk.Button(right_frame, text="Etikett drucken", command=self.print_label).pack(fill="x", pady=5)

        ttk.Label(right_frame, text="Etikett-Vorschau").pack(pady=(15, 5), anchor="w")
        self.label_preview = tk.Text(right_frame, height=10, wrap="word")
        self.label_preview.pack(fill="both", expand=True)
# ----------------------------------------------------------------------------
    def preview_label(self):
        code = self.entry_code.get()

        # Produkt abrufen
        products = self.odoo_client.search_read_products_by_code(code)
        if not products:
            print("Kein Produkt gefunden.")
            exit()

        product = products[0]
        
        self.label_preview.delete("1.0", tk.END)
        self.label_preview.insert(tk.END, f"Produkt: {product['name']}")
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
    def load_sales_data(self):
        try:
            self.sales_data = self.odoo_client.get_sales(limit=20)
            self.tree.delete(*self.tree.get_children())  # vorherige Zeilen löschen

            for i, sale in enumerate(self.sales_data):
                self.tree.insert("", "end", iid=i, values=(sale.name, sale.customer, sale.date, f"{sale.total:.2f} €"))

        except Exception as e:
            messagebox.showerror("Fehler", f"Verkaufsdaten konnten nicht geladen werden:\n{str(e)}")
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
    def load_sales_data_with_invoices(self):
        try:
            sales = self.odoo_client.models.execute_kw(
                self.odoo_client.db,
                self.odoo_client.uid,
                self.odoo_client.password,
                'sale.order',
                'search_read',
                [[['invoice_ids', '!=', False]]],
                {'fields': ['id', 'partner_id', 'date_order', 'amount_total', 'invoice_ids'], 'limit': 20}
            )

            self.tree.delete(*self.tree.get_children())

            for sale in sales:
                partner = sale.get("partner_id", ["", "Unbekannt"])[1]
                date_order = sale.get("date_order", "")[:10]
                amount = sale.get("amount_total", 0.0)
                invoice_ids = sale.get("invoice_ids", [])

                invoice_name = "—"
                if invoice_ids:
                    invoices = self.odoo_client.models.execute_kw(
                        self.odoo_client.db,
                        self.odoo_client.uid,
                        self.odoo_client.password,
                        'account.move',
                        'read',
                        [invoice_ids],
                        {'fields': ['name', 'state']}
                    )
                    posted_invoices = [inv for inv in invoices if inv['state'] == 'posted']
                    if posted_invoices:
                        invoice_name = posted_invoices[0]['name']
                    elif invoices:
                        invoice_name = invoices[0]['name']

                self.tree.insert("", "end", values=(invoice_name, partner, date_order, amount))

        except Exception as e:
            messagebox.showerror("Fehler", f"Verkaufsdaten konnten nicht geladen werden:\n{e}")
# ----------------------------------------------------------------------------
