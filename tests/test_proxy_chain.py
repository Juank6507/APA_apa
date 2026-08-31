#!/usr/bin/env python3
"""
Test de Validacion Completa de la Cadena Proxy LLM

Version adaptada para Windows (PC del usuario con APA + MB Sandbox).

Diferencias respecto al test original (test_proxy_chain.py):
  1. 'thinking:' eliminado de contenido_prohibido en index.ts
     — El SDK z-ai-web-dev-sdk anade thinking: {type:'disabled'} automaticamente
       (linea 93 de dist/index.js). Tenerlo explicito en el codigo NO causa
       respuestas vacias.
  2. Eslabon 1 (archivos del proxy) se omite: solo existen en el sandbox Z.ai
  3. La ruta del MB Sandbox es mb-sandbox/ (no mini-services/mb-sandbox/)
  4. .z-ai-config se busca en mb-sandbox/.z-ai-config con URL preview-chat-*space-z.ai
  5. Los scripts .ps1 se verifican como opcionales (WARN, no FAIL)

Ejecucion:
    python test_proxy_chain_windows.py
    python test_proxy_chain_windows.py --base-dir C:/Python/Proyectos/APA
    python test_proxy_chain_windows.py --json
"""

from __future__ import annotations

import sys
import os
import json
import time
import re
import platform
import socket
import urllib.request
import urllib.error
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════════
# MODELOS DE DATOS
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class FileSpec:
    """Especificacion de un archivo requerido."""
    id: str
    nombre: str
    ruta_relativa: str
    descripcion: str
    es_critico: bool = True
    contenido_esperado: Optional[List[str]] = None
    contenido_prohibido: Optional[List[str]] = None
    es_json_valido: bool = False
    extension: str = ""


@dataclass
class ValidationResult:
    """Resultado de una verificacion individual."""
    nombre: str
    paso: str
    status: str  # "PASS", "FAIL", "WARN", "SKIP"
    mensaje: str
    detalle: str = ""
    fix: str = ""


@dataclass
class TestReport:
    """Reporte completo del test."""
    resultados: List[ValidationResult] = field(default_factory=list)
    inicio: float = 0.0
    fin: float = 0.0
    base_dir: str = ""

    def add(self, r: ValidationResult):
        self.resultados.append(r)

    @property
    def total(self) -> int:
        return len(self.resultados)

    @property
    def pasaron(self) -> int:
        return sum(1 for r in self.resultados if r.status == "PASS")

    @property
    def fallaron(self) -> int:
        return sum(1 for r in self.resultados if r.status == "FAIL")

    @property
    def advertencias(self) -> int:
        return sum(1 for r in self.resultados if r.status == "WARN")

    @property
    def omitidos(self) -> int:
        return sum(1 for r in self.resultados if r.status == "SKIP")


# ═══════════════════════════════════════════════════════════════════════
# CONSTANTES — DEFINICION DE TODOS LOS ARCHIVOS REQUERIDOS
# ═══════════════════════════════════════════════════════════════════════

# Archivos del MB SANDBOX (PC del usuario Windows)
# ADAPTACION: 'thinking:' eliminado de contenido_prohibido
MB_SANDBOX_FILES: List[FileSpec] = [
    FileSpec(
        id="mb-1",
        nombre="package.json (MB Sandbox)",
        ruta_relativa="mb-sandbox/package.json",
        descripcion="Declara la dependencia z-ai-web-dev-sdk para el servidor MB",
        es_json_valido=True,
        contenido_esperado=["z-ai-web-dev-sdk"],
    ),
    FileSpec(
        id="mb-2",
        nombre="index.ts (servidor MB Sandbox)",
        ruta_relativa="mb-sandbox/index.ts",
        descripcion="Servidor HTTP Bun en puerto 8100. Expone /api/status, /api/models, /api/call."
        " Usa z-ai-web-dev-sdk para conectarse al proxy.",
        extension=".ts",
        contenido_esperado=[
            'z-ai-web-dev-sdk',
            'Bun.serve',
            '/api/status',
            '/api/models',
            '/api/call',
            'role: "system"',  # CRITICO: no debe ser "assistant"
            'PORT = 8100',
        ],
        contenido_prohibido=[
            'role: "assistant"',  # BUG: causa respuestas vacias
            # NOTA: 'thinking:' fue eliminado de esta lista.
            # El SDK anade thinking: {type:'disabled'} automaticamente
            # (linea 93 de z-ai-web-dev-sdk/dist/index.js), por lo que
            # tenerlo explicito en index.ts es inocuo.
        ],
    ),
    FileSpec(
        id="mb-3",
        nombre=".z-ai-config (configuracion SDK)",
        ruta_relativa="mb-sandbox/.z-ai-config",
        descripcion="Configuracion del SDK. Debe estar en la misma carpeta que index.ts."
        " Apunta al proxy del sandbox de Z.ai via preview-chat-{uuid}.space-z.ai.",
        es_json_valido=True,
        contenido_esperado=["baseUrl", "apiKey"],
    ),
]

