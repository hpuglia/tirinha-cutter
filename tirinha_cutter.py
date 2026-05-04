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
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse


APP_NAME = "Tirinha Cutter"
APP_VERSION = "0.2.1"
HOST = "127.0.0.1"
PORT = 8765
OUTPUT_FOLDER_NAME = "TirinhaCutter"
PRESETS_FILE = "presets.json"


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
        candidates.extend(
            [
                home / "Downloads",
                home / "downloads",
            ]
        )
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

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = output_dir / f"{base_name}_{timestamp}"
    session_dir.mkdir(parents=True, exist_ok=True)

    if simple_names:
        filenames = ["1.png", "2.png", "3.png", "4.png"]
    else:
        filenames = [
            f"{base_name}_1.png",
            f"{base_name}_2.png",
            f"{base_name}_3.png",
            f"{base_name}_4.png",
        ]

    output_files = []

    for crop, filename in zip(crops, filenames):
        output_file = session_dir / filename
        crop.save(output_file, format="PNG")
        output_files.append(output_file)

    zip_path = session_dir / f"{base_name}_recortes.zip"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for file in output_files:
            zip_file.write(file, arcname=file.name)

    return {
        "width": width,
        "height": height,
        "cut_x": cut_x,
        "cut_y": cut_y,
        "cut_x_percent": round(cut_x_ratio * 100, 2),
        "cut_y_percent": round(cut_y_ratio * 100, 2),
        "aspect_ratio": calculate_aspect_ratio(width, height),
        "output_dir": str(session_dir),
        "files": [str(file) for file in output_files],
        "zip": str(zip_path),
        "zip_url": f"/download?path={quote(str(zip_path))}",
    }


def get_html() -> str:
    output_dir = str(get_default_output_dir())
    presets = json.dumps(load_presets(), ensure_ascii=False)

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>{APP_NAME}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root {{
      --bg: #101114;
      --panel: #181a20;
      --panel2: #20232b;
      --text: #f4f4f5;
      --muted: #a1a1aa;
      --line: #22c55e;
      --line2: #38bdf8;
      --danger: #ef4444;
      --accent: #f97316;
      --border: #2f3340;
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      background: radial-gradient(circle at top, #1f2937 0, var(--bg) 45%);
      color: var(--text);
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}

    header {{
      padding: 18px 20px;
      border-bottom: 1px solid var(--border);
      background: rgba(16, 17, 20, 0.92);
      position: sticky;
      top: 0;
      z-index: 10;
      backdrop-filter: blur(12px);
    }}

    header h1 {{
      margin: 0;
      font-size: 20px;
      letter-spacing: -0.02em;
    }}

    header p {{
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 13px;
    }}

    main {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 360px;
      gap: 18px;
      padding: 18px;
      max-width: 1400px;
      margin: 0 auto;
    }}

    .viewer, .panel {{
      background: rgba(24, 26, 32, 0.92);
      border: 1px solid var(--border);
      border-radius: 18px;
      box-shadow: 0 18px 60px rgba(0,0,0,.28);
    }}

    .viewer {{
      min-height: 78vh;
      padding: 14px;
      display: flex;
      align-items: center;
      justify-content: center;
    }}

    .canvasWrap {{
      position: relative;
      max-width: 100%;
      max-height: 78vh;
      overflow: hidden;
      border-radius: 14px;
      background: #0a0a0a;
      border: 1px solid #2b2f3a;
    }}

    canvas {{
      display: block;
      max-width: 100%;
      max-height: 78vh;
      cursor: crosshair;
      touch-action: none;
    }}

    .empty {{
      text-align: center;
      color: var(--muted);
      padding: 40px 20px;
    }}

    .empty strong {{
      display: block;
      color: var(--text);
      font-size: 22px;
      margin-bottom: 8px;
    }}

    .panel {{
      padding: 16px;
      overflow: auto;
      max-height: 82vh;
    }}

    .block {{
      background: var(--panel2);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px;
      margin-bottom: 12px;
    }}

    .block h2 {{
      margin: 0 0 12px;
      font-size: 15px;
    }}

    label {{
      display: block;
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 6px;
    }}

    input[type="file"],
    input[type="text"],
    select {{
      width: 100%;
      background: #111318;
      border: 1px solid var(--border);
      color: var(--text);
      border-radius: 10px;
      padding: 10px;
    }}

    input[type="range"] {{
      width: 100%;
    }}

    .row {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }}

    button {{
      border: 0;
      background: #2f3340;
      color: var(--text);
      padding: 10px 12px;
      border-radius: 11px;
      cursor: pointer;
      font-weight: 650;
    }}

    button:hover {{
      filter: brightness(1.12);
    }}

    button.primary {{
      background: linear-gradient(135deg, var(--accent), #ea580c);
      color: white;
    }}

    button.success {{
      background: linear-gradient(135deg, #16a34a, #15803d);
      color: white;
    }}

    button.danger {{
      background: linear-gradient(135deg, #ef4444, #b91c1c);
      color: white;
    }}

    .btnGrid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      align-items: center;
    }}

    .btnGrid .blank {{
      visibility: hidden;
    }}

    .info {{
      font-size: 13px;
      line-height: 1.55;
      color: var(--muted);
      word-break: break-word;
    }}

    .info b {{
      color: var(--text);
    }}

    .result {{
      white-space: pre-wrap;
      font-size: 13px;
      line-height: 1.45;
      color: #d4d4d8;
      background: #0f1117;
      border-radius: 10px;
      padding: 10px;
      border: 1px solid var(--border);
    }}

    .small {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }}

    .checkboxLine {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      color: var(--muted);
    }}

    a {{
      color: #7dd3fc;
      text-decoration: none;
    }}

    a:hover {{
      text-decoration: underline;
    }}

    @media (max-width: 980px) {{
      main {{
        grid-template-columns: 1fr;
        padding: 12px;
      }}

      .panel {{
        max-height: none;
      }}

      .viewer {{
        min-height: auto;
      }}

      canvas {{
        max-height: 68vh;
      }}
    }}
  </style>
