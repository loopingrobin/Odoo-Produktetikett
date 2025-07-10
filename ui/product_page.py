import tkinter as tk
from tkinter import ttk

class ProductPage(ttk.Frame):
    def __init__(self, parent, app, odoo_client, label_printer):
        super().__init__(parent)

        ttk.Label(self, text="Produktsuche").pack(pady=10)

        self.entry_code = ttk.Entry(self)
        self.entry_code.pack(pady=5)

        ttk.Button(self, text="Etikett anzeigen", command=self.preview_label).pack(pady=5)
        ttk.Button(self, text="Etikett drucken", command=self.print_label).pack(pady=5)

        self.label_preview = tk.Text(self, height=10, width=60)
        self.label_preview.pack(pady=10)
# ----------------------------------------------------------------------------
    def preview_label(self):
        code = self.entry_code.get()
        self.label_preview.delete("1.0", tk.END)
        self.label_preview.insert(tk.END, f"(ZPL-Vorschau für Code: {code})")
# ----------------------------------------------------------------------------
    def print_label(self):
        code = self.entry_code.get()
        print(f"Etikett für {code} wird gedruckt.")
# ----------------------------------------------------------------------------
