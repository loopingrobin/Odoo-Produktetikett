import json
import os

CONFIG_FILE = "config.json"

class SettingsManager:
    def __init__(self):
        self.config_file = CONFIG_FILE
        self.settings = {
            "odoo": {
                "url": "",
                "db": "",
                "username": "",
                "password": ""
            },
            "printnode": {
                "api_key": ""
            },
            "printer": {
                "last_printer_id": None,
                "save_pdf": False
            },
            "label_settings": {
                "pdf_path": "",
                "address_lines": ["", "", "", "", ""]
            }
        }
        self.load_settings()
# ----------------------------------------------------------------------------  
    def load_settings(self):
        """Lädt config.json, ergänzt fehlende Felder automatisch."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    file_data = json.load(f)

                    # Bestehende Werte einfügen, fehlende ergänzen
                    for key, default_value in self.settings.items():
                        if key not in file_data:
                            file_data[key] = default_value
                        else:
                            # auch Unterschlüssel prüfen
                            for sub_key, sub_default in default_value.items():
                                if sub_key not in file_data[key]:
                                    file_data[key][sub_key] = sub_default

                    self.settings = file_data

            except Exception as e:
                print(f"⚠️ Fehler beim Laden der Einstellungen: {e}")
        else:
            print("⚠️ Keine vorhandene Konfigurationsdatei gefunden – Standardwerte werden verwendet.")
# ----------------------------------------------------------------------------  
    def save_settings(self, section, new_data):
        """Speichert ein einzelnes Einstellungs-Segment."""
        self.settings[section] = new_data
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=4)
# ----------------------------------------------------------------------------  
# Getter
    def get_odoo_settings(self):
        return self.settings["odoo"]

    def get_printnode_settings(self):
        return self.settings["printnode"]

    def get_printer_settings(self):
        return self.settings["printer"]

    def get_label_settings(self):
        return self.settings["label_settings"]
# ----------------------------------------------------------------------------  
# Setter / Updates
    def update_odoo_settings(self, url, db, username, password):
        if not url.startswith("http://") and not url.startswith("https://"):
            raise ValueError("Odoo-URL muss mit http:// oder https:// beginnen.")
        
        self.save_settings("odoo", {
            "url": url,
            "db": db,
            "username": username,
            "password": password
        })
        
    def update_printnode_settings(self, api_key):
        self.save_settings("printnode", {"api_key": api_key})

    def update_printer_settings(self, last_printer_id, save_pdf):
        self.save_settings("printer", {
            "last_printer_id": last_printer_id,
            "save_pdf": save_pdf
        })

    def update_label_settings(self, pdf_path, address_lines):
        self.save_settings("label_settings", {
            "pdf_path": pdf_path,
            "address_lines": address_lines
        })
# ----------------------------------------------------------------------------  
