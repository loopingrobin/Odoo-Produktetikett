# label_printer.py
from datetime import datetime
import io
import os
from xml.sax.saxutils import escape
import requests
import base64
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
import qrcode
from io import BytesIO
from PIL import Image
from odoo_client import Invoice, ManufacturingOrder, PurchaseOrder, PurchaseOrderLine

# Bilder und Schrift liegen neben dem Programm, unabhängig vom Arbeitsverzeichnis.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRINTNODE_URL = "https://api.printnode.com"
# Timeout in Sekunden: (Verbindungsaufbau, Antwort)
REQUEST_TIMEOUT = (5, 30)
# Maße, auf die das Etikett-Layout entworfen ist (Koordinaten im Code in mm)
DESIGN_WIDTH_MM = 100
DESIGN_HEIGHT_MM = 50

def _asset(*parts: str) -> str:
    return os.path.join(BASE_DIR, *parts)

class LabelPrinter:
# ----------------------------------------------------------------------------
# region Konstruktor
# ----------------------------------------------------------------------------
    def __init__(self, api_key="", settings_manager=None, printer_id=""):
        self.api_key = api_key
        self.settings_manager = settings_manager
        self.printer_id = printer_id

        self.isConnected: bool = False

        # PDF-Pfad aus den Settings laden
        self.load_settings()
            
        self.logo = ImageReader(_asset("label_pictures", "Logo_CHW.png"))
        self.ref_image = ImageReader(_asset("label_pictures", "REF.png"))
        self.udi_image = ImageReader(_asset("label_pictures", "UDI.png"))
        self.lot_image = ImageReader(_asset("label_pictures", "LOT.png"))
        self.sn_image = ImageReader(_asset("label_pictures", "SN.png"))
        self.md_image = ImageReader(_asset("label_pictures", "MD.png"))
        self.instruction_image = ImageReader(_asset("label_pictures", "Instruction.png"))
        self.single_patient_image = ImageReader(_asset("label_pictures", "Single-patient.png"))
        self.ce_image = ImageReader(_asset("label_pictures", "CE.png"))
        self.production_date_image = ImageReader(_asset("label_pictures", "Firma.png"))

        # Vordefinierte Styles
        pdfmetrics.registerFont(TTFont('Titillium', _asset("fonts", "titilliumtext25l.ttf")))
        self.styles = {
            "header": ParagraphStyle(
                name="Header",
                fontName="Titillium",
                fontSize=18,
                leading=24,
                alignment=1  # 0=linksbündig, 1=zentriert
            ),
            "small": ParagraphStyle(
                name="Small",
                fontName="Titillium",
                fontSize=7,
                leading=9,
                alignment=0
            ),
        }  

        if self.api_key != "":
            success, message = self.connect()
            self.isConnected = success
            if not success:
                print("❌ Drucker-Verbindung fehlgeschlagen:", message)
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region Initialisierung
# ----------------------------------------------------------------------------
    def connect(self) -> tuple[bool, str]:
        """
        Prüft den API-Key bei PrintNode.
        Rückgabe: (Erfolg, Meldung). Setzt zusätzlich isConnected.
        """
        self.isConnected = False
        if not self.api_key:
            return False, "Kein API-Key angegeben."
        try:
            response = requests.get(
                f"{PRINTNODE_URL}/printers",
                auth=(self.api_key, ''),
                timeout=REQUEST_TIMEOUT
            )
        except requests.exceptions.RequestException as e:
            return False, f"Verbindungsfehler: {e}"

        if response.status_code == 200:
            self.isConnected = True
            return True, "Verbindung erfolgreich"
        if response.status_code in (401, 403):
            return False, "Zugriff verweigert: API-Key ungültig"
        return False, f"Fehler: Status {response.status_code}"
# ----------------------------------------------------------------------------
    def load_settings(self):
        if self.settings_manager:
            label_settings = self.settings_manager.get_label_settings()
            self.file_path: str = label_settings.get("pdf_path", "")
            self.address_lines = label_settings.get("address_lines", ["", "", "", "", ""])
            self.label_width_mm = self._valid_size(label_settings.get("width_mm"), DESIGN_WIDTH_MM)
            self.label_height_mm = self._valid_size(label_settings.get("height_mm"), DESIGN_HEIGHT_MM)
        else:
            self.file_path = ""
            self.address_lines = ["", "", "", "", ""]
            self.label_width_mm = DESIGN_WIDTH_MM
            self.label_height_mm = DESIGN_HEIGHT_MM
