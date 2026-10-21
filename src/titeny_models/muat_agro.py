"""Pemuat CSV untuk panen dan demand (skema: `sintetis_agro.py`). Tanpa koneksi DB; tidak membaca masa depan."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from .demand import InputDemand
from .muat import DataTidakLengkap, _baca
from .panen import InputPanen

YIELD_MIN, YIELD_MAKS = 500.0, 15000.0  # FR-004: hasil/ha valid 500-15.000 kg/ha


def muat_masukan_panen(data_dir: Path, hari_ini: date) -> list[InputPanen]:
    """Satu `InputPanen` per (komoditas, kabupaten) yang punya riwayat hasil panen."""
    tanam: dict[tuple[str, str], list[tuple[date, float]]] = defaultdict(list)
    for b in _baca(data_dir / "tanam.csv"):
        d = date.fromisoformat(b["tanggal_tanam"])
        if d < hari_ini:
            tanam[(b["komoditas_id"], b["kabupaten_id"])].append((d, float(b["luas_ha"])))

    # musim -> (tanggal paling awal, luas, kg, baris), per pasangan
    musim: dict[tuple[str, str], dict[str, list]] = defaultdict(dict)
    for b in _baca(data_dir / "hasil_panen.csv"):
        d = date.fromisoformat(b["tanggal"])
        if d >= hari_ini:
            continue
        m = musim[(b["komoditas_id"], b["kabupaten_id"])].setdefault(b["musim"], [d, 0.0, 0.0, 0])
        m[0] = min(m[0], d)
        m[1] += float(b["luas_panen_ha"])
        m[2] += float(b["hasil_kg"])
        m[3] += 1
    if not musim:
        raise DataTidakLengkap("hasil_panen.csv tidak berisi data sebelum tanggal hitung")

    hujan: dict[str, float] = defaultdict(float)
    peringatan: dict[str, tuple[date, str]] = {}
    for b in _baca(data_dir / "cuaca.csv"):
        d = date.fromisoformat(b["tanggal"])
        if hari_ini - timedelta(days=30) <= d < hari_ini:
            hujan[b["kabupaten_id"]] += float(b["curah_hujan_mm"])
        baru = b["peringatan"] and hari_ini - timedelta(days=7) <= d < hari_ini
        if baru and (b["kabupaten_id"] not in peringatan or d >= peringatan[b["kabupaten_id"]][0]):
            peringatan[b["kabupaten_id"]] = (d, b["peringatan"])

    hasil = []
    for (kom, kab), per_musim in sorted(musim.items()):
        urut = sorted(per_musim.values(), key=lambda m: m[0])  # lama -> baru
        yields = [m[2] / m[1] for m in urut if m[1] > 0 and YIELD_MIN <= m[2] / m[1] <= YIELD_MAKS]
        hasil.append(
            InputPanen(
                komoditas_id=kom,
                kabupaten_id=kab,
                hari_ini=hari_ini,
                tanam=tanam.get((kom, kab), []),
                yield_musim=yields,
                jumlah_catatan=urut[-1][3],
                hujan_30h_mm=hujan.get(kab, 0.0),
                peringatan=peringatan[kab][1] if kab in peringatan else None,
            )
        )
    return hasil


def muat_rasio_harga(data_dir: Path, keluar_dir: Path, hari_ini: date) -> dict[str, float]:
    """Rasio per komoditas: rerata harga prediksi H+7 (lintas pasar) / rerata harga 28 hari terakhir."""
    prediksi = keluar_dir / "prediksi_harga.jsonl"
    if not prediksi.exists():
        raise DataTidakLengkap(f"prediksi_harga.jsonl belum ada di {keluar_dir} (job harga harus lebih dulu)")
    h7: dict[str, list[float]] = defaultdict(list)
    for baris in prediksi.read_text().splitlines():
        b = json.loads(baris)
        if b["horizon"] == "H+7":
            h7[b["komoditas_id"]].append(float(b["harga_prediksi"]))
    awal = hari_ini - timedelta(days=28)
    lalu: dict[str, list[float]] = defaultdict(list)
    for b in _baca(data_dir / "harga_harian.csv"):
        d = date.fromisoformat(b["tanggal"])
        if awal <= d < hari_ini:
            lalu[b["komoditas_id"]].append(float(b["harga_median"]))
    return {
        kom: (sum(v) / len(v)) / (sum(lalu[kom]) / len(lalu[kom]))
        for kom, v in h7.items()
        if v and lalu.get(kom)
    }


def muat_masukan_demand(data_dir: Path, hari_ini: date, rasio: dict[str, float]) -> list[InputDemand]:
    volume: dict[tuple[str, str], dict[date, float]] = defaultdict(dict)
    for b in _baca(data_dir / "transaksi_harian.csv"):
        d = date.fromisoformat(b["tanggal"])
        if d < hari_ini:
            volume[(b["komoditas_id"], b["zona"])][d] = float(b["volume_kg"])
    if not volume:
        raise DataTidakLengkap("transaksi_harian.csv tidak berisi data sebelum tanggal hitung")
    besar: dict[date, str] = {}
    berkas = data_dir / "hari_besar.csv"
    if berkas.exists():
        besar = {date.fromisoformat(b["tanggal"]): b["hari_besar"] for b in _baca(berkas)}
    return [
        InputDemand(
            komoditas_id=kom, zona=zona, hari_ini=hari_ini, volume=seri, hari_besar=besar,
            rasio_harga=rasio.get(kom, 1.0),
        )
        for (kom, zona), seri in sorted(volume.items())
    ]  # fmt: skip
