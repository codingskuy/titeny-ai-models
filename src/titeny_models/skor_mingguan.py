"""Skor MAPE mingguan (Minggu 23.00 WIB, BR-301): prediksi yang sudah diarsipkan vs aktual yang kini tersedia.

Arsip: `<keluar>/arsip/prediksi_{harga|demand|panen}-YYYY-MM-DD.jsonl` (satu berkas per hari hitung, ditulis oleh
job terkait; idempoten bila job diulang). Minggu skor = Senin..Minggu yang berakhir pada tanggal hitung.

ASUMSI (dicatat di PR):
- Harga: titik dengan `tanggal_prediksi` di minggu skor, horizon H+1 dan H+7, dibandingkan dengan harga median
  harian aktual (S1) per (komoditas, pasar).
- Demand: `H+7_total_kg` dinilai bila `tanggal`+7 jatuh di minggu skor, `H+30` bila `tanggal`+30 jatuh di minggu
  skor; aktual = jumlah volume harian (S3) selama horizon, harus lengkap. Per (komoditas, zona).
- Panen: per (komoditas, kabupaten, musim) = |jumlah prediksi - jumlah aktual| / jumlah aktual pada minggu yang
  memiliki keduanya (MAPE total musim); aktual dari `hasil_panen.csv` dijumlah per minggu ISO.
- Alarm MAPE H+7 harga > 15% dua minggu berturut-turut -> `pager_analis`; bias > +5% dua minggu berturut-turut ->
  `tinjauan_analis` (metrik/10-akurasi-dan-adopsi.md bagian 2 dan 5).
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path

from .evaluasi import bias_ringkas, mape, tinjauan_bias
from .panen import minggu_iso

MAPE_H7_ALARM = 15.0


def baca_arsip(arsip_dir: Path, jenis: str) -> list[dict]:
    baris: list[dict] = []
    for berkas in sorted(arsip_dir.glob(f"prediksi_{jenis}-*.jsonl")):
        baris.extend(json.loads(b) for b in berkas.read_text().splitlines() if b.strip())
    return baris


def tulis_arsip(arsip_dir: Path, jenis: str, hari_ini: date, baris: Sequence[dict]) -> None:
    arsip_dir.mkdir(parents=True, exist_ok=True)
    tujuan = arsip_dir / f"prediksi_{jenis}-{hari_ini.isoformat()}.jsonl"
    sementara = tujuan.with_suffix(".jsonl.tmp")
    sementara.write_text("".join(json.dumps(b, ensure_ascii=False) + "\n" for b in baris))
    sementara.replace(tujuan)


def awal_minggu_skor(akhir: date) -> date:
    return akhir - timedelta(days=6)


def skor_harga(
    arsip: Sequence[dict], aktual: Mapping[tuple[str, str], Mapping[date, float]], akhir: date
) -> list[dict]:
    awal = awal_minggu_skor(akhir)
    kelompok: dict[tuple[str, str, str], tuple[list, list]] = defaultdict(lambda: ([], []))
    for b in arsip:
        if b["horizon"] not in ("H+1", "H+7"):
            continue
        target = date.fromisoformat(b["tanggal_prediksi"])
        nilai = aktual.get((b["komoditas_id"], b["pasar_id"]), {}).get(target)
        if nilai is None or not (awal <= target <= akhir):
            continue
        a, p = kelompok[(b["komoditas_id"], b["pasar_id"], b["horizon"])]
        a.append(nilai)
        p.append(b["harga_prediksi"])
    return [
        _baris("harga", {"komoditas_id": k, "pasar_id": u}, h, a, p, "harga_v1.0.0")
        for (k, u, h), (a, p) in sorted(kelompok.items())
    ]


def skor_demand(
    arsip: Sequence[dict], volume: Mapping[tuple[str, str], Mapping[date, float]], akhir: date
) -> list[dict]:
    awal = awal_minggu_skor(akhir)
    panjang = {"H+7_total_kg": 7, "H+30": 30}
    kelompok: dict[tuple[str, str, str], tuple[list, list]] = defaultdict(lambda: ([], []))
    for b in arsip:
        n = panjang.get(b["horizon"])
        asal = date.fromisoformat(b["tanggal"])
        if n is None or not (awal <= asal + timedelta(days=n) <= akhir):
            continue
        seri = volume.get((b["komoditas_id"], b["zona"]), {})
        hari = [asal + timedelta(days=j) for j in range(1, n + 1)]
        if any(d not in seri for d in hari):
            continue
        a, p = kelompok[(b["komoditas_id"], b["zona"], b["horizon"])]
        a.append(sum(seri[d] for d in hari))
        p.append(b["demand_prediksi_kg"])
    return [
        _baris("demand", {"komoditas_id": k, "zona": u}, h, a, p, "demand_v1.0.0")
        for (k, u, h), (a, p) in sorted(kelompok.items())
    ]


def skor_panen(
    arsip: Sequence[dict], hasil_per_minggu: Mapping[tuple[str, str], Mapping[str, tuple[str, float]]]
) -> list[dict]:
    """`hasil_per_minggu[(komoditas, kab)][minggu_iso] = (musim, kg aktual)`; MAPE total musim."""
    per_musim: dict[tuple[str, str, str], list[float]] = defaultdict(lambda: [0.0, 0.0, 0])
    for b in arsip:
        aktual = hasil_per_minggu.get((b["komoditas_id"], b["kabupaten_id"]), {}).get(b["minggu"])
        if aktual is None:
            continue
        musim, kg = aktual
        acc = per_musim[(b["komoditas_id"], b["kabupaten_id"], musim)]
        acc[0] += kg
        acc[1] += b["panen_prediksi_kg"]
        acc[2] += 1
    hasil = []
    for (kom, kab, musim), (akt, pred, n) in sorted(per_musim.items()):
        nilai = mape([akt], [pred])
        hasil.append(
            {"jenis": "panen", "komoditas_id": kom, "kabupaten_id": kab, "horizon": musim, "mape": nilai,
             "bias_pct": None if akt <= 0 else 100.0 * (pred - akt) / akt, "n": n, "model_version": "panen_v1.0.0"}
        )  # fmt: skip
    return hasil


def _baris(jenis: str, kunci: dict, horizon: str, aktual: list, prediksi: list, versi: str) -> dict:
    b = bias_ringkas(aktual, prediksi)
    return {"jenis": jenis, **kunci, "horizon": horizon, "mape": mape(aktual, prediksi),
            "bias_pct": b["bias_rata_pct"], "rata_over_pct": b["rata_over_pct"],
            "rata_under_pct": b["rata_under_pct"], "n": b["n"], "model_version": versi}  # fmt: skip


def ringkas_minggu(skor: Sequence[dict], akhir: date) -> dict:
    """Ringkasan per minggu: MAPE makro + bias gabungan per jenis/horizon (dasar alarm lintas minggu)."""

    def rata(nilai):
        nilai = [n for n in nilai if n is not None]
        return sum(nilai) / len(nilai) if nilai else None

    def bias_gabungan(baris):
        total = sum(b["n"] for b in baris if b.get("bias_pct") is not None)
        if not total:
            return None
        return sum(b["bias_pct"] * b["n"] for b in baris if b.get("bias_pct") is not None) / total

    harga = [s for s in skor if s["jenis"] == "harga"]
    demand = [s for s in skor if s["jenis"] == "demand"]
    return {
        "minggu": minggu_iso(akhir),
        "akhir": akhir.isoformat(),
        "harga": {
            "mape_h1": rata(s["mape"] for s in harga if s["horizon"] == "H+1"),
            "mape_h7": rata(s["mape"] for s in harga if s["horizon"] == "H+7"),
            "bias_pct": bias_gabungan(harga),
            "n": sum(s["n"] for s in harga),
        },
        "demand": {
            "mape_h7": rata(s["mape"] for s in demand if s["horizon"] == "H+7_total_kg"),
            "mape_h30": rata(s["mape"] for s in demand if s["horizon"] == "H+30"),
            "bias_pct": bias_gabungan(demand),
            "n": sum(s["n"] for s in demand),
        },
        "panen": {
            "mape_musim": rata(s["mape"] for s in skor if s["jenis"] == "panen"),
            "n": sum(1 for s in skor if s["jenis"] == "panen"),
        },
    }


def alarm_mape_h7(riwayat_h7: Sequence[float | None]) -> bool:
    """True bila MAPE H+7 > 15% pada dua minggu terakhir berturut-turut (pager analis)."""
    if len(riwayat_h7) < 2:
        return False
    return all(n is not None and n > MAPE_H7_ALARM for n in riwayat_h7[-2:])


def riwayat_ringkasan(arsip_dir: Path, sebelum_minggu: str) -> list[dict]:
    """Ringkasan minggu-minggu sebelumnya (urut lama -> baru) dari `arsip/ringkasan_mape-<minggu>.json`."""
    hasil = []
    for berkas in sorted(arsip_dir.glob("ringkasan_mape-*.json")):
        r = json.loads(berkas.read_text())
        if r["minggu"] < sebelum_minggu:
            hasil.append(r)
    return hasil


def evaluasi_alarm(sebelumnya: Sequence[dict], sekarang: dict) -> dict:
    urut = [*sebelumnya, sekarang]
    return {
        "pager_analis": alarm_mape_h7([r["harga"]["mape_h7"] for r in urut]),
        "tinjauan_analis": {
            "harga": tinjauan_bias([r["harga"]["bias_pct"] for r in urut]),
            "demand": tinjauan_bias([r["demand"]["bias_pct"] for r in urut]),
        },
    }