# Archivos de configuracion de APA
APA_CONFIG_FILES: List[FileSpec] = [
    FileSpec(
        id="apa-1",
        nombre=".env de APA",
        ruta_relativa="apa/.env",
        descripcion="Variables de entorno: MODEL_BROKER_URL, MODEL_BROKER_START_CMD, MODEL_BROKER_SANDBOX_PATH."
        " Sin este archivo APA no lanza MB.",
        contenido_esperado=[
            "MODEL_BROKER_URL",
            "MODEL_BROKER_START_CMD",
            "8100",
            "bun",
        ],
    ),
    FileSpec(
        id="apa-2",
        nombre="settings.py (configuracion central)",
        ruta_relativa="apa/config/settings.py",
        descripcion="Configuracion centralizada de APA. Lee variables del .env."
        " Expone model_broker_url, model_broker_start_cmd, model_broker_start_dir.",
        contenido_esperado=[
            "MODEL_BROKER_URL",
            "MODEL_BROKER_START_CMD",
            "SANDBOX_PATH",
            "model_broker_url",
            "model_broker_start_cmd",
            "model_broker_start_dir",
            "class Settings",
        ],
    ),
    FileSpec(
        id="apa-3",
        nombre="mb_launcher.py (lanzador de MB)",
        ruta_relativa="apa/core/mb_launcher.py",
        descripcion="Asegura que MB este corriendo al arrancar APA."
        " Estrategia de 3 niveles: verificar URL, lanzar sandbox, o fallback.",
        contenido_esperado=[
            "ensure_mb_running",
            "_health_check",
            "/api/status",
            "stop_mb",
            "get_mb_status",
        ],
    ),
    FileSpec(
        id="apa-4",
        nombre="chat_engine.py (motor de chat)",
        ruta_relativa="apa/interface/app/chat_engine.py",
        descripcion="Maneja respuestas del chat. Debe extraer content del dict retornado por MB.",
        contenido_esperado=[
            'call_llm',
            'system_prompt',
            'user_prompt',
            'content',
        ],
    ),
]

# Scripts auxiliares (opcionales, WARN si faltan)
AUX_FILES: List[FileSpec] = [
    FileSpec(
        id="aux-1",
        nombre="setup-mb.ps1",
        ruta_relativa="setup-mb.ps1",
        descripcion="Script PowerShell que crea el MB Sandbox automaticamente (opcional)",
        es_critico=False,
        contenido_esperado=["mb-sandbox", ".z-ai-config", "bun install"],
    ),
    FileSpec(
        id="aux-2",
        nombre="start-apa.ps1",
        ruta_relativa="start-apa.ps1",
        descripcion="Script PowerShell que lanza MB + APA automaticamente (opcional)",
        es_critico=False,
        contenido_esperado=["bun", "app_apa.py", "8100"],
    ),
]


# ═══════════════════════════════════════════════════════════════════════
# UTILIDADES
# ═══════════════════════════════════════════════════════════════════════

def _buscar_env_hacia_arriba(desde: Path) -> Optional[Path]:
    """Busca un archivo .env subiendo directorios desde 'desde'."""
    actual = desde.resolve()
    for _ in range(8):
        candidato = actual / ".env"
        if candidato.is_file():
            return candidato
        candidato = actual / "apa" / ".env"
        if candidato.is_file():
            return candidato
        padre = actual.parent
        if padre == actual:
            break
        actual = padre
    return None


