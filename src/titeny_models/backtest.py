"""Backtest walk-forward 90 hari (BR-301, BR-206, FR-105) untuk harga dan demand.

Tiap hari asal O di jendela 90 hari terakhir, model dijalankan HANYA dengan data < O (model sudah menyaring
`d < hari_ini`; uji kebocoran ada di tests), lalu dibandingkan dengan aktual yang sudah tersedia (O+i < akhir).
`akhir` (T) = hari pertama tanpa data; data terakhir = T-1.

ASUMSI (dicatat di PR):
- Backtest demand memakai `rasio_harga = 1,0` (elastisitas tidak diuji di sini karena butuh prediksi harga historis).
- Panen TIDAK dibacktest: aktual panen mingguan belum tersedia sebagai masukan; evaluasi panen per musim berjalan
  lewat job `mape` bila data nyata ada. Model card panen menyatakan ini apa adanya (tanpa mengarang angka).
- Gerbang naik versi memakai harga H+7 (lihat `evaluasi.keputusan_naik_versi`).
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import statistics
from collections import defaultdict
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

from .demand import InputDemand, ramal_demand_pasangan
from .evaluasi import (
    MAPE_DEMAND_H7_MAKS,
    MAPE_DEMAND_H30_PANTAU,
    bias_ringkas,
    keputusan_naik_versi,
    mape,
    periksa_target,
)
from .harga import WIB, InputHarga, ramal_harga_pasangan
from .kalibrasi import cakupan_walk_forward, rentang_harga, rentang_kg, status_cakupan
from .muat import muat_masukan_harga
from .muat_agro import muat_masukan_demand

MODEL_HARGA = Callable[[InputHarga], list | None]
MODEL_DEMAND = Callable[[InputDemand], list | None]
HARI_BACKTEST = 90
PENANDA_SINTETIS = "SINTETIS.txt"


def backtest_harga(
    masukan: list[InputHarga],
    akhir: date,
    hari: int = HARI_BACKTEST,
    model: MODEL_HARGA = ramal_harga_pasangan,
) -> list[dict]:
    """Baris {origin, komoditas_id, pasar_id, horizon, aktual, prediksi} untuk H+1..H+7."""
    waktu = datetime(2000, 1, 1, tzinfo=WIB)  # tetap: backtest deterministik
    baris = []
    for m in masukan:
        for k in range(hari, 0, -1):
            asal = akhir - timedelta(days=k)
            hasil = model(replace(m, hari_ini=asal, waktu_hitung=waktu))
            if hasil is None:
                continue
            for p in hasil:
                aktual = m.harga.get(p.tanggal_prediksi)
                if aktual is None or p.tanggal_prediksi >= akhir:
                    continue
                baris.append(
                    {
                        "origin": asal.isoformat(),
                        "komoditas_id": m.komoditas_id,
                        "pasar_id": m.pasar_id,
                        "horizon": p.horizon,
                        "aktual": aktual,
                        "prediksi": p.harga_prediksi,
                    }
                )
    return baris


def backtest_demand(
    masukan: list[InputDemand],
    akhir: date,
    hari: int = HARI_BACKTEST,
    model: MODEL_DEMAND = ramal_demand_pasangan,
) -> list[dict]:
    """Baris untuk `H+7_total_kg` dan `H+30`: aktual = jumlah volume harian pada horizon bila lengkap."""
    waktu = datetime(2000, 1, 1, tzinfo=WIB)
    panjang = {"H+7_total_kg": 7, "H+30": 30}
    baris = []
    for m in masukan:
        for k in range(hari, 0, -1):
            asal = akhir - timedelta(days=k)
            hasil = model(replace(m, hari_ini=asal, waktu_hitung=waktu))
            if hasil is None:
                continue
            for p in hasil:
                n = panjang[p.horizon]
                hari_aktual = [asal + timedelta(days=j) for j in range(1, n + 1)]
                if hari_aktual[-1] >= akhir or any(d not in m.volume for d in hari_aktual):
                    continue
                baris.append(
                    {
                        "origin": asal.isoformat(),
                        "komoditas_id": m.komoditas_id,
                        "zona": m.zona,
                        "horizon": p.horizon,
                        "aktual": sum(m.volume[d] for d in hari_aktual),
                        "prediksi": p.demand_prediksi_kg,
                    }
                )
    return baris


def _mape_per_kelompok(baris: list[dict], kunci_unit: str) -> dict[tuple[str, str], float]:
    """MAPE per (unit=pasangan, horizon) lalu dirata-rata makro per (komoditas, horizon)."""
    per_pasang: dict[tuple[str, str, str], tuple[list, list]] = defaultdict(lambda: ([], []))
    for b in baris:
        a, p = per_pasang[(b["komoditas_id"], b[kunci_unit], b["horizon"])]
        a.append(b["aktual"])
        p.append(b["prediksi"])
    per_kom: dict[tuple[str, str], list[float]] = defaultdict(list)
    for (kom, _unit, hor), (a, p) in per_pasang.items():
        nilai = mape(a, p)
        if nilai is not None:
            per_kom[(kom, hor)].append(nilai)
    return {k: sum(v) / len(v) for k, v in per_kom.items()}


def _ringkas_kalibrasi(baris: list[dict], kunci_unit: str, fn_rentang) -> dict:
    """Cakupan P10-P90 out-of-sample (interval dikalibrasi hanya dari residual yang sudah diketahui)."""
    r = cakupan_walk_forward(baris, kunci_unit, fn_rentang)
    return {**r, "status": status_cakupan(r["cakupan_pct"])}


def ringkas_harga(baris: list[dict]) -> dict:
    per_kom = _mape_per_kelompok(baris, "pasar_id")
    h1 = {k: v for (k, hor), v in per_kom.items() if hor == "H+1"}
    h7 = {k: v for (k, hor), v in per_kom.items() if hor == "H+7"}
    h7_baris = [b for b in baris if b["horizon"] == "H+7"]
    return {
        "mape_h1_per_komoditas": dict(sorted(h1.items())),
        "mape_h7_per_komoditas": dict(sorted(h7.items())),
        "mape_h1_median": statistics.median(h1.values()) if h1 else None,
        "mape_h7_rata_makro": sum(h7.values()) / len(h7) if h7 else None,
        "bias_h7": bias_ringkas([b["aktual"] for b in h7_baris], [b["prediksi"] for b in h7_baris]),
        "target": periksa_target(h1, h7),
        "jumlah_titik": len(baris),
        "kalibrasi": _ringkas_kalibrasi(baris, "pasar_id", lambda p, k: rentang_harga(int(p), k)),
    }


def ringkas_demand(baris: list[dict]) -> dict:
    per_kom = _mape_per_kelompok(baris, "zona")
    keluar: dict = {
        "jumlah_titik": len(baris),
        "kalibrasi": _ringkas_kalibrasi(baris, "zona", rentang_kg),
    }
    for hor, nama, batas in (
        ("H+7_total_kg", "h7", MAPE_DEMAND_H7_MAKS),
        ("H+30", "h30", MAPE_DEMAND_H30_PANTAU),
    ):
        nilai = {k: v for (k, h), v in per_kom.items() if h == hor}
        rata = sum(nilai.values()) / len(nilai) if nilai else None
        sub = [b for b in baris if b["horizon"] == hor]
        keluar[f"mape_{nama}_per_komoditas"] = dict(sorted(nilai.items()))
        keluar[f"mape_{nama}_rata_makro"] = rata
        keluar[f"bias_{nama}"] = bias_ringkas([b["aktual"] for b in sub], [b["prediksi"] for b in sub])
        keluar[f"target_{nama}"] = {"batas": batas, "lulus": rata is not None and rata <= batas,
                                    "status": "pantau" if nama == "h30" else "target"}  # fmt: skip
    return keluar


def _muat_fungsi(spesifikasi: str):
    modul, _, nama = spesifikasi.partition(":")
    if not nama:
        raise ValueError("format kandidat: paket.modul:fungsi")
    return getattr(importlib.import_module(modul), nama)


def _tulis_csv(path: Path, baris: list[dict]) -> None:
    if not baris:
        return
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(baris[0]))
        w.writeheader()
        w.writerows(baris)


def jalankan_backtest(
    data_dir: Path,
    keluar: Path,
    akhir: date,
    hari: int = HARI_BACKTEST,
    kandidat_harga: MODEL_HARGA | None = None,
    tanggal_backtest: date | None = None,
) -> dict:
    """Backtest harga (berjalan, +kandidat bila ada) dan demand; tulis CSV + `ringkasan_backtest.json`."""
    keluar.mkdir(parents=True, exist_ok=True)
    masukan_harga = muat_masukan_harga(data_dir, akhir)
    harga_berjalan = backtest_harga(masukan_harga, akhir, hari)
    ringkas = {
        "tanggal_backtest": (tanggal_backtest or datetime.now(WIB).date()).isoformat(),
        "akhir_data": (akhir - timedelta(days=1)).isoformat(),
        "hari": hari,
        "sumber_data": "SINTETIS"
        if (data_dir / PENANDA_SINTETIS).exists()
        else "tidak ditandai (periksa asal data)",
        "harga": {"model_version": "harga_v1.0.0", **ringkas_harga(harga_berjalan)},
    }
    _tulis_csv(keluar / "backtest.csv", harga_berjalan)

    if kandidat_harga is not None:
        harga_kandidat = backtest_harga(masukan_harga, akhir, hari, kandidat_harga)
        rk = ringkas_harga(harga_kandidat)
        keputusan = keputusan_naik_versi(
            ringkas["harga"]["mape_h7_per_komoditas"], rk["mape_h7_per_komoditas"]
        )
        ringkas["kandidat_harga"] = {
            **rk,
            "keputusan_naik_versi": {
                "naik": keputusan.naik,
                "alasan": keputusan.alasan,
                "turun_poin": keputusan.turun_poin,
                "memburuk": keputusan.memburuk,
            },
        }
        _tulis_csv(keluar / "backtest_kandidat.csv", harga_kandidat)

    if (data_dir / "transaksi_harian.csv").exists():
        demand = backtest_demand(muat_masukan_demand(data_dir, akhir, {}), akhir, hari)
        ringkas["demand"] = {"model_version": "demand_v1.0.0", **ringkas_demand(demand)}
        _tulis_csv(keluar / "backtest_demand.csv", demand)
    ringkas["panen"] = {
        "model_version": "panen_v1.0.0",
        "status": "tidak dibacktest: aktual panen mingguan belum tersedia sebagai masukan",
    }
    (keluar / "ringkasan_backtest.json").write_text(json.dumps(ringkas, indent=2, ensure_ascii=False))
    return ringkas


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Backtest 90 hari harga + demand (walk-forward)")
    p.add_argument("--data", required=True, type=Path)
    p.add_argument("--keluar", required=True, type=Path)
    p.add_argument("--akhir", required=True, help="T = hari pertama tanpa data (YYYY-MM-DD)")
    p.add_argument("--hari", type=int, default=HARI_BACKTEST)
    p.add_argument(
        "--kandidat-harga", help="paket.modul:fungsi kandidat (InputHarga -> list[PrediksiHarga] | None)"
    )
    p.add_argument("--tanggal-backtest", help="tanggal laporan (bawaan: hari ini WIB)")
    a = p.parse_args(argv)
    kandidat = _muat_fungsi(a.kandidat_harga) if a.kandidat_harga else None
    r = jalankan_backtest(
        a.data, a.keluar, date.fromisoformat(a.akhir), a.hari, kandidat,
        date.fromisoformat(a.tanggal_backtest) if a.tanggal_backtest else None,
    )  # fmt: skip
    print(json.dumps({k: r[k] for k in ("tanggal_backtest", "sumber_data", "hari")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
