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
from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path

from .demand import ramal_demand_pasangan, terapkan_sinyal
from .harga import WIB, ramal_harga_pasangan
from .katalog import KABUPATEN_TERDEKAT
from .muat import DataTidakLengkap, muat_masukan_harga
from .muat_agro import muat_masukan_demand, muat_masukan_panen, muat_rasio_harga
from .panen import awal_minggu, minggu_iso, ramal_panen_pasangan
from .sinyal import rekomendasi_zona

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


def _tulis_jsonl(tujuan: Path, baris: list[dict]) -> None:
    tujuan.parent.mkdir(parents=True, exist_ok=True)
    sementara = tujuan.with_suffix(".jsonl.tmp")
    with sementara.open("w") as f:
        for b in baris:
            f.write(json.dumps(b, ensure_ascii=False) + "\n")
    sementara.replace(tujuan)


def job_panen(data_dir: Path, keluar: Path, hari_ini: date) -> int:
    """Panen M+1..M+4 (6 komoditas x 5 kabupaten); tulis `prediksi_panen.jsonl`."""
    try:
        masukan = muat_masukan_panen(data_dir, hari_ini)
    except DataTidakLengkap as e:
        _log("error", "gagal", job="panen", alasan=str(e))
        return KELUAR_GAGAL
    baris, dilewati = [], []
    for m in masukan:
        hasil = ramal_panen_pasangan(m)
        if hasil is None:
            dilewati.append(f"{m.komoditas_id}|{m.kabupaten_id}")
            continue
        baris.extend(p.as_dict() for p in hasil)
    if not baris:
        _log("error", "gagal", job="panen", alasan="tidak ada prediksi yang dihasilkan")
        return KELUAR_GAGAL
    _tulis_jsonl(keluar / "prediksi_panen.jsonl", baris)
    rendah = sorted(
        {f"{b['komoditas_id']}|{b['kabupaten_id']}" for b in baris if b["kepercayaan"] == "rendah"}
    )
    _log("info", "sukses", job="panen", tanggal=hari_ini.isoformat(), baris=len(baris),
         pasangan=len(masukan) - len(dilewati), tanpa_riwayat_yield=dilewati, kepercayaan_rendah=rendah)  # fmt: skip
    return KELUAR_OK


def _panen_untuk_sinyal(keluar: Path, hari_ini: date):
    """({(komoditas, kab, horizon): kg}, {(komoditas, kab) berkepercayaan rendah}) dari prediksi_panen.jsonl."""
    berkas = keluar / "prediksi_panen.jsonl"
    if not berkas.exists():
        return {}, frozenset()
    m1 = minggu_iso(awal_minggu(hari_ini) + timedelta(days=7))
    total: dict[tuple[str, str, str], float] = defaultdict(float)
    rendah = set()
    for baris in berkas.read_text().splitlines():
        b = json.loads(baris)
        kom, kab = b["komoditas_id"], b["kabupaten_id"]
        total[(kom, kab, "H+30")] += b["panen_prediksi_kg"]  # M+1..M+4 ~ 28 hari
        if b["minggu"] == m1:
            total[(kom, kab, "H+7_total_kg")] += b["panen_prediksi_kg"]
        if b["kepercayaan"] == "rendah":
            rendah.add((kom, kab))
    return dict(total), frozenset(rendah)


def job_demand(data_dir: Path, keluar: Path, hari_ini: date) -> int:
    """Demand H+7/H+30 + sinyal + rekomendasi. Butuh `prediksi_harga.jsonl` (job harga lebih dulu)."""
    try:
        rasio = muat_rasio_harga(data_dir, keluar, hari_ini)
        masukan = muat_masukan_demand(data_dir, hari_ini, rasio)
    except DataTidakLengkap as e:
        _log("error", "gagal", job="demand", alasan=str(e))
        return KELUAR_GAGAL
    prediksi, dihentikan = [], []
    for m in masukan:
        hasil = ramal_demand_pasangan(m)
        if hasil is None:
            dihentikan.append(f"{m.komoditas_id}|{m.zona}")
            continue
        prediksi.extend(hasil)
    if not prediksi:
        _log("error", "gagal", job="demand", alasan="tidak ada prediksi yang dihasilkan")
        return KELUAR_GAGAL

    panen_kg, rendah = _panen_untuk_sinyal(keluar, hari_ini)
    if not panen_kg:
        _log("warning", "tanpa_panen", job="demand", alasan="prediksi_panen.jsonl belum ada; sinyal seimbang")
    prediksi = terapkan_sinyal(prediksi, panen_kg, rendah)

    # selisih per zona-komoditas (H+7) dihitung dari data yang sama dengan sinyal
    per_zona: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
    grup: dict[tuple[str, str], float] = defaultdict(float)
    for p in prediksi:
        if p.horizon == "H+7_total_kg":
            grup[(p.komoditas_id, KABUPATEN_TERDEKAT[p.zona])] += p.demand_prediksi_kg
    for p in prediksi:
        if p.horizon != "H+7_total_kg" or p.sinyal == "seimbang":
            continue
        kab = KABUPATEN_TERDEKAT[p.zona]
        total = grup[(p.komoditas_id, kab)]
        selisih = abs(panen_kg[(p.komoditas_id, kab, p.horizon)] - total) * (p.demand_prediksi_kg / total)
        per_zona[p.zona].append((p.komoditas_id, p.sinyal, selisih))
    zonas = sorted({p.zona for p in prediksi})
    rekom = [
        {
            "id": f"rek_{hari_ini:%Y%m%d}_{zona}",
            "zona": zona,
            "teks": rekomendasi_zona(per_zona.get(zona, []), zona),
            "status": "baru",
            "dibuat_pada": datetime.now(WIB).isoformat(),
        }
        for zona in zonas
    ]
    _tulis_jsonl(keluar / "prediksi_demand.jsonl", [p.as_dict() for p in prediksi])
    _tulis_jsonl(keluar / "rekomendasi.jsonl", rekom)
    label = [
        {"komoditas_id": p.komoditas_id, "zona": p.zona, "horizon": p.horizon, "label": p.label}
        for p in prediksi
        if p.label
    ]
    _tulis_jsonl(keluar / "demand_label.jsonl", label)  # label non-kontrak (mis. `estimasi`), terpisah
    ringkas = defaultdict(int)
    for p in prediksi:
        ringkas[p.sinyal] += 1
    _log("info", "sukses", job="demand", tanggal=hari_ini.isoformat(), baris=len(prediksi),
         sinyal=dict(ringkas), rekomendasi=len(rekom), estimasi=len(label), dihentikan=dihentikan)  # fmt: skip
    return KELUAR_OK


JOB: dict[str, Callable[[Path, Path, date], int]] = {
    "harga": job_harga,
    "panen": job_panen,
    "demand": job_demand,
}


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
