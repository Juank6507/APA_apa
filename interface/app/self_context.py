# apa/interface/app/self_context.py
"""
self_context.py — Cargador de autoconocimiento de APA.

Lee los archivos BITACORA.md y WHITEPAPER.md del directorio de
documentación para proporcionar contexto de autoconocimiento al
motor de chat. Cachea el resultado tras la primera carga.

Clases:
    SelfContextLoader: Cargador y cache de autoconocimiento.

Funciones:
    register_self_context_routes: No registra rutas (servicio interno).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import Optional

from fastapi import FastAPI

from app.config_apa import logger


# ── Archivos de autoconocimiento ─────────────────────────────────────────

BITACORA_FILENAME: str = "BITACORA.md"
WHITEPAPER_FILENAME: str = "WHITEPAPER.md"


class SelfContextLoader:
    """Cargador de contexto de autoconocimiento de APA.

    Lee BITACORA.md y WHITEPAPER.md del directorio especificado,
    concatena su contenido y lo cachea en memoria. Este contexto
    se inyecta en los prompts del chat para que APA conozca
    su propia historia y capacidades.

    Attributes:
        docs_dir: Ruta al directorio de documentación.
        _cached_content: Contenido cacheado tras primera carga.
    """

    def __init__(self, docs_dir: str) -> None:
        """Inicializa el cargador con la ruta al directorio de docs.

        Args:
            docs_dir: Ruta al directorio que contiene BITACORA.md
                      y WHITEPAPER.md. Puede ser string o Path.
        """
        self.docs_dir = Path(docs_dir)
        self._cached_content: Optional[str] = None
        logger.info("SelfContextLoader: docs_dir=%s", self.docs_dir)

    def load(self) -> str:
        """Lee y concatena BITACORA.md y WHITEPAPER.md.

        Lee ambos archivos del directorio configurado, los concatena
        con separadores claros y cachea el resultado. Si un archivo
        no existe o hay errores de codificación, se omite graciosa-
        mente incluyendo un marcador en el contenido.

        Returns:
            Contenido concatenado de ambos archivos, o string vacío
            si ninguno se pudo leer.
        """
        parts: list = []

        # Leer BITACORA.md
        bitacora_path = self.docs_dir / BITACORA_FILENAME
        bitacora_content = self._read_file_safe(bitacora_path, "BITACORA")
        if bitacora_content:
            parts.append(f"# BITACORA\n\n{bitacora_content}")

        # Leer WHITEPAPER.md
        whitepaper_path = self.docs_dir / WHITEPAPER_FILENAME
        whitepaper_content = self._read_file_safe(whitepaper_path, "WHITEPAPER")
        if whitepaper_content:
            parts.append(f"# WHITEPAPER\n\n{whitepaper_content}")

        # Concatenar con separador
        content = "\n\n---\n\n".join(parts) if parts else ""

        # Cachear resultado
        self._cached_content = content

        loaded_files = []
        if bitacora_content:
            loaded_files.append(BITACORA_FILENAME)
        if whitepaper_content:
            loaded_files.append(WHITEPAPER_FILENAME)
        logger.info(
            "SelfContextLoader: cargados %d archivos: %s",
            len(loaded_files),
            loaded_files,
        )

        return content

    def get_context(self) -> str:
        """Retorna el contenido cacheado.

        Si aún no se ha cargado, retorna string vacío.
        Para forzar una recarga, usar reload().

        Returns:
            Contenido cacheado o string vacío.
        """
        return self._cached_content or ""

    def reload(self) -> str:
        """Fuerza una re-lectura de los archivos de documentación.

        Limpia el cache y vuelve a leer BITACORA.md y WHITEPAPER.md.

        Returns:
            Contenido recargado.
        """
        self._cached_content = None
        return self.load()

    # ── Interno ───────────────────────────────────────────────────────

    @staticmethod
    def _read_file_safe(file_path: Path, label: str) -> Optional[str]:
        """Lee un archivo de texto de forma segura.

        Maneja FileNotFoundError y errores de codificación de
        forma graciosa, retornando None en lugar de lanzar.

        Args:
            file_path: Ruta al archivo a leer.
            label: Nombre descriptivo para los logs.

        Returns:
            Contenido del archivo como string, o None si falla.
        """
        if not file_path.exists():
            logger.debug("SelfContextLoader: %s no encontrado: %s", label, file_path)
            return None

        try:
            return file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            logger.warning(
                "SelfContextLoader: error de codificación en %s: %s",
                label, file_path,
            )
            # Intentar con latin-1 como fallback
            try:
                return file_path.read_text(encoding="latin-1")
            except Exception as exc:
                logger.error(
                    "SelfContextLoader: no se pudo leer %s: %s", label, exc
                )
                return None
        except Exception as exc:
            logger.error(
                "SelfContextLoader: error leyendo %s: %s", label, exc
            )
            return None


# ── Registro de rutas (servicio interno, sin rutas) ─────────────────────

def register_self_context_routes(app: FastAPI, loader: SelfContextLoader) -> None:
    """No registra rutas — este es un servicio interno.

    El contexto de autoconocimiento se usa desde ChatEngine, no
    directamente como endpoint HTTP.

    Args:
        app: Aplicación FastAPI (no se modifica).
        loader: Instancia de SelfContextLoader (no se usa en rutas).
    """
    logger.debug("SelfContextLoader: servicio interno, sin rutas HTTP")


if __name__ == "__main__":
    import tempfile
    import os

    print("=== Validación de self_context.py ===")
    print()

    # 1. Crear instancia
    with tempfile.TemporaryDirectory() as tmpdir:
        loader = SelfContextLoader(docs_dir=tmpdir)
        print(f"[OK] SelfContextLoader creado, docs_dir={loader.docs_dir}")

        # 2. load() sin archivos retorna string vacío
        content = loader.load()
        assert content == "", f"Sin archivos debería retornar vacío, got: '{content}'"
        print("[OK] load() sin archivos retorna string vacío")

        # 3. get_context() sin carga previa retorna string vacío
        loader2 = SelfContextLoader(docs_dir=tmpdir)
        assert loader2.get_context() == ""
        print("[OK] get_context() sin carga previa retorna string vacío")

        # 4. Crear BITACORA.md
        bitacora_path = Path(tmpdir) / BITACORA_FILENAME
        bitacora_path.write_text("# Bitácora de APA\n\nContenido de prueba.", encoding="utf-8")

        # 5. Crear WHITEPAPER.md
        whitepaper_path = Path(tmpdir) / WHITEPAPER_FILENAME
        whitepaper_path.write_text("# Whitepaper de APA\n\nDescripción del sistema.", encoding="utf-8")

        # 6. load() lee ambos archivos
        content = loader.load()
        assert "Bitácora de APA" in content
        assert "Whitepaper de APA" in content
        assert "# BITACORA" in content
        assert "# WHITEPAPER" in content
        assert "---" in content  # Separador
        print("[OK] load() lee y concatena ambos archivos correctamente")

        # 7. get_context() retorna contenido cacheado
        cached = loader.get_context()
        assert cached == content
        assert "Bitácora de APA" in cached
        print("[OK] get_context() retorna contenido cacheado")

        # 8. reload() fuerza re-lectura
        bitacora_path.write_text("# Bitácora actualizada\n\nNuevo contenido.", encoding="utf-8")
        reloaded = loader.reload()
        assert "Bitácora actualizada" in reloaded
        assert "Nuevo contenido" in reloaded
        print("[OK] reload() fuerza re-lectura con contenido actualizado")

        # 9. Solo un archivo existe
        with tempfile.TemporaryDirectory() as tmpdir2:
            loader3 = SelfContextLoader(docs_dir=tmpdir2)
            solo_path = Path(tmpdir2) / BITACORA_FILENAME
            solo_path.write_text("Solo bitácora", encoding="utf-8")
            content3 = loader3.load()
            assert "Solo bitácora" in content3
            assert "WHITEPAPER" not in content3
            print("[OK] Con un solo archivo, no incluye sección del otro")

        # 10. Archivo con encoding incorrecto
        with tempfile.TemporaryDirectory() as tmpdir3:
            loader4 = SelfContextLoader(docs_dir=tmpdir3)
            bad_path = Path(tmpdir3) / BITACORA_FILENAME
            # Escribir bytes inválidos para UTF-8
            bad_path.write_bytes(b"\xff\xfe Contenido binario")
            content4 = loader4.load()
            # No debe crashear, puede retornar vacío o latin-1 fallback
            assert isinstance(content4, str)
            print("[OK] Archivo con encoding incorrecto no crashea")

        # 11. register_self_context_routes no crashea
        from app.config_apa import create_app
        test_app = create_app()
        register_self_context_routes(test_app, loader)
        print("[OK] register_self_context_routes() no crashea")

    print()
    print("=== Todas las validaciones pasaron ===")