def detectar_base_dir() -> str:
    """Detecta automaticamente el directorio base del proyecto.
    Busca el .env y de ahi deriva la raiz. Si no lo encuentra, usa CWD."""
    script_dir = Path(__file__).resolve().parent

    # Buscar .env subiendo desde el directorio del script
    env_file = _buscar_env_hacia_arriba(script_dir)
    if env_file:
        if env_file.parent.name.lower() == "apa":
            return str(env_file.parent.parent)
        return str(env_file.parent)

    # Buscar mb-sandbox/ subiendo
    actual = script_dir
    for _ in range(6):
        if (actual / "mb-sandbox" / "index.ts").is_file():
            return str(actual)
        padre = actual.parent
        if padre == actual:
            break
        actual = padre

    # Ultimo recurso: CWD
    return os.getcwd()


def _banner(texto: str, ancho: int = 70) -> str:
    return f"\n{'=' * ancho}\n  {texto}\n{'=' * ancho}"


def _sub_banner(texto: str, ancho: int = 70) -> str:
    return f"\n--- {texto} {'-' * (ancho - 5 - len(texto))}"


# ═══════════════════════════════════════════════════════════════════════
# VERIFICADORES
# ═══════════════════════════════════════════════════════════════════════

def verificar_archivo_existe(spec: FileSpec, base_dir: str) -> ValidationResult:
    ruta = Path(base_dir) / spec.ruta_relativa
    if ruta.exists():
        return ValidationResult(
            nombre=spec.nombre,
            paso="existencia",
            status="PASS",
            mensaje=f"Archivo encontrado: {spec.ruta_relativa}",
            detalle=str(ruta.resolve()),
        )
    return ValidationResult(
        nombre=spec.nombre,
        paso="existencia",
        status="FAIL",
        mensaje=f"ARCHIVO FALTANTE: {spec.ruta_relativa}",
        detalle=str(ruta.resolve()),
        fix="Crear el archivo en la ubicacion indicada",
    )


def verificar_contenido(spec: FileSpec, base_dir: str) -> ValidationResult:
    ruta = Path(base_dir) / spec.ruta_relativa
    if not ruta.exists():
        return ValidationResult(
            nombre=spec.nombre,
            paso="contenido",
            status="SKIP",
            mensaje="Omitido: archivo no existe",
        )
    try:
        content = ruta.read_text(encoding="utf-8-sig", errors="replace")
    except Exception as e:
        return ValidationResult(
            nombre=spec.nombre,
            paso="contenido",
            status="FAIL",
            mensaje=f"No se puede leer: {e}",
        )

    errores: List[str] = []

    if spec.es_json_valido:
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            errores.append(f"JSON invalido: {e}")

    if spec.contenido_esperado:
        for esperado in spec.contenido_esperado:
            if esperado not in content:
                errores.append(f'Falta el texto: "{esperado}"')

    if spec.contenido_prohibido:
        for prohibido in spec.contenido_prohibido:
            if prohibido in content:
                errores.append(f'ENCONTRADO contenido prohibido: "{prohibido}"')

    if errores:
        return ValidationResult(
            nombre=spec.nombre,
            paso="contenido",
            status="FAIL",
            mensaje=f"Problemas de contenido ({len(errores)}):",
            detalle="\n    ".join(errores),
        )
    return ValidationResult(
        nombre=spec.nombre,
        paso="contenido",
        status="PASS",
        mensaje="Contenido verificado correctamente",
    )


def verificar_puerto_en_uso(puerto: int) -> ValidationResult:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(1)
        resultado = sock.connect_ex(("127.0.0.1", puerto))
        if resultado == 0:
            return ValidationResult(
                nombre=f"Puerto {puerto}",
                paso="puerto",
                status="PASS",
                mensaje=f"Puerto {puerto} esta en uso (servicio corriendo)",
            )
        return ValidationResult(
            nombre=f"Puerto {puerto}",
            paso="puerto",
            status="WARN",
            mensaje=f"Puerto {puerto} esta libre (ningun servicio)",
            fix=f"Iniciar el servicio: cd mb-sandbox && bun --hot index.ts",
        )
    except Exception as e:
        return ValidationResult(
            nombre=f"Puerto {puerto}",
            paso="puerto",
            status="WARN",
            mensaje=f"No se pudo verificar: {e}",
        )
    finally:
        sock.close()


