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
            }
        }
        self.load_settings()
# ----------------------------------------------------------------------------  
    def load_settings(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self.settings.update(json.load(f))
            except Exception as e:
                print(f"⚠️ Fehler beim Laden der Einstellungen: {e}")
        else:
            print("⚠️ Keine vorhandene Konfigurationsdatei gefunden – Standardwerte werden verwendet.")
# ----------------------------------------------------------------------------  
    def save_settings(self, section, new_data):
        if self.settings.get(section) != new_data:
            self.settings[section] = new_data
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4)
# ----------------------------------------------------------------------------  
    def get_odoo_settings(self):
        return self.settings.get("odoo", {})
# ----------------------------------------------------------------------------  
    def get_printnode_settings(self):
        return self.settings.get("printnode", {})
# ----------------------------------------------------------------------------  
    def update_odoo_settings(self, url, db, username, password):
        if not url.startswith("http://") and not url.startswith("https://"):
            raise ValueError("Odoo-URL muss mit http:// oder https:// beginnen.")
        
        new_data = {
            "url": url,
            "db": db,
            "username": username,
            "password": password
        }
        return self.save_settings("odoo", new_data)
# ----------------------------------------------------------------------------  
    def update_printnode_settings(self, api_key):
        new_data = {
            "api_key": api_key
        }
        return self.save_settings("printnode", new_data)
# ----------------------------------------------------------------------------  
