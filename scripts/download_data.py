"""Скачивание исходных данных СберИндекса в data/raw/.

    python scripts/download_data.py

Источники (лицензия CC BY-SA 4.0, см. Данные_СберИндекс_лицензия.pdf внутри архива):
  * конкурсный набор hackathonlicence.zip — расходы, доступность рынков, связи между МО;
  * справочник МО t_dict_municipal.rar — названия, ОКТМО, границы.

Внешняя проверка (не признаки модели): Росстат, БД показателей муниципальных образований в обработке
проекта «Если быть точным» (CC BY 4.0). Архивы разделов весят 1,3–3,7 ГБ, поэтому из них берутся только
нужные файлы: по HTTP Range читается центральный каталог zip, затем сжатые данные одного файла; CRC32 из
каталога проверяется при распаковке. Из файлов извлекаются годы 2023–2024 -> data/external/rosstat_bdpmo_2023_2024.csv.

    python scripts/download_data.py --only rosstat

Сервер www.sberbank.com подписан сертификатом Минцифры (Russian Trusted Root CA), которого нет
в стандартных хранилищах. Скрипт не отключает проверку TLS: он берёт корневой сертификат с
Госуслуг, сверяет его SHA-256 с опубликованным отпечатком и только тогда использует.
"""
from __future__ import annotations

import hashlib
import argparse
import shutil
import ssl
import struct
import subprocess
import sys
import urllib.request
import zipfile
import zlib
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


TOCHNO = "https://storage.yandexcloud.net/tochno-st-catalog/Rosstat/data_bdmo_118_v20250918/by_indicator/"
# (раздел, код показателя, год): файлы-срезы по годам внутри архива раздела
ROSSTAT_PARTS = [(32, "Y48423007", y) for y in (2023, 2024)] + [(32, "Y48423005", y) for y in (2023, 2024)] + [(31, "Y48112027", 2024)]
ROSSTAT_SHA256 = {  # SHA-256 извлечённых из архивов файлов, с которыми выполнен анализ (09.10.2026)
    "data_Y48423007_year2023_112_v20250918.csv": "23c8c6635e6d7d7d2e34ef6894c0ad9f56648b2436f61802a9842c4ee080a86c",
    "data_Y48423007_year2024_112_v20250918.csv": "78477a030f2bc4d17d0152eaf25b9c4bcd8decabe0252154d12a3306d0d4f922",
    "data_Y48423005_year2023_112_v20250918.csv": "e2cc8f029abd940fc301ea6f13e1c565fdd08803d626cc8e3836b3fe64858e42",
    "data_Y48423005_year2024_112_v20250918.csv": "cdde683ec93bd434554ad6f6c09ab13a155e5b56c74a38fd7c9d7d92670567af",
    "data_Y48112027_year2024_112_v20250918.csv": "51c0f94db92e3b7e16b145b67c78fc1ee0367bd1b84a144711dbc2a899d688fc",
}


