# label_printer.py
import requests
import base64
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

class LabelPrinter:
    def __init__(self, api_key="", printer_id=""):
        self.api_key = api_key
        self.printer_id = printer_id if printer_id != "" else "74652188"
        self.isConnected = False

        if self.api_key != "":
            success, message = self.connect()
            if success:
                self.isConnected = True
            else:
                print("❌ Drucker-Verbindung fehlgeschlagen:", message)
# ----------------------------------------------------------------------------
    def connect(self):
        try:
            response = requests.get(
                "https://api.printnode.com/printers",
                auth=(self.api_key, '')
            )
            if response.status_code == 200:
                return True, "Verbindung erfolgreich"
            elif response.status_code == 403:
                return False, "Zugriff verweigert: API-Key ungültig"
            else:
                return False, f"Fehler: Status {response.status_code}"
        except requests.exceptions.RequestException as e:
            return False, f"Verbindungsfehler: {e}"
# ----------------------------------------------------------------------------
    def create_zpl(self, product):
        return f"""
^XA
^PW800                          ; Etikettbreite (100 mm bei 203 dpi)
^LL400                          ; Etiketthöhe (50 mm bei 203 dpi)

^FO30,30
^A0N,40,40
^FDName: {product['name']}^FS

^FO30,90
^A0N,40,40
^FDPrice: ${product['list_price']}^FS

^FO30,160
^BY2
^BCN,100,Y,N,N
^FD{product['barcode']}^FS

^XZ
"""
# ----------------------------------------------------------------------------
    def send_zpl_to_printnode(self, zpl_string):
        """
        Sendet ein ZPL an PrintNode über die API.
        """
        response = requests.post(
            "https://api.printnode.com/printjobs",
            auth=(self.api_key, ''),
            json={
                "printerId": self.printer_id,
                "title": "Produktetikett",
                "contentType": "raw_base64",
                "content": zpl_string.encode("utf-8").decode("latin1").encode("base64").decode(),
            }
        )

        if response.status_code != 201:
            raise Exception(f"Druck fehlgeschlagen: {response.text}")
                
        return response.ok
# ----------------------------------------------------------------------------
    def create_pdf(self, file_path, product):
        c = canvas.Canvas(file_path, pagesize=(100 * mm, 50 * mm))  # 100x50 mm

        c.setFont("Helvetica", 12)
        c.drawString(10 * mm, 40 * mm, f"Name: {product.product_name}")
        c.drawString(10 * mm, 30 * mm, f"Price: ${product.price}")

        # Optional: Barcode zeichnen (mit weiteren libs)

        c.save()
# ----------------------------------------------------------------------------
    def send_pdf_to_printnode(self, file_path, title="Etikett"):
        """
        Sendet ein PDF an PrintNode über die API.
        """
        with open(file_path, "rb") as f:
            pdf_b64 = base64.b64encode(f.read()).decode()

        response = requests.post(
            "https://api.printnode.com/printjobs",
            auth=(self.api_key, ""),
            json={
                "printerId": self.printer_id,
                "title": title,
                "contentType": "pdf_base64",
                "content": pdf_b64,
                "source": "Etikett-Druck per Python"
            }
        )

        if response.status_code == 201:
            print("✅ Etikett erfolgreich an den Drucker gesendet.")
        else:
            print("❌ Fehler beim Senden:", response.status_code, response.text)
# ----------------------------------------------------------------------------
