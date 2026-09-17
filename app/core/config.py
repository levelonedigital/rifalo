import os


class Configuracion:
    """Configuracion central de RIFALO.

    Los valores que dependen del entorno (como la base de datos)
    se leen de variables de entorno. Los demas quedan fijos aca.
    """

    # Identidad del sistema
    NOMBRE_APP = "RIFALO"
    VERSION = "0.1.0"

    # Zona horaria oficial del sistema (horario de Buenos Aires)
    ZONA_HORARIA = "America/Argentina/Buenos_Aires"

    # Fuente oficial de resultados de la quiniela de Tucuman
    URL_QUINIELA = "https://resultadosquiniela.cajapopular.gov.ar/"

    # Tiempo maximo de reintentos de lectura de resultados (en minutos)
    REINTENTOS_RESULTADOS_MINUTOS = 5

    # Retencion de backups en Google Drive (en dias)
    BACKUP_RETENCION_DIAS = 30

    # Base de datos: en Railway usa la variable DATABASE_URL.
    # Si no existe (pruebas locales), usa una base SQLite temporal.
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///rifalo_local.db")

    # Clave secreta para sesiones y seguridad.
    # En Railway se configura como variable de entorno propia.
    SECRET_KEY = os.getenv("SECRET_KEY", "clave-de-desarrollo-cambiar-en-produccion")