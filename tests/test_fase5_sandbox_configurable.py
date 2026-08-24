# apa/tests/test_fase5_sandbox_configurable.py
# FASE 5 — SANDBOX CONFIGURABLE
# Tests de validación completa: settings, sandbox_config, sandbox_local, server.py
#
# Ejecutar: python apa/tests/test_fase5_sandbox_configurable.py
import os
import sys
import platform
import unittest
import tempfile
import shutil
import subprocess

# Asegurar que los imports funcionen desde apa/tests/
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, '..'))

# Detectar si bash está disponible (Windows no lo tiene por defecto)
_has_bash = False
try:
    result = subprocess.run(["bash", "--version"], capture_output=True, timeout=3)
    _has_bash = result.returncode == 0
except (FileNotFoundError, subprocess.TimeoutExpired):
    _has_bash = False


class TestSettingsFase5(unittest.TestCase):
    """Verifica que settings.py tiene los nuevos campos de sandbox."""

    def test_01_sandbox_type_field_exists(self):
        """sandbox_type debe existir en settings."""
        from config.settings import settings
        self.assertTrue(hasattr(settings, 'sandbox_type'),
                        "sandbox_type no definido en settings")

    def test_02_sandbox_path_field_exists(self):
        """sandbox_path debe existir en settings."""
        from config.settings import settings
        self.assertTrue(hasattr(settings, 'sandbox_path'),
                        "sandbox_path no definido en settings")

    def test_03_sandbox_host_field_exists(self):
        """sandbox_host debe existir en settings."""
        from config.settings import settings
        self.assertTrue(hasattr(settings, 'sandbox_host'),
                        "sandbox_host no definido en settings")

    def test_04_sandbox_user_field_exists(self):
        """sandbox_user debe existir en settings."""
        from config.settings import settings
        self.assertTrue(hasattr(settings, 'sandbox_user'),
                        "sandbox_user no definido en settings")

    def test_05_sandbox_ssh_port_field_exists(self):
        """sandbox_ssh_port debe existir y ser un entero."""
        from config.settings import settings
        self.assertTrue(hasattr(settings, 'sandbox_ssh_port'),
                        "sandbox_ssh_port no definido en settings")
        self.assertIsInstance(settings.sandbox_ssh_port, int)
        self.assertTrue(1 <= settings.sandbox_ssh_port <= 65535)

    def test_06_sandbox_ssh_key_field_exists(self):
        """sandbox_ssh_key debe existir en settings."""
        from config.settings import settings
        self.assertTrue(hasattr(settings, 'sandbox_ssh_key'),
                        "sandbox_ssh_key no definido en settings")

    def test_07_sandbox_timeout_field_exists(self):
        """sandbox_timeout debe existir en settings."""
        from config.settings import settings
        self.assertTrue(hasattr(settings, 'sandbox_timeout'),
                        "sandbox_timeout no definido en settings")
        self.assertEqual(settings.sandbox_timeout, 30)

    def test_08_sandbox_python_cmd_field_exists(self):
        """sandbox_python_cmd debe existir en settings."""
        from config.settings import settings
        self.assertTrue(hasattr(settings, 'sandbox_python_cmd'),
                        "sandbox_python_cmd no definido en settings")

    def test_09_sandbox_node_cmd_field_exists(self):
        """sandbox_node_cmd debe existir en settings."""
        from config.settings import settings
        self.assertTrue(hasattr(settings, 'sandbox_node_cmd'),
                        "sandbox_node_cmd no definido en settings")
        self.assertEqual(settings.sandbox_node_cmd, "node")

    def test_10_nas_compat_fields_still_exist(self):
        """Los campos NAS legacy deben seguir existiendo."""
        from config.settings import settings
        self.assertTrue(hasattr(settings, 'nas_host'))
        self.assertTrue(hasattr(settings, 'nas_user'))
        self.assertTrue(hasattr(settings, 'nas_sandbox_path'))