</head>
<body>
<header>
  <h1>{APP_NAME}</h1>
  <p>Recorte visual de tirinhas 2x2 — arraste as linhas, ajuste e salve as 4 cenas.</p>
</header>

<main>
  <section class="viewer">
    <div id="empty" class="empty">
      <strong>Selecione uma tirinha</strong>
      A imagem aparecerá aqui com as linhas de corte.
    </div>

    <div id="canvasWrap" class="canvasWrap" style="display:none;">
      <canvas id="canvas"></canvas>
    </div>
  </section>

  <aside class="panel">
    <div class="block">
      <h2>1. Imagem</h2>
      <label>Selecionar arquivo</label>
      <input id="fileInput" type="file" accept="image/png,image/jpeg,image/webp">
      <p class="small">No celular, este botão abre o seletor de imagens do Android. No Windows, abre o seletor do navegador.</p>
    </div>

    <div class="block">
      <h2>2. Preset</h2>
      <label>Preset de corte</label>
      <select id="presetSelect"></select>

      <div class="row" style="margin-top:10px;">
        <button onclick="applySelectedPreset()">Aplicar</button>
        <button onclick="savePreset()">Salvar atual</button>
      </div>
    </div>

    <div class="block">
      <h2>3. Ajuste das linhas</h2>

      <label>Linha vertical: <span id="xLabel">50%</span></label>
      <input id="xRange" type="range" min="1" max="99" step="0.1" value="50">

      <label style="margin-top:12px;">Linha horizontal: <span id="yLabel">50%</span></label>
      <input id="yRange" type="range" min="1" max="99" step="0.1" value="50">

      <div style="height:12px;"></div>

      <div class="btnGrid">
        <span class="blank"></span>
        <button onclick="nudge(0, -1)">↑</button>
        <span class="blank"></span>

        <button onclick="nudge(-1, 0)">←</button>
        <button onclick="resetCuts()">50/50</button>
        <button onclick="nudge(1, 0)">→</button>

        <span class="blank"></span>
        <button onclick="nudge(0, 1)">↓</button>
        <span class="blank"></span>
      </div>

      <p class="small">Você também pode arrastar as linhas diretamente sobre a imagem.</p>
    </div>

    <div class="block">
      <h2>4. Saída</h2>

      <label>Pasta padrão detectada</label>
      <input id="outputDir" type="text" value="{output_dir}">

      <p class="small">
        O app salva no caminho acima. No Windows e Termux, o padrão é Downloads/TirinhaCutter.
      </p>

      <label class="checkboxLine">
        <input id="simpleNames" type="checkbox">
        Salvar como 1.png, 2.png, 3.png e 4.png
      </label>

      <div style="height:12px;"></div>

      <button class="success" style="width:100%;" onclick="cropImage()">Recortar e salvar 4 cenas</button>
    </div>

    <div class="block">
      <h2>Informações</h2>
      <div id="info" class="info">Nenhuma imagem carregada.</div>
    </div>

    <div class="block">
      <h2>Resultado</h2>
      <div id="result" class="result">Aguardando recorte.</div>
    </div>
  </aside>