# ----------------------------------------------------------------------------
    @staticmethod
    def _valid_size(value, default: float) -> float:
        """Etikettengröße aus den Einstellungen; bei ungültigem Wert das Standardmaß."""
        try:
            value = float(value)
        except (TypeError, ValueError):
            return default
        return value if value > 0 else default
# ----------------------------------------------------------------------------
    def _new_canvas(self, buffer) -> canvas.Canvas:
        """
        Legt ein PDF in der eingestellten Etikettengröße an. Das Layout ist auf
        100 x 50 mm entworfen und wird proportional skaliert und zentriert,
        sodass der Inhalt auf jedes Format passt.
        """
        width, height = self.label_width_mm * mm, self.label_height_mm * mm
        c = canvas.Canvas(buffer, pagesize=(width, height))

        scale = min(width / (DESIGN_WIDTH_MM * mm), height / (DESIGN_HEIGHT_MM * mm))
        offset_x = (width - DESIGN_WIDTH_MM * mm * scale) / 2
        offset_y = (height - DESIGN_HEIGHT_MM * mm * scale) / 2
        c.translate(offset_x, offset_y)
        c.scale(scale, scale)
        return c
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region PDF
# ----------------------------------------------------------------------------
    def create_order_label_pdf(
        self, 
        order: PurchaseOrder, 
        component: PurchaseOrderLine, 
        invoice: Invoice, 
        user_quantity: int | None = None, 
        edited_name: str | None = None
    ) -> bytes:
        """
        Erzeugt ein Auftragsetikett (Bestellposition) als PDF im Speicher
        und gibt es als Bytes zurück.

        Parameter
        ---------
        order : PurchaseOrder
            Die zugehörige Bestellung (z. B. Lieferant, Datum).

        component : PurchaseOrderLine
            Die gewählte Bestellposition mit Artikelnummer, Name und Menge.

        invoice : Invoice
            Die Rechnung, u. a. für die Chargennummer.

        user_quantity : int | None
            Optional vom Anwender eingegebene Menge. Wird nur angezeigt, wenn vorhanden.

        edited_name : str | None
            Optional vom Anwender veränderter Produktname.

        Rückgabe
        --------
        bytes
            Das fertige PDF-Dokument im Speicher.
        """
        buffer = io.BytesIO()
        c = self._new_canvas(buffer)

        # --- PDF Inhalt zeichnen ---
        # Y-Koordinate von oben nach unten
        y = 45 * mm  

        # Logo links oben
        self.draw_logo(c, 4 * mm, 39 * mm)
        c.setFont("Titillium", 10)

        user_quantity = str(user_quantity or "")

        # Chargennummer rechts neben Logo
        nummer = invoice.name.removeprefix("RG")
        c.drawString(56 * mm, y - 2 * mm, f"Chargennummer   {nummer}")

        # Bezeichnung (zentriert in Box)
        y -= 30 * mm
        name_to_print = edited_name or component.name
        self.draw_paragraph(
            c, name_to_print,
            x=5 * mm, y=y,
            w=90 * mm, h=30 * mm,
            style="header"
        )

        # Artikelnummer
        y -= 4 * mm
        # c.drawString(35 * mm, y, f"{component.default_code}")
        self.draw_paragraph(
            c, component.default_code,
            x=5 * mm, y=y,
            w=90 * mm, h=15 * mm,
            style="header"
        )

        # Menge
        y -= 3 * mm
        if user_quantity.isdigit():
            c.setFont("Titillium", 7)
            quantity_sting = f"Stück {user_quantity} / {int(getattr(component, 'quantity', 0) or 0)}"
        else:
            quantity_sting = f"Stück   {int(component.quantity)}"
            
        c.drawString(5 * mm, y, quantity_sting)

        # QR-Code
        qr_img = self.generate_qr_code(f"{component.default_code or ''}-{invoice.name}")
        c.drawImage(qr_img, 80 * mm, y - 6 * mm, width=18 * mm, height=18 * mm)

        # Lieferant nebeneinander
        y -= 5 * mm
        c.drawString(5 * mm, y, f"Lieferant   {order.partner_name}")
        
        # Speichern
        c.save()

        pdf_bytes = buffer.getvalue()
        buffer.close()

        return pdf_bytes
