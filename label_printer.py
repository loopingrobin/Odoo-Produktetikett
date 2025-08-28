# label_printer.py
from datetime import datetime
import requests
import base64
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
import qrcode
from io import BytesIO
from PIL import Image
from odoo_client import Invoice, ManufacturingOrder, PurchaseOrder, PurchaseOrderLine

class LabelPrinter:
# ----------------------------------------------------------------------------
# region Konstruktor
# ----------------------------------------------------------------------------
    def __init__(self, api_key="", printer_id=""):
        self.api_key = api_key
        self.printer_id = printer_id if printer_id != "" else "74652188"
        self.isConnected: bool = False
        self.file_path: str = ''
        self.logo = ImageReader("label_pictures\\Logo_CHW.png")
        self.ref_image = ImageReader("label_pictures\\REF.png")
        self.udi_image = ImageReader("label_pictures\\UDI.png")
        self.lot_image = ImageReader("label_pictures\\LOT.png")
        self.sn_image = ImageReader("label_pictures\\SN.png")
        self.md_image = ImageReader("label_pictures\\MD.png")
        self.instruction_image = ImageReader("label_pictures\\Instruction.png")
        self.single_patient_image = ImageReader("label_pictures\\Single-patient.png")
        self.ce_image = ImageReader("label_pictures\\CE.png")
        self.production_date_image = ImageReader("label_pictures\\Firma.png")

        # Vordefinierte Styles
        self.styles = {
            "header": ParagraphStyle(
                name="Header",
                fontName="Helvetica",
                fontSize=20,
                leading=24,
                alignment=0  # linksbündig
            ),
            "small": ParagraphStyle(
                name="Small",
                fontName="Helvetica",
                fontSize=7,
                leading=9,
                alignment=0
            ),
        }  

        if self.api_key != "":
            success, message = self.connect()
            if success:
                self.isConnected = True
            else:
                print("❌ Drucker-Verbindung fehlgeschlagen:", message)
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region Initialisierung
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
# endregion
# ----------------------------------------------------------------------------
# region ZPL
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
# endregion
# ----------------------------------------------------------------------------
# region PDF
# ----------------------------------------------------------------------------
    def create_pdf(self, file_name, product):
        c = canvas.Canvas(self.file_path + file_name, pagesize=(100 * mm, 50 * mm))  # 100x50 mm

        c.setFont("Helvetica", 12)
        c.drawString(10 * mm, 40 * mm, f"Name: {product.product_name}")
        c.drawString(10 * mm, 30 * mm, f"Price: ${product.price}")

        # Optional: Barcode zeichnen (mit weiteren libs)

        c.save()
# ----------------------------------------------------------------------------
    def create_order_label_pdf(self, file_name: str, order: PurchaseOrder, component: PurchaseOrderLine, invoice: Invoice):
        """
        Erstellt das Auftragsetikett und speichert es als PDF.
        """
        # Grundeinstellungen
        c = canvas.Canvas(self.file_path + file_name, pagesize=(100 * mm, 50 * mm))  # 100x50 mm
        c.setFont("Helvetica", 10)

        # Y-Koordinate von oben nach unten
        y = 45 * mm  

        # Logo links oben
        self.draw_logo(c, 5 * mm, 41 * mm)
        c.setFont("Helvetica", 10)

        # Chargennummer rechts neben Logo
        nummer = invoice.name.removeprefix("RG")
        c.drawString(50 * mm, y - 2 * mm, f"Chargennummer   {nummer}")

        # Bezeichnung (zentriert in Box)
        y -= 28 * mm
        self.draw_paragraph(
            c, component.name,
            x=5 * mm, y=y,
            w=90 * mm, h=30 * mm,
            style="header"
        )

        # Artikelnummer
        # y += 1 * mm
        c.drawString(5 * mm, y, f"Artikelnummer   {component.default_code}")

        # Menge und Datum
        y -= 6 * mm
        c.drawString(5 * mm, y, f"Stück   {int(component.quantity)}")
        c.drawString(35 * mm, y, f"Rechnung vom {invoice.date}")

        # QR-Code
        qr_img = self.generate_qr_code(component.default_code + "-" + invoice.name)
        c.drawImage(qr_img, 80 * mm, y - 7 * mm, width=16 * mm, height=16 * mm)

        # Lieferant nebeneinander
        y -= 6 * mm
        c.drawString(5 * mm, y, f"Lieferant   {order.partner_name}")
        
        # Speichern
        c.save()
