#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tirinha Cutter
Recorta uma tirinha 2x2 em 4 imagens separadas.

Uso básico:
    python tirinha_cutter.py

Uso com imagem direta:
    python tirinha_cutter.py caminho/da/imagem.png

Exemplo no Termux:
    python tirinha_cutter.py /storage/emulated/0/Download/tirinha.png
"""

from __future__ import annotations

import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


APP_NAME = "Tirinha Cutter"
OUTPUT_FOLDER_NAME = "TirinhaCutter"
PRESETS_FILE = "presets.json"


def ensure_dependencies() -> None:
    """
    Verifica se Pillow está instalado.
    Se não estiver, pede confirmação para instalar automaticamente.
    """
    try:
        import PIL  # noqa: F401
        return
    except ImportError:
        print("\n[!] Dependência ausente: Pillow")
        print("O Pillow é necessário para abrir e recortar imagens.")

        answer = input("Deseja instalar agora? [s/N]: ").strip().lower()

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


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def get_script_dir() -> Path:
    return Path(__file__).resolve().parent


def get_presets_path() -> Path:
    return get_script_dir() / PRESETS_FILE


def is_termux() -> bool:
    """
    Detecta ambiente Termux de forma simples.
    """
    prefix = os.environ.get("PREFIX", "")
    termux_version = os.environ.get("TERMUX_VERSION", "")
    home = str(Path.home())

    return (
        "com.termux" in prefix
        or bool(termux_version)
        or "/data/data/com.termux" in home
    )


def load_presets() -> dict:
    presets_path = get_presets_path()

    if not presets_path.exists():
        default_presets = {
            "padrao_2x2": {
                "vertical_ratio": 0.5,
                "horizontal_ratio": 0.5,
                "description": "Corte padrão exatamente no meio da imagem.",
            }
        }
        save_presets(default_presets)
        return default_presets

    try:
        with presets_path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        print("[!] Não foi possível ler presets.json. Usando padrão 2x2.")
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


def detect_downloads_folder() -> Path:
    """
    Tenta detectar a pasta Downloads no Windows, Linux e Android/Termux.
    Se não encontrar, usa ./saida.
    """
    candidates = []

    system = platform.system().lower()
    home = Path.home()

    if system == "windows":
        candidates.append(home / "Downloads")

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


def ask_output_folder() -> Path:
    detected = detect_downloads_folder()
    default_output = detected / OUTPUT_FOLDER_NAME

    print(f"\nPasta de saída detectada:")
    print(f"  {default_output}")

    answer = input("Usar essa pasta? [S/n]: ").strip().lower()

    if answer in {"", "s", "sim", "y", "yes"}:
        default_output.mkdir(parents=True, exist_ok=True)
        return default_output

    while True:
        custom = input("Digite a pasta de saída: ").strip().strip('"').strip("'")

        if not custom:
            print("Caminho vazio. Tente novamente.")
            continue

        path = Path(custom).expanduser()

        try:
            path.mkdir(parents=True, exist_ok=True)
            return path
        except Exception as error:
            print(f"Não foi possível usar essa pasta: {error}")


def normalize_path(raw_path: str) -> Path:
    return Path(raw_path.strip().strip('"').strip("'")).expanduser()


def select_image_with_tkinter() -> Path | None:
    """
    Seletor visual de arquivo para Windows/Linux com ambiente gráfico.
    Usa tkinter, que normalmente já vem com Python no Windows.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        selected = filedialog.askopenfilename(
            title="Selecione a tirinha",
            filetypes=[
                ("Imagens", "*.png *.jpg *.jpeg *.webp"),
                ("PNG", "*.png"),
                ("JPEG", "*.jpg *.jpeg"),
                ("WEBP", "*.webp"),
                ("Todos os arquivos", "*.*"),
            ],
        )

        root.destroy()

        if selected:
            return Path(selected)

        return None

    except Exception as error:
        print(f"[AVISO] Seletor visual indisponível: {error}")
        return None