# ----------------------------------------------------------------------------
    def create_product_label_pdf(
        self, 
        product: ManufacturingOrder, 
        user_quantity: int | None = None, 
        edited_name: str | None = None
    ) -> bytes:
        """
        Erzeugt ein Produktetikett als PDF im Speicher und gibt es als Bytes zurück.

        Parameter
        ---------
        product : ManufacturingOrder
            Das Produkt, für das das Etikett erstellt wird (z. B. Artikelnummer, LOT, UDI).
        
        user_quantity : int | None
            Vom Anwender eingegebene Menge für "Stück X / Gesamt".
            Wird nur gedruckt, wenn ein Wert vorliegt.
        
        edited_name : str | None
            Optional geänderter Produktname. Falls None, wird der Standardname verwendet.

        Rückgabe
        --------
        bytes
            Das fertige PDF-Dokument im Speicher.
        """
        buffer = io.BytesIO()
        c = self._new_canvas(buffer)
        user_quantity = str(user_quantity or "")

        # --- PDF Inhalt zeichnen ---
        # Y-Koordinate von oben nach unten
        y = 45 * mm

        # Logo links oben
        self.draw_logo(c, 91 * mm, 48 * mm, rotation=-90)

        # Bezeichnung (zentriert in Box)
        y -= 20 * mm
        name_to_print = edited_name or product.name
        self.draw_paragraph(
            c, name_to_print,
            x=5 * mm, y=y,
            w=80 * mm, h=30 * mm,
            style="header"
        )

        # Symbol-Einstellungen
        width_symbol = 15
        heigth_symbol = 9
        x_symbol = 21 * mm

        # REF
        y -= 1 * mm
        c.drawImage(self.ref_image, 4 * mm, y, width=width_symbol, height=heigth_symbol, preserveAspectRatio=True, mask='auto')
        y -= 5 * mm
        self.draw_paragraph(
            c, product.default_code,
            x=5 * mm, y=y,
            w=80 * mm, h=15 * mm,
            style="header"
        )
        c.setFont("Titillium", 7)
        
        # UDI
        y -= 2 * mm
        if product.udi:
            c.drawImage(self.udi_image, x_symbol, y, width=width_symbol, height=heigth_symbol, preserveAspectRatio=True, mask='auto')
            c.drawString(x_symbol + 6 * mm, y + 1 * mm, f"{product.udi}")

        # LOT
        y -= 5 * mm
        c.drawImage(self.lot_image, x_symbol, y, width=width_symbol, height=heigth_symbol, preserveAspectRatio=True, mask='auto')
        lot = getattr(product, "lot_producing_id", None)
        c.drawString(x_symbol + 6 * mm, y + 0.5 * mm, f"{lot[1]}" if lot else "")

        # QR-Code
        x_qr = 3 * mm
        production_date = datetime.strptime(product.date_start, "%Y-%m-%d").strftime("%Y/%m") if getattr(product, "date_start", None) else ""
        qr_string = (
            (f"(01){product.udi}" if getattr(product, "udi", None) else "") +
            (f"(10){product.lot_producing_id[1]}" if getattr(product, "lot_producing_id", None) else "") +
            (f"(11){production_date}" if production_date != "" else "")
        ) or "NO DATA"

        qr_img = self.generate_qr_code(qr_string)
        c.drawImage(qr_img, x_qr, y - 7 * mm, width=16 * mm, height=16 * mm)
        c.drawString(x_qr + 1 * mm, y - 10 * mm, f"{qr_string}")

        # MD, Instruction, single patient, CE, production date
        y -= 5 * mm
        x_symbol_row = 0
        if product.medical_device:
            c.drawImage(self.md_image, x_symbol, y, width=width_symbol, height=heigth_symbol, preserveAspectRatio=True, mask='auto')
            x_symbol_row += 7 * mm
        if product.user_manual:
            c.drawImage(self.instruction_image, x_symbol + x_symbol_row, y - 0.5 * mm, width=11, height=11, preserveAspectRatio=True, mask='auto')
            x_symbol_row += 5 * mm
        if product.single_use:
            c.drawImage(self.single_patient_image, x_symbol + x_symbol_row, y - 0.5 * mm, width=11, height=11, preserveAspectRatio=True, mask='auto')
            x_symbol_row += 5 * mm
        if product.ce:
            c.drawImage(self.ce_image, x_symbol + x_symbol_row, y, width=10, height=10, preserveAspectRatio=True, mask='auto')
            x_symbol_row += 5 * mm
        c.drawImage(self.production_date_image, x_symbol + x_symbol_row + 2 * mm, y + 1 * mm, width=8, height=8, preserveAspectRatio=True, mask='auto')
        c.setFont("Titillium", 5)
        c.drawString(x_symbol + x_symbol_row, y - 0.5 * mm, production_date)
        x_symbol_row += 8 * mm

        # Stückzahl
        if user_quantity.isdigit():
            c.setFont("Titillium", 7)
            c.drawString(x_symbol + x_symbol_row, y + 1 * mm, f"Stück {user_quantity} / {int(getattr(product, 'quantity', 0) or 0)}")

        # Kontaktdaten
        x_contact = 70 * mm
        y_contact = 14 * mm
        c.setFont("Titillium", 7)
        c.drawString(x_contact, y_contact, self.address_lines[0])
        c.drawString(x_contact, y_contact - 3 * mm, self.address_lines[1])
        c.drawString(x_contact, y_contact - 6 * mm, self.address_lines[2])
        c.drawString(x_contact, y_contact - 9 * mm, self.address_lines[3])
        c.drawString(x_contact, y_contact - 12 * mm, self.address_lines[4])
        
        # Speichern
        c.save()

        pdf_bytes = buffer.getvalue()
        buffer.close()

        return pdf_bytes
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
        c.drawImage(self.logo, 0, 0, width=8 * mm, height=8 * mm, preserveAspectRatio=True)

        # Text daneben
        c.setFont("Titillium", 8)
        c.drawString(9 * mm, 4 * mm, "CHW-Technik")
        c.setFont("Titillium", 5)
        c.drawString(9 * mm, 2 * mm, "OT-Produkte GmbH")

        # Zustand zurücksetzen
        c.restoreState()