</main>

<script>
const SERVER_PRESETS = {presets};

let image = new Image();
let imageDataUrl = null;
let originalFilename = "tirinha.png";
let originalBytesSize = 0;

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

function applySelectedPreset() {{
  const name = presetSelect.value;
  const preset = window.allPresets[name];

  if (!preset) return;

  xPercent = Number(preset.vertical_ratio || 0.5) * 100;
  yPercent = Number(preset.horizontal_ratio || 0.5) * 100;

  syncControls();
  draw();
}}

function savePreset() {{
  const nameRaw = prompt("Nome do preset:", "meu_preset");

  if (!nameRaw) return;

  const name = nameRaw
    .trim()
    .toLowerCase()
    .replaceAll(" ", "_")
    .replace(/[^a-z0-9_\\-]/g, "");

  if (!name) return alert("Nome inválido.");

  const local = JSON.parse(localStorage.getItem("tirinhaCutterPresets") || "{{}}");

  local[name] = {{
    vertical_ratio: xPercent / 100,
    horizontal_ratio: yPercent / 100,
    description: "Preset salvo no navegador."
  }};

  localStorage.setItem("tirinhaCutterPresets", JSON.stringify(local));
  initPresets();
  presetSelect.value = name;

  alert("Preset salvo: " + name);
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

fileInput.addEventListener("change", event => {{
  const file = event.target.files[0];
  if (!file) return;

  originalFilename = file.name;
  originalBytesSize = file.size;

  const reader = new FileReader();

  reader.onload = e => {{
    imageDataUrl = e.target.result;
    image = new Image();

    image.onload = () => {{
      empty.style.display = "none";
      canvasWrap.style.display = "block";
      resetCanvasSize();
      syncControls();
      draw();
    }};

    image.src = imageDataUrl;
  }};

  reader.readAsDataURL(file);
}});

function resetCanvasSize() {{
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
}}

function draw() {{
  if (!image || !image.naturalWidth) return;

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(image, 0, 0);

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
  ctx.fillText("X: " + Math.round(x) + " px", 22, 38);
  ctx.fillText("Y: " + Math.round(y) + " px", 22, 66);

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

async function cropImage() {{
  if (!imageDataUrl) {{
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

    result.innerHTML =
      "[OK] Recortes salvos com sucesso\\n\\n" +
      "Pasta:\\n" + data.output_dir + "\\n\\n" +
      "Arquivos:\\n" + data.files.join("\\n") + "\\n\\n" +
      "ZIP:\\n" + data.zip + "\\n\\n" +
      `<a href="${{data.zip_url}}" target="_blank">Baixar ZIP com os 4 recortes</a>`;

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
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
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
            simple_names = bool(payload.get("simple_names", False))

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
    """
    Abre o navegador automaticamente no Windows, Linux e Android/Termux.

    No Android/Termux tenta, em ordem:
    1. termux-open-url
    2. am start com intent do Android
    3. webbrowser.open

    A ideia é executar o comando remoto e já cair direto na interface.
    """
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

    threading.Thread(target=open_browser_later, args=(url,), daemon=True).start()

    try:
        server = ThreadingHTTPServer((HOST, PORT), TirinhaCutterHandler)
    except OSError as error:
        print("\n[ERRO] Não foi possível iniciar o servidor local.")
        print(f"Detalhe: {error}")
        print("\nTalvez a porta 8765 já esteja em uso.")
        print("Feche outra execução do Tirinha Cutter e tente novamente.")
        sys.exit(1)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando Tirinha Cutter...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