def select_image_with_termux_storage_get() -> Path | None:
    """
    Seletor de arquivo no Android/Termux usando Termux:API.

    Requisitos no Android:
        pkg install termux-api
        instalar o app Termux:API
        termux-setup-storage

    O comando termux-storage-get abre o seletor do Android e copia
    o arquivo escolhido para o caminho informado.
    """
    command_path = shutil.which("termux-storage-get")

    if not command_path:
        return None

    temp_dir = Path(tempfile.gettempdir()) / "tirinha-cutter"
    temp_dir.mkdir(parents=True, exist_ok=True)

    temp_file = temp_dir / "imagem_selecionada"

    print("\nAbrindo seletor de arquivos do Android...")
    print("Escolha a imagem da tirinha.")

    try:
        result = subprocess.run(
            [command_path, str(temp_file)],
            check=False,
        )

        if result.returncode != 0:
            print("[AVISO] Nenhum arquivo foi selecionado ou o seletor falhou.")
            return None

        if temp_file.exists() and temp_file.is_file():
            return temp_file

        return None

    except Exception as error:
        print(f"[AVISO] Falha ao usar termux-storage-get: {error}")
        return None


def ask_image_path_manual() -> Path:
    while True:
        raw_path = input("\nDigite o caminho da imagem: ").strip()
        image_path = normalize_path(raw_path)

        if image_path.exists() and image_path.is_file():
            return image_path

        print("[ERRO] Imagem não encontrada. Tente novamente.")
        print("Exemplo Termux:")
        print("  /storage/emulated/0/Download/tirinha.png")


def ask_image_path() -> Path:
    """
    Fluxo de seleção da imagem:
    1. Android/Termux: tenta termux-storage-get.
    2. Windows/Linux GUI: tenta tkinter.
    3. Fallback: pede caminho manual.
    """
    print("\nSeleção da imagem")
    print("1. Abrir seletor de arquivo")
    print("2. Digitar caminho manualmente")

    choice = input("Escolha [1]: ").strip()

    if not choice:
        choice = "1"

    if choice == "1":
        selected_path = None

        if is_termux():
            selected_path = select_image_with_termux_storage_get()

            if selected_path is None:
                print("\n[AVISO] Seletor do Termux indisponível.")
                print("Para ativar no Android, instale:")
                print("  pkg install termux-api")
                print("E também o app Termux:API.")
                print("Depois rode:")
                print("  termux-setup-storage")

        if selected_path is None:
            selected_path = select_image_with_tkinter()

        if selected_path is not None and selected_path.exists():
            return selected_path

        print("\nNão foi possível usar o seletor visual.")
        print("Vamos pelo caminho manual.")

    return ask_image_path_manual()


def get_image_path_from_args() -> Path | None:
    if len(sys.argv) >= 2:
        image_path = normalize_path(sys.argv[1])

        if image_path.exists() and image_path.is_file():
            return image_path

        print(f"[ERRO] Arquivo informado não existe: {image_path}")
        sys.exit(1)

    return None


def calculate_aspect_ratio(width: int, height: int) -> str:
    divisor = math.gcd(width, height)
    ratio_w = width // divisor
    ratio_h = height // divisor

    decimal = width / height if height else 0

    return f"{ratio_w}:{ratio_h} ({decimal:.4f})"


def is_near_9_16(width: int, height: int) -> bool:
    if height == 0:
        return False

    current = width / height
    expected = 9 / 16

    return abs(current - expected) <= 0.03


