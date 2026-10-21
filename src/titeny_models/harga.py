"""Model harga `harga_v1.0.0`: metode 5 langkah tanpa deep learning (BR-201, BR-202, FR-101, FR-104).

Per pasangan (komoditas, pasar), untuk tiap horizon H+1..H+7:

1. Baseline musiman-naif: median 14 hari terakhir pada `jenis_hari` yang sama dengan hari target.
2. Koreksi tren: regresi linier 21 hari terakhir; kemiringan relatif dibatasi +-8%/hari.
3. Koreksi stok: stok < 60% rerata 30 hari -> +4%; > 140% -> -4%.
4. Koreksi logistik: 80% selisih `biaya_per_kg` terhadap bulan lalu diteruskan ke harga.
5. Potong ke [0,70 x median_30h, 1,60 x median_30h], lalu bulatkan ke kelipatan 500 IDR.

Fungsi di modul ini murni (tanpa I/O) agar tiap langkah dapat diuji sendiri.

ASUMSI (tidak ada rumus tertulis di TownHall; dicatat di PR):
- Koreksi tren untuk horizon i: `nilai = baseline x (1 + lereng_relatif_terbatas x i)`;
  `lereng_relatif = kemiringan / rerata 21 hari`.
- Koreksi logistik menambah `0,8 x (biaya_terakhir - biaya_bulan_lalu)` IDR/kg ke harga (satuan sama: IDR per kg).
- Koreksi stok dan logistik memakai nilai H-1 dan sama untuk semua horizon.
- `jenis_hari` in {biasa, akhir_pekan, libur}; daftar libur (S9) disuplai pemanggil.
- Fallback FR-104: kosong 1-2 hari memakai median 7 hari sebagai baseline (langkah 2-5 tetap jalan)
  berlabel `data_kemarin`; kosong >= 3 hari -> pasangan dihentikan (`None`).
- Rentang P10-P90 dan kepercayaan dikalibrasi oleh TTN-AI-005; sebelum ada kalibrasi rentang = titik
  dan kepercayaan `rendah` (tidak mengarang rentang).
"""

from __future__ import annotations

import argparse
import statistics
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import numpy as np

from .kalibrasi import Kalibrasi, hitung_kepercayaan, rentang_harga
from .katalog import VERSI_HARGA

WIB = timezone(timedelta(hours=7))

LERENG_MAKS = 0.08
STOK_RENDAH, STOK_TINGGI, KOREKSI_STOK = 0.60, 1.40, 0.04
TERUSKAN_LOGISTIK = 0.80
BATAS_BAWAH, BATAS_ATAS = 0.70, 1.60
JENDELA_BASELINE, JENDELA_TREN, JENDELA_STOK, JENDELA_MEDIAN = 14, 21, 30, 30
JENDELA_FALLBACK = 7
HENTI_KOSONG_HARI = 3

Seri = Mapping[date, float]


def jenis_hari(tanggal: date, libur: frozenset[date] = frozenset()) -> str:
    """`libur` (S9) menang atas akhir pekan."""
    if tanggal in libur:
        return "libur"
    return "akhir_pekan" if tanggal.weekday() >= 5 else "biasa"


def _jendela(seri: Seri, hari_ini: date, hari: int) -> dict[date, float]:
    """Data pada H-hari .. H-1 (H = hari_ini)."""
    awal = hari_ini - timedelta(days=hari)
    return {d: v for d, v in seri.items() if awal <= d < hari_ini}


def _median(nilai) -> float:
    return float(statistics.median(nilai))


# --------------------------- Langkah 1 ---------------------------
def baseline_musiman(
    harga: Seri, hari_ini: date, target: date, libur: frozenset[date] = frozenset()
) -> tuple[float, bool]:
    """Median 14 hari terakhir pada `jenis_hari` yang sama dengan `target`.

    Mengembalikan (nilai, jatuh_ke_semua_hari). Bila tak ada hari sejenis di jendela, dipakai median
    semua hari di jendela. Jendela kosong -> ValueError (pemanggil sudah menyaring lewat `status_data`).
    """
    jendela = _jendela(harga, hari_ini, JENDELA_BASELINE)
    if not jendela:
        raise ValueError("tidak ada data harga pada 14 hari terakhir")
    jenis = jenis_hari(target, libur)
    sejenis = [v for d, v in jendela.items() if jenis_hari(d, libur) == jenis]
    if sejenis:
        return _median(sejenis), False
    return _median(jendela.values()), True


# --------------------------- Langkah 2 ---------------------------
def koreksi_tren(nilai: float, harga: Seri, hari_ini: date, langkah: int) -> tuple[float, float]:
    """Regresi linier 21 hari terakhir; lereng relatif dibatasi +-8%/hari.

    Mengembalikan (nilai_terkoreksi, lereng_relatif_terbatas). Kurang dari 3 titik -> tanpa koreksi.
    """
    lereng = _lereng_relatif(harga, hari_ini)
    return nilai * (1.0 + lereng * langkah), lereng