def verificar_http(url: str, nombre: str, metodo: str = "GET",
                   body: Optional[dict] = None, timeout: float = 5.0) -> ValidationResult:
    try:
        req_data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=req_data, method=metodo)
        if body:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status_code = resp.getcode()
            resp_body = resp.read().decode("utf-8", errors="replace")
            try:
                resp_json = json.loads(resp_body)
                body_preview = json.dumps(resp_json, ensure_ascii=False)[:200]
            except (json.JSONDecodeError, ValueError):
                body_preview = resp_body[:200]
            if status_code == 200:
                return ValidationResult(
                    nombre=nombre, paso="http", status="PASS",
                    mensaje=f"HTTP {status_code} OK",
                    detalle=f"Respuesta: {body_preview}",
                )
            return ValidationResult(
                nombre=nombre, paso="http", status="FAIL",
                mensaje=f"HTTP {status_code} (esperaba 200)",
                detalle=f"Respuesta: {body_preview}",
            )
    except urllib.error.HTTPError as e:
        b = ""
        try:
            b = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        return ValidationResult(
            nombre=nombre, paso="http", status="FAIL",
            mensaje=f"HTTP {e.code} - {e.reason}",
            detalle=f"Body: {b}",
        )
    except urllib.error.URLError as e:
        return ValidationResult(
            nombre=nombre, paso="http", status="FAIL",
            mensaje=f"No se puede conectar: {e.reason}",
        )
    except Exception as e:
        return ValidationResult(
            nombre=nombre, paso="http", status="FAIL",
            mensaje=f"Error inesperado: {e}",
        )


def _leer_env_vars(base_dir: str) -> Dict[str, str]:
    """Lee el archivo .env y retorna un dict con las variables."""
    for candidato in ["apa/.env", ".env"]:
        ruta = Path(base_dir) / candidato
        if ruta.exists():
            try:
                contenido = ruta.read_text(encoding="utf-8", errors="replace")
                vars_dict = {}
                for line in contenido.splitlines():
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        key, _, value = line.partition("=")
                        vars_dict[key.strip()] = value.strip()
                return vars_dict
            except Exception:
                continue
    return {}


# ═══════════════════════════════════════════════════════════════════════
# VERIFICACION PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════

