"""Data SINTETIS deterministik untuk uji, demo, dan backtest lokal.

PERHATIAN: semua angka di sini dibangkitkan acak-terkendali (seed tetap), BUKAN data pasar nyata.
Metrik yang dihitung di atasnya (MAPE, cakupan) hanya membuktikan kode berjalan, bukan akurasi produksi.
Skema CSV (ASUMSI; belum ada kontrak ekspor dari titeny-data-pipeline):

- harga_harian.csv : tanggal,komoditas_id,pasar_id,harga_median,sampel_lapak
- stok_harian.csv  : tanggal,komoditas_id,stok_kg
- logistik.csv     : tanggal,komoditas_id,pasar_id,biaya_per_kg
- kalender.csv     : tanggal,jenis_hari          (hanya hari libur: jenis_hari=libur)
"""

from __future__ import annotations

import argparse
import csv
import zlib
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from .harga import InputHarga
from .katalog import KOMODITAS_HARGA, PASAR

TANGGAL_ACUAN = date(2026, 10, 5)  # Senin

HARGA_DASAR = {  # IDR/kg (atau per butir/liter) kasar; hanya untuk skala fixture
    "cmd_beras_medium": 13000,
    "cmd_telur_ayam": 30000,
    "cmd_cabai_merah": 45000,
    "cmd_cabai_rawit": 55000,
    "cmd_bawang_merah": 38000,
    "cmd_bawang_putih": 36000,
    "cmd_minyak_goreng_curah": 17000,
    "cmd_gula_pasir": 18000,
    "cmd_daging_ayam": 38000,
    "cmd_daging_sapi": 130000,
    "cmd_tomat": 12000,
    "cmd_kangkung": 6000,
}
# komoditas segar lebih fluktuatif
VOLATIL = {
    "cmd_cabai_merah": 0.05,
    "cmd_cabai_rawit": 0.06,
    "cmd_bawang_merah": 0.04,
    "cmd_tomat": 0.05,
    "cmd_kangkung": 0.045,
}


def _rng(*kunci: str, seed: int = 20261005) -> np.random.Generator:
    return np.random.default_rng(seed + zlib.crc32("|".join(kunci).encode()))


def libur_sintetis(awal: date, akhir: date) -> frozenset[date]:
    """Libur nasional fiktif (tanggal 17 tiap bulan) agar jenis_hari `libur` teruji."""
    out, d = set(), awal
    while d <= akhir:
        if d.day == 17:
            out.add(d)
        d += timedelta(days=1)
    return frozenset(out)


def seri_harga(
    komoditas: str, pasar: str, awal: date, hari: int, seed: int = 20261005
) -> dict[date, tuple[int, int]]:
    """{tanggal: (harga_median, sampel_lapak)} sepanjang `hari` hari mulai `awal`."""
    r = _rng("harga", komoditas, pasar, seed=seed)
    dasar = HARGA_DASAR[komoditas] * (0.95 + 0.1 * r.random())
    vol = VOLATIL.get(komoditas, 0.02)
    level, out = dasar, {}
    for k in range(hari):
        d = awal + timedelta(days=k)
        level *= 1.0 + r.normal(0.0, vol * 0.25)  # jalan acak lambat
        level = float(np.clip(level, 0.6 * dasar, 1.6 * dasar))
        mingguan = 1.0 + (0.03 if d.weekday() >= 5 else 0.0)
        musim = 1.0 + 0.04 * np.sin(2 * np.pi * k / 90.0)
        harga = level * mingguan * musim * (1.0 + r.normal(0.0, vol * 0.6))
        out[d] = (int(round(harga / 100.0) * 100), int(r.integers(2, 9)))
    return out


def seri_stok(komoditas: str, awal: date, hari: int, seed: int = 20261005) -> dict[date, float]:
    r = _rng("stok", komoditas, seed=seed)
    return {awal + timedelta(days=k): float(max(0.0, 1000 * (1 + r.normal(0, 0.18)))) for k in range(hari)}


def seri_logistik(
    komoditas: str, pasar: str, awal: date, hari: int, seed: int = 20261005
) -> dict[date, float]:
    r = _rng("logistik", komoditas, pasar, seed=seed)
    dasar = 800 + 400 * r.random()
    return {
        awal + timedelta(days=k): float(round(dasar * (1 + 0.1 * np.sin(k / 20) + r.normal(0, 0.01))))
        for k in range(hari)
    }


def bangun_masukan_harga_sintetis(
    komoditas: str, pasar: str, hari_ini: date = TANGGAL_ACUAN, riwayat: int = 60
) -> InputHarga:
    awal = hari_ini - timedelta(days=riwayat)
    harga = {d: float(v[0]) for d, v in seri_harga(komoditas, pasar, awal, riwayat).items()}
    sampel = list(seri_harga(komoditas, pasar, awal, riwayat).values())[-1][1]
    return InputHarga(
        komoditas_id=komoditas,
        pasar_id=pasar,
        hari_ini=hari_ini,
        harga=harga,
        stok=seri_stok(komoditas, awal, riwayat),
        biaya_logistik=seri_logistik(komoditas, pasar, awal, riwayat),
        libur=libur_sintetis(awal, hari_ini + timedelta(days=8)),
        sampel_lapak=sampel,
    )


def tulis_fixture(keluar: Path, awal: date, hari: int) -> None:
    """Menulis CSV sintetis untuk 12 komoditas x 8 pasar sepanjang `hari` hari mulai `awal`."""
    keluar.mkdir(parents=True, exist_ok=True)
    with (
        (keluar / "harga_harian.csv").open("w", newline="") as f1,
        (keluar / "logistik.csv").open("w", newline="") as f2,
    ):
        w1, w2 = csv.writer(f1), csv.writer(f2)
        w1.writerow(["tanggal", "komoditas_id", "pasar_id", "harga_median", "sampel_lapak"])
        w2.writerow(["tanggal", "komoditas_id", "pasar_id", "biaya_per_kg"])
        for kom in KOMODITAS_HARGA:
            for psr in PASAR:
                for d, (h, s) in seri_harga(kom, psr, awal, hari).items():
                    w1.writerow([d.isoformat(), kom, psr, h, s])
                for d, b in seri_logistik(kom, psr, awal, hari).items():
                    w2.writerow([d.isoformat(), kom, psr, int(b)])
    with (keluar / "stok_harian.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tanggal", "komoditas_id", "stok_kg"])
        for kom in KOMODITAS_HARGA:
            for d, v in seri_stok(kom, awal, hari).items():
                w.writerow([d.isoformat(), kom, f"{v:.2f}"])
    with (keluar / "kalender.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tanggal", "jenis_hari"])
        for d in sorted(libur_sintetis(awal, awal + timedelta(days=hari + 40))):
            w.writerow([d.isoformat(), "libur"])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Tulis fixture SINTETIS (bukan data nyata)")
    p.add_argument("--keluar", required=True, type=Path)
    p.add_argument("--akhir", default=TANGGAL_ACUAN.isoformat(), help="tanggal hari ini (H); data sampai H-1")
    p.add_argument("--hari", type=int, default=150)
    a = p.parse_args()
    akhir = date.fromisoformat(a.akhir)
    tulis_fixture(a.keluar, akhir - timedelta(days=a.hari), a.hari)
    print(f"fixture SINTETIS ditulis ke {a.keluar}")