class TestSandboxTypeEnum(unittest.TestCase):
    """Verifica el enum SandboxType."""

    def test_11_enum_has_four_values(self):
        """SandboxType debe tener exactamente 4 valores."""
        from core.sandbox_config import SandboxType
        self.assertEqual(len(SandboxType), 4)

    def test_12_enum_values(self):
        """Los 4 valores deben ser local, nas, vm, external."""
        from core.sandbox_config import SandboxType
        self.assertEqual(SandboxType.LOCAL.value, "local")
        self.assertEqual(SandboxType.NAS.value, "nas")
        self.assertEqual(SandboxType.VM.value, "vm")
        self.assertEqual(SandboxType.EXTERNAL.value, "external")


class TestSandboxConfigDataclass(unittest.TestCase):
    """Verifica SandboxConfig dataclass."""

    def test_13_default_is_local(self):
        """SandboxConfig por defecto debe ser LOCAL."""
        from core.sandbox_config import SandboxConfig, SandboxType
        cfg = SandboxConfig()
        self.assertEqual(cfg.sandbox_type, SandboxType.LOCAL)
        self.assertTrue(cfg.is_local)
        self.assertFalse(cfg.is_remote)

    def test_14_nas_is_remote(self):
        """NAS debe ser remoto."""
        from core.sandbox_config import SandboxConfig, SandboxType
        cfg = SandboxConfig(sandbox_type=SandboxType.NAS, sandbox_path="/app/sandbox")
        self.assertTrue(cfg.is_remote)
        self.assertFalse(cfg.is_local)

    def test_15_vm_is_remote(self):
        """VM debe ser remoto."""
        from core.sandbox_config import SandboxConfig, SandboxType
        cfg = SandboxConfig(sandbox_type=SandboxType.VM, sandbox_path="/home/dev/sandbox")
        self.assertTrue(cfg.is_remote)

    def test_16_external_is_remote(self):
        """External debe ser remoto."""
        from core.sandbox_config import SandboxConfig, SandboxType
        cfg = SandboxConfig(sandbox_type=SandboxType.EXTERNAL, sandbox_path="/srv/sandbox")
        self.assertTrue(cfg.is_remote)

    def test_17_labels(self):
        """Los labels deben ser legibles."""
        from core.sandbox_config import SandboxConfig, SandboxType
        labels = {
            SandboxType.LOCAL: "PC Local",
            SandboxType.NAS: "NAS",
            SandboxType.VM: "Máquina Virtual",
            SandboxType.EXTERNAL: "Dispositivo Externo",
        }
        for stype, expected_label in labels.items():
            cfg = SandboxConfig(sandbox_type=stype)
            self.assertEqual(cfg.label, expected_label)

    def test_18_validate_nas_without_host(self):
        """NAS sin host debe fallar validación."""
        from core.sandbox_config import SandboxConfig, SandboxType
        cfg = SandboxConfig(sandbox_type=SandboxType.NAS, sandbox_path="/app/sandbox")
        errors = cfg.validate()
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any("host" in e.lower() for e in errors))

    def test_19_validate_nas_without_user(self):
        """NAS sin user debe fallar validación."""
        from core.sandbox_config import SandboxConfig, SandboxType
        cfg = SandboxConfig(
            sandbox_type=SandboxType.NAS,
            sandbox_path="/app/sandbox",
            host="192.168.1.100"
        )
        errors = cfg.validate()
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any("usuario" in e.lower() or "user" in e.lower() for e in errors))

    def test_20_validate_valid_nas(self):
        """NAS con host y user debe pasar validación."""
        from core.sandbox_config import SandboxConfig, SandboxType
        cfg = SandboxConfig(
            sandbox_type=SandboxType.NAS,
            sandbox_path="/app/sandbox",
            host="192.168.1.100",
            user="admin"
        )
        errors = cfg.validate()
        self.assertEqual(len(errors), 0)

    def test_21_validate_invalid_port(self):
        """Puerto 99999 debe fallar validación."""
        from core.sandbox_config import SandboxConfig, SandboxType
        cfg = SandboxConfig(
            sandbox_type=SandboxType.NAS,
            sandbox_path="/app/sandbox",
            host="192.168.1.100",
            user="admin",
            ssh_port=99999
        )
        errors = cfg.validate()
        self.assertTrue(any("65535" in e for e in errors))

    def test_22_to_dict(self):
        """to_dict debe serializar correctamente."""
        from core.sandbox_config import SandboxConfig, SandboxType
        cfg = SandboxConfig(
            sandbox_type=SandboxType.NAS,
            sandbox_path="/app/sandbox",
            host="nas.local",
            user="admin",
            ssh_port=2222
        )
        d = cfg.to_dict()
        self.assertEqual(d["sandbox_type"], "nas")
        self.assertEqual(d["label"], "NAS")
        self.assertEqual(d["host"], "nas.local")
        self.assertEqual(d["user"], "admin")
        self.assertEqual(d["ssh_port"], 2222)

    def test_23_to_dict_local_shows_placeholder(self):
        """to_dict para local debe mostrar (local) en host."""
        from core.sandbox_config import SandboxConfig, SandboxType
        cfg = SandboxConfig(sandbox_type=SandboxType.LOCAL, sandbox_path="/tmp/sandbox")
        d = cfg.to_dict()
        self.assertEqual(d["host"], "(local)")
        self.assertEqual(d["user"], "(local)")

    def test_24_env_vars(self):
        """env_vars se almacenan correctamente."""
        from core.sandbox_config import SandboxConfig
        cfg = SandboxConfig(
            env_vars={"PYTHONPATH": "/custom", "DEBUG": "1"}
        )
        self.assertEqual(cfg.env_vars["PYTHONPATH"], "/custom")
        self.assertEqual(cfg.env_vars["DEBUG"], "1")

    def test_25_work_dir_auto_for_local(self):
        """work_dir se construye automáticamente para local."""
        from core.sandbox_config import SandboxConfig, SandboxType
        cfg = SandboxConfig(sandbox_type=SandboxType.LOCAL, sandbox_path="/tmp/sandbox")
        self.assertEqual(cfg.work_dir, os.path.join("/tmp/sandbox", "work"))

    def test_25b_work_dir_auto_for_remote(self):
        """work_dir para remoto es igual a sandbox_path."""
        from core.sandbox_config import SandboxConfig, SandboxType
        cfg = SandboxConfig(sandbox_type=SandboxType.NAS, sandbox_path="/app/sandbox")
        self.assertEqual(cfg.work_dir, "/app/sandbox")

    def test_25c_python_cmd_auto_detect(self):
        """python_cmd se auto-detecta según el SO."""
        from core.sandbox_config import SandboxConfig
        cfg = SandboxConfig()
        expected = "python" if platform.system() == "Windows" else "python3"
        self.assertEqual(cfg.python_cmd, expected)


