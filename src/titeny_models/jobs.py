"""Titik masuk job terjadwal: `python -m titeny_models.jobs <harga|demand|panen|mape>`.

Kontrak dengan titeny-infra-devops (ADR-0002 di sana): sub-perintah `harga|demand|panen|mape`;
kode keluar 0 = sukses, bukan nol = gagal (pembungkus job menghitung gagal berturut-turut/pager).
Opsi `--only-if-missing` dan `--stale-on-fail` ditangani pembungkus, bukan modul ini.

Masukan/keluaran (ASUMSI; belum ada kontrak final dengan data-pipeline/backend):
- masukan: direktori CSV agregat (`--data` atau env `TITENY_DATA_DIR`), skema di `sintetis.py`.
- keluaran: JSON-lines dalam bentuk kolom tabel DB `titeny` (`--keluar` atau env `TITENY_OUT_DIR`),
  mis. `prediksi_harga.jsonl`. Penulisan ke DB `titeny` TIDAK dilakukan di sini (tidak ada driver DB di
  dependensi terkunci); pemuat ke DB disepakati dengan titeny-backend-service/data-pipeline.
- tanggal hitung H: `--tanggal` atau env `TITENY_TANGGAL`, bawaan hari ini WIB.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from .harga import WIB, ramal_harga_pasangan
from .muat import DataTidakLengkap, muat_masukan_harga

KELUAR_OK, KELUAR_GAGAL, KELUAR_PAKAI = 0, 1, 2


def _log(level: str, status: str, **kv) -> None:
    baris = {
        "ts": datetime.now(WIB).isoformat(timespec="seconds"),
        "komponen": "titeny_models.jobs",
        "level": level,
        "status": status,
        **kv,
    }
    print(json.dumps(baris, ensure_ascii=False), flush=True)


def job_harga(data_dir: Path, keluar: Path, hari_ini: date) -> int:
    """Hitung harga H+1..H+7 untuk semua pasangan yang punya data; tulis `prediksi_harga.jsonl`."""
    try:
        masukan = muat_masukan_harga(data_dir, hari_ini)
    except DataTidakLengkap as e:
        _log("error", "gagal", job="harga", alasan=str(e))
        return KELUAR_GAGAL

    baris, dihentikan = [], []
    for m in masukan:
        hasil = ramal_harga_pasangan(m)
        if hasil is None:
            dihentikan.append(f"{m.komoditas_id}|{m.pasar_id}")  # FR-104: "Data harga belum cukup"
            continue
        baris.extend(p.as_dict() for p in hasil)

    if not baris:
        _log(
            "error",
            "gagal",
            job="harga",
            alasan="tidak ada prediksi yang dihasilkan",
            dihentikan=len(dihentikan),
        )
        return KELUAR_GAGAL

    keluar.mkdir(parents=True, exist_ok=True)
    tujuan = keluar / "prediksi_harga.jsonl"
    sementara = tujuan.with_suffix(".jsonl.tmp")
    with sementara.open("w") as f:
        for b in baris:
            f.write(json.dumps(b, ensure_ascii=False) + "\n")
    sementara.replace(tujuan)  # atomik: tidak ada berkas setengah jadi
    _log(
        "info",
        "sukses",
        job="harga",
        tanggal=hari_ini.isoformat(),
        baris=len(baris),
        pasangan=len(masukan) - len(dihentikan),
        dihentikan=dihentikan,
    )
    return KELUAR_OK


JOB: dict[str, Callable[[Path, Path, date], int]] = {"harga": job_harga}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m titeny_models.jobs", description=__doc__.splitlines()[0])
    p.add_argument("jenis", choices=["harga", "demand", "panen", "mape"])
    p.add_argument("--data", type=Path, default=os.environ.get("TITENY_DATA_DIR"))
    p.add_argument("--keluar", type=Path, default=os.environ.get("TITENY_OUT_DIR"))
    p.add_argument("--tanggal", default=os.environ.get("TITENY_TANGGAL"))
    a = p.parse_args(argv)

    if a.jenis not in JOB:
        _log("error", "belum_diimplementasikan", job=a.jenis)
        return KELUAR_PAKAI
    if not a.data or not a.keluar:
        _log("error", "salah_pakai", alasan="--data/TITENY_DATA_DIR dan --keluar/TITENY_OUT_DIR wajib")
        return KELUAR_PAKAI
    try:
        hari_ini = date.fromisoformat(a.tanggal) if a.tanggal else datetime.now(WIB).date()
    except ValueError:
        _log("error", "salah_pakai", alasan="--tanggal harus YYYY-MM-DD")
        return KELUAR_PAKAI
    return JOB[a.jenis](Path(a.data), Path(a.keluar), hari_ini)


if __name__ == "__main__":
    sys.exit(main())
