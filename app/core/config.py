import os


class Configuracion:
    """Configuracion central de RIFALO."""

    # Identidad del sistema
    NOMBRE_APP = "RIFALO"
    VERSION = "0.3.0"

    # Zona horaria oficial del sistema (horario de Buenos Aires)
    ZONA_HORARIA = "America/Argentina/Buenos_Aires"

    # Fuente oficial de resultados de la quiniela de Tucuman
    URL_QUINIELA = "https://resultadosquiniela.cajapopular.gov.ar/"

    # Tiempo maximo de reintentos de lectura de resultados (en minutos)
    REINTENTOS_RESULTADOS_MINUTOS = 5

    # Retencion de backups en Google Drive (en dias)
    BACKUP_RETENCION_DIAS = 30

    # Reglas de pago del modulo clasico: multiplicador del pleno al numero
    PAGO_PLENO_NUMERO = 70.0

    # Base de datos
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///rifalo_local.db")

    # Clave secreta para sesiones y seguridad
    SECRET_KEY = os.getenv("SECRET_KEY", "clave-de-desarrollo-cambiar-en-produccion")

    # Admin inicial: se crea solo si la base esta vacia
    ADMIN_INICIAL_USUARIO = os.getenv("ADMIN_INICIAL_USUARIO", "admin")
    ADMIN_INICIAL_PASSWORD = os.getenv("ADMIN_INICIAL_PASSWORD", "Rifalo2026!")