# ----------------------------------------------------------------------------
    def draw_paragraph(self, c, text: str, x: float, y: float, w: float, h: float, style: str = "header"):
        """Hilfsmethode: zeichnet Text vertikal zentriert in eine Box."""
        # Sonderzeichen wie & oder < würden sonst den Paragraph-Parser abbrechen lassen.
        para = Paragraph(escape(str(text or "")), self.styles[style])
        w_used, h_used = para.wrap(w, h)
        para.drawOn(c, x, y + (h - h_used) / 2)
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
# region QR
# ----------------------------------------------------------------------------
    def generate_qr_pil(self,data: str, size: int = 150) -> Image.Image:
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
    def get_printers(self) -> list[dict]:
        """
        Gibt eine Liste der verfügbaren Drucker mit ID und Namen zurück.
        """
        # Ohne API-Key gibt es keine Drucker (sonst 401 von PrintNode).
        if not self.api_key:
            return []

        response = requests.get(
            f"{PRINTNODE_URL}/printers",
            auth=(self.api_key, ''),
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()  # Fehler werfen, falls HTTP-Fehler

        printers = response.json()
        return [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "description": p.get("description"),
                "computer": p.get("computer", {}).get("name")
            }
            for p in printers
        ]

# ----------------------------------------------------------------------------
    def send_pdf_to_printnode(self, pdf_bytes, title="Etikett", copies: int = 1):
        """
        Sendet ein PDF an PrintNode über die API.
        copies: Anzahl der Kopien (ein einziger Druckauftrag mit 'qty').
        Wirft bei einem Fehler eine Exception mit verständlicher Meldung.
        """
        if not self.api_key:
            raise Exception("Kein PrintNode-API-Key hinterlegt (siehe Einstellungen).")

        pdf_b64 = base64.b64encode(pdf_bytes).decode()

        try:
            response = requests.post(
                f"{PRINTNODE_URL}/printjobs",
                auth=(self.api_key, ""),
                json={
                    "printerId": self.printer_id,
                    "title": title,
                    "contentType": "pdf_base64",
                    "content": pdf_b64,
                    "qty": copies,
                    "source": "Etikett-Druck per Python"
                },
                timeout=REQUEST_TIMEOUT
            )
        except requests.exceptions.RequestException as e:
            raise Exception(f"Verbindung zu PrintNode fehlgeschlagen: {e}")

        if response.status_code != 201:
            raise Exception(f"Druckauftrag abgelehnt (Status {response.status_code}): {response.text}")

        print("✅ Etikett erfolgreich an den Drucker gesendet.")
# ----------------------------------------------------------------------------
# endregion
# ----------------------------------------------------------------------------
