"""Hindcast untuk kalibrasi: residual walk-forward pasangan (TTN-AI-005).

Residual diambil dari replay model pada hari-hari lampau (`backtest_*`), hanya memakai data sebelum tiap hari asal.
Pada hari hitung H, sebuah residual baru "diketahui" bila tanggal targetnya < H.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import date

from .backtest import backtest_demand, backtest_harga
from .demand import InputDemand
from .evaluasi import mape
from .harga import InputHarga
from .kalibrasi import Kalibrasi, kalibrasi_dari_residual, residual_relatif

HINDCAST_HARI_HARGA = 45  # cukup untuk 30 residual H+7 (origin <= H-8)
HINDCAST_HARI_DEMAND = 60
JENDELA_MAPE_14H = 14


def kalibrasi_dari_baris(baris: list[dict]) -> dict[str, Kalibrasi]:
    """Per horizon: P10/P90 dari 30 residual terbaru (urut origin). Horizon < MIN_RESIDUAL titik dilewati."""
    per_horizon: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for b in baris:
        r = residual_relatif(b["aktual"], b["prediksi"])
        if r is not None:
            per_horizon[b["horizon"]].append((b["origin"], r))
    hasil = {}
    for horizon, titik in per_horizon.items():
        kal = kalibrasi_dari_residual([r for _, r in sorted(titik)])
        if kal is not None:
            hasil[horizon] = kal
    return hasil


def mape_14h(baris: list[dict]) -> float | None:
    """MAPE H+1 pada 14 titik terbaru."""
    h1 = sorted((b for b in baris if b["horizon"] == "H+1"), key=lambda b: b["origin"])[-JENDELA_MAPE_14H:]
    return mape([b["aktual"] for b in h1], [b["prediksi"] for b in h1])


def kalibrasi_harga_pasangan(
    m: InputHarga, hari_ini: date | None = None
) -> tuple[dict[str, Kalibrasi], float | None]:
    """(kalibrasi per horizon, MAPE_14h) untuk satu pasangan komoditas-pasar pada `hari_ini` (bawaan `m.hari_ini`)."""
    h = hari_ini or m.hari_ini
    baris = backtest_harga([m], h, HINDCAST_HARI_HARGA)
    return kalibrasi_dari_baris(baris), mape_14h(baris)


def mape_14h_pasangan(m: InputHarga, hari_ini: date | None = None) -> float | None:
    """MAPE_14h saja (replay pendek: 16 hari asal) untuk job harian."""
    return mape_14h(backtest_harga([m], hari_ini or m.hari_ini, JENDELA_MAPE_14H + 2))


def kalibrasi_demand_pasangan(m: InputDemand, hari_ini: date | None = None) -> dict[str, Kalibrasi]:
    h = hari_ini or m.hari_ini
    return kalibrasi_dari_baris(backtest_demand([m], h, HINDCAST_HARI_DEMAND))


def kunci_pasangan(komoditas_id: str, unit: str) -> str:
    return f"{komoditas_id}|{unit}"


def simpan_kalibrasi(kal: Mapping[str, Kalibrasi]) -> dict:
    return {h: {"p10": k.p10, "p90": k.p90, "n": k.n} for h, k in sorted(kal.items())}


def muat_kalibrasi(blok: Mapping[str, Mapping[str, float]]) -> dict[str, Kalibrasi]:
    return {h: Kalibrasi(p10=v["p10"], p90=v["p90"], n=int(v["n"])) for h, v in blok.items()}


__all__ = [
    "HINDCAST_HARI_DEMAND",
    "HINDCAST_HARI_HARGA",
    "kalibrasi_dari_baris",
    "kalibrasi_demand_pasangan",
    "kalibrasi_harga_pasangan",
    "kunci_pasangan",
    "mape_14h",
    "mape_14h_pasangan",
    "muat_kalibrasi",
    "residual_relatif",
    "simpan_kalibrasi",
]