def _lereng_relatif(harga: Seri, hari_ini: date) -> float:
    """Kemiringan OLS 21 hari / rerata, dibatasi +-8%/hari; 0 bila < 3 titik atau rerata <= 0."""
    jendela = _jendela(harga, hari_ini, JENDELA_TREN)
    if len(jendela) < 3:
        return 0.0
    xs = np.array([(d - hari_ini).days for d in jendela], dtype=float)
    ys = np.array(list(jendela.values()), dtype=float)
    rerata = float(ys.mean())
    if rerata <= 0:
        return 0.0
    dx = xs - xs.mean()
    kemiringan = float((dx * (ys - rerata)).sum() / (dx * dx).sum())  # regresi linier kuadrat terkecil
    return max(-LERENG_MAKS, min(LERENG_MAKS, kemiringan / rerata))


# --------------------------- Langkah 3 ---------------------------
def koreksi_stok(nilai: float, stok: Seri, hari_ini: date) -> tuple[float, float | None]:
    """Stok gabungan terbaru (<= H-1) vs rerata 30 hari. Mengembalikan (nilai, rasio|None)."""
    jendela = _jendela(stok, hari_ini, JENDELA_STOK)
    if not jendela:
        return nilai, None
    rerata = float(np.mean(list(jendela.values())))
    if rerata <= 0:
        return nilai, None
    terbaru = jendela[max(jendela)]
    rasio = terbaru / rerata
    if rasio < STOK_RENDAH:
        return nilai * (1.0 + KOREKSI_STOK), rasio
    if rasio > STOK_TINGGI:
        return nilai * (1.0 - KOREKSI_STOK), rasio
    return nilai, rasio


# --------------------------- Langkah 4 ---------------------------
def koreksi_logistik(nilai: float, biaya: Seri, hari_ini: date) -> tuple[float, float]:
    """80% selisih biaya/kg (terbaru vs bulan lalu) diteruskan. Mengembalikan (nilai, selisih)."""
    sebelum_hari_ini = {d: v for d, v in biaya.items() if d < hari_ini}
    if not sebelum_hari_ini:
        return nilai, 0.0
    acuan = hari_ini - timedelta(days=JENDELA_MEDIAN)  # "bulan lalu" = H-30
    lama = {d: v for d, v in sebelum_hari_ini.items() if d <= acuan}
    if not lama:
        return nilai, 0.0
    selisih = sebelum_hari_ini[max(sebelum_hari_ini)] - lama[max(lama)]
    return nilai + TERUSKAN_LOGISTIK * selisih, float(selisih)