# ----------------------------------------------------------------------------
    def create_product_label_pdf(self, file_name: str, product: ManufacturingOrder):
        """
        Erstellt das Auftragsetikett und speichert es als PDF.
        """
        # Grundeinstellungen
        c = canvas.Canvas(self.file_path + file_name, pagesize=(100 * mm, 50 * mm))  # 100x50 mm
        c.setFont("Helvetica", 10)

        # Y-Koordinate von oben nach unten
        y = 45 * mm  

        # Logo links oben
        self.draw_logo(c, 92 * mm, 48 * mm, rotation=-90)
        c.setFont("Helvetica", 10)

        # Bezeichnung (zentriert in Box)
        y -= 20 * mm
        self.draw_paragraph(
            c, product.name,
            x=5 * mm, y=y,
            w=80 * mm, h=30 * mm,
            style="header"
        )

        # Symbol-Einstellungen
        width_symbol = 13
        heigth_symbol = 8
        x_symbol = 21 * mm

        # REF
        c.drawImage(self.ref_image, 4 * mm, y, width=width_symbol, height=heigth_symbol, preserveAspectRatio=True, mask='auto')
        c.drawString(10 * mm, y + 0.5 * mm, f"{product.default_code}")

        # UDI
        y -= 6 * mm
        c.drawImage(self.udi_image, x_symbol, y, width=width_symbol, height=heigth_symbol, preserveAspectRatio=True, mask='auto')
        c.drawString(x_symbol + 6 * mm, y + 0.5 * mm, f"{product.udi}")

        # LOT
        y -= 5 * mm
        c.drawImage(self.lot_image, x_symbol, y, width=width_symbol, height=heigth_symbol, preserveAspectRatio=True, mask='auto')
        c.drawString(x_symbol + 6 * mm, y, f"{product.lot_producing_id[1]}")

        # QR-Code
        x_qr = 3 * mm
        qr_string = "(01)" + product.udi + "(10)" + product.lot_producing_id[1]
        qr_img = self.generate_qr_code(qr_string)
        c.drawImage(qr_img, x_qr, y - 7 * mm, width=16 * mm, height=16 * mm)
        c.drawString(x_qr, y - 10 * mm, f"{qr_string}")

        # MD, Instruction, single patient, CE, production date
        y -= 5 * mm
        c.drawImage(self.md_image, x_symbol, y, width=width_symbol, height=heigth_symbol, preserveAspectRatio=True, mask='auto')
        c.drawImage(self.instruction_image, x_symbol + 6 * mm, y - 0.5 * mm, width=11, height=11, preserveAspectRatio=True, mask='auto')
        c.drawImage(self.single_patient_image, x_symbol + 11 * mm, y - 0.5 * mm, width=11, height=11, preserveAspectRatio=True, mask='auto')
        c.drawImage(self.ce_image, x_symbol + 16 * mm, y, width=10, height=10, preserveAspectRatio=True, mask='auto')
        c.drawImage(self.production_date_image, x_symbol + 21.5 * mm, y + 0.5 * mm, width=8, height=8, preserveAspectRatio=True, mask='auto')
        c.setFont("Helvetica", 3)
        c.drawString(x_symbol + 21 * mm, y - 0.5 * mm, datetime.strptime(product.date_start, "%Y-%m-%d").strftime("%y-%m-%d"))

        # Kontaktdaten
        x_contact = 65 * mm
        y_contact = 23 * mm
        c.setFont("Helvetica", 7)
        c.drawString(x_contact, y_contact, "CHW-Technik GmbH")
        c.drawString(x_contact, y_contact - 3 * mm, "Kolligsbrunnen 1")
        c.drawString(x_contact, y_contact - 6 * mm, "37115 Duderstadt")
        c.drawString(x_contact, y_contact - 9 * mm, "c.wagner@chw-technik.de")
        c.drawString(x_contact, y_contact - 12 * mm, "+49 5527 99896-9")
        
        # Speichern
        c.save()
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region Draw-Hilfsmeth.
# ----------------------------------------------------------------------------
    def draw_logo(self, c, x: float, y: float, rotation: int = 0):
        """
        Hilfsmethode: zeichnet Firmenlogo + Schrift.
        rotation: 0 = normal, 90 = im Uhrzeigersinn, -90 = gegen Uhrzeigersinn
        """
        if not self.logo:
            return

        # Speichere aktuellen Zustand, damit die Rotation nur für Logo+Text gilt
        c.saveState()

        # Verschiebe Ursprung zur gewünschten Position
        c.translate(x, y)

        # Drehe Koordinatensystem
        if rotation in (90, -90):
            c.rotate(rotation)

        # Logo und Text zeichnen (jetzt relativ zum Ursprung x=0,y=0)
        c.drawImage(self.logo, 0, 0, width=7 * mm, height=7 * mm, preserveAspectRatio=True)

        # Text daneben
        c.setFont("Helvetica", 7)
        c.drawString(8 * mm, 3 * mm, "CHW-Technik")
        c.setFont("Helvetica", 3)
        c.drawString(8 * mm, 1 * mm, "OT-Produkte GmbH")

        # Zustand zurücksetzen
        c.restoreState()
# ----------------------------------------------------------------------------
    def draw_paragraph(self, c, text: str, x: float, y: float, w: float, h: float, style: str = "header"):
        """Hilfsmethode: zeichnet Text vertikal zentriert in eine Box."""
        para = Paragraph(text, self.styles[style])
        w_used, h_used = para.wrap(w, h)
        para.drawOn(c, x, y + (h - h_used) / 2)
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region QR
# ----------------------------------------------------------------------------
    @staticmethod
    def generate_qr_pil(data: str, size: int = 150) -> Image.Image:
        """Erzeugt einen QR-Code als PIL-Image"""
        if not data:
            return None
        qr = qrcode.QRCode(box_size=4, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        return img.resize((size, size), Image.Resampling.LANCZOS)
# ----------------------------------------------------------------------------
    @staticmethod
    def generate_qr_code(data: str) -> ImageReader:
        """
        Erzeugt ein QR-Code-Bild aus einem String.

        Args:
            data (str): Text, der in den QR-Code soll.
            size (int): Größe (Breite/Höhe) in Pixeln für das zurückgegebene Bild.

        Returns:
            PIL.Image.Image: QR-Code Bild.
        """
        if not data:
            return None  # Wenn kein Inhalt, kein QR-Code

        qr = qrcode.QRCode(box_size=4, border=2)
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # PIL → BytesIO → ReportLab ImageReader
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return ImageReader(buffer)
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region PrintNode
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
    def send_pdf_to_printnode(self, file_name, title="Etikett"):
        """
        Sendet ein PDF an PrintNode über die API.
        """
        with open(self.file_path + file_name, "rb") as f:
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
# endregion
# ----------------------------------------------------------------------------
