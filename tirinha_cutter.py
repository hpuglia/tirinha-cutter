#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tirinha Cutter
Interface visual local para recortar tirinhas 2x2 em 4 imagens.

Uso:
    python tirinha_cutter.py

Depois abre automaticamente:
    http://127.0.0.1:8765
"""

from __future__ import annotations

import base64
import io
import json
import mimetypes
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from html import escape as html_escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


APP_NAME = "Tirinha Cutter"
APP_VERSION = "0.2.6"
HOST = "127.0.0.1"
PORT = 8765
OUTPUT_FOLDER_NAME = "TirinhaCutter"
PRESETS_FILE = "presets.json"
SHUTDOWN_TOKEN = secrets.token_urlsafe(32)


def ensure_dependencies() -> None:
    try:
        import PIL  # noqa: F401
        return
    except ImportError:
        print("\n[!] Dependência ausente: Pillow")
        print("O Pillow é necessário para abrir e recortar imagens.")

        try:
            answer = input("Deseja instalar agora? [s/N]: ").strip().lower()
        except EOFError:
            answer = "s"

        if answer not in {"s", "sim", "y", "yes"}:
            print("Instalação cancelada. Rode manualmente:")
            print("    pip install Pillow")
            sys.exit(1)

        print("\nInstalando Pillow...\n")

        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "Pillow>=10.0.0"]
            )
        except subprocess.CalledProcessError:
            print("\n[ERRO] Não foi possível instalar Pillow automaticamente.")
            print("Tente instalar manualmente:")
            print("    pip install Pillow")
            sys.exit(1)

        print("\nPillow instalado com sucesso.\n")


ensure_dependencies()

from PIL import Image  # noqa: E402


def get_script_dir() -> Path:
    return Path(__file__).resolve().parent


def get_presets_path() -> Path:
    return get_script_dir() / PRESETS_FILE


def is_termux() -> bool:
    prefix = os.environ.get("PREFIX", "")
    termux_version = os.environ.get("TERMUX_VERSION", "")
    home = str(Path.home())

    return (
        "com.termux" in prefix
        or bool(termux_version)
        or "/data/data/com.termux" in home
    )


def detect_downloads_folder() -> Path:
    home = Path.home()
    system = platform.system().lower()

    candidates: list[Path] = []

    if system == "windows":
        candidates.extend([home / "Downloads", home / "downloads"])
    else:
        candidates.extend(
            [
                Path("/storage/emulated/0/Download"),
                home / "storage" / "downloads",
                home / "Downloads",
                home / "downloads",
            ]
        )

    for path in candidates:
        if path.exists() and path.is_dir():
            return path

    fallback = get_script_dir() / "saida"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def get_default_output_dir() -> Path:
    output_dir = detect_downloads_folder() / OUTPUT_FOLDER_NAME
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def load_presets() -> dict:
    presets_path = get_presets_path()

    if not presets_path.exists():
        presets = {
            "padrao_2x2": {
                "vertical_ratio": 0.5,
                "horizontal_ratio": 0.5,
                "description": "Corte padrão exatamente no meio da imagem.",
            }
        }
        save_presets(presets)
        return presets

    try:
        with presets_path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {
            "padrao_2x2": {
                "vertical_ratio": 0.5,
                "horizontal_ratio": 0.5,
                "description": "Corte padrão exatamente no meio da imagem.",
            }
        }


def save_presets(presets: dict) -> None:
    presets_path = get_presets_path()

    with presets_path.open("w", encoding="utf-8") as file:
        json.dump(presets, file, indent=2, ensure_ascii=False)


def sanitize_filename(name: str) -> str:
    name = Path(name).stem
    name = re.sub(r"[^\w\-.]+", "_", name, flags=re.UNICODE)
    name = name.strip("._-")

    if not name:
        name = "tirinha"

    return name


def decode_data_url(data_url: str) -> bytes:
    if "," not in data_url:
        raise ValueError("Imagem inválida.")

    _header, encoded = data_url.split(",", 1)
    return base64.b64decode(encoded)


def calculate_aspect_ratio(width: int, height: int) -> str:
    import math

    divisor = math.gcd(width, height)
    ratio_w = width // divisor
    ratio_h = height // divisor
    decimal = width / height if height else 0

    return f"{ratio_w}:{ratio_h} ({decimal:.4f})"


def crop_and_save(
    image_bytes: bytes,
    original_filename: str,
    cut_x_ratio: float,
    cut_y_ratio: float,
    output_dir: Path,
    simple_names: bool,
) -> dict:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    width, height = image.size

    cut_x_ratio = max(0.01, min(0.99, cut_x_ratio))
    cut_y_ratio = max(0.01, min(0.99, cut_y_ratio))

    cut_x = int(width * cut_x_ratio)
    cut_y = int(height * cut_y_ratio)

    crops = [
        image.crop((0, 0, cut_x, cut_y)),
        image.crop((cut_x, 0, width, cut_y)),
        image.crop((0, cut_y, cut_x, height)),
        image.crop((cut_x, cut_y, width, height)),
    ]

    base_name = sanitize_filename(original_filename)

    output_dir.mkdir(parents=True, exist_ok=True)

    if simple_names:
        filenames = ["1.png", "2.png", "3.png", "4.png"]
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filenames = [
            f"{base_name}_{timestamp}_1.png",
            f"{base_name}_{timestamp}_2.png",
            f"{base_name}_{timestamp}_3.png",
            f"{base_name}_{timestamp}_4.png",
        ]

    output_files = []

    for crop, filename in zip(crops, filenames):
        output_file = output_dir / filename
        crop.save(output_file, format="PNG")
        output_files.append(output_file)

    return {
        "width": width,
        "height": height,
        "cut_x": cut_x,
        "cut_y": cut_y,
        "cut_x_percent": round(cut_x_ratio * 100, 2),
        "cut_y_percent": round(cut_y_ratio * 100, 2),
        "aspect_ratio": calculate_aspect_ratio(width, height),
        "output_dir": str(output_dir),
        "files": [str(file) for file in output_files],
    }


def select_output_folder_native() -> dict:
    """
    Abre seletor nativo de pasta.

    Funciona bem no Windows com tkinter.
    Em Android/Termux, não há seletor universal de pasta equivalente via navegador;
    nesse caso retorna a pasta padrão detectada.
    """
    if is_termux():
        output = get_default_output_dir()
        return {
            "ok": True,
            "path": str(output),
            "warning": "No Android/Termux, usando pasta padrão de saída.",
        }

    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        selected = filedialog.askdirectory(
            title="Escolha a pasta de saída dos recortes"
        )

        root.destroy()

        if selected:
            return {"ok": True, "path": selected}

        return {"ok": False, "error": "Nenhuma pasta selecionada."}

    except Exception as error:
        output = get_default_output_dir()
        return {
            "ok": True,
            "path": str(output),
            "warning": f"Seletor nativo indisponível. Usando padrão. Detalhe: {error}",
        }


def get_html() -> str:
    output_dir = html_escape(str(get_default_output_dir()), quote=True)
    presets = json.dumps(load_presets(), ensure_ascii=False)

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>{APP_NAME}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>

:root {{
  color-scheme: dark;
  --bg: #0b1019;
  --card: #151c29;
  --card-soft: #1d2636;
  --text: #f3f6fb;
  --muted: #9eaabd;
  --border: #303c4f;
  --accent: #66e4ad;
  --accent-deep: #123d31;
  --blue: #76b7fd;
  --danger: #ff8f95;
  --shadow: 0 16px 48px rgba(0, 0, 0, .20);
}}
* {{ box-sizing: border-box; }}
[hidden] {{ display: none !important; }}
html {{ scroll-behavior: smooth; }}
body {{
  min-width: 320px;
  margin: 0;
  color: var(--text);
  background:
    radial-gradient(ellipse 70% 35% at 25% -4%, rgba(54, 115, 112, .2), transparent),
    linear-gradient(140deg, #0d1521 0%, var(--bg) 60%);
  font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 14px;
}}
button, input {{ font: inherit; }}
button {{ cursor: pointer; }}
button:disabled {{ cursor: not-allowed; opacity: .52; }}
button:focus-visible, input:focus-visible, canvas:focus-visible, .dropZone:focus-visible {{
  outline: 2px solid var(--blue);
  outline-offset: 3px;
}}
header {{
  position: sticky;
  top: 0;
  z-index: 12;
  border-bottom: 1px solid rgba(117, 144, 168, .14);
  background: rgba(12, 18, 29, .95);
  backdrop-filter: blur(14px);
}}
.topbar {{
  max-width: 1512px;
  min-height: 68px;
  padding: 12px 24px;
  margin: auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}}
.brand {{ display: flex; align-items: center; gap: 12px; min-width: 0; }}
.brandIcon {{
  flex: none;
  width: 39px; height: 39px;
  display: grid; place-items: center;
  background: linear-gradient(145deg, #184c3c, #1c6b54);
  color: #a6f5cd;
  border: 1px solid rgba(102,228,173,.26);
  border-radius: 12px;
  font-size: 21px;
}}
h1 {{ margin: 0; font-size: 17px; font-weight: 760; letter-spacing: -.4px; }}
.brandSubtitle {{ margin: 3px 0 0; color: var(--muted); font-size: 11px; }}
.headerTools {{ display: flex; gap: 8px; align-items: center; }}
.versionPill, .pill {{
  display: inline-flex; align-items: center; justify-content: center;
  min-height: 26px; padding: 4px 9px;
  border: 1px solid var(--border); border-radius: 999px;
  background: #202b3b; color: #d2dfef;
  font-size: 11px; font-weight: 700; white-space: nowrap;
}}
.versionPill {{ color: #92dfb4; border-color: #2a6550; background: #16392e; }}
.ghostButton, .subtleButton {{
  border: 1px solid var(--border); border-radius: 10px;
  background: #202c3d; color: var(--text);
  padding: 9px 12px; font-size: 12px; font-weight: 700;
  transition: background .15s, border-color .15s;
}}
.ghostButton:hover, .subtleButton:hover {{ background: #293a50; border-color: #51607a; }}
.workspace {{
  max-width: 1512px;
  margin: auto;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(300px, 336px);
  align-items: start;
  gap: 17px;
  padding: 20px 22px 136px;
}}
.stage, .panel {{
  border: 1px solid var(--border); background: rgba(21, 28, 41, .96);
  box-shadow: var(--shadow); border-radius: 17px;
}}
.stage {{ min-width: 0; overflow: hidden; }}
.stageTop {{
  padding: 17px 19px;
  display: flex; align-items: center; justify-content: space-between; gap: 14px;
  border-bottom: 1px solid rgba(117,144,168,.14);
}}
.eyebrow {{ font-size: 10px; font-weight: 800; letter-spacing: .10em; text-transform: uppercase; color: #8aa0b8; }}
.stageTop h2 {{ margin: 5px 0 0; font-size: 15px; font-weight: 750; }}
.stageSurface {{
  min-height: min(66vh, 660px);
  display: grid; place-items: center;
  padding: 25px;
  background:
    linear-gradient(45deg, rgba(255,255,255,.025) 25%, transparent 25%, transparent 75%, rgba(255,255,255,.025) 75%),
    linear-gradient(45deg, rgba(255,255,255,.025) 25%, transparent 25%, transparent 75%, rgba(255,255,255,.025) 75%),
    #101722;
  background-size: 26px 26px;
  background-position: 0 0, 13px 13px;
  position: relative;
  transition: background .16s;
}}
.stageSurface.isDragging {{ background-color: #17372f; }}
.dropZone {{
  width: min(100%, 490px);
  min-height: 300px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 12px;
  padding: 28px; text-align: center; cursor: pointer;
  border: 1.5px dashed #51657f; border-radius: 18px;
  background: rgba(21,31,46,.92);
  transition: border-color .15s, background .15s, transform .15s;
}}
.dropZone:hover, .stageSurface.isDragging .dropZone {{
  border-color: var(--accent); background: #1c3031;
  transform: translateY(-1px);
}}
.dropSymbol {{
  width: 58px; height: 58px; display: grid; place-items: center;
  border-radius: 16px; background: #263b4d;
  color: var(--accent); font-size: 27px; font-weight: 300;
}}
.dropZone strong {{ font-size: 17px; letter-spacing: -.2px; }}
.dropZone .supportText {{ color: var(--muted); font-size: 12px; line-height: 1.55; max-width: 320px; }}
.dropZone .dropAction {{
  background: var(--accent); color: #0b251d;
  padding: 10px 16px; border-radius: 10px;
  font-weight: 800; font-size: 12px;
}}
.canvasWrap {{
  max-width: 100%; display: flex; align-items: center; justify-content: center;
  border: 1px solid #45526a; background: #090f17;
  border-radius: 9px; overflow: hidden;
}}
canvas {{
  display: block; max-width: 100%; max-height: min(66vh, 710px);
  width: auto; height: auto; touch-action: none; cursor: crosshair;
  user-select: none;
}}
.stageBottom {{
  min-height: 55px; padding: 10px 16px;
  display: flex; align-items: center; flex-wrap: wrap; gap: 8px;
  border-top: 1px solid rgba(117,144,168,.14);
}}
.stageHint {{ margin-left: auto; color: var(--muted); font-size: 11px; }}
.inspector {{ display: grid; gap: 13px; min-width: 0; }}
.panel {{ padding: 17px; box-shadow: 0 9px 26px rgba(0,0,0,.1); }}
.panelHeading {{
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; margin-bottom: 14px;
}}
.panelHeading h2 {{ margin: 0; font-size: 14px; font-weight: 780; letter-spacing: -.15px; }}
.panelNumber {{
  display: grid; place-items: center; width: 22px; height: 22px;
  flex: none; border-radius: 7px; background: #26364a; color: #9ec8f1;
  font-size: 11px; font-weight: 850;
}}
.panelTitle {{ display: inline-flex; gap: 9px; align-items: center; }}
.helpText {{ color: var(--muted); line-height: 1.55; margin: 9px 0 0; font-size: 11px; }}
.fieldLabel {{ display: block; color: #bdcada; font-size: 12px; font-weight: 600; margin: 0 0 8px; }}
.fileInput {{
  display: block; width: 100%;
  padding: 9px; background: #101825; border: 1px solid var(--border);
  color: #d2dfef; border-radius: 11px; font-size: 11px;
}}
.fileInput::file-selector-button {{
  border: none; background: #2d4053; color: var(--text);
  font: inherit; font-weight: 750; padding: 7px 9px; border-radius: 7px; margin-right: 9px;
  cursor: pointer;
}}
.axisBlock {{ padding: 11px 11px 9px; border: 1px solid #303e51; border-radius: 13px; background: #192334; margin-bottom: 10px; }}
.axisTop {{ display: flex; justify-content: space-between; gap: 10px; align-items: center; margin-bottom: 7px; }}
.axisTitle {{ font-size: 12px; font-weight: 740; display: flex; gap: 8px; align-items: center; }}
.axisSwatch {{ width: 9px; height: 9px; border-radius: 50%; display: inline-block; background: #65e0a4; }}
.axisSwatch.y {{ background: #7dbbf7; }}
.axisValue {{ color: #acf2cc; background: #173c31; border-color: #2f7155; min-width: 55px; }}
.axisValue.y {{ color: #afd8ff; background: #1b3c5a; border-color: #315b7e; }}
input[type=range] {{ display: block; width: 100%; accent-color: var(--accent); margin: 11px 0 3px; cursor: pointer; }}
#yRange {{ accent-color: var(--blue); }}
.axisCaption {{ display: flex; justify-content: space-between; color: #7e90a7; font-size: 10px; }}
.toolPills {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 12px; }}
.toolPills button {{
  border: 1px solid #38485c; border-radius: 999px;
  color: #d9e5f3; background: #253349;
  min-height: 30px; padding: 5px 10px; font-size: 11px; font-weight: 780;
}}
.toolPills button:hover {{ background: #324964; border-color: #6688ab; }}
.toolPills button.resetPill {{ background: var(--accent-deep); color: #a7f6ca; border-color: #356b56; }}
.toolPills .pillGroupLabel {{ color: #9daec3; font-size: 10px; margin-right: 3px; }}
.inputRow {{ display: grid; grid-template-columns: minmax(0, 1fr) 39px; gap: 8px; align-items: stretch; }}
.textField {{
  width: 100%; min-width: 0; padding: 10px 11px; border-radius: 10px;
  color: var(--text); background: #0f1723; border: 1px solid var(--border);
  font-size: 12px; outline-offset: 2px;
}}
.iconButton {{
  display: grid; place-items: center; border: 1px solid var(--border);
  border-radius: 10px; background: #263448; color: #e2ebf6; font-size: 17px;
}}
.iconButton:hover {{ background: #344760; }}
.checkRow {{ display: flex; gap: 9px; align-items: center; margin-top: 13px; color: #c9d7e7; font-size: 12px; }}
.checkRow input {{ accent-color: #61d69f; width: 16px; height: 16px; }}
.resultBox {{
  white-space: pre-wrap; overflow-wrap: anywhere; max-height: 160px; overflow-y: auto;
  border: 1px solid #2f4255; background: #101b29; color: #bde6cf;
  border-radius: 10px; font-size: 11px; line-height: 1.55; padding: 11px;
}}
.actionDock {{
  position: fixed; z-index: 20; inset: auto 0 0;
  background: rgba(13,21,33,.96); border-top: 1px solid #334356;
  box-shadow: 0 -15px 48px rgba(0,0,0,.35);
  backdrop-filter: blur(14px);
  padding-bottom: env(safe-area-inset-bottom, 0px);
}}
.dockInner {{
  max-width: 1512px; margin: auto; padding: 14px 22px;
  display: flex; align-items: center; justify-content: space-between; gap: 24px;
}}
.statusBlock {{ min-width: 0; display: flex; align-items: flex-start; gap: 11px; }}
.statusDot {{
  flex: none; margin-top: 6px; width: 9px; height: 9px; border-radius: 50%;
  background: #75869c; box-shadow: 0 0 0 4px rgba(117,134,156,.12);
}}
.statusDot[data-kind=ready] {{ background: #72dfac; box-shadow: 0 0 0 4px rgba(114,223,172,.12); }}
.statusDot[data-kind=busy] {{ background: #85beff; box-shadow: 0 0 0 4px rgba(133,190,255,.12); animation: glow 1.1s infinite; }}
.statusDot[data-kind=error] {{ background: #ff9597; box-shadow: 0 0 0 4px rgba(255,149,151,.13); }}
.statusDot[data-kind=success] {{ background: #72dfac; }}
@keyframes glow {{ 50% {{ opacity: .35; }} }}
.statusTitle {{ font-size: 13px; font-weight: 780; overflow-wrap: anywhere; }}
.statusDesc {{ font-size: 11px; line-height: 1.4; color: var(--muted); margin-top: 3px; overflow-wrap: anywhere; }}
.primaryButton {{
  min-width: 242px; min-height: 52px; display: flex; align-items: center; justify-content: center;
  gap: 11px; border: none; border-radius: 13px;
  background: linear-gradient(120deg, #8cf5bf, #57cc9f);
  color: #10271d; box-shadow: 0 8px 26px rgba(67,204,148,.15);
  font-size: 14px; font-weight: 850; letter-spacing: -.1px;
  transition: filter .15s, transform .15s;
}}
.primaryButton:enabled:hover {{ filter: brightness(1.05); transform: translateY(-1px); }}
.primaryButton:disabled {{ background: #344438; color: #a0b3a9; box-shadow: none; opacity: .8; }}
.primaryButton .actionIcon {{ font-size: 19px; }}
.primaryButton small {{ font-size: 10px; font-weight: 700; opacity: .7; }}
@media (max-width: 1020px) {{
  .workspace {{ grid-template-columns: 1fr; padding: 14px 14px 146px; }}
  .inspector {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  #editorControls {{ grid-column: 1 / -1; }}
  .stageSurface {{ min-height: 45vh; }}
}}
@media (max-width: 600px) {{
  .topbar {{ padding: 10px 13px; min-height: 62px; }}
  .brandSubtitle, .versionPill {{ display: none; }}
  .brandIcon {{ width: 34px; height: 34px; }}
  h1 {{ font-size: 15px; }}
  .headerTools .ghostButton {{ padding: 8px; font-size: 11px; }}
  .workspace {{ gap: 11px; padding: 11px 10px 180px; }}
  .stageTop {{ padding: 13px; }}
  .stageSurface {{ padding: 12px; min-height: 320px; }}
  .dropZone {{ min-height: 270px; padding: 21px; }}
  .inspector {{ grid-template-columns: 1fr; gap: 10px; }}
  #editorControls {{ grid-column: auto; }}
  .panel {{ padding: 14px; }}
  .stageHint {{ width: 100%; margin-left: 0; }}
  canvas {{ max-height: 54vh; }}
  .dockInner {{ padding: 10px 12px; align-items: stretch; gap: 11px; flex-direction: column; }}
  .primaryButton {{ min-width: 0; min-height: 48px; width: 100%; }}
  .statusBlock {{ align-items: center; }}
  .statusDot {{ margin-top: 0; }}
}}
@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{ scroll-behavior: auto !important; animation-duration: .01ms !important; transition-duration: .01ms !important; }}
}}

  </style>
</head>

<body>
  <header>
    <div class="topbar">
      <div class="brand">
        <div class="brandIcon" aria-hidden="true">✂</div>
        <div>
          <h1>{APP_NAME}</h1>
          <p class="brandSubtitle">Cortes precisos · 4 cenas · processamento local</p>
        </div>
      </div>
      <div class="headerTools">
        <span class="versionPill">v0.2.6</span>
        <button class="ghostButton" id="stopButton" type="button">Encerrar servidor</button>
      </div>
    </div>
  </header>

  <main class="workspace">
    <section class="stage" aria-label="Área de visualização da tirinha">
      <div class="stageTop">
        <div>
          <div class="eyebrow">Pré-visualização</div>
          <h2 id="stageTitle">Sua tirinha, quatro cenas</h2>
        </div>
        <button class="ghostButton" type="button" id="replaceButton" hidden>Trocar imagem</button>
      </div>
      <div class="stageSurface" id="stageSurface">
        <div id="dropZone" class="dropZone" tabindex="0" role="button" aria-label="Selecionar imagem para recortar">
          <span class="dropSymbol" aria-hidden="true">＋</span>
          <strong>Adicione uma imagem</strong>
          <span class="supportText">Arraste para esta área, cole do clipboard (Ctrl+V) ou escolha um arquivo PNG, JPG ou WebP.</span>
          <span class="dropAction">Escolher imagem</span>
        </div>
        <div id="canvasWrap" class="canvasWrap" hidden>
          <canvas id="canvas" tabindex="0" aria-label="Imagem com linhas de corte ajustáveis"></canvas>
        </div>
      </div>
      <div class="stageBottom" id="stageBottom" hidden>
        <span class="pill" id="filenamePill">Imagem</span>
        <span class="pill" id="dimensionsPill">—</span>
        <span class="stageHint">Arraste as linhas na imagem ou ajuste no painel.</span>
      </div>
    </section>

    <aside class="inspector" aria-label="Ferramentas de recorte">
      <section class="panel" id="imagePanel">
        <div class="panelHeading">
          <span class="panelTitle"><span class="panelNumber">01</span><h2>Imagem</h2></span>
        </div>
        <label class="fieldLabel" for="fileInput">Escolher arquivo</label>
        <input class="fileInput" id="fileInput" type="file" accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp">
        <p class="helpText">A imagem é processada neste computador. A prévia pode ser reduzida, mas o arquivo final mantém sua resolução.</p>
      </section>

      <section class="panel" id="editorControls" hidden>
        <div class="panelHeading">
          <span class="panelTitle"><span class="panelNumber">02</span><h2>Ajustar cortes</h2></span>
          <span class="pill">4 quadrantes</span>
        </div>
        <div class="axisBlock">
          <div class="axisTop">
            <label class="axisTitle" for="xRange"><span class="axisSwatch"></span> Linha vertical</label>
            <output class="pill axisValue" id="xLabel" for="xRange">50.0%</output>
          </div>
          <input id="xRange" type="range" min="1" max="99" step="0.1" value="50" aria-label="Posição do corte vertical">
          <div class="axisCaption"><span>Esquerda</span><span>Direita</span></div>
        </div>
        <div class="axisBlock">
          <div class="axisTop">
            <label class="axisTitle" for="yRange"><span class="axisSwatch y"></span> Linha horizontal</label>
            <output class="pill axisValue y" id="yLabel" for="yRange">50.0%</output>
          </div>
          <input id="yRange" type="range" min="1" max="99" step="0.1" value="50" aria-label="Posição do corte horizontal">
          <div class="axisCaption"><span>Topo</span><span>Base</span></div>
        </div>
        <div class="toolPills" aria-label="Ajustes rápidos das linhas">
          <span class="pillGroupLabel">X</span>
          <button type="button" data-nudge-x="-1" title="Vertical 0,25% à esquerda">−</button>
          <button type="button" data-nudge-x="1" title="Vertical 0,25% à direita">＋</button>
          <span class="pillGroupLabel">Y</span>
          <button type="button" data-nudge-y="-1" title="Horizontal 0,25% para cima">↑</button>
          <button type="button" data-nudge-y="1" title="Horizontal 0,25% para baixo">↓</button>
          <button type="button" id="resetButton" class="resetPill" title="Restaurar corte central">50/50</button>
        </div>
        <p class="helpText">Setas do teclado nos controles. Use 50/50 para voltar ao centro.</p>
      </section>

      <section class="panel" id="outputSettings" hidden>
        <div class="panelHeading">
          <span class="panelTitle"><span class="panelNumber">03</span><h2>Salvar recortes</h2></span>
        </div>
        <label class="fieldLabel" for="outputDir">Pasta de destino</label>
        <div class="inputRow">
          <input class="textField" id="outputDir" type="text" value="{output_dir}" spellcheck="false" autocomplete="off">
          <button class="iconButton" id="folderButton" type="button" title="Escolher pasta de saída" aria-label="Selecionar pasta de saída">▣</button>
        </div>
        <label class="checkRow"><input type="checkbox" id="simpleNames" checked>Salvar como 1.png, 2.png, 3.png e 4.png</label>
        <p class="helpText">Se o seletor de pastas não abrir, digite o caminho acima. No Android/Termux, a saída padrão é usada.</p>
      </section>

      <section class="panel" id="resultPanel" hidden>
        <div class="panelHeading"><span class="panelTitle"><span class="panelNumber">✓</span><h2>Última exportação</h2></span></div>
        <div class="resultBox" id="result" aria-live="polite"></div>
      </section>
    </aside>
  </main>

  <footer class="actionDock" aria-label="Status e exportação">
    <div class="dockInner">
      <div class="statusBlock" role="status" aria-live="polite" aria-atomic="true">
        <span class="statusDot" id="statusDot" data-kind="idle" aria-hidden="true"></span>
        <div>
          <div class="statusTitle" id="statusTitle">Aguardando imagem</div>
          <div class="statusDesc" id="statusDesc">Selecione ou arraste uma tirinha para começar.</div>
        </div>
      </div>
      <button class="primaryButton" id="cropButton" type="button" disabled>
        <span class="actionIcon" aria-hidden="true">✂</span>
        <span id="cropButtonText">Recortar e salvar <small>4 cenas</small></span>
      </button>
    </div>
  </footer>

<script>
const SERVER_PRESETS = {presets};
const SHUTDOWN_TOKEN = {json.dumps(SHUTDOWN_TOKEN)};

let image = new Image();
let imageDataUrl = null;
let originalFilename = "tirinha.png";
let originalBytesSize = 0;
let loadSequence = 0;
let currentReader = null;
let isLoadingImage = false;

// Limita somente o canvas da prévia; o recorte final usa o arquivo original.
const PREVIEW_MAX_SIDE = 2560;
const PREVIEW_MAX_PIXELS = 4000000;

let xPercent = 50;
let yPercent = 50;

let dragging = null;

const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
const fileInput = document.getElementById("fileInput");
const xRange = document.getElementById("xRange");
const yRange = document.getElementById("yRange");
const xLabel = document.getElementById("xLabel");
const yLabel = document.getElementById("yLabel");
const info = document.getElementById("info");
const result = document.getElementById("result");
const empty = document.getElementById("empty");
const canvasWrap = document.getElementById("canvasWrap");
const presetSelect = document.getElementById("presetSelect");

function initPresets() {{
  const local = JSON.parse(localStorage.getItem("tirinhaCutterPresets") || "{{}}");
  const merged = {{...SERVER_PRESETS, ...local}};

  presetSelect.innerHTML = "";

  Object.keys(merged).forEach(name => {{
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    presetSelect.appendChild(opt);
  }});

  window.allPresets = merged;
}}

function resetCuts() {{
  xPercent = 50;
  yPercent = 50;
  syncControls();
  draw();
}}

function nudge(dx, dy) {{
  xPercent = clamp(xPercent + dx * 0.25, 1, 99);
  yPercent = clamp(yPercent + dy * 0.25, 1, 99);
  syncControls();
  draw();
}}

function clamp(v, min, max) {{
  return Math.max(min, Math.min(max, v));
}}

function syncControls() {{
  xRange.value = xPercent;
  yRange.value = yPercent;
  xLabel.textContent = xPercent.toFixed(1) + "%";
  yLabel.textContent = yPercent.toFixed(1) + "%";
  updateInfo();
}}

xRange.addEventListener("input", () => {{
  xPercent = Number(xRange.value);
  syncControls();
  draw();
}});

yRange.addEventListener("input", () => {{
  yPercent = Number(yRange.value);
  syncControls();
  draw();
}});

function imageLoadError(message, sequence) {{
  if (sequence !== loadSequence) return;

  isLoadingImage = false;
  currentReader = null;
  image = new Image();
  imageDataUrl = null;
  canvasWrap.style.display = "none";
  empty.style.display = "block";
  empty.textContent = "Não foi possível carregar esta imagem.";
  info.textContent = "Nenhuma imagem carregada.";
  result.textContent = "[ERRO] " + message;
}}

fileInput.addEventListener("change", event => {{
  const file = event.target.files && event.target.files[0];

  // Liberar o input permite selecionar o mesmo arquivo sem recarregar a página.
  fileInput.value = "";
  if (!file) return;

  const sequence = ++loadSequence;

  // Cancela leituras anteriores e ignora conclusões assíncronas atrasadas.
  if (currentReader && currentReader.readyState === FileReader.LOADING) {{
    currentReader.abort();
  }}

  isLoadingImage = true;
  imageDataUrl = null;
  image = new Image();
  originalFilename = file.name;
  originalBytesSize = file.size;

  canvasWrap.style.display = "none";
  empty.style.display = "block";
  empty.textContent = "Carregando imagem...";
  info.textContent = "Lendo " + file.name + "...";
  result.textContent = "Preparando a imagem...";

  const reader = new FileReader();
  currentReader = reader;

  reader.onload = () => {{
    if (sequence !== loadSequence) return;

    const dataUrl = reader.result;
    if (typeof dataUrl !== "string" || !dataUrl.startsWith("data:")) {{
      imageLoadError("Arquivo inválido ou formato não reconhecido.", sequence);
      return;
    }}

    const candidate = new Image();
    candidate.onload = () => {{
      if (sequence !== loadSequence) return;

      if (!candidate.naturalWidth || !candidate.naturalHeight) {{
        imageLoadError("Imagem sem dimensões válidas.", sequence);
        return;
      }}

      try {{
        image = candidate;
        imageDataUrl = dataUrl;
        resetCanvasSize();
        xPercent = 50;
        yPercent = 50;
        isLoadingImage = false;
        currentReader = null;
        empty.style.display = "none";
        canvasWrap.style.display = "block";
        syncControls();
        draw();
        result.textContent = "Imagem carregada. Ajuste as linhas e recorte.";
      }} catch (error) {{
        imageLoadError("Falha ao preparar a prévia: " + error.message, sequence);
      }}
    }};

    candidate.onerror = () => {{
      imageLoadError("Não foi possível decodificar esta imagem.", sequence);
    }};

    candidate.src = dataUrl;
  }};

  reader.onerror = () => {{
    imageLoadError("Falha ao ler o arquivo. Tente selecioná-lo novamente.", sequence);
  }};

  try {{
    reader.readAsDataURL(file);
  }} catch (error) {{
    imageLoadError("Erro ao abrir o arquivo: " + error.message, sequence);
  }}
}});

function resetCanvasSize() {{
  const width = image.naturalWidth;
  const height = image.naturalHeight;
  const scale = Math.min(
    1,
    PREVIEW_MAX_SIDE / Math.max(width, height),
    Math.sqrt(PREVIEW_MAX_PIXELS / (width * height))
  );

  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
}}

function draw() {{
  if (!image || !image.naturalWidth) return;

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(image, 0, 0, canvas.width, canvas.height);

  const x = canvas.width * (xPercent / 100);
  const y = canvas.height * (yPercent / 100);

  ctx.save();

  ctx.lineWidth = Math.max(3, canvas.width * 0.004);

  ctx.strokeStyle = "rgba(34, 197, 94, 0.95)";
  ctx.beginPath();
  ctx.moveTo(x, 0);
  ctx.lineTo(x, canvas.height);
  ctx.stroke();

  ctx.strokeStyle = "rgba(56, 189, 248, 0.95)";
  ctx.beginPath();
  ctx.moveTo(0, y);
  ctx.lineTo(canvas.width, y);
  ctx.stroke();

  ctx.fillStyle = "rgba(0,0,0,0.58)";
  ctx.fillRect(10, 10, 158, 74);

  ctx.fillStyle = "#fff";
  ctx.font = Math.max(16, canvas.width * 0.018) + "px system-ui";
  ctx.fillText("X: " + Math.round(image.naturalWidth * xPercent / 100) + " px", 22, 38);
  ctx.fillText("Y: " + Math.round(image.naturalHeight * yPercent / 100) + " px", 22, 66);

  ctx.restore();

  updateInfo();
}}

function canvasPoint(event) {{
  const rect = canvas.getBoundingClientRect();
  const touch = event.touches ? event.touches[0] : event;

  const scaleX = canvas.width / rect.width;
  const scaleY = canvas.height / rect.height;

  return {{
    x: (touch.clientX - rect.left) * scaleX,
    y: (touch.clientY - rect.top) * scaleY
  }};
}}

function startDrag(event) {{
  if (!image || !image.naturalWidth) return;

  event.preventDefault();

  const p = canvasPoint(event);
  const x = canvas.width * (xPercent / 100);
  const y = canvas.height * (yPercent / 100);

  const distanceX = Math.abs(p.x - x);
  const distanceY = Math.abs(p.y - y);
  const threshold = Math.max(35, canvas.width * 0.025);

  if (distanceX < threshold && distanceY < threshold) {{
    dragging = "both";
  }} else if (distanceX < threshold) {{
    dragging = "x";
  }} else if (distanceY < threshold) {{
    dragging = "y";
  }} else {{
    const dx = Math.abs(p.x - x);
    const dy = Math.abs(p.y - y);
    dragging = dx < dy ? "x" : "y";
  }}

  moveDrag(event);
}}

function moveDrag(event) {{
  if (!dragging) return;

  event.preventDefault();

  const p = canvasPoint(event);

  if (dragging === "x" || dragging === "both") {{
    xPercent = clamp((p.x / canvas.width) * 100, 1, 99);
  }}

  if (dragging === "y" || dragging === "both") {{
    yPercent = clamp((p.y / canvas.height) * 100, 1, 99);
  }}

  syncControls();
  draw();
}}

function endDrag() {{
  dragging = null;
}}

canvas.addEventListener("mousedown", startDrag);
canvas.addEventListener("mousemove", moveDrag);
window.addEventListener("mouseup", endDrag);

canvas.addEventListener("touchstart", startDrag, {{passive:false}});
canvas.addEventListener("touchmove", moveDrag, {{passive:false}});
window.addEventListener("touchend", endDrag);

function updateInfo() {{
  if (!image || !image.naturalWidth) {{
    info.innerHTML = "Nenhuma imagem carregada.";
    return;
  }}

  const w = image.naturalWidth;
  const h = image.naturalHeight;
  const x = Math.round(w * (xPercent / 100));
  const y = Math.round(h * (yPercent / 100));
  const ratio = (w / h).toFixed(4);
  const mb = (originalBytesSize / 1024 / 1024).toFixed(2);

  info.innerHTML = `
    <b>Arquivo:</b> ${{originalFilename}}<br>
    <b>Tamanho:</b> ${{w}} x ${{h}} px<br>
    <b>Aspect ratio:</b> ${{ratio}}<br>
    <b>Peso:</b> ${{mb}} MB<br>
    <b>Corte vertical:</b> ${{x}} px (${{xPercent.toFixed(1)}}%)<br>
    <b>Corte horizontal:</b> ${{y}} px (${{yPercent.toFixed(1)}}%)<br>
  `;
}}

async function selectOutputFolder() {{
  result.textContent = "Abrindo seletor de pasta...";

  try {{
    const response = await fetch("/api/select-output-folder", {{
      method: "POST"
    }});

    const data = await response.json();

    if (!response.ok || !data.ok) {{
      throw new Error(data.error || "Nenhuma pasta selecionada.");
    }}

    document.getElementById("outputDir").value = data.path;
    result.textContent = data.warning || "Pasta de saída definida:\\n" + data.path;

  }} catch (error) {{
    result.textContent = "[ERRO] " + error.message;
  }}
}}

async function stopApplication() {{
  if (!confirm("Fechar o Tirinha Cutter e encerrar o servidor local?")) {{
    return;
  }}

  try {{
    const response = await fetch("/api/shutdown", {{
      method: "POST",
      headers: {{"X-Tirinha-Shutdown-Token": SHUTDOWN_TOKEN}}
    }});

    const data = await response.json();

    if (!response.ok || !data.ok) {{
      throw new Error(data.error || "Não foi possível encerrar o servidor.");
    }}

    document.body.innerHTML = `
      <main style="display:block;max-width:680px;padding-top:80px;">
        <section class="viewer" style="min-height:auto;padding:40px;text-align:center;display:block;">
          <h1>Tirinha Cutter encerrado</h1>
          <p style="color:var(--muted);">O servidor local foi finalizado. Você já pode fechar esta aba.</p>
        </section>
      </main>`;
  }} catch (error) {{
    alert("Erro ao encerrar: " + error.message);
  }}
}}

async function cropImage() {{
  if (isLoadingImage) {{
    result.textContent = "Aguarde o carregamento da imagem antes de recortar.";
    return;
  }}

  if (!imageDataUrl || !image.naturalWidth) {{
    alert("Selecione uma imagem primeiro.");
    return;
  }}

  result.textContent = "Recortando e salvando...";

  const payload = {{
    image_data: imageDataUrl,
    filename: originalFilename,
    cut_x_ratio: xPercent / 100,
    cut_y_ratio: yPercent / 100,
    output_dir: document.getElementById("outputDir").value,
    simple_names: document.getElementById("simpleNames").checked
  }};

  try {{
    const response = await fetch("/api/crop", {{
      method: "POST",
      headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify(payload)
    }});

    const data = await response.json();

    if (!response.ok || !data.ok) {{
      throw new Error(data.error || "Erro desconhecido.");
    }}

    result.textContent =
      "[OK] Recortes salvos com sucesso\\n\\n" +
      "Pasta:\\n" + data.output_dir + "\\n\\n" +
      "Arquivos:\\n" + data.files.join("\\n");

  }} catch (error) {{
    result.textContent = "[ERRO] " + error.message;
  }}
}}

initPresets();
syncControls();
</script>
</body>
</html>
"""