def verificar_cadena_proxy(report: TestReport, base_dir: str):
    """Verifica cada eslabon de la cadena proxy para Windows."""

    env_vars = _leer_env_vars(base_dir)
    mb_sandbox_dir = Path(base_dir) / "mb-sandbox"

    # ─── ESLABON 1: Archivos del Proxy (SKIP en Windows) ───
    report.add(ValidationResult(
        nombre="ESLABON 1: Archivos del Proxy en Sandbox",
        paso="cadena", status="SKIP",
        mensaje="Omitido: los archivos del proxy estan en el sandbox de Z.ai, no en la PC del usuario",
    ))

    # ─── ESLABON 2: Archivos del MB Sandbox ───
    report.add(ValidationResult(
        nombre="ESLABON 2: Archivos del MB Sandbox",
        paso="cadena", status="PASS",
        mensaje="Verificando archivos del MB Sandbox en la PC del usuario",
    ))

    for spec in MB_SANDBOX_FILES:
        report.add(verificar_archivo_existe(spec, base_dir))
        r = verificar_contenido(spec, base_dir)
        if r.status != "SKIP":
            report.add(r)

    # Verificar .z-ai-config del MB
    zai_config_path = mb_sandbox_dir / ".z-ai-config"
    if zai_config_path.exists():
        try:
            zai_config = json.loads(zai_config_path.read_text(encoding="utf-8-sig"))
            base_url = zai_config.get("baseUrl", "")
            api_key = zai_config.get("apiKey", "")
            chat_id = zai_config.get("chatId", "")

            # Verificar apiKey
            if api_key:
                report.add(ValidationResult(
                    nombre=".z-ai-config apiKey",
                    paso="config", status="PASS",
                    mensaje=f"apiKey presente: {api_key[:8]}...",
                ))
            else:
                report.add(ValidationResult(
                    nombre=".z-ai-config apiKey",
                    paso="config", status="FAIL",
                    mensaje="apiKey no encontrado en .z-ai-config",
                    fix="Ejecutar ./setup-mb.ps1 para regenerar el config",
                ))

            # Verificar baseUrl: debe apuntar al proxy Z.ai
            if "preview-chat-" in base_url and "space-z.ai" in base_url:
                report.add(ValidationResult(
                    nombre=".z-ai-config baseUrl (proxy Z.ai)",
                    paso="config", status="PASS",
                    mensaje=f"baseUrl apunta al proxy: ...{base_url[-50:]}",
                ))
                # Extraer y mostrar el chat_id de la URL
                match = re.search(r'preview-chat-([a-f0-9-]+)', base_url)
                if match:
                    cid = match.group(1)
                    report.add(ValidationResult(
                        nombre=f"chat_id en URL: {cid[:16]}...",
                        paso="config", status="PASS",
                        mensaje=f"chat_id detectado correctamente en la URL del proxy",
                        detalle=f"Si la sesion de Z.ai cambio, actualizar con: ./setup-mb.ps1 -ChatId \"nuevo-chat-id\"",
                    ))
            elif "REEMPLAZAR" in base_url or not base_url:
                report.add(ValidationResult(
                    nombre=".z-ai-config baseUrl",
                    paso="config", status="FAIL",
                    mensaje="baseUrl NO configurado (valor de template o vacio)",
                    fix="Ejecutar: ./setup-mb.ps1 -ChatId \"tu-chat-id\"",
                ))
            elif "internal-api" in base_url:
                report.add(ValidationResult(
                    nombre=".z-ai-config baseUrl",
                    paso="config", status="WARN",
                    mensaje=f"baseUrl apunta a API interna (solo funciona dentro del sandbox Z.ai)",
                    detalle=f"URL actual: {base_url}",
                    fix="En Windows debe usar preview-chat-{{uuid}}.space-z.ai. Ejecutar ./setup-mb.ps1",
                ))
            else:
                report.add(ValidationResult(
                    nombre=".z-ai-config baseUrl",
                    paso="config", status="WARN",
                    mensaje=f"baseUrl con formato inesperado: {base_url[:80]}",
                ))

            # Verificar chatId
            if chat_id:
                report.add(ValidationResult(
                    nombre=".z-ai-config chatId",
                    paso="config", status="PASS",
                    mensaje=f"chatId configurado: {chat_id[:24]}...",
                ))
            else:
                report.add(ValidationResult(
                    nombre=".z-ai-config chatId",
                    paso="config", status="WARN",
                    mensaje="chatId no configurado (puede causar error 410)",
                    fix="Ejecutar ./setup-mb.ps1 -ChatId \"tu-chat-id\"",
                ))

            # Verificar que NO tiene BOM
            raw = zai_config_path.read_bytes()
            if len(raw) >= 3 and raw[0] == 0xEF and raw[1] == 0xBB and raw[2] == 0xBF:
                report.add(ValidationResult(
                    nombre=".z-ai-config sin BOM",
                    paso="config", status="FAIL",
                    mensaje=".z-ai-config tiene BOM UTF-8 (causa error de SDK)",
                    fix="Guardar el archivo como UTF-8 sin BOM",
                ))
            else:
                report.add(ValidationResult(
                    nombre=".z-ai-config sin BOM",
                    paso="config", status="PASS",
                    mensaje=".z-ai-config sin BOM (correcto)",
                ))

        except Exception as e:
            report.add(ValidationResult(
                nombre=".z-ai-config parsing",
                paso="config", status="FAIL",
                mensaje=f"Error parseando .z-ai-config: {e}",
            ))
    else:
        report.add(ValidationResult(
            nombre=".z-ai-config",
            paso="config", status="FAIL",
            mensaje="No existe: mb-sandbox/.z-ai-config",
            fix="Ejecutar: ./setup-mb.ps1 -ChatId \"tu-chat-id\"",
        ))

    # Verificar SDK instalado
    node_modules = mb_sandbox_dir / "node_modules" / "z-ai-web-dev-sdk"
    if node_modules.exists():
        report.add(ValidationResult(
            nombre="z-ai-web-dev-sdk instalado",
            paso="dependencias", status="PASS",
            mensaje="SDK encontrado en node_modules",
        ))
    elif mb_sandbox_dir.exists():
        report.add(ValidationResult(
            nombre="z-ai-web-dev-sdk instalado",
            paso="dependencias", status="FAIL",
            mensaje="SDK NO encontrado en node_modules",
            fix=f"Ejecutar: cd {mb_sandbox_dir} && bun install",
        ))

    # ─── ESLABON 3: Configuracion de APA ───
    report.add(ValidationResult(
        nombre="ESLABON 3: Configuracion de APA",
        paso="cadena", status="PASS",
        mensaje="Verificando configuracion de APA",
    ))

    for spec in APA_CONFIG_FILES:
        report.add(verificar_archivo_existe(spec, base_dir))
        r = verificar_contenido(spec, base_dir)
        if r.status != "SKIP":
            report.add(r)

    # Verificar variables del .env
    env_path = Path(base_dir) / "apa" / ".env"
    if not env_path.exists():
        env_path = Path(base_dir) / ".env"

    if env_path.exists():
        # MODEL_BROKER_URL
        mb_url = env_vars.get("MODEL_BROKER_URL", "")
        if mb_url and "8100" in mb_url:
            report.add(ValidationResult(
                nombre="MODEL_BROKER_URL",
                paso="env", status="PASS",
                mensaje=f"MODEL_BROKER_URL = {mb_url}",
            ))
        else:
            report.add(ValidationResult(
                nombre="MODEL_BROKER_URL",
                paso="env", status="FAIL",
                mensaje=f"MODEL_BROKER_URL no configurado correctamente: '{mb_url}'",
                fix="Agregar al .env: MODEL_BROKER_URL=http://127.0.0.1:8100",
            ))

        # MODEL_BROKER_START_CMD
        start_cmd = env_vars.get("MODEL_BROKER_START_CMD", "")
        if start_cmd and "bun" in start_cmd:
            report.add(ValidationResult(
                nombre="MODEL_BROKER_START_CMD",
                paso="env", status="PASS",
                mensaje=f"MODEL_BROKER_START_CMD = {start_cmd}",
            ))
        else:
            report.add(ValidationResult(
                nombre="MODEL_BROKER_START_CMD",
                paso="env", status="FAIL",
                mensaje=f"MODEL_BROKER_START_CMD no configurado: '{start_cmd}'",
                fix="Agregar al .env: MODEL_BROKER_START_CMD=bun --hot index.ts",
            ))

        # MODEL_BROKER_SANDBOX_PATH (opcional pero recomendado)
        mb_path = env_vars.get("MODEL_BROKER_SANDBOX_PATH", "")
        if mb_path and "mb-sandbox" in mb_path:
            report.add(ValidationResult(
                nombre="MODEL_BROKER_SANDBOX_PATH",
                paso="env", status="PASS",
                mensaje=f"MODEL_BROKER_SANDBOX_PATH = {mb_path}",
            ))
        else:
            report.add(ValidationResult(
                nombre="MODEL_BROKER_SANDBOX_PATH",
                paso="env", status="WARN",
                mensaje=f"MODEL_BROKER_SANDBOX_PATH no configurado (opcional)",
                detalle="APA buscara mb-sandbox/ relativo al directorio del proyecto",
            ))

    # ─── ESLABON 4: Servicios corriendo ───
    report.add(ValidationResult(
        nombre="ESLABON 4: Servicios Corriendo",
        paso="cadena", status="PASS",
        mensaje="Verificando que los servicios esten activos",
    ))

    port_result = verificar_puerto_en_uso(8100)
    report.add(port_result)

    if port_result.status == "PASS":
        report.add(verificar_http(
            "http://127.0.0.1:8100/api/status",
            "MB /api/status (health check)",
        ))
        report.add(verificar_http(
            "http://127.0.0.1:8100/api/models",
            "MB /api/models (lista modelos)",
        ))

        # Llamada real al LLM
        call_result = verificar_http(
            "http://127.0.0.1:8100/api/call",
            "MB /api/call (llamada real al LLM)",
            metodo="POST",
            body={
                "system_prompt": "Eres un asistente. Responde en una linea.",
                "user_prompt": "Di hola en espanol, una sola palabra",
            },
            timeout=30.0,
        )
        report.add(call_result)

        # Verificar estructura y contenido
        if call_result.status == "PASS":
            try:
                resp_text = call_result.detalle.split("Respuesta: ", 1)[1]
                resp_json = json.loads(resp_text)
                campos_faltantes = [c for c in ["content", "model_used", "provider", "success"] if c not in resp_json]

                if not campos_faltantes:
                    report.add(ValidationResult(
                        nombre="MB /api/call estructura de respuesta",
                        paso="http", status="PASS",
                        mensaje=f"Todos los campos presentes. Modelo: {resp_json.get('model_used', '?')}",
                        detalle=f"success={resp_json.get('success')}, provider={resp_json.get('provider')}",
                    ))

                    if resp_json.get("provider") == "sandbox-fallback":
                        report.add(ValidationResult(
                            nombre="MB modo real vs fallback",
                            paso="http", status="FAIL",
                            mensaje="MB en modo FALLBACK (respuestas simuladas, no LLM real)",
                            detalle=f"sdk_error: {resp_json.get('sdk_error', 'N/A')}",
                            fix="Verificar que .z-ai-config tenga chatId correcto y que el proxy Z.ai este activo",
                        ))
                    elif resp_json.get("provider") == "sandbox" and resp_json.get("success"):
                        content = resp_json.get("content", "")
                        if content and len(content) > 0:
                            report.add(ValidationResult(
                                nombre="MB respuesta LLM real",
                                paso="http", status="PASS",
                                mensaje=f"LLM real respondio: \"{content[:60]}\" ({len(content)} chars)",
                                detalle=f"Modelo: {resp_json.get('model_used')}, Latencia: {resp_json.get('latency_ms')}ms",
                            ))
                        else:
                            report.add(ValidationResult(
                                nombre="MB respuesta LLM real",
                                paso="http", status="FAIL",
                                mensaje="La respuesta del LLM esta vacia",
                                fix="Verificar index.ts: system prompt con role 'system', sin role 'assistant'",
                            ))
                else:
                    report.add(ValidationResult(
                        nombre="MB /api/call estructura",
                        paso="http", status="FAIL",
                        mensaje=f"Campos faltantes: {campos_faltantes}",
                    ))
            except (json.JSONDecodeError, IndexError, KeyError) as e:
                report.add(ValidationResult(
                    nombre="MB /api/call parseo",
                    paso="http", status="WARN",
                    mensaje=f"No se pudo verificar estructura: {e}",
                ))
    else:
        report.add(ValidationResult(
            nombre="MB /api/status, /api/models, /api/call",
            paso="http", status="SKIP",
            mensaje="Omitido: MB Sandbox no esta corriendo en :8100",
            fix="Ejecutar: cd mb-sandbox && bun --hot index.ts",
        ))

    # ─── ESLABON 5: Scripts auxiliares (opcionales) ───
    report.add(ValidationResult(
        nombre="ESLABON 5: Scripts Auxiliares (no criticos)",
        paso="cadena", status="PASS",
        mensaje="Verificando scripts opcionales",
    ))

    for spec in AUX_FILES:
        r = verificar_archivo_existe(spec, base_dir)
        if r.status == "FAIL":
            r.status = "WARN"
            r.mensaje = f"(Opcional) {r.mensaje}"
        report.add(r)
        if r.status != "FAIL":
            c = verificar_contenido(spec, base_dir)
            if c.status == "FAIL":
                c.status = "WARN"
            if c.status != "SKIP":
                report.add(c)