def show_image_info(
    image_path: Path,
    image: Image.Image,
    cut_x: int,
    cut_y: int,
    output_dir: Path,
) -> None:
    width, height = image.size
    file_size_kb = image_path.stat().st_size / 1024

    print("\n" + "=" * 52)
    print("INFORMAÇÕES DA IMAGEM")
    print("=" * 52)
    print(f"Arquivo:        {image_path.name}")
    print(f"Caminho:        {image_path}")
    print(f"Formato:        {image.format}")
    print(f"Tamanho:        {width} x {height} px")
    print(f"Aspect ratio:   {calculate_aspect_ratio(width, height)}")
    print(f"Peso:           {file_size_kb:.1f} KB")
    print(f"Proporção 9:16: {'sim' if is_near_9_16(width, height) else 'não/fora do padrão'}")
    print(f"Corte vertical: {cut_x}px ({cut_x / width * 100:.2f}%)")
    print(f"Corte horiz.:   {cut_y}px ({cut_y / height * 100:.2f}%)")
    print(f"Saída:          {output_dir}")
    print("=" * 52)


def choose_preset(width: int, height: int) -> tuple[int, int, str]:
    presets = load_presets()

    print("\nPresets disponíveis:")

    preset_names = list(presets.keys())

    for index, name in enumerate(preset_names, start=1):
        preset = presets[name]
        description = preset.get("description", "")
        print(f"{index}. {name} - {description}")

    print("0. Corte padrão 50% / 50%")

    choice = input("\nEscolha um preset [0]: ").strip()

    if not choice:
        choice = "0"

    if choice == "0":
        return width // 2, height // 2, "padrao_2x2"

    try:
        selected_index = int(choice) - 1
        selected_name = preset_names[selected_index]
        selected = presets[selected_name]

        vertical_ratio = float(selected.get("vertical_ratio", 0.5))
        horizontal_ratio = float(selected.get("horizontal_ratio", 0.5))

        cut_x = int(width * vertical_ratio)
        cut_y = int(height * horizontal_ratio)

        return cut_x, cut_y, selected_name

    except Exception:
        print("[!] Preset inválido. Usando padrão 50% / 50%.")
        return width // 2, height // 2, "padrao_2x2"


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def adjust_cuts(width: int, height: int, cut_x: int, cut_y: int) -> tuple[int, int]:
    """
    Ajuste manual simples por terminal.
    """
    while True:
        print("\nAjuste atual:")
        print(f"  Vertical X:   {cut_x}px ({cut_x / width * 100:.2f}%)")
        print(f"  Horizontal Y: {cut_y}px ({cut_y / height * 100:.2f}%)")

        print("\nComandos:")
        print("  a  = mover vertical para esquerda 1px")
        print("  d  = mover vertical para direita 1px")
        print("  w  = mover horizontal para cima 1px")
        print("  s  = mover horizontal para baixo 1px")
        print("  A  = mover vertical para esquerda 10px")
        print("  D  = mover vertical para direita 10px")
        print("  W  = mover horizontal para cima 10px")
        print("  S  = mover horizontal para baixo 10px")
        print("  x  = definir X manualmente em pixels")
        print("  y  = definir Y manualmente em pixels")
        print("  p  = definir por porcentagem")
        print("  ok = confirmar corte")

        command = input("\nComando: ").strip()

        if command == "ok":
            return cut_x, cut_y

        elif command == "a":
            cut_x -= 1
        elif command == "d":
            cut_x += 1
        elif command == "w":
            cut_y -= 1
        elif command == "s":
            cut_y += 1

        elif command == "A":
            cut_x -= 10
        elif command == "D":
            cut_x += 10
        elif command == "W":
            cut_y -= 10
        elif command == "S":
            cut_y += 10

        elif command == "x":
            raw = input("Novo X em pixels: ").strip()
            if raw.isdigit():
                cut_x = int(raw)
            else:
                print("[!] Valor inválido.")

        elif command == "y":
            raw = input("Novo Y em pixels: ").strip()
            if raw.isdigit():
                cut_y = int(raw)
            else:
                print("[!] Valor inválido.")

        elif command == "p":
            try:
                raw_x = input("Vertical em % da largura. Ex: 50: ").strip().replace(",", ".")
                raw_y = input("Horizontal em % da altura. Ex: 50: ").strip().replace(",", ".")

                percent_x = float(raw_x)
                percent_y = float(raw_y)

                cut_x = int(width * (percent_x / 100))
                cut_y = int(height * (percent_y / 100))
            except ValueError:
                print("[!] Porcentagem inválida.")

        else:
            print("[!] Comando inválido.")

        cut_x = clamp(cut_x, 1, width - 1)
        cut_y = clamp(cut_y, 1, height - 1)