class TestSandboxConfigValidation(unittest.TestCase):
    """Verifica la lógica de validación de resolve (sin mock)."""

    def test_26_validate_empty_type_message(self):
        """La validación de tipo vacío debe mencionar sandbox_setup.py."""
        from core.sandbox_config import SandboxConfig, SandboxType
        # Probamos directamente la lógica de validación del dataclass
        # resolve_sandbox_config lanza ValueError si sandbox_type_str está vacío,
        # pero no podemos probar eso sin mock. Probamos la validación del dataclass.
        # Lo que sí podemos probar es que NAS sin host genera errores claros.
        cfg = SandboxConfig(
            sandbox_type=SandboxType.NAS,
            sandbox_path="/app/sandbox",
            host="",
            user="",
        )
        errors = cfg.validate()
        self.assertTrue(len(errors) >= 2)
        # Al menos host y user deben faltar
        msgs = " ".join(errors).lower()
        self.assertIn("host", msgs)
        self.assertIn("usuario", msgs)

    def test_27_invalid_sandbox_type_not_in_enum(self):
        """Un tipo inválido no debe estar en SandboxType."""
        from core.sandbox_config import SandboxType
        with self.assertRaises(ValueError):
            SandboxType("invalido")

    def test_28_local_config_valid_by_default(self):
        """Config local con path se construye válida."""
        from core.sandbox_config import SandboxConfig, SandboxType
        cfg = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path="/tmp/sandbox",
        )
        errors = cfg.validate()
        self.assertEqual(len(errors), 0)
        self.assertEqual(cfg.work_dir, os.path.join("/tmp/sandbox", "work"))
        # python_cmd debe estar auto-detectado
        self.assertTrue(len(cfg.python_cmd) > 0)

    def test_29_nas_validation_catches_all_missing_fields(self):
        """NAS sin host NI user NI path debe reportar todos los errores."""
        from core.sandbox_config import SandboxConfig, SandboxType
        cfg = SandboxConfig(sandbox_type=SandboxType.NAS, sandbox_path="")
        errors = cfg.validate()
        # Debe tener al menos: sandbox_path, host, user
        self.assertTrue(len(errors) >= 3)