# ═══════════════════════════════════════════════════════════════════════
# REPORTADOR
# ═══════════════════════════════════════════════════════════════════════

def imprimir_reporte(report: TestReport):
    print(_banner("TEST DE VALIDACION - CADENA PROXY LLM (Windows)"))
    print(f"  Directorio base: {report.base_dir}")
    print(f"  Entorno: PC del usuario (Windows)")
    print(f"  Inicio: {time.strftime('%H:%M:%S', time.localtime(report.inicio))}")
    print()

    paso_actual = ""
    for r in report.resultados:
        if r.paso == "cadena" and r.status in ("PASS", "SKIP"):
            if paso_actual != r.nombre:
                print(_sub_banner(r.nombre))
                paso_actual = r.nombre
            continue

        iconos = {"PASS": "  PASS", "FAIL": "  FAIL", "WARN": "  WARN", "SKIP": "  SKIP"}
        icono = iconos.get(r.status, "  ????")
        print(f"  {icono} | {r.mensaje}")
        if r.detalle:
            for linea in r.detalle.split("\n"):
                print(f"         | {linea}")
        if r.fix:
            print(f"    FIX | {r.fix}")

    duracion = report.fin - report.inicio
    print()
    print(_banner("RESUMEN"))
    print(f"  Total verificaciones: {report.total}")
    print(f"  Pasaron:  {report.pasaron}")
    print(f"  Fallaron: {report.fallaron}")
    print(f"  Advertencias: {report.advertencias}")
    print(f"  Omitidos: {report.omitidos}")
    print(f"  Duracion: {duracion:.1f}s")
    print()

    # Archivos faltantes
    faltantes = [r for r in report.resultados if r.status == "FAIL" and r.paso == "existencia"]
    if faltantes:
        print(_sub_banner("ARCHIVOS FALTANTES - QUE HACER"))
        for f in faltantes:
            print(f"  FALTA: {f.mensaje}")
            print(f"         Ubicacion esperada: {f.detalle}")
            if f.fix:
                print(f"         Accion: {f.fix}")
            print()

    # Problemas de contenido
    contenido_fails = [r for r in report.resultados if r.status == "FAIL" and r.paso == "contenido"]
    if contenido_fails:
        print(_sub_banner("PROBLEMAS DE CONTENIDO - QUE HACER"))
        for c in contenido_fails:
            print(f"  ERROR: {c.mensaje}")
            for linea in c.detalle.split("\n"):
                print(f"         {linea}")
            if c.fix:
                print(f"         Accion: {c.fix}")
            print()

    # Veredicto
    print("=" * 70)
    if report.fallaron == 0 and report.advertencias == 0:
        print("  RESULTADO: TODAS LAS VERIFICACIONES PASARON")
        print("  La cadena Proxy LLM esta completamente configurada.")
    elif report.fallaron == 0:
        print("  RESULTADO: OK con advertencias")
        print("  La cadena funciona pero hay detalles que revisar.")
    else:
        print(f"  RESULTADO: {report.fallaron} ERROR(ES) ENCONTRADO(S)")
        print("  Revisar las secciones 'ARCHIVOS FALTANTES' y 'PROBLEMAS DE CONTENIDO' arriba.")
    print("=" * 70)

    return report.fallaron == 0


