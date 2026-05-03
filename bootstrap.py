#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Bootstrap do Tirinha Cutter.

Uso remoto:

Termux / Linux / macOS:
    curl -fsSL https://raw.githubusercontent.com/hpuglia/tirinha-cutter/main/bootstrap.py | python

Windows PowerShell:
    irm https://raw.githubusercontent.com/hpuglia/tirinha-cutter/main/bootstrap.py | py -

ou:
    irm https://raw.githubusercontent.com/hpuglia/tirinha-cutter/main/bootstrap.py | python -
"""

from __future__ import annotations

import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


REPO_RAW_BASE = "https://raw.githubusercontent.com/hpuglia/tirinha-cutter/main"

APP_DIR_NAME = ".tirinha-cutter"

FILES_TO_DOWNLOAD = {
    "tirinha_cutter.py": f"{REPO_RAW_BASE}/tirinha_cutter.py",
    "requirements.txt": f"{REPO_RAW_BASE}/requirements.txt",
}

OPTIONAL_FILES = {
    "presets.json": f"{REPO_RAW_BASE}/presets.json",
}


def print_header() -> None:
    print("=" * 56)
    print("Tirinha Cutter - Bootstrap")
    print("Baixador e executor remoto")
    print("=" * 56)


def get_app_dir() -> Path:
    """
    Usa uma pasta oculta no usuário:
    - Windows: C:/Users/Nome/.tirinha-cutter
    - Linux/Termux: ~/.tirinha-cutter
    """
    return Path.home() / APP_DIR_NAME


def download_text(url: str) -> str:
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "tirinha-cutter-bootstrap/1.0"
            },
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")

    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Erro HTTP {error.code} ao baixar: {url}") from error

    except urllib.error.URLError as error:
        raise RuntimeError(f"Erro de conexão ao baixar: {url}\nDetalhe: {error}") from error

    except Exception as error:
        raise RuntimeError(f"Erro inesperado ao baixar: {url}\nDetalhe: {error}") from error


def write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def download_required_files(app_dir: Path) -> None:
    print("\nBaixando/atualizando arquivos principais...")

    for filename, url in FILES_TO_DOWNLOAD.items():
        target = app_dir / filename
        content = download_text(url)
        write_file(target, content)
        print(f"  [OK] {filename}")


def download_optional_files(app_dir: Path) -> None:
    print("\nVerificando arquivos opcionais...")

    for filename, url in OPTIONAL_FILES.items():
        target = app_dir / filename

        if target.exists():
            print(f"  [OK] {filename} já existe, mantendo arquivo local.")
            continue

        try:
            content = download_text(url)
            write_file(target, content)
            print(f"  [OK] {filename}")
        except RuntimeError as error:
            print(f"  [AVISO] Não foi possível baixar {filename}.")
            print(f"          {error}")


def get_real_stdin():
    """
    Corrige execução via pipe.

    Quando o bootstrap é chamado assim:
        irm URL | py -
        curl URL | python

    o stdin normal fica ocupado ou fechado.
    Esta função tenta reabrir a entrada real do terminal.
    """
    if os.name == "nt":
        try:
            return open("CONIN$", "r", encoding="utf-8", errors="ignore")
        except Exception:
            return None

    try:
        return open("/dev/tty", "r", encoding="utf-8", errors="ignore")
    except Exception:
        return None


def run_main_script(app_dir: Path) -> int:
    script_path = app_dir / "tirinha_cutter.py"

    if not script_path.exists():
        print("\n[ERRO] Script principal não encontrado.")
        print(f"Esperado em: {script_path}")
        return 1

    print("\nExecutando Tirinha Cutter...\n")

    command = [sys.executable, str(script_path)]

    real_stdin = get_real_stdin()

    try:
        process = subprocess.run(
            command,
            cwd=str(app_dir),
            stdin=real_stdin if real_stdin else None,
        )
        return process.returncode

    except KeyboardInterrupt:
        print("\nExecução interrompida pelo usuário.")
        return 130

    except Exception as error:
        print(f"\n[ERRO] Falha ao executar o script principal: {error}")
        return 1

    finally:
        if real_stdin:
            real_stdin.close()


def main() -> int:
    print_header()

    app_dir = get_app_dir()

    try:
        app_dir.mkdir(parents=True, exist_ok=True)
    except Exception as error:
        print(f"\n[ERRO] Não foi possível criar a pasta do app: {app_dir}")
        print(error)
        return 1

    print(f"\nPasta local do app:")
    print(f"  {app_dir}")

    try:
        download_required_files(app_dir)
        download_optional_files(app_dir)
    except RuntimeError as error:
        print(f"\n[ERRO] {error}")
        return 1

    return run_main_script(app_dir)


if __name__ == "__main__":
    raise SystemExit(main())