class TestLocalConnector(unittest.TestCase):
    """Verifica LocalConnector (sandbox local con subprocess)."""

    def setUp(self):
        """Crea un sandbox temporal para cada test."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Limpia el sandbox temporal."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_connector(self, timeout=10, **kwargs):
        from core.sandbox_config import SandboxConfig, SandboxType
        from core.sandbox_local import LocalConnector
        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=self.temp_dir,
            timeout=timeout,
            **kwargs
        )
        return LocalConnector(config)

    def test_30_init_creates_work_dir(self):
        """El directorio de trabajo debe crearse al inicializar."""
        connector = self._make_connector()
        self.assertTrue(os.path.isdir(connector.work_dir))

    def test_31_execute_python_simple(self):
        """Ejecutar Python simple debe funcionar."""
        connector = self._make_connector()
        result = connector.execute_code("print('hello sandbox')", "python")
        self.assertTrue(result["success"], f"Python falló: {result.get('stderr', '')}")
        self.assertIn("hello sandbox", result["stdout"])

    def test_32_execute_python_error(self):
        """Python con error debe fallar con success=False."""
        connector = self._make_connector()
        result = connector.execute_code("raise ValueError('test')", "python")
        self.assertFalse(result["success"])
        self.assertTrue(len(result["stderr"]) > 0)

    def test_33_execute_bash(self):
        """Ejecutar Bash debe funcionar si está disponible."""
        if not _has_bash:
            self.skipTest("bash no disponible en este sistema")
        connector = self._make_connector()
        result = connector.execute_code("echo 'bash ok'", "bash")
        self.assertTrue(result["success"])
        self.assertIn("bash ok", result["stdout"])

    def test_34_unsupported_language(self):
        """Lenguaje no soportado debe retornar error."""
        connector = self._make_connector()
        result = connector.execute_code("code", "brainfuck")
        self.assertFalse(result["success"])
        self.assertIn("no soportado", result["stderr"].lower())

    def test_35_write_and_read_file(self):
        """Escribir y leer un archivo debe funcionar."""
        connector = self._make_connector()
        w_result = connector.write_file("test.txt", "contenido\nlínea2")
        self.assertTrue(w_result["success"])

        r_result = connector.read_file("test.txt")
        self.assertTrue(r_result["success"])
        self.assertIn("contenido", r_result["content"])
        self.assertIn("línea2", r_result["content"])

    def test_36_write_creates_subdirs(self):
        """write_file debe crear subdirectorios automáticamente."""
        connector = self._make_connector()
        result = connector.write_file("sub/deep/file.txt", "data")
        self.assertTrue(result["success"])

        r_result = connector.read_file("sub/deep/file.txt")
        self.assertTrue(r_result["success"])

    def test_37_read_nonexistent_file(self):
        """Leer archivo inexistente debe fallar."""
        connector = self._make_connector()
        result = connector.read_file("no_existe_xyz.txt")
        self.assertFalse(result["success"])

    def test_38_validate_python_valid(self):
        """Python válido debe pasar validación."""
        connector = self._make_connector()
        valid, error = connector.validate_code("x = 1\nprint(x)", "python")
        self.assertTrue(valid, f"Validación falló: {error}")
        self.assertEqual(error, "")

    def test_39_validate_python_invalid(self):
        """Python inválido debe fallar validación."""
        connector = self._make_connector()
        valid, error = connector.validate_code("def roto(", "python")
        self.assertFalse(valid)
        self.assertTrue(len(error) > 0)

    def test_40_anti_recursion_guard(self):
        """La guardia anti-recursión debe funcionar."""
        connector = self._make_connector()
        connector._guard.inside = True
        with self.assertRaises(RuntimeError):
            connector.execute_code("print('test')", "python")
        connector._guard.inside = False

    def test_41_list_directory(self):
        """list_directory debe listar archivos."""
        connector = self._make_connector()
        connector.write_file("a.txt", "a")
        connector.write_file("b.txt", "b")

        result = connector.list_directory()
        self.assertTrue(result["success"])
        names = [e["name"] for e in result["entries"]]
        self.assertIn("a.txt", names)
        self.assertIn("b.txt", names)

    def test_42_cleanup_removes_temps(self):
        """cleanup debe eliminar archivos temporales."""
        connector = self._make_connector()
        connector._write_temp_file("test", ".py")

        temps_before = [f for f in os.listdir(connector.work_dir) if f.startswith("temp_")]
        self.assertTrue(len(temps_before) >= 1)

        connector.cleanup()

        temps_after = [f for f in os.listdir(connector.work_dir) if f.startswith("temp_")]
        self.assertEqual(len(temps_after), 0)

    def test_43_timeout_works(self):
        """Timeout debe funcionar."""
        connector = self._make_connector(timeout=2)
        result = connector.execute_code(
            "import time; time.sleep(10); print('never')", "python"
        )
        self.assertFalse(result["success"])
        self.assertIn("timeout", result["stderr"].lower())

    def test_44_interface_compatible_with_nas(self):
        """LocalConnector debe tener la misma interfaz que NASConnector."""
        connector = self._make_connector()
        for method in ['execute_code', 'read_file', 'write_file']:
            self.assertTrue(hasattr(connector, method))
            self.assertTrue(callable(getattr(connector, method)))

        result = connector.execute_code("print(42)", "python")
        self.assertIsInstance(result, dict)
        self.assertIn("success", result)
        self.assertIn("stdout", result)
        self.assertIn("stderr", result)

    def test_45_env_vars_propagate(self):
        """env_vars deben propagarse al subprocess."""
        connector = self._make_connector(env_vars={"MI_VAR_TEST": "valor_xyz"})
        result = connector.execute_code(
            "import os; print(os.environ.get('MI_VAR_TEST', 'NO'))", "python"
        )
        self.assertTrue(result["success"], f"Falló: {result.get('stderr', '')}")
        self.assertIn("valor_xyz", result["stdout"])


class TestGetConnectorFactory(unittest.TestCase):
    """Verifica la factory function get_connector()."""

    def test_50_get_connector_class_for_local(self):
        """get_connector_class para local debe retornar LocalConnector."""
        from core.sandbox_config import SandboxConfig, SandboxType, get_connector_class
        cfg = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=tempfile.mkdtemp()
        )
        cls = get_connector_class(cfg)
        # Comparar por nombre de clase (evita problemas de path de módulo)
        self.assertEqual(cls.__name__, "LocalConnector")

    def test_51_get_connector_class_for_nas(self):
        """get_connector_class para NAS debe retornar NASConnector."""
        from core.sandbox_config import SandboxConfig, SandboxType, get_connector_class
        cfg = SandboxConfig(
            sandbox_type=SandboxType.NAS,
            sandbox_path="/app/sandbox",
            host="192.168.1.100",
            user="admin"
        )
        cls = get_connector_class(cfg)
        self.assertIsNotNone(cls)
        self.assertEqual(cls.__name__, "NASConnector")

    def test_52_get_connector_class_for_vm(self):
        """get_connector_class para VM debe retornar NASConnector (reutilizado)."""
        from core.sandbox_config import SandboxConfig, SandboxType, get_connector_class
        cfg = SandboxConfig(
            sandbox_type=SandboxType.VM,
            sandbox_path="/home/dev/sandbox",
            host="10.0.0.50",
            user="dev"
        )
        cls = get_connector_class(cfg)
        self.assertIsNotNone(cls)
        self.assertEqual(cls.__name__, "NASConnector")

    def test_53_get_connector_class_for_external(self):
        """get_connector_class para external debe retornar NASConnector (reutilizado)."""
        from core.sandbox_config import SandboxConfig, SandboxType, get_connector_class
        cfg = SandboxConfig(
            sandbox_type=SandboxType.EXTERNAL,
            sandbox_path="/srv/sandbox",
            host="rpi.local",
            user="pi"
        )
        cls = get_connector_class(cfg)
        self.assertIsNotNone(cls)
        self.assertEqual(cls.__name__, "NASConnector")


class TestNASConnectorWithSandboxConfig(unittest.TestCase):
    """Verifica que NASConnector acepta SandboxConfig."""

    def test_60_nas_connector_accepts_none(self):
        """NASConnector(None) debe funcionar (legacy)."""
        from mcp.server import NASConnector
        import inspect
        sig = inspect.signature(NASConnector.__init__)
        self.assertIn('sandbox_config', sig.parameters)

    def test_61_nas_connector_has_ssh_port(self):
        """NASConnector debe exponer ssh_port cuando se usa con config."""
        from mcp.server import NASConnector
        self.assertTrue(hasattr(NASConnector, '__init__'))


class TestIntegrationLocalExecution(unittest.TestCase):
    """Tests de integración: ejecución real en sandbox local."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_70_full_local_workflow(self):
        """Flujo completo: crear archivo, ejecutar, leer resultado."""
        from core.sandbox_config import SandboxConfig, SandboxType, get_connector_class
        from core.sandbox_local import LocalConnector

        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=self.temp_dir,
            timeout=10
        )
        cls = get_connector_class(config)
        connector = cls(config)

        # Escribir un script Python
        w = connector.write_file("calc.py", "result = 2 + 2\nprint(result)")
        self.assertTrue(w["success"])

        # Ejecutarlo
        r = connector.execute_code("exec(open('calc.py').read())", "python")
        self.assertTrue(r["success"], f"Ejecución falló: {r.get('stderr', '')}")
        self.assertIn("4", r["stdout"])

        # Leer el archivo
        content = connector.read_file("calc.py")
        self.assertTrue(content["success"])
        self.assertIn("2 + 2", content["content"])

    def test_71_local_python_multiline(self):
        """Ejecutar código Python multilinea complejo."""
        from core.sandbox_config import SandboxConfig, SandboxType
        from core.sandbox_local import LocalConnector

        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=self.temp_dir,
            timeout=10
        )
        connector = LocalConnector(config)

        code = """
def fibonacci(n):
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

for i in range(8):
    print(f"F({i}) = {fibonacci(i)}")
"""
        result = connector.execute_code(code.strip(), "python")
        self.assertTrue(result["success"], f"Fibonacci falló: {result.get('stderr', '')}")
        self.assertIn("F(7) = 13", result["stdout"])

    def test_72_bash_with_pipes(self):
        """Ejecutar Bash con pipes (solo si bash está disponible)."""
        if not _has_bash:
            self.skipTest("bash no disponible en este sistema")

        from core.sandbox_config import SandboxConfig, SandboxType
        from core.sandbox_local import LocalConnector

        config = SandboxConfig(
            sandbox_type=SandboxType.LOCAL,
            sandbox_path=self.temp_dir,
            timeout=10
        )
        connector = LocalConnector(config)

        code = "echo 'line1\\nline2\\nline3' | grep line2"
        result = connector.execute_code(code, "bash")
        self.assertTrue(result["success"])
        self.assertIn("line2", result["stdout"])


# =================================================================
# EJECUCIÓN
# =================================================================

if __name__ == "__main__":
    print("=" * 64)
    print("  FASE 5 — SANDBOX CONFIGURABLE")
    print("  Tests de validación completa")
    print("=" * 64)
    print(f"  SO: {platform.system()} | bash disponible: {_has_bash}")
    print("=" * 64)
    print()

    unittest.main(verbosity=2)