# --------------------------- Langkah 5 ---------------------------
def bulatkan_500(x: float) -> int:
    """Pembulatan ke kelipatan 500 IDR terdekat; setengah dibulatkan ke atas."""
    return int((x + 250) // 500) * 500


def potong_dan_bulatkan(nilai: float, median_30h: float) -> int:
    bawah, atas = BATAS_BAWAH * median_30h, BATAS_ATAS * median_30h
    return bulatkan_500(max(bawah, min(atas, nilai)))


# --------------------------- Fallback FR-104 ---------------------------
def status_data(harga: Seri, hari_ini: date) -> tuple[str, int]:
    """(`normal`|`data_kemarin`|`dihentikan`, jumlah hari kosong terakhir)."""
    ada = [d for d in harga if d < hari_ini]
    if not ada:
        return "dihentikan", HENTI_KOSONG_HARI
    kosong = (hari_ini - timedelta(days=1) - max(ada)).days
    if kosong >= HENTI_KOSONG_HARI:
        return "dihentikan", kosong
    return ("data_kemarin" if kosong >= 1 else "normal"), kosong


# --------------------------- Pipeline ---------------------------
@dataclass(frozen=True)
class InputHarga:
    komoditas_id: str
    pasar_id: str
    hari_ini: date  # H; data yang dipakai hanya sampai H-1
    harga: Seri  # median harian S1 (IDR/kg)
    stok: Seri = field(default_factory=dict)  # stok gabungan gudang S2 (kg)
    biaya_logistik: Seri = field(default_factory=dict)  # S6 (IDR/kg)
    libur: frozenset[date] = frozenset()  # S9
    sampel_lapak: int = 0  # S4; dipakai kepercayaan (TTN-AI-005)
    waktu_hitung: datetime | None = None
    kalibrasi: Mapping[str, Kalibrasi] = field(default_factory=dict)  # per horizon ("H+1".."H+7"), TTN-AI-005
    mape_14h: float | None = None  # MAPE H+1 14 hari terakhir pasangan ini (kepercayaan)


@dataclass(frozen=True)
class PrediksiHarga:
    komoditas_id: str
    pasar_id: str
    tanggal_prediksi: date  # tanggal TARGET (H+i); sejalan dengan PK tabel prediksi_harga
    horizon: str
    harga_prediksi: int
    rentang_bawah: int
    rentang_atas: int
    kepercayaan: str
    alasan_singkat: str
    model_version: str
    dihitung_pada: datetime

    def as_dict(self) -> dict:
        return {
            "komoditas_id": self.komoditas_id,
            "pasar_id": self.pasar_id,
            "tanggal_prediksi": self.tanggal_prediksi.isoformat(),
            "horizon": self.horizon,
            "harga_prediksi": self.harga_prediksi,
            "rentang_bawah": self.rentang_bawah,
            "rentang_atas": self.rentang_atas,
            "kepercayaan": self.kepercayaan,
            "alasan_singkat": self.alasan_singkat,
            "model_version": self.model_version,
            "dihitung_pada": self.dihitung_pada.isoformat(),
        }


def _irisan_biaya(biaya: Seri, hari_ini: date) -> dict[date, float]:
    """Hanya dua titik yang dipakai koreksi logistik: terbaru (< H) dan terbaru pada/sebelum H-30."""
    sebelum = [d for d in biaya if d < hari_ini]
    if not sebelum:
        return {}
    acuan = hari_ini - timedelta(days=JENDELA_MEDIAN)
    lama = [d for d in sebelum if d <= acuan]
    return {d: biaya[d] for d in ([max(sebelum)] + ([max(lama)] if lama else []))}


def ramal_harga_pasangan(masuk: InputHarga) -> list[PrediksiHarga] | None:
    """H+1..H+7 untuk satu pasangan; `None` bila dihentikan (S1 kosong >= 3 hari)."""
    status, _ = status_data(masuk.harga, masuk.hari_ini)
    if status == "dihentikan":
        return None

    waktu = masuk.waktu_hitung or datetime.now(WIB)
    # Semua langkah hanya memakai <= 30 hari terakhir: iris sekali agar replay (backtest/kalibrasi) cepat.
    harga = _jendela(masuk.harga, masuk.hari_ini, JENDELA_MEDIAN)
    stok = _jendela(masuk.stok, masuk.hari_ini, JENDELA_STOK)
    biaya = _irisan_biaya(masuk.biaya_logistik, masuk.hari_ini)
    lereng = _lereng_relatif(harga, masuk.hari_ini)  # sama untuk semua horizon
    median_30h = _median(harga.values())
    fallback = status == "data_kemarin"
    median_7h = _median(_jendela(harga, masuk.hari_ini, JENDELA_FALLBACK).values()) if fallback else 0.0

    hasil: list[PrediksiHarga] = []
    for i in range(1, 8):
        target = masuk.hari_ini + timedelta(days=i)
        alasan: list[str] = []

        if fallback:
            nilai, jatuh = median_7h, False
            alasan.append("data_kemarin")
            alasan.append("median_7h")
        else:
            nilai, jatuh = baseline_musiman(harga, masuk.hari_ini, target, masuk.libur)
            jenis = "semua_hari" if jatuh else jenis_hari(target, masuk.libur)
            alasan.append(f"median_14h_{jenis}")

        nilai *= 1.0 + lereng * i
        if abs(lereng) >= 0.0005:
            alasan.append("tren_naik" if lereng > 0 else "tren_turun")

        nilai, rasio = koreksi_stok(nilai, stok, masuk.hari_ini)
        if rasio is not None and (rasio < STOK_RENDAH or rasio > STOK_TINGGI):
            alasan.append(f"stok_gudang_{round(rasio * 100)}%_dari_rerata")

        nilai, selisih = koreksi_logistik(nilai, biaya, masuk.hari_ini)
        if selisih:
            alasan.append(f"logistik_{selisih:+.0f}_per_kg")

        if not (BATAS_BAWAH * median_30h <= nilai <= BATAS_ATAS * median_30h):
            alasan.append("dipotong_batas_30h")
        akhir = potong_dan_bulatkan(nilai, median_30h)

        # Rentang P10-P90 dan kepercayaan (TTN-AI-005). Tanpa kalibrasi: rentang = titik, kepercayaan `rendah`
        # (tidak mengarang rentang).
        kal = masuk.kalibrasi.get(f"H+{i}")
        if kal is None:
            alasan.append("rentang_belum_dikalibrasi")
            bawah, atas, kepercayaan = akhir, akhir, "rendah"
        else:
            bawah, atas = rentang_harga(akhir, kal)
            kepercayaan = hitung_kepercayaan(masuk.sampel_lapak, masuk.mape_14h)
        hasil.append(
            PrediksiHarga(
                komoditas_id=masuk.komoditas_id,
                pasar_id=masuk.pasar_id,
                tanggal_prediksi=target,
                horizon=f"H+{i}",
                harga_prediksi=akhir,
                rentang_bawah=bawah,
                rentang_atas=atas,
                kepercayaan=kepercayaan,
                alasan_singkat=" + ".join(alasan),
                model_version=VERSI_HARGA,
                dihitung_pada=waktu,
            )
        )
    return hasil


if __name__ == "__main__":  # demo data sintetis; produksi lewat `python -m titeny_models.jobs harga`
    from .sintetis import bangun_masukan_harga_sintetis

    p = argparse.ArgumentParser(description="Demo harga_v1.0.0 pada data SINTETIS")
    p.add_argument("--komoditas", default="cmd_cabai_merah")
    p.add_argument("--pasar", default="psr_jakarta_timur_01")
    a = p.parse_args()
    for baris in ramal_harga_pasangan(bangun_masukan_harga_sintetis(a.komoditas, a.pasar)) or []:
        print(baris.as_dict())
