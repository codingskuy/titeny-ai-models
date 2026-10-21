"""Kalibrasi rentang P10-P90 dan label kepercayaan (BR-205, FR-103, metrik/10 bagian 2).

Fungsi murni (tanpa I/O, tanpa impor model) agar harga/demand/panen dapat memakainya tanpa impor melingkar.

Definisi (ASUMSI di mana TownHall tidak eksplisit; dicatat di PR dan ADR-0003):
- Residual relatif = (aktual - prediksi) / prediksi; rentang = prediksi x (1 + P10) .. prediksi x (1 + P90).
- "Residual 30 hari" = 30 residual terbaru yang sudah dapat dievaluasi untuk pasangan dan horizon yang sama;
  kurang dari `MIN_RESIDUAL` (10) titik -> tidak dikalibrasi (rentang = titik / `None`).
- Rentang selalu dipaksa memuat titik prediksi (bawah <= titik <= atas) walau residual berbias satu arah.
- Kepercayaan: `rendah` bila sampel < 3 atau MAPE_14h > 15; `tinggi` bila sampel >= 5 dan MAPE_14h < 8;
  selain itu `sedang`. Tanpa MAPE_14h (belum ada riwayat) tidak pernah `tinggi`.
- Status cakupan: 70-90% = ok; < 60% = kalibrasi ulang otomatis; 60-70% = di_bawah_target (pantau);
  > 90% = terlalu_lebar (tidak memicu apa pun; hanya dilaporkan).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

JENDELA_RESIDUAL = 30
MIN_RESIDUAL = 10
CAKUPAN_MIN, CAKUPAN_MAKS, CAKUPAN_KALIBRASI_ULANG = 70.0, 90.0, 60.0
SAMPEL_TINGGI, SAMPEL_RENDAH = 5, 3
MAPE_TINGGI, MAPE_RENDAH = 8.0, 15.0


@dataclass(frozen=True)
class Kalibrasi:
    p10: float  # residual relatif P10
    p90: float  # residual relatif P90
    n: int  # jumlah residual yang dipakai


def kalibrasi_dari_residual(residual: Sequence[float]) -> Kalibrasi | None:
    """P10/P90 dari 30 residual relatif terbaru (urut lama -> baru); `None` bila < MIN_RESIDUAL titik."""
    terbaru = list(residual)[-JENDELA_RESIDUAL:]
    if len(terbaru) < MIN_RESIDUAL:
        return None
    p10, p90 = np.percentile(np.array(terbaru, dtype=float), [10, 90])
    return Kalibrasi(float(p10), float(p90), len(terbaru))


def _bulatkan_500(x: float) -> int:
    return int((x + 250) // 500) * 500


def rentang_harga(harga: int, kal: Kalibrasi | None) -> tuple[int, int]:
    """(bawah, atas) kelipatan 500 IDR yang memuat `harga`; tanpa kalibrasi = (harga, harga)."""
    if kal is None:
        return harga, harga
    bawah = _bulatkan_500(harga * (1.0 + kal.p10))
    atas = _bulatkan_500(harga * (1.0 + kal.p90))
    return max(0, min(bawah, harga)), max(atas, harga)


def rentang_kg(nilai: float, kal: Kalibrasi | None) -> tuple[float | None, float | None]:
    """(bawah, atas) kg tidak negatif yang memuat `nilai`; tanpa kalibrasi = (None, None)."""
    if kal is None:
        return None, None
    bawah = nilai * (1.0 + kal.p10)
    atas = nilai * (1.0 + kal.p90)
    return max(0.0, min(bawah, nilai)), max(atas, nilai)


def hitung_kepercayaan(sampel_lapak: int, mape_14h: float | None) -> str:
    """`tinggi` | `sedang` | `rendah` menurut BR-205."""
    if sampel_lapak < SAMPEL_RENDAH or (mape_14h is not None and mape_14h > MAPE_RENDAH):
        return "rendah"
    if sampel_lapak >= SAMPEL_TINGGI and mape_14h is not None and mape_14h < MAPE_TINGGI:
        return "tinggi"
    return "sedang"


def cakupan(aktual: Sequence[float], bawah: Sequence[float], atas: Sequence[float]) -> float | None:
    """Persentase titik dengan bawah <= aktual <= atas; `None` bila kosong."""
    if not (len(aktual) == len(bawah) == len(atas)):
        raise ValueError("panjang aktual, bawah, atas harus sama")
    if not aktual:
        return None
    dalam = sum(1 for a, b, t in zip(aktual, bawah, atas, strict=True) if b <= a <= t)
    return 100.0 * dalam / len(aktual)


def perlu_kalibrasi_ulang(cakupan_pct: float | None) -> bool:
    return cakupan_pct is not None and cakupan_pct < CAKUPAN_KALIBRASI_ULANG


def status_cakupan(cakupan_pct: float | None) -> str:
    if cakupan_pct is None:
        return "tidak_ada_data"
    if cakupan_pct < CAKUPAN_KALIBRASI_ULANG:
        return "kalibrasi_ulang"
    if cakupan_pct < CAKUPAN_MIN:
        return "di_bawah_target"
    if cakupan_pct <= CAKUPAN_MAKS:
        return "ok"
    return "terlalu_lebar"