def ask_yes_no(question: str, default_yes: bool = True) -> bool:
    suffix = "[S/n]" if default_yes else "[s/N]"
    answer = input(f"{question} {suffix}: ").strip().lower()

    if not answer:
        return default_yes

    return answer in {"s", "sim", "y", "yes"}


def save_current_preset(width: int, height: int, cut_x: int, cut_y: int) -> None:
    if not ask_yes_no("\nDeseja salvar essa posição como preset?", default_yes=False):
        return

    name = input("Nome do preset: ").strip()

    if not name:
        print("[!] Nome vazio. Preset não salvo.")
        return

    safe_name = (
        name.lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
        .replace("\\", "_")
    )

    presets = load_presets()

    presets[safe_name] = {
        "vertical_ratio": cut_x / width,
        "horizontal_ratio": cut_y / height,
        "description": f"Preset criado manualmente. X={cut_x}px, Y={cut_y}px.",
    }

    save_presets(presets)

    print(f"[OK] Preset salvo: {safe_name}")


def crop_image(image: Image.Image, cut_x: int, cut_y: int) -> list[Image.Image]:
    width, height = image.size

    crops = [
        image.crop((0, 0, cut_x, cut_y)),
        image.crop((cut_x, 0, width, cut_y)),
        image.crop((0, cut_y, cut_x, height)),
        image.crop((cut_x, cut_y, width, height)),
    ]

    return crops


def get_output_files(image_path: Path, output_dir: Path, simple_names: bool) -> list[Path]:
    if simple_names:
        return [
            output_dir / "1.png",
            output_dir / "2.png",
            output_dir / "3.png",
            output_dir / "4.png",
        ]

    stem = image_path.stem if image_path.stem != "imagem_selecionada" else "tirinha"

    return [
        output_dir / f"{stem}_1.png",
        output_dir / f"{stem}_2.png",
        output_dir / f"{stem}_3.png",
        output_dir / f"{stem}_4.png",
    ]


def save_crops(crops: list[Image.Image], output_files: list[Path]) -> None:
    for crop, output_file in zip(crops, output_files):
        crop.save(output_file, format="PNG")


def main() -> None:
    clear_screen()

    print("=" * 52)
    print(APP_NAME)
    print("Recorte automático de tirinha 2x2")
    print("=" * 52)

    image_path = get_image_path_from_args()

    if image_path is None:
        image_path = ask_image_path()

    output_dir = ask_output_folder()

    try:
        image = Image.open(image_path)
    except Exception as error:
        print(f"[ERRO] Não foi possível abrir a imagem: {error}")
        sys.exit(1)

    width, height = image.size

    cut_x, cut_y, preset_name = choose_preset(width, height)

    show_image_info(image_path, image, cut_x, cut_y, output_dir)

    if ask_yes_no("\nDeseja ajustar manualmente os cortes?", default_yes=True):
        cut_x, cut_y = adjust_cuts(width, height, cut_x, cut_y)

    show_image_info(image_path, image, cut_x, cut_y, output_dir)

    save_current_preset(width, height, cut_x, cut_y)

    simple_names = ask_yes_no("\nSalvar como 1.png, 2.png, 3.png e 4.png?", default_yes=False)

    crops = crop_image(image, cut_x, cut_y)
    output_files = get_output_files(image_path, output_dir, simple_names)

    save_crops(crops, output_files)

    print("\n[OK] Recortes salvos com sucesso:\n")

    for file in output_files:
        print(f"  {file}")

    print("\nFinalizado.")


if __name__ == "__main__":
    main()
