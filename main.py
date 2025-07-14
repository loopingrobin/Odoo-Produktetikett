# https://pypi.org/project/odoo-api-wrapper/
# https://api.printnode.com/app/apikeys
# main.py
from ui.app import EtikettApp

# Globale App-Version
APP_VERSION = "v1.0.1"

if __name__ == "__main__":
    app = EtikettApp(app_version=APP_VERSION)
    app.mainloop()
