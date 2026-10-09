"""Скачивание исходных данных СберИндекса в data/raw/.

    python scripts/download_data.py

Источники (лицензия CC BY-SA 4.0, см. Данные_СберИндекс_лицензия.pdf внутри архива):
  * конкурсный набор hackathonlicence.zip — расходы, доступность рынков, связи между МО;
  * справочник МО t_dict_municipal.rar — названия, ОКТМО, границы.

Сервер www.sberbank.com подписан сертификатом Минцифры (Russian Trusted Root CA), которого нет
в стандартных хранилищах. Скрипт не отключает проверку TLS: он берёт корневой сертификат с
Госуслуг, сверяет его SHA-256 с опубликованным отпечатком и только тогда использует.
"""
from __future__ import annotations

import hashlib
import shutil
import ssl
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CONTEST_ZIP = "https://www.sberbank.com/common/img/uploaded/files/pdf/sberindex/hackathonlicence.zip"
REFERENCE_RAR = "https://www.sberbank.com/common/files/t_dict_municipal.rar"
MINCIFRY_ROOT = "https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt"
MINCIFRY_SHA256 = "D26D2D0231B7C39F92CC738512BA54103519E4405D68B5BD703E9788CA8ECF31"
EXPECTED = {  # SHA-256 файлов, с которыми выполнен анализ (08.10.2026)
    "hackathonlicence.zip": "a9f932ff4096a7df797d1547987937f34d3995ac445b4748177114488d12b010",
    "t_dict_municipal.rar": "319ed22684b77716641bc15b61f7325adc44e9fc47e9be2973d88412d27d21f5",
}


def ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    pem = urllib.request.urlopen(MINCIFRY_ROOT, timeout=60).read().decode("ascii")
    der = ssl.PEM_cert_to_DER_cert(pem)
    if hashlib.sha256(der).hexdigest().upper() != MINCIFRY_SHA256:
        sys.exit("Отпечаток корневого сертификата Минцифры не совпал — скачивание остановлено.")
    ctx.load_verify_locations(cadata=pem)
    return ctx


def fetch(url: str, dest: Path, ctx: ssl.SSLContext) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"скачиваю {url}")
    with urllib.request.urlopen(url, context=ctx, timeout=300) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    want = EXPECTED.get(dest.name)
    note = "совпадает с версией анализа" if want == digest else ("ОТЛИЧАЕТСЯ от версии анализа" if want else "")
    print(f"  {dest.name}: {dest.stat().st_size} байт, sha256 {digest} {note}")


def extract_rar(rar: Path, dest: Path) -> None:
    """RAR распаковывает bsdtar (встроен в Windows 10+ как tar.exe, в Linux — пакет libarchive-tools) или 7z."""
    for tool in (["tar", "-xf", str(rar), "-C", str(dest)], ["bsdtar", "-xf", str(rar), "-C", str(dest)],
                 ["7z", "x", "-y", f"-o{dest}", str(rar)]):
        if shutil.which(tool[0]):
            if subprocess.run(tool, capture_output=True).returncode == 0 and any(dest.glob("*.xlsx")):
                return
    sys.exit(f"Не удалось распаковать {rar}: установите bsdtar (libarchive) или 7-Zip и распакуйте в {dest}")


def main() -> None:
    ctx = ssl_context()
    z = RAW / "hackathonlicence.zip"
    fetch(CONTEST_ZIP, z, ctx)
    out = RAW / "hackathonlicence"
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(z) as zf:
        for m in zf.infolist():
            name = Path(m.filename).name
            if name and not m.is_dir():
                (out / name).write_bytes(zf.read(m))  # без путей из архива: защита от выхода за каталог
    r = RAW / "t_dict_municipal.rar"
    fetch(REFERENCE_RAR, r, ctx)
    ref = RAW / "reference"
    ref.mkdir(parents=True, exist_ok=True)
    extract_rar(r, ref)
    print("готово:", sorted(p.name for p in out.iterdir()), sorted(p.name for p in ref.iterdir()))


if __name__ == "__main__":
    main()
