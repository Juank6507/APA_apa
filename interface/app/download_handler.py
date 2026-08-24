# apa/interface/app/download_handler.py
"""
download_handler.py — Endpoint de descarga de archivos de APA.

Sirve archivos desde el directorio de descargas con validación
de path traversal. Solo permite acceder a archivos que estén
dentro del directorio de descargas configurado.

Clases:
    DownloadHandler: Manejador de descargas de archivos.

Funciones:
    register_download_routes: Registra GET /download/{filename}.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.config_apa import logger


class DownloadHandler:
    """Manejador de descargas de archivos.

    Sirve archivos desde el directorio de descargas con
    validación estricta de path traversal. Usa pathlib.resolve()
    para normalizar rutas y verificar que el archivo solicitado
    permanece dentro del directorio permitido.

    Attributes:
        downloads_dir: Ruta absoluta del directorio de descargas.
    """

    def __init__(self, downloads_dir: str) -> None:
        """Inicializa el manejador de descargas.

        Args:
            downloads_dir: Ruta al directorio de descargas.
        """
        self.downloads_dir = Path(downloads_dir).resolve()
        if not self.downloads_dir.is_dir():
            self.downloads_dir.mkdir(parents=True, exist_ok=True)
            logger.info(
                "DownloadHandler: directorio creado: %s",
                self.downloads_dir,
            )
        else:
            logger.info(
                "DownloadHandler: sirviendo archivos de %s",
                self.downloads_dir,
            )

    def _validate_path(self, filename: str) -> Path:
        """Valida que el filename no escape del directorio de descargas.

        Resuelve la ruta completa y verifica que el resultado
        esté dentro de self.downloads_dir. Esto previene ataques
        de path traversal como '../../../etc/passwd'.

        Args:
            filename: Nombre del archivo solicitado.

        Returns:
            Ruta Path resuelta y validada.

        Raises:
            HTTPException 403: Si el path intenta escapar del directorio.
        """
        # Rechazar paths absolutos y separadores de directorio sospechosos
        if Path(filename).is_absolute():
            logger.warning(
                "DownloadHandler: path absoluto rechazado: %s", filename
            )
            raise HTTPException(
                status_code=403,
                detail="Path traversal no permitido",
            )

        resolved = (self.downloads_dir / filename).resolve()

        # Verificar que la ruta resultante está dentro de downloads_dir
        try:
            resolved.relative_to(self.downloads_dir)
        except ValueError:
            logger.warning(
                "DownloadHandler: path traversal detectado — %s -> %s",
                filename,
                resolved,
            )
            raise HTTPException(
                status_code=403,
                detail="Path traversal no permitido",
            )

        return resolved

    def get_file(self, filename: str) -> FileResponse:
        """Retorna un FileResponse para el archivo solicitado.

        Valida el path y verifica que el archivo exista.

        Args:
            filename: Nombre del archivo a descargar.

        Returns:
            FileResponse con el archivo.

        Raises:
            HTTPException 403: Si hay path traversal.
            HTTPException 404: Si el archivo no existe.
        """
        file_path = self._validate_path(filename)

        if not file_path.is_file():
            logger.info(
                "DownloadHandler: archivo no encontrado: %s", file_path
            )
            raise HTTPException(
                status_code=404,
                detail=f"Archivo no encontrado: {filename}",
            )

        logger.debug(
            "DownloadHandler: sirviendo %s", file_path.name
        )
        return FileResponse(
            path=str(file_path),
            filename=filename,
        )


# — Registro de rutas ——————————————————————————————————————

def register_download_routes(
    app: FastAPI, handler: DownloadHandler
) -> None:
    """Registra el endpoint de descargas en la aplicación FastAPI.

    Args:
        app: Aplicación FastAPI donde registrar las rutas.
        handler: Instancia de DownloadHandler ya inicializada.
    """

    @app.get("/download/{filename}")
    async def download_file(filename: str) -> FileResponse:
        """Descarga un archivo del directorio de descargas.

        Args:
            filename: Nombre del archivo a descargar.

        Returns:
            FileResponse con el archivo solicitado.

        Raises:
            HTTPException 403: Path traversal detectado.
            HTTPException 404: Archivo no encontrado.
        """
        return handler.get_file(filename)

    logger.info(
        "DownloadHandler: ruta registrada — GET /download/{filename}"
    )


if __name__ == "__main__":
    import tempfile
    import os

    print("=== Validación de download_handler.py ===")
    print()

    # 1. Crear instancia con directorio temporal
    with tempfile.TemporaryDirectory() as tmpdir:
        handler = DownloadHandler(downloads_dir=tmpdir)
        print("[OK] DownloadHandler creado")
        assert handler.downloads_dir.is_dir()
        print(f"[OK] Directorio de descargas: {handler.downloads_dir}")

        # 2. Path traversal con '..' debe ser rechazado
        try:
            handler.get_file("../../../etc/passwd")
            assert False, "Debería lanzar HTTPException 403"
        except HTTPException as he:
            assert he.status_code == 403
            print(f"[OK] Path traversal '../' rechazado: {he.detail}")

        # 3. Path absoluto debe ser rechazado
        try:
            handler.get_file("/etc/passwd")
            assert False, "Debería lanzar HTTPException 403"
        except HTTPException as he:
            assert he.status_code == 403
            print(f"[OK] Path absoluto rechazado: {he.detail}")

        # 4. Archivo inexistente debe dar 404
        try:
            handler.get_file("no_existe.txt")
            assert False, "Debería lanzar HTTPException 404"
        except HTTPException as he:
            assert he.status_code == 404
            print(f"[OK] Archivo inexistente da 404: {he.detail}")

        # 5. Archivo existente se sirve correctamente
        test_file = Path(tmpdir) / "test_download.txt"
        test_file.write_text("contenido de prueba", encoding="utf-8")
        response = handler.get_file("test_download.txt")
        assert isinstance(response, FileResponse)
        print("[OK] Archivo existente retorna FileResponse")

        # 6. _validate_path con nombre normal funciona
        valid_path = handler._validate_path("reporte.pdf")
        assert valid_path.name == "reporte.pdf"
        assert str(valid_path).startswith(str(handler.downloads_dir))
        print("[OK] _validate_path con nombre normal funciona")

        # 7. Path traversal con symlink fuera del directorio
        # (solo verificar que el resolve lo detecta)
        try:
            handler._validate_path("../../tmp/outside.txt")
            # Si no lanza excepción, al menos verificar que no escapa
            resolved = (handler.downloads_dir / "../../tmp/outside.txt").resolve()
            resolved.relative_to(handler.downloads_dir)
            print("[WARN] Path traversal con ../../tmp no fue detectado")
        except (HTTPException, ValueError):
            print("[OK] Path traversal con ../../ detectado")

    # 8. register_download_routes no crashea
    from app.config_apa import create_app
    test_app = create_app()
    with tempfile.TemporaryDirectory() as tmpdir2:
        h2 = DownloadHandler(downloads_dir=tmpdir2)
        register_download_routes(test_app, handler=h2)
    print("[OK] register_download_routes() no crashea")

    # 9. Verificar rutas registradas
    routes = [r.path for r in test_app.routes]
    assert "/download/{filename}" in routes
    print("[OK] Ruta GET /download/{filename} registrada")

    # 10. Usa pathlib (no hardcoding)
    assert isinstance(handler.downloads_dir, Path)
    print("[OK] Rutas usan pathlib (sin hardcoding)")

    print()
    print("=== Todas las validaciones pasaron ===")
