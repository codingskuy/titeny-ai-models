"""Pembangkit model card (harga/panen/demand) dari `ringkasan_backtest.json` (BR-301).

Setiap kartu memuat versi model, metrik eval, dan tanggal backtest. Angka HANYA disalin dari ringkasan hasil
jalan nyata; bagian yang belum ada datanya ditulis apa adanya ("belum dievaluasi"), tidak diisi tebakan.

Pakai: python -m titeny_models.kartu_model --ringkasan <ringkasan_backtest.json> --keluar model-card/
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .evaluasi import (
    MAPE_DEMAND_H7_MAKS,
    MAPE_DEMAND_H30_PANTAU,
    MAPE_H1_MEDIAN_MAKS,
    MAPE_H1_PER_KOMODITAS_MAKS,
    MAPE_H7_HARGA_MAKS,
    MAPE_PANEN_MUSIM_MAKS,
)


def _f(x, satuan="%") -> str:
    return "n/a" if x is None else f"{x:.2f}{satuan}"


def _lulus(ok: bool | None) -> str:
    return "n/a" if ok is None else ("lulus" if ok else "GAGAL")


def _banner(r: dict) -> str:
    if r["sumber_data"] == "SINTETIS":
        return (
            "> PERINGATAN: metrik di kartu ini dihitung dari data SINTETIS (fixture deterministik), BUKAN data pasar nyata. "
            "Angka hanya membuktikan alur backtest berjalan; bukan klaim akurasi produksi. "
            "Ganti dengan backtest data nyata sebelum rilis.\n"
        )
    return f"> Sumber data: {r['sumber_data']}.\n"


def _kepala(nama: str, versi: str, r: dict) -> str:
    return (
        f"# Model card: {nama} `{versi}`\n\n{_banner(r)}\n"
        f"| Item | Nilai |\n|---|---|\n| Versi model | `{versi}` |\n"
        f"| Tanggal backtest | {r['tanggal_backtest']} |\n"
        f"| Data terakhir dipakai | {r['akhir_data']} |\n"
        f"| Jendela backtest | {r['hari']} hari, walk-forward (hanya data sebelum hari asal) |\n"
        f"| Sumber data | {r['sumber_data']} |\n\n"
    )


def _kalibrasi(blok: dict | None) -> str:
    if not blok:
        return "## Kalibrasi rentang P10-P90\n\nBelum dihitung pada ringkasan ini (lihat TTN-AI-005).\n\n"
    return (
        "## Kalibrasi rentang P10-P90\n\n"
        f"- Cakupan aktual: {_f(blok.get('cakupan_pct'))} (target 70-90%; < 60% memicu kalibrasi ulang)\n"
        f"- Status: {blok.get('status', 'n/a')}\n\n"
    )


def kartu_harga(r: dict) -> str:
    h = r["harga"]
    t = h["target"]
    bias = h["bias_h7"]
    baris = "\n".join(
        f"| `{k}` | {_f(h['mape_h1_per_komoditas'].get(k))} | {_f(h['mape_h7_per_komoditas'].get(k))} |"
        for k in sorted(h["mape_h1_per_komoditas"])
    )
    return (
        _kepala("Harga 12 komoditas x 8 pasar, H+1..H+7", "harga_v1.0.0", r)
        + "## Metode\n\nTanpa deep learning, 5 langkah per (komoditas, pasar): baseline median 14 hari pada `jenis_hari` sama; "
        "koreksi tren regresi linier 21 hari (+-8%/hari); koreksi stok +-4%; koreksi logistik 80%; potong 0,70-1,60x median 30 hari "
        "lalu bulatkan ke 500 IDR. Fallback: median 7 hari (data kemarin) bila S1 kosong 1-2 hari; pasangan dihentikan bila >= 3 hari.\n\n"
        "## Metrik evaluasi (backtest)\n\n"
        "| Metrik | Nilai | Target | Status |\n|---|---|---|---|\n"
        f"| MAPE H+1, median 12 komoditas | {_f(h['mape_h1_median'])} | <= {MAPE_H1_MEDIAN_MAKS:g}% | {_lulus(t['h1_median_le_8'])} |\n"
        f"| MAPE H+1, komoditas terburuk | {_f(max(h['mape_h1_per_komoditas'].values(), default=None))} | <= {MAPE_H1_PER_KOMODITAS_MAKS:g}% | {_lulus(t['h1_tidak_ada_gt_15'])} |\n"
        f"| MAPE H+7, rata-rata makro | {_f(h['mape_h7_rata_makro'])} | <= {MAPE_H7_HARGA_MAKS:g}% | {_lulus(t['h7_le_12'])} |\n\n"
        f"Jumlah titik evaluasi: {h['jumlah_titik']}.\n\n"
        "### Bias H+7 (over/under dilaporkan terpisah)\n\n"
        f"- Bias rata-rata: {_f(bias['bias_rata_pct'])}; porsi overpredict: {_f(None if bias['porsi_over'] is None else bias['porsi_over'] * 100)}\n"
        f"- Rata-rata over: {_f(bias['rata_over_pct'])}; rata-rata under: {_f(bias['rata_under_pct'])}\n"
        "- Overpredict > 5% dua minggu berturut-turut memicu tinjauan analis.\n\n"
        f"### MAPE per komoditas\n\n| Komoditas | H+1 | H+7 |\n|---|---|---|\n{baris}\n\n"
        + _kalibrasi(h.get("kalibrasi"))
        + "## Batasan\n\nDi atas H+7 dipotong; tanpa teks bebas/sentimen; naik versi hanya bila backtest 90 hari menunjukkan "
        "MAPE H+7 turun >= 0,5 poin dan tidak ada komoditas memburuk > 2 poin (BR-206).\n"
    )


def kartu_demand(r: dict) -> str:
    d = r.get("demand")
    if not d:
        return (
            _kepala("Demand H+7/H+30", "demand_v1.0.0", r)
            + "## Metrik evaluasi\n\nBelum dievaluasi: data transaksi (S3) tidak tersedia pada backtest ini.\n"
        )
    return (
        _kepala("Demand 12 komoditas x 16 zona, H+7/H+30", "demand_v1.0.0", r)
        + "## Metode\n\nBaseline rata-rata 28 hari x faktor hari besar (puasa 1,18; lebaran 1,35/1,10; natal-tahun baru 1,12) x elastisitas harga "
        "(-4% pokok / -7% sayur per +10%), batas +-30% vs baseline. Sinyal surplus (>= 120%) / defisit (<= 80%) terhadap panen kabupaten terdekat.\n\n"
        "## Metrik evaluasi (backtest)\n\n"
        "| Metrik | Nilai | Batas | Status |\n|---|---|---|---|\n"
        f"| MAPE H+7, rata-rata makro | {_f(d['mape_h7_rata_makro'])} | <= {MAPE_DEMAND_H7_MAKS:g}% | {_lulus(d['target_h7']['lulus'])} |\n"
        f"| MAPE H+30, rata-rata makro | {_f(d['mape_h30_rata_makro'])} | <= {MAPE_DEMAND_H30_PANTAU:g}% (hanya pantau) | {_lulus(d['target_h30']['lulus'])} (pantau) |\n\n"
        f"Jumlah titik evaluasi: {d['jumlah_titik']}. Backtest memakai `rasio_harga = 1,0` (elastisitas tidak diuji).\n\n"
        f"- Bias H+7: rata-rata {_f(d['bias_h7']['bias_rata_pct'])}; over {_f(d['bias_h7']['rata_over_pct'])}; under {_f(d['bias_h7']['rata_under_pct'])}\n"
        f"- Bias H+30: rata-rata {_f(d['bias_h30']['bias_rata_pct'])}; over {_f(d['bias_h30']['rata_over_pct'])}; under {_f(d['bias_h30']['rata_under_pct'])}\n\n"
        + _kalibrasi(d.get("kalibrasi"))
        + "## Batasan\n\nRekomendasi bersifat anjuran, tidak membuat pesanan otomatis; H+30 hanya dipantau (<= 22%).\n"
    )


def kartu_panen(r: dict) -> str:
    p = r.get("panen", {})
    return (
        _kepala("Panen 6 komoditas x 5 kabupaten, M+1..M+4", "panen_v1.0.0", r)
        + "## Metode\n\nPanen mingguan = luas panen ekspektasi (catatan tanam mundur 90-120 hari padi/jagung, 60-75 hari sayur) x yield baseline "
        "(median 3 musim) x faktor cuaca (1,00 / 0,85 hujan > 300 mm atau banjir / 0,90 kekeringan) x faktor musim; bulat 50 kg. "
        "Kabupaten terkunci: Karawang, Subang, Garut, Brebes, Malang.\n\n"
        "## Metrik evaluasi\n\n"
        f"Belum dievaluasi: {p.get('status', 'tidak ada data aktual panen')}. Target: MAPE total musim <= {MAPE_PANEN_MUSIM_MAKS:g}%. "
        "Skor per musim dihitung job `mape` (Minggu 23.00 WIB) begitu data aktual panen nyata tersedia.\n\n"
        + _kalibrasi(p.get("kalibrasi"))
        + "## Batasan\n\nKepercayaan `rendah` + rekomendasi generik bila catatan panen < 10 baris per kabupaten/musim.\n"
    )


def tulis_kartu(ringkasan: dict, keluar: Path) -> list[Path]:
    keluar.mkdir(parents=True, exist_ok=True)
    hasil = []
    for versi, fungsi in (
        ("harga_v1.0.0", kartu_harga),
        ("panen_v1.0.0", kartu_panen),
        ("demand_v1.0.0", kartu_demand),
    ):
        tujuan = keluar / f"{versi}.md"
        tujuan.write_text(fungsi(ringkasan))
        hasil.append(tujuan)
    return hasil


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Bangkitkan model card dari ringkasan backtest")
    p.add_argument("--ringkasan", required=True, type=Path)
    p.add_argument("--keluar", required=True, type=Path)
    a = p.parse_args(argv)
    for berkas in tulis_kartu(json.loads(a.ringkasan.read_text()), a.keluar):
        print(berkas)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
