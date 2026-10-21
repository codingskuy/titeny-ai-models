"""Fixture SINTETIS panen + demand (BUKAN data nyata; seed tetap). Lihat peringatan di `sintetis.py`.

Skema CSV tambahan (ASUMSI; belum ada kontrak ekspor titeny-data-pipeline):

- tanam.csv            : tanggal_tanam,komoditas_id,kabupaten_id,luas_ha
- hasil_panen.csv      : tanggal,musim,komoditas_id,kabupaten_id,luas_panen_ha,hasil_kg
- cuaca.csv            : tanggal,kabupaten_id,curah_hujan_mm,peringatan   (peringatan: kosong|banjir|kekeringan)
- transaksi_harian.csv : tanggal,komoditas_id,zona,volume_kg
- hari_besar.csv       : tanggal,hari_besar                               (puasa|lebaran|natal_tahun_baru)
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from .katalog import (
    KABUPATEN,
    KABUPATEN_TERDEKAT,
    KOMODITAS_HARGA,
    KOMODITAS_PANEN,
    ZONA_DEMAND,
)
from .sintetis import _rng

YIELD_DASAR = {  # kg/ha kasar (rentang valid FR-004: 500-15.000)
    "cmd_padi": 5500.0, "cmd_jagung": 6000.0, "cmd_cabai_merah": 9000.0,
    "cmd_cabai_rawit": 7000.0, "cmd_bawang_merah": 10000.0, "cmd_tomat": 12000.0,
}  # fmt: skip
HA_PER_HARI = 2.0  # luas tanam harian per (komoditas, kabupaten) di fixture
MUSIM = ("2025-MT1", "2025-MT2", "2026-MT1")
CATATAN_SEDIKIT = ("cmd_tomat", "kab_malang")  # sengaja < 10 baris di musim terakhir -> kepercayaan rendah


def _tanam(awal: date, hari: int):
    for kom in KOMODITAS_PANEN:
        for kab in KABUPATEN:
            r = _rng("tanam", kom, kab)
            for k in range(hari):
                yield awal + timedelta(days=k), kom, kab, round(HA_PER_HARI * (0.7 + 0.6 * r.random()), 2)


def _panen_mingguan_kg(kom: str, kab: str) -> float:
    """Keadaan tunak: tiap minggu panen = luas tanam 7 hari x yield dasar."""
    return HA_PER_HARI * 7 * YIELD_DASAR[kom]


def tulis_fixture_agro(keluar: Path, hari_ini: date, hari: int) -> None:
    awal = hari_ini - timedelta(days=hari)
    keluar.mkdir(parents=True, exist_ok=True)

    with (keluar / "tanam.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tanggal_tanam", "komoditas_id", "kabupaten_id", "luas_ha"])
        for d, kom, kab, ha in _tanam(awal - timedelta(days=140), hari + 140):
            w.writerow([d.isoformat(), kom, kab, ha])

    with (keluar / "hasil_panen.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tanggal", "musim", "komoditas_id", "kabupaten_id", "luas_panen_ha", "hasil_kg"])
        for kom in KOMODITAS_PANEN:
            for kab in KABUPATEN:
                r = _rng("hasil", kom, kab)
                for i, musim in enumerate(MUSIM):
                    n = 6 if (kom, kab) == CATATAN_SEDIKIT and i == len(MUSIM) - 1 else 14
                    for j in range(n):
                        tgl = hari_ini - timedelta(days=400 - 130 * i - 5 * j)
                        ha = round(2 + 3 * r.random(), 2)
                        yld = YIELD_DASAR[kom] * (0.9 + 0.2 * r.random())
                        w.writerow([tgl.isoformat(), musim, kom, kab, ha, int(ha * yld)])

    with (keluar / "cuaca.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tanggal", "kabupaten_id", "curah_hujan_mm", "peringatan"])
        for kab in KABUPATEN:
            r = _rng("cuaca", kab)
            for k in range(hari):
                tgl = awal + timedelta(days=k)
                w.writerow([tgl.isoformat(), kab, round(float(r.gamma(1.2, 4.0)), 1), ""])

    # volume demand: komoditas panen ~ sebanding panen kabupaten terdekat (supaya sinyal bermakna),
    # komoditas lain basis tetap. Keduanya hanya skala fixture, bukan angka pasar.
    zona_per_kab: dict[str, list[str]] = defaultdict(list)
    for z in ZONA_DEMAND:
        zona_per_kab[KABUPATEN_TERDEKAT[z]].append(z)
    with (keluar / "transaksi_harian.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tanggal", "komoditas_id", "zona", "volume_kg"])
        for kom in KOMODITAS_HARGA:
            for z in ZONA_DEMAND:
                r = _rng("demand", kom, z)
                if kom in KOMODITAS_PANEN:
                    kab = KABUPATEN_TERDEKAT[z]
                    skala = 0.6 + 0.9 * _rng("skala", kom, kab).random()  # 0,6x-1,5x panen kabupaten
                    dasar = _panen_mingguan_kg(kom, kab) * skala / 7 / len(zona_per_kab[kab])
                else:
                    dasar = 300 + 600 * r.random()
                for k in range(hari):
                    tgl = awal + timedelta(days=k)
                    w.writerow([tgl.isoformat(), kom, z, round(dasar * (1 + r.normal(0, 0.08)), 2)])

    with (keluar / "hari_besar.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tanggal", "hari_besar"])
        # fiktif untuk menguji jalur faktor (bukan kalender resmi)
        for k in range(30):
            w.writerow([(hari_ini + timedelta(days=15 + k)).isoformat(), "puasa"])
        for k in range(10):
            w.writerow([(date(2026, 12, 24) + timedelta(days=k)).isoformat(), "natal_tahun_baru"])