def _range(url: str, a: int, b: int) -> bytes:
    req = urllib.request.Request(url, headers={"Range": f"bytes={a}-{b}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = r.read()
    if len(data) != b - a + 1:
        sys.exit(f"сервер вернул {len(data)} байт вместо {b - a + 1}: Range не поддержан")
    return data


def zip_directory(url: str) -> dict[str, tuple[int, int, int, int]]:
    """Центральный каталог удалённого zip (в т. ч. ZIP64): имя -> (метод, crc32, сжатый размер, смещение)."""
    with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60) as r:
        n = int(r.headers["Content-Length"])
    tail = _range(url, max(0, n - 65558), n - 1)
    i = tail.rfind(b"PK")
    cd_size, cd_off = struct.unpack("<II", tail[i + 12:i + 20])
    j = tail.rfind(b"PK")
    if j >= 0:  # ZIP64: настоящие размер и смещение каталога в записи ZIP64 EOCD
        (z64,) = struct.unpack("<Q", tail[j + 8:j + 16])
        cd_size, cd_off = struct.unpack("<QQ", _range(url, z64, z64 + 55)[40:56])
    cd, p, out = _range(url, cd_off, cd_off + cd_size - 1), 0, {}
    while cd[p:p + 4] == b"PK":
        meth, = struct.unpack("<H", cd[p + 10:p + 12])
        crc, csz, usz = struct.unpack("<III", cd[p + 16:p + 28])
        fl, el, cl = struct.unpack("<HHH", cd[p + 28:p + 34])
        off, = struct.unpack("<I", cd[p + 42:p + 46])
        name = cd[p + 46:p + 46 + fl].decode("utf-8", "replace")
        ex, q = cd[p + 46 + fl:p + 46 + fl + el], 0
        while q + 4 <= len(ex):
            hid, hl = struct.unpack("<HH", ex[q:q + 4])
            body = ex[q + 4:q + 4 + hl]
            if hid == 1:  # ZIP64: 8-байтные поля идут в порядке usz, csz, off — только для «переполненных»
                vals = list(struct.unpack(f"<{hl // 8}Q", body[:hl // 8 * 8]))
                usz = vals.pop(0) if usz == 0xFFFFFFFF else usz
                csz = vals.pop(0) if csz == 0xFFFFFFFF else csz
                off = vals.pop(0) if off == 0xFFFFFFFF else off
            q += 4 + hl
        out[name] = (meth, crc, csz, off)
        p += 46 + fl + el + cl
    return out


def zip_member(url: str, entry: tuple[int, int, int, int]) -> bytes:
    meth, crc, csz, off = entry
    head = _range(url, off, off + 29)
    if head[:4] != b"PK":
        sys.exit("неверный заголовок файла в архиве")
    fl, el = struct.unpack("<HH", head[26:30])
    raw = _range(url, off + 30 + fl + el, off + 30 + fl + el + csz - 1)
    data = zlib.decompress(raw, -15) if meth == 8 else raw
    if zlib.crc32(data) != crc:
        sys.exit("CRC32 файла не совпал с каталогом архива")
    return data


def rosstat() -> None:
    """Зарплата и численность работников по ОКВЭД2 (2023–2024), население (2024) -> data/external/."""
    import io

    import pandas as pd

    dl = RAW / "rosstat"
    dl.mkdir(parents=True, exist_ok=True)
    frames = []
    dirs = {}
    for sec, code, year in ROSSTAT_PARTS:
        url = TOCHNO + f"data_section{sec}_112_v20250918.zip"
        name = f"data_{code}_parts/data_{code}_year{year}_112_v20250918.csv"
        dest = dl / Path(name).name
        if not dest.exists():
            if url not in dirs:
                dirs[url] = zip_directory(url)
            print(f"скачиваю {name} из раздела {sec}")
            dest.write_bytes(zip_member(url, dirs[url][name]))
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        want = ROSSTAT_SHA256.get(dest.name)
        print(f"  {dest.name}: {dest.stat().st_size} байт, sha256 {digest}" + ("" if want is None else " совпадает" if want == digest else " ОТЛИЧАЕТСЯ"))
        frames.append(pd.read_csv(io.BytesIO(dest.read_bytes()), sep=";", dtype=str))
    out = ROOT / "data" / "external" / "rosstat_bdpmo_2023_2024.csv"
    extract_rosstat(pd.concat(frames)).to_csv(out, index=False, encoding="utf-8")
    print(f"извлечено -> {out.relative_to(ROOT)}")


LATIN = str.maketrans("АВЕНСО", "ABEHCO")   # в названиях разделов ОКВЭД2 часть букв кириллические
SECTIONS = ["A", "B", "C", "D", "E", "G", "O", "P", "Q"]


def extract_rosstat(d):
    """Годовые значения (январь–декабрь) по МО -> одна строка на (ОКТМО, год): зарплата всего, численность
    работников всего и по разделам ОКВЭД2, население на 1 января. Строки с пометкой «Аномальное значение
    показателя» отбрасываются. Субъекты РФ не берутся."""
    import pandas as pd

    d = d[(d.mun_level != "Субъект РФ") & (d.comment != "Аномальное значение показателя")].reset_index(drop=True)
    d = d[(d.indicator_code == "Y48112027") | (d.indicator_period == "Январь-декабрь")]
    sec = d.okved2.fillna("").str.extract(r"^Раздел (\S)")[0].str.translate(LATIN)
    d["var"] = d.indicator_code.map({"Y48423007": "wage", "Y48423005": "emp", "Y48112027": "pop"})
    d.loc[d.okved2.fillna("").str.startswith("Всего") | (d["var"] == "pop"), "sec"] = "total"
    d.loc[sec.isin(SECTIONS), "sec"] = sec
    d = d[d.sec.notna() & ((d["var"] == "emp") | (d.sec == "total"))]
    d["col"] = d["var"] + "_" + d.sec
    d["value"] = pd.to_numeric(d.indicator_value.str.replace(",", "."), errors="coerce")
    w = d.pivot_table(index=["oktmo", "oktmo_stable", "year"], columns="col", values="value", aggfunc="first").reset_index()
    names = d.drop_duplicates(["oktmo", "year"]).set_index(["oktmo", "year"])[["region_name", "municipality", "mun_type"]]
    w = w.join(names, on=["oktmo", "year"])
    cols = ["oktmo", "oktmo_stable", "year", "region_name", "municipality", "mun_type", "wage_total", "emp_total"] +            [f"emp_{s}" for s in SECTIONS] + ["pop_total"]
    w = w[w.wage_total.notna() | w.emp_total.notna()]   # население поселений без данных о труде не нужно
    return w.reindex(columns=cols).sort_values(["year", "oktmo"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["sberindex", "rosstat"])
    only = ap.parse_args().only
    if only != "sberindex":
        rosstat()
    if only == "rosstat":
        return
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
