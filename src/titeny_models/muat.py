"""Pemuat CSV agregat -> struktur masukan model. Tanpa koneksi DB (read-only terhadap sumber).

Skema CSV: lihat `sintetis.py` (ASUMSI sampai titeny-data-pipeline menerbitkan kontrak ekspor).
Jalur tulis ke DB `titeny` disepakati dengan backend; modul ini hanya membaca berkas agregat.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

from .harga import InputHarga


class DataTidakLengkap(Exception):
    """Berkas masukan wajib tidak ada atau kosong; job harus gagal (kode keluar 1)."""


def _baca(path: Path):
    if not path.exists():
        raise DataTidakLengkap(f"berkas tidak ada: {path}")
    with path.open(newline="") as f:
        yield from csv.DictReader(f)


def muat_masukan_harga(data_dir: Path, hari_ini: date) -> list[InputHarga]:
    """Satu `InputHarga` per pasangan (komoditas, pasar) yang punya data harga sebelum `hari_ini`."""
    harga: dict[tuple[str, str], dict[date, float]] = defaultdict(dict)
    sampel: dict[tuple[str, str], tuple[date, int]] = {}
    for b in _baca(data_dir / "harga_harian.csv"):
        d = date.fromisoformat(b["tanggal"])
        if d >= hari_ini:
            continue  # tidak boleh membaca masa depan
        kunci = (b["komoditas_id"], b["pasar_id"])
        harga[kunci][d] = float(b["harga_median"])
        if kunci not in sampel or d >= sampel[kunci][0]:
            sampel[kunci] = (d, int(b["sampel_lapak"]))
    if not harga:
        raise DataTidakLengkap("harga_harian.csv tidak berisi data sebelum tanggal hitung")

    stok: dict[str, dict[date, float]] = defaultdict(dict)
    for b in _baca(data_dir / "stok_harian.csv"):
        d = date.fromisoformat(b["tanggal"])
        if d < hari_ini:
            stok[b["komoditas_id"]][d] = float(b["stok_kg"])

    biaya: dict[tuple[str, str], dict[date, float]] = defaultdict(dict)
    for b in _baca(data_dir / "logistik.csv"):
        d = date.fromisoformat(b["tanggal"])
        if d < hari_ini:
            biaya[(b["komoditas_id"], b["pasar_id"])][d] = float(b["biaya_per_kg"])

    libur: set[date] = set()
    kalender = data_dir / "kalender.csv"
    if kalender.exists():
        libur = {date.fromisoformat(b["tanggal"]) for b in _baca(kalender) if b["jenis_hari"] == "libur"}

    return [
        InputHarga(
            komoditas_id=kom,
            pasar_id=psr,
            hari_ini=hari_ini,
            harga=seri,
            stok=stok.get(kom, {}),
            biaya_logistik=biaya.get((kom, psr), {}),
            libur=frozenset(libur),
            sampel_lapak=sampel[(kom, psr)][1],
        )
        for (kom, psr), seri in sorted(harga.items())
    ]
