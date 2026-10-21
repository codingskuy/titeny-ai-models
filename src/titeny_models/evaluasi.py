"""Metrik evaluasi (BR-301, metrik/10-akurasi-dan-adopsi.md bagian 2): MAPE, bias, target, gerbang versi.

Fungsi murni tanpa I/O. Definisi (ASUMSI di mana TownHall tidak eksplisit; dicatat di PR):
- MAPE = rata-rata |aktual - prediksi| / aktual x 100, titik dengan aktual <= 0 dilewati.
- Bias relatif per titik = (prediksi - aktual) / aktual x 100; over = positif, under = negatif.
- MAPE per komoditas = rata-rata (makro) MAPE seluruh pasangan komoditas-pasar/zona milik komoditas itu.
- "MAPE H+7 turun >= 0,5 poin" memakai rata-rata makro MAPE H+7 lintas komoditas.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

MAPE_H1_MEDIAN_MAKS = 8.0
MAPE_H1_PER_KOMODITAS_MAKS = 15.0
MAPE_H7_HARGA_MAKS = 12.0
MAPE_DEMAND_H7_MAKS = 15.0
MAPE_DEMAND_H30_PANTAU = 22.0
MAPE_PANEN_MUSIM_MAKS = 20.0
BIAS_OVER_AMBANG = 5.0  # % ; > ambang 2 minggu berturut -> tinjauan analis
KENAIKAN_VERSI_MIN_TURUN = 0.5  # poin
KENAIKAN_VERSI_MAKS_MEMBURUK = 2.0  # poin


def _pasangan_valid(aktual: Sequence[float], prediksi: Sequence[float]):
    if len(aktual) != len(prediksi):
        raise ValueError("panjang aktual dan prediksi harus sama")
    return [(a, p) for a, p in zip(aktual, prediksi, strict=True) if a > 0]


def mape(aktual: Sequence[float], prediksi: Sequence[float]) -> float | None:
    """MAPE dalam persen; `None` bila tak ada titik dengan aktual > 0."""
    pasangan = _pasangan_valid(aktual, prediksi)
    if not pasangan:
        return None
    return 100.0 * sum(abs(a - p) / a for a, p in pasangan) / len(pasangan)


def bias_ringkas(aktual: Sequence[float], prediksi: Sequence[float]) -> dict:
    """Bias rata-rata, serta rata-rata over dan under yang dilaporkan terpisah (dalam persen)."""
    rel = [100.0 * (p - a) / a for a, p in _pasangan_valid(aktual, prediksi)]
    over = [r for r in rel if r > 0]
    under = [r for r in rel if r < 0]
    return {
        "n": len(rel),
        "bias_rata_pct": sum(rel) / len(rel) if rel else None,
        "rata_over_pct": sum(over) / len(over) if over else None,
        "rata_under_pct": sum(under) / len(under) if under else None,
        "porsi_over": len(over) / len(rel) if rel else None,
    }


def tinjauan_bias(bias_mingguan: Sequence[float | None]) -> bool:
    """True bila bias rata-rata > +5% (overpredict) pada DUA minggu terakhir berturut-turut."""
    if len(bias_mingguan) < 2:
        return False
    terakhir = bias_mingguan[-2:]
    return all(b is not None and b > BIAS_OVER_AMBANG for b in terakhir)


def periksa_target(
    mape_h1_per_komoditas: Mapping[str, float], mape_h7_per_komoditas: Mapping[str, float]
) -> dict[str, bool]:
    """Target harga v1.0.0: H+1 median <= 8% dan tidak ada komoditas > 15%; H+7 <= 12% (rata-rata makro)."""
    h1 = list(mape_h1_per_komoditas.values())
    h7 = list(mape_h7_per_komoditas.values())
    return {
        "h1_median_le_8": bool(h1) and statistics.median(h1) <= MAPE_H1_MEDIAN_MAKS,
        "h1_tidak_ada_gt_15": bool(h1) and max(h1) <= MAPE_H1_PER_KOMODITAS_MAKS,
        "h7_le_12": bool(h7) and sum(h7) / len(h7) <= MAPE_H7_HARGA_MAKS,
    }


@dataclass(frozen=True)
class KeputusanVersi:
    naik: bool
    alasan: str
    turun_poin: float
    memburuk: list[str] = field(default_factory=list)


def keputusan_naik_versi(
    mape_h7_berjalan: Mapping[str, float], mape_h7_kandidat: Mapping[str, float]
) -> KeputusanVersi:
    """Naik versi hanya bila MAPE H+7 (rata-rata makro) turun >= 0,5 poin DAN tidak ada komoditas memburuk > 2 poin."""
    if set(mape_h7_berjalan) != set(mape_h7_kandidat):
        raise ValueError("komoditas versi berjalan dan kandidat harus sama")
    if not mape_h7_berjalan:
        raise ValueError("tidak ada komoditas untuk dibandingkan")
    n = len(mape_h7_berjalan)
    turun = sum(mape_h7_berjalan.values()) / n - sum(mape_h7_kandidat.values()) / n
    memburuk = sorted(
        k
        for k in mape_h7_berjalan
        if mape_h7_kandidat[k] - mape_h7_berjalan[k] > KENAIKAN_VERSI_MAKS_MEMBURUK
    )
    if memburuk:
        return KeputusanVersi(False, f"komoditas memburuk > 2 poin: {', '.join(memburuk)}", turun, memburuk)
    if turun < KENAIKAN_VERSI_MIN_TURUN:
        return KeputusanVersi(False, f"MAPE H+7 turun {turun:.2f} poin (< 0,5 poin)", turun)
    return KeputusanVersi(
        True, f"MAPE H+7 turun {turun:.2f} poin (>= 0,5) dan tidak ada komoditas memburuk > 2 poin", turun
    )
