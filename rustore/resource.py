import os
import sys

def app_dir() -> str:
    """
    Папка, где лежит app.exe (в onefile PyInstaller) или текущий проект.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(".")

def resource_path(relative_path: str) -> str:
    """
    Путь к ресурсу внутри onefile сборки (sys._MEIPASS) или в проекте.
    """
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)

def external_or_embedded(relative_path: str) -> str:
    """
    1) Сначала ищем внешний файл рядом с exe/проектом
    2) Если нет — берем встроенный (MEIPASS)
    """
    ext = os.path.join(app_dir(), relative_path)
    if os.path.exists(ext):
        return ext
    return resource_path(relative_path)