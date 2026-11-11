import copy
import json
import os

try:
    import keyring
    import keyring.backends.fail
    from keyring.errors import PasswordDeleteError
except ImportError:  # Paket nicht installiert → Zugangsdaten bleiben in der config.json
    keyring = None

# Immer neben dem Programm speichern, unabhängig vom aktuellen Arbeitsverzeichnis.
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# Zugangsdaten liegen im Windows-Anmeldeinformationsspeicher, nicht in der config.json.
KEYRING_SERVICE = "Odoo-Produktetikett"
# (Abschnitt, Schlüssel) in den Einstellungen → Name des Eintrags im Anmeldeinformationsspeicher
SECRET_FIELDS = {
    ("odoo", "password"): "odoo_api_key",
    ("printnode", "api_key"): "printnode_api_key",
}

# Standard-Etikettenformat (Breite x Höhe in mm) und erlaubter Bereich
DEFAULT_LABEL_WIDTH_MM = 100
DEFAULT_LABEL_HEIGHT_MM = 50
MIN_LABEL_SIZE_MM = 20
MAX_LABEL_SIZE_MM = 300

class SettingsManager:
    def __init__(self):
        self.config_file = CONFIG_FILE
        self._keyring_ok = self._check_keyring()
        self._in_keyring: set[str] = set()  # Einträge, die tatsächlich im Speicher liegen
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
                "address_lines": ["", "", "", "", ""],
                "width_mm": DEFAULT_LABEL_WIDTH_MM,
                "height_mm": DEFAULT_LABEL_HEIGHT_MM
            },
            "window": {
                "geometry": "",
                "maximized": False
            }
        }
        self.load_settings()
# ----------------------------------------------------------------------------
# region Sichere Ablage der Zugangsdaten
# ----------------------------------------------------------------------------
    @staticmethod
    def _check_keyring() -> bool:
        """True, wenn ein echter Anmeldeinformationsspeicher verfügbar ist."""
        if keyring is None:
            return False
        try:
            return not isinstance(keyring.get_keyring(), keyring.backends.fail.Keyring)
        except Exception:
            return False
# ----------------------------------------------------------------------------
    @property
    def secure_storage(self) -> bool:
        """True, wenn Zugangsdaten verschlüsselt (nicht in der config.json) gespeichert werden."""
        return self._keyring_ok
# ----------------------------------------------------------------------------
    def _secret_get(self, name: str) -> str:
        if not self._keyring_ok:
            return ""
        try:
            return keyring.get_password(KEYRING_SERVICE, name) or ""
        except Exception as e:
            print(f"⚠️ Zugangsdaten konnten nicht gelesen werden: {e}")
            return ""
# ----------------------------------------------------------------------------
    def _secret_set(self, name: str, value: str) -> bool:
        """Speichert (oder löscht bei leerem Wert) einen Eintrag. True bei Erfolg."""
        if not self._keyring_ok:
            return False
        try:
            if value:
                keyring.set_password(KEYRING_SERVICE, name, value)
                self._in_keyring.add(name)
            else:
                try:
                    keyring.delete_password(KEYRING_SERVICE, name)
                except PasswordDeleteError:
                    pass  # war nicht vorhanden
                self._in_keyring.discard(name)
            return True
        except Exception as e:
            print(f"⚠️ Zugangsdaten konnten nicht sicher gespeichert werden (sie bleiben in der config.json): {e}")
            return False
# ----------------------------------------------------------------------------
    def _load_secrets(self):
        """
        Holt die Zugangsdaten aus dem Anmeldeinformationsspeicher. Stehen sie noch
        im Klartext in der config.json (ältere Version), werden sie dorthin
        übernommen und aus der Datei entfernt.
        """
        migrated = False
        for (section, key), name in SECRET_FIELDS.items():
            value = self.settings.get(section, {}).get(key, "")
            if value:
                if self._secret_set(name, value):
                    migrated = True
            else:
                stored = self._secret_get(name)
                if stored:
                    self.settings[section][key] = stored
                    self._in_keyring.add(name)
        if migrated:
            self._write_file()
            print("🔒 Zugangsdaten wurden in den Windows-Anmeldeinformationsspeicher verschoben.")
# ----------------------------------------------------------------------------
# endregion
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

        self._load_secrets()
# ----------------------------------------------------------------------------
    def _write_file(self):
        """Schreibt die config.json; im Anmeldeinformationsspeicher abgelegte Werte bleiben draußen."""
        data = copy.deepcopy(self.settings)
        for (section, key), name in SECRET_FIELDS.items():
            if name in self._in_keyring:
                data[section][key] = ""
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
# ----------------------------------------------------------------------------
    def save_settings(self, section, new_data):
        """Speichert ein einzelnes Einstellungs-Segment."""
        self.settings[section] = new_data
        for (secret_section, key), name in SECRET_FIELDS.items():
            if secret_section == section:
                self._secret_set(name, new_data.get(key, ""))
        self._write_file()
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

    def get_window_settings(self):
        return self.settings["window"]
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

    def update_label_settings(self, pdf_path, address_lines,
                              width_mm=DEFAULT_LABEL_WIDTH_MM, height_mm=DEFAULT_LABEL_HEIGHT_MM):
        for name, value in (("Breite", width_mm), ("Höhe", height_mm)):
            if not MIN_LABEL_SIZE_MM <= value <= MAX_LABEL_SIZE_MM:
                raise ValueError(
                    f"Etikett-{name} muss zwischen {MIN_LABEL_SIZE_MM} und {MAX_LABEL_SIZE_MM} mm liegen."
                )
        self.save_settings("label_settings", {
            "pdf_path": pdf_path,
            "address_lines": address_lines,
            "width_mm": width_mm,
            "height_mm": height_mm
        })

    def update_window_settings(self, geometry: str, maximized: bool):
        self.save_settings("window", {
            "geometry": geometry,
            "maximized": maximized
        })
# ----------------------------------------------------------------------------
