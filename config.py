import os
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise EnvironmentError(
            f"Missing required environment variable: {name}\n"
            f"Copy .env.example to .env and fill in your values."
        )
    return value


def _require_int(name: str) -> int:
    return int(_require(name))


# Personal / appointment data — all required, no fallback defaults
FECHA_NACIMIENTO = _require("FECHA_NACIMIENTO")
PAIS = _require("PAIS")
LOCALIZADOR = _require("LOCALIZADOR")
CONFIRMATION_CODE = _require("CONFIRMATION_CODE")
CENTRO = _require("CENTRO")

# Scheduling
CHECK_INTERVAL_MINUTES = _require_int("CHECK_INTERVAL_MINUTES")
START_HOUR = _require_int("START_HOUR")
END_HOUR = _require_int("END_HOUR")

# DGT URLs (structural constants, not user data)
DGT_START_URL = "https://sedeclave.dgt.gob.es/WEB_CITE_CONSULTA/paginas/inicio.faces"
DGT_CATALOG_URL = "https://sedeclave.dgt.gob.es/WEB_CITE_CONSULTA/paginas/catalogo.faces"
DGT_CANJE_URL = "https://sedeclave.dgt.gob.es/WEB_CITE_CONSULTA/paginas/canjes/inicio.faces"
DGT_CITA_URL = "https://sedeclave.dgt.gob.es/WEB_CITE_CONSULTA/paginas/cita.faces"
CLAVE_DOMAIN = "pasarela.clave.gob.es"
DGT_DOMAIN = "sedeclave.dgt.gob.es"