# ═══════════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Test de cadena proxy LLM para APA en Windows",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python test_proxy_chain_windows.py
  python test_proxy_chain_windows.py --base-dir C:/Python/Proyectos/APA
  python test_proxy_chain_windows.py --json

El test verifica:
  1. Archivos del proxy — OMITIDO (solo en sandbox Z.ai)
  2. Archivos del MB Sandbox — index.ts, package.json, .z-ai-config
  3. Configuracion de APA — .env, settings.py, mb_launcher.py, chat_engine.py
  4. Servicios corriendo — MB en :8100, llamada real al LLM
  5. Scripts auxiliares — setup-mb.ps1, start-apa.ps1 (opcionales)
""",
    )
    parser.add_argument(
        "--base-dir", default="",
        help="Directorio base del proyecto (se detecta automaticamente si no se especifica)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output en formato JSON",
    )

    args = parser.parse_args()
    base_dir = args.base_dir or detectar_base_dir()

    report = TestReport(inicio=time.time(), base_dir=base_dir)
    verificar_cadena_proxy(report, base_dir)
    report.fin = time.time()

    if args.json:
        print(json.dumps({
            "base_dir": report.base_dir,
            "total": report.total,
            "pasaron": report.pasaron,
            "fallaron": report.fallaron,
            "advertencias": report.advertencias,
            "omitidos": report.omitidos,
            "duracion_seg": round(report.fin - report.inicio, 1),
            "resultados": [{
                "nombre": r.nombre, "paso": r.paso, "status": r.status,
                "mensaje": r.mensaje, "detalle": r.detalle, "fix": r.fix,
            } for r in report.resultados],
        }, ensure_ascii=False, indent=2))
        sys.exit(0 if report.fallaron == 0 else 1)
    else:
        exito = imprimir_reporte(report)
        sys.exit(0 if exito else 1)


if __name__ == "__main__":
    main()