class TirinhaCutterHandler(BaseHTTPRequestHandler):
    server_version = f"{APP_NAME}/{APP_VERSION}"

    def log_message(self, format: str, *args) -> None:
        print("[WEB]", format % args)

    def send_text(
        self,
        text: str,
        status: int = 200,
        content_type: str = "text/html; charset=utf-8",
    ) -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/":
            self.send_text(get_html())
            return

        if parsed.path == "/download":
            query = parsed.query
            path_value = ""

            for part in query.split("&"):
                if part.startswith("path="):
                    path_value = unquote(part[5:])
                    break

            file_path = Path(path_value)

            if not file_path.exists() or not file_path.is_file():
                self.send_text(
                    "Arquivo não encontrado.",
                    status=404,
                    content_type="text/plain; charset=utf-8",
                )
                return

            mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            data = file_path.read_bytes()

            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{file_path.name}"',
            )
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_text(
            "Página não encontrada.",
            status=404,
            content_type="text/plain; charset=utf-8",
        )

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/shutdown":
            supplied_token = self.headers.get("X-Tirinha-Shutdown-Token", "")

            if not secrets.compare_digest(supplied_token, SHUTDOWN_TOKEN):
                self.send_json(
                    {"ok": False, "error": "Solicitação de encerramento inválida."},
                    status=403,
                )
                return

            self.send_json({"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return

        if parsed.path == "/api/select-output-folder":
            result = select_output_folder_native()
            self.send_json(result, status=200 if result.get("ok") else 400)
            return

        if parsed.path != "/api/crop":
            self.send_json({"ok": False, "error": "Rota inválida."}, status=404)
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(content_length)
            payload = json.loads(raw.decode("utf-8"))

            image_data = payload.get("image_data")
            filename = payload.get("filename", "tirinha.png")
            cut_x_ratio = float(payload.get("cut_x_ratio", 0.5))
            cut_y_ratio = float(payload.get("cut_y_ratio", 0.5))
            simple_names = bool(payload.get("simple_names", True))

            output_dir_raw = str(payload.get("output_dir") or get_default_output_dir()).strip()
            output_dir = Path(output_dir_raw).expanduser()
            output_dir.mkdir(parents=True, exist_ok=True)

            if not image_data:
                raise ValueError("Nenhuma imagem recebida.")

            image_bytes = decode_data_url(image_data)

            result = crop_and_save(
                image_bytes=image_bytes,
                original_filename=filename,
                cut_x_ratio=cut_x_ratio,
                cut_y_ratio=cut_y_ratio,
                output_dir=output_dir,
                simple_names=simple_names,
            )

            self.send_json({"ok": True, **result})

        except Exception as error:
            self.send_json({"ok": False, "error": str(error)}, status=400)


def open_browser_later(url: str) -> None:
    time.sleep(1.0)

    if is_termux():
        print("\nTentando abrir o navegador automaticamente no Android...")

        termux_open_url = shutil.which("termux-open-url")
        if termux_open_url:
            try:
                result = subprocess.run(
                    [termux_open_url, url],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

                if result.returncode == 0:
                    print("[OK] Navegador solicitado via termux-open-url.")
                    return
            except Exception:
                pass

        am_path = shutil.which("am") or "/system/bin/am"
        if Path(am_path).exists():
            try:
                result = subprocess.run(
                    [
                        am_path,
                        "start",
                        "-a",
                        "android.intent.action.VIEW",
                        "-d",
                        url,
                    ],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

                if result.returncode == 0:
                    print("[OK] Navegador solicitado via Android intent.")
                    return
            except Exception:
                pass

    try:
        opened = webbrowser.open(url)

        if opened:
            print("[OK] Navegador solicitado pelo Python.")
            return
    except Exception:
        pass

    print("\n[AVISO] Não consegui abrir o navegador automaticamente.")
    print("Abra manualmente este endereço:")
    print(f"  {url}")


def main() -> None:
    output_dir = get_default_output_dir()
    url = f"http://{HOST}:{PORT}"

    print("=" * 56)
    print(f"{APP_NAME} {APP_VERSION}")
    print("Interface visual local")
    print("=" * 56)
    print(f"\nPasta padrão de saída:")
    print(f"  {output_dir}")
    print(f"\nAbrindo interface automaticamente:")
    print(f"  {url}")
    print("\nSe o navegador não abrir sozinho, copie esse endereço.")
    print("Para encerrar, pressione CTRL + C neste terminal.")
    print("=" * 56)

    try:
        server = ThreadingHTTPServer((HOST, PORT), TirinhaCutterHandler)
    except OSError as error:
        print("\n[ERRO] Não foi possível iniciar o servidor local.")
        print(f"Detalhe: {error}")
        print("\nTalvez a porta 8765 já esteja em uso.")
        print("Feche outra execução do Tirinha Cutter e tente novamente.")
        sys.exit(1)

    # O navegador só abre depois que o servidor conseguir ocupar a porta.
    threading.Thread(target=open_browser_later, args=(url,), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando Tirinha Cutter...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
