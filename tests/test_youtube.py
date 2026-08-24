# apa/tests/test_youtube.py
import os, sys, tempfile, logging, shutil, subprocess, importlib.util
from pathlib import Path

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

try:
    from apa.core.orchestrator import Orchestrator
except ImportError as e:
    logger.critical("Fallo critico al importar 'Orchestrator': %s", e)
    logger.critical("Rutas en sys.path: %s", sys.path)
    logger.critical("Verifica que 'apa/core/orchestrator.py' exista en %s", _PROJECT_ROOT)
    sys.exit(1)

SPEC = """\
# Desktop Application: YouTube Playlist to PDF
## Description
Create a modern desktop application using `tkinter` that allows users to extract transcripts from YouTube playlist videos and export them to a PDF document.

## User Interface (tkinter)
- **Text input field 1:** YouTube playlist URL.
- **Text field 2 (ScrolledText):** Logs/status area and transcript preview.
- **Button 1:** "Load Playlist" (Validates URL and lists videos).
- **Button 2:** "Start Transcription" (Starts process and updates UI in real-time).
- **Button 3:** "Clear" (Clears fields and logs).
- **Button 4:** "Download PDF" (Generates and saves the PDF).

## Backend Logic
- Use `pytube` to extract metadata and video links from the playlist.
- Use `youtube-transcript-api` to obtain transcripts for each video.
- Use `fpdf` to generate a structured PDF with title, video, and transcribed text.
- Robust exception handling for videos without transcripts or network errors.
- Real-time UI updates using `self.after()` or `queue` to avoid blocking tkinter's main thread.

## Technical Requirements
- Clean, commented, and modularized code.
- Python 3.8+ compatibility.
- Correct handling of relative and absolute paths.
"""

def check_dependencies():
    deps = {"pytube": "pytube", "youtube-transcript-api": "youtube_transcript_api", "fpdf": "fpdf", "PyInstaller": "PyInstaller"}
    missing = [n for n, imp in deps.items() if importlib.util.find_spec(imp) is None]
    if missing:
        logger.warning("Missing dependencies: %s. Generation will continue, but execution will require installing them.", ", ".join(missing))
    return missing

def run_youtube_test(output_dir: str = None):
    if output_dir is None:
        output_dir = os.path.join("C:", "APA_Proyectos", "YouTubeTranscriptor") if sys.platform == "win32" else os.path.expanduser("~/APA_Proyectos/YouTubeTranscriptor")
    os.makedirs(output_dir, exist_ok=True)
    logger.info("Output directory: %s", output_dir)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as spec_file:
        spec_file.write(SPEC)
        spec_path = spec_file.name
        logger.info("Temporary spec created at: %s", spec_path)
    try:
        logger.info("Initializing Orchestrator...")
        orchestrator = Orchestrator()
        logger.info("Starting project generation... This may take several minutes.")
        logger.info("========================================")
        result = orchestrator.run(spec_path)
        logger.info("========================================")
        if isinstance(result, dict) and not result.get('success', True):
            logger.error("Orchestrator failed: %s", result.get('error', 'Unknown error'))
            return
        logger.info("Generation completed successfully.")
        project_id = result.get('project_id') if isinstance(result, dict) else None
        if project_id:
            # CORRECCIÓN: Usar _PROJECT_ROOT para construir la ruta correcta a specs/
            specs_dir = Path(_PROJECT_ROOT) / "specs" / project_id
            if specs_dir.exists():
                shutil.copytree(specs_dir, output_dir, dirs_exist_ok=True)
                logger.info("✅ Proyecto copiado a: %s", output_dir)
            else:
                logger.warning("❌ Project directory not found at %s", specs_dir)
                logger.warning("Buscando en directorios alternativos...")
                alt_dir = Path(_PROJECT_ROOT) / "apa" / "specs" / project_id
                if alt_dir.exists():
                    shutil.copytree(alt_dir, output_dir, dirs_exist_ok=True)
                    logger.info("✅ Proyecto copiado desde ruta alternativa: %s", output_dir)
                else:
                    logger.error("No se encontró el proyecto en ninguna ruta conocida.")
                    return
        else:
            logger.warning("Could not obtain project_id from result.")
        logger.info("Checking PyInstaller availability for compilation...")
        if importlib.util.find_spec("PyInstaller") is not None or shutil.which("pyinstaller"):
            try:
                logger.info("Compiling executable with PyInstaller...")
                main_script = os.path.join(output_dir, "main.py")
                if os.path.exists(main_script):
                    r = subprocess.run([sys.executable, "-m", "PyInstaller", "--onefile", "--noconsole", main_script], cwd=output_dir, capture_output=True, text=True)
                    if r.returncode == 0:
                        logger.info("Executable compiled successfully in %s/dist/", output_dir)
                    else:
                        logger.warning("PyInstaller failed. Error: %s", r.stderr)
                else:
                    logger.warning("main.py not found in generated directory.")
            except Exception as e:
                logger.warning("Error during PyInstaller compilation: %s", e)
        else:
            logger.info("PyInstaller not installed. To compile manually: cd %s && pip install pyinstaller && pyinstaller --onefile main.py", output_dir)
    except Exception as e:
        logger.error("Error during test execution: %s", e, exc_info=True)
        raise
    finally:
        if os.path.exists(spec_path):
            os.remove(spec_path)
            logger.info("Temporary file removed.")
    logger.info("SUMMARY: Project generated successfully at: %s", output_dir)
    logger.info("Directory NOT deleted for inspection or later execution.")

if __name__ == "__main__":
    check_dependencies()
    logger.info("Starting YouTube -> PDF generation test...")
    run_youtube_test()
    logger.info("Test finished.")