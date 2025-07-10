# https://pypi.org/project/odoo-api-wrapper/
# https://api.printnode.com/app/apikeys
# main.py
from ui.app import EtikettApp

# Globale App-Version
APP_VERSION = "v1.0.0"

if __name__ == "__main__":
    app = EtikettApp(app_version=APP_VERSION)
    app.mainloop()

    # # Produkt abrufen
    # products = odoo.search_read_products_by_code("07790-1-1")
    # if not products:
    #     print("Kein Produkt gefunden.")
    #     exit()

    # product = products[0]

    # # Etikett drucken
    # # zpl = printer.generate_zpl(product)
    # # printer.print_label(zpl)
    # pfad = "etikett.pdf"
    # printer.create_pdf(pfad, product)
    # printer.send_pdf_to_printnode(pfad)

    # print("Etikett wurde gesendet.")
