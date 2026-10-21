"""Model panen `panen_v1.0.0` (BR-203, FR-102): luas ekspektasi x yield baseline x faktor cuaca x faktor musim.

Per (komoditas, kabupaten), mingguan M+1..M+4, dibulatkan ke 50 kg.

ASUMSI (rumus TownHall tidak lengkap; dicatat di PR):
- Luas panen ekspektasi minggu W: tiap catatan tanam (tanggal t, luas ha) dianggap panen merata pada hari
  [t+lag_min, t+lag_maks] (padi/jagung 90-120 hari, sayur 60-75 hari; jagung disamakan dengan padi);
  luas minggu W = jumlah luas x (hari irisan dengan W) / (lebar jendela).
- Yield baseline = median 3 musim terakhir (kg/ha); bila `baseline_tahun_lalu` ada, perubahan dibatasi +-20%.
- `faktor_musim` berasal dari kalender tanam S9; belum ada tabel nilai di TownHall -> bawaan 1,00.
- Kepercayaan sebelum kalibrasi (TTN-AI-005): `rendah` bila catatan panen < 10 baris per kabupaten/musim;
  selain itu `sedang`. Rentang P10-P90 diisi TTN-AI-005 (sebelum itu `None`).
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .harga import WIB
from .kalibrasi import Kalibrasi, rentang_kg
from .katalog import VERSI_PANEN

LAG_SEREAL = (90, 120)  # padi, jagung
LAG_SAYUR = (60, 75)
HUJAN_BANJIR_MM = 300.0
FAKTOR_BANJIR, FAKTOR_KERING = 0.85, 0.90
CATATAN_MIN = 10
PERUBAHAN_YIELD_MAKS = 0.20
HORIZON_MINGGU = 4


def bulatkan_50(x: float) -> int:
    return int((x + 25) // 50) * 50


def awal_minggu(d: date) -> date:
    return d - timedelta(days=d.weekday())


def minggu_iso(d: date) -> str:
    tahun, minggu, _ = d.isocalendar()
    return f"{tahun}-W{minggu:02d}"


def faktor_cuaca(hujan_30h_mm: float, peringatan: str | None) -> float:
    """1,00 normal; 0,85 bila hujan > 300 mm/30 hari atau banjir; 0,90 bila kekeringan."""
    if peringatan == "kekeringan":
        return FAKTOR_KERING
    if peringatan == "banjir" or hujan_30h_mm > HUJAN_BANJIR_MM:
        return FAKTOR_BANJIR
    return 1.00


def yield_baseline(yield_musim: Sequence[float], baseline_tahun_lalu: float | None = None) -> float | None:
    """Median 3 musim terakhir (urut lama -> baru); perubahan maks +-20% vs `baseline_tahun_lalu`."""
    if not yield_musim:
        return None
    nilai = float(statistics.median(list(yield_musim)[-3:]))
    if baseline_tahun_lalu:
        nilai = max(
            baseline_tahun_lalu * (1 - PERUBAHAN_YIELD_MAKS),
            min(baseline_tahun_lalu * (1 + PERUBAHAN_YIELD_MAKS), nilai),
        )
    return nilai


def _lag(komoditas_id: str) -> tuple[int, int]:
    return LAG_SEREAL if komoditas_id in ("cmd_padi", "cmd_jagung") else LAG_SAYUR


def luas_ekspektasi(tanam: Sequence[tuple[date, float]], komoditas_id: str, minggu_mulai: date) -> float:
    """Luas (ha) yang diharapkan panen pada minggu [minggu_mulai, minggu_mulai+6]."""
    lo, hi = _lag(komoditas_id)
    lebar = hi - lo + 1
    akhir_minggu = minggu_mulai + timedelta(days=6)
    total = 0.0
    for t, ha in tanam:
        irisan = (
            min(t + timedelta(days=hi), akhir_minggu) - max(t + timedelta(days=lo), minggu_mulai)
        ).days + 1
        if irisan > 0:
            total += ha * irisan / lebar
    return total


@dataclass(frozen=True)
class InputPanen:
    komoditas_id: str
    kabupaten_id: str
    hari_ini: date
    tanam: Sequence[tuple[date, float]]  # (tanggal_tanam, luas_ha) dari S5
    yield_musim: Sequence[float]  # kg/ha per musim, lama -> baru (S5)
    jumlah_catatan: int  # baris catatan panen kabupaten/musim terakhir
    hujan_30h_mm: float = 0.0  # S8
    peringatan: str | None = None  # None | banjir | kekeringan (S8)
    faktor_musim: float = 1.0
    baseline_tahun_lalu: float | None = None
    waktu_hitung: datetime | None = None
    kalibrasi: Kalibrasi | None = None  # P10/P90 residual relatif (TTN-AI-005); None = belum ada aktual panen


@dataclass(frozen=True)
class PrediksiPanen:
    komoditas_id: str
    kabupaten_id: str
    minggu: str
    panen_prediksi_kg: int
    rentang_bawah_kg: int | None
    rentang_atas_kg: int | None
    kepercayaan: str
    model_version: str
    dihitung_pada: datetime

    def as_dict(self) -> dict:
        return {
            "jenis": "panen",
            "komoditas_id": self.komoditas_id,
            "kabupaten_id": self.kabupaten_id,
            "minggu": self.minggu,
            "panen_prediksi_kg": self.panen_prediksi_kg,
            "rentang_bawah_kg": self.rentang_bawah_kg,
            "rentang_atas_kg": self.rentang_atas_kg,
            "kepercayaan": self.kepercayaan,
            "model_version": self.model_version,
            "dihitung_pada": self.dihitung_pada.isoformat(),
        }


def ramal_panen_pasangan(masuk: InputPanen) -> list[PrediksiPanen] | None:
    """M+1..M+4 untuk satu (komoditas, kabupaten); `None` bila tak ada riwayat yield."""
    yld = yield_baseline(masuk.yield_musim, masuk.baseline_tahun_lalu)
    if yld is None:
        return None
    waktu = masuk.waktu_hitung or datetime.now(WIB)
    cuaca = faktor_cuaca(masuk.hujan_30h_mm, masuk.peringatan)
    kepercayaan = "rendah" if masuk.jumlah_catatan < CATATAN_MIN else "sedang"
    senin = awal_minggu(masuk.hari_ini)

    hasil = []
    for k in range(1, HORIZON_MINGGU + 1):
        mulai = senin + timedelta(days=7 * k)
        luas = luas_ekspektasi(masuk.tanam, masuk.komoditas_id, mulai)
        kg = luas * yld * cuaca * masuk.faktor_musim
        titik = bulatkan_50(kg)
        bawah, atas = rentang_kg(kg, masuk.kalibrasi)
        if bawah is not None:  # kelipatan 50 kg dan tetap memuat titik
            bawah, atas = min(bulatkan_50(bawah), titik), max(bulatkan_50(atas), titik)
        hasil.append(
            PrediksiPanen(
                komoditas_id=masuk.komoditas_id,
                kabupaten_id=masuk.kabupaten_id,
                minggu=minggu_iso(mulai),
                panen_prediksi_kg=titik,
                rentang_bawah_kg=bawah,
                rentang_atas_kg=atas,
                kepercayaan=kepercayaan,
                model_version=VERSI_PANEN,
                dihitung_pada=waktu,
            )
        )
    return hasil


__all__ = [
    "InputPanen",
    "PrediksiPanen",
    "awal_minggu",
    "bulatkan_50",
    "faktor_cuaca",
    "luas_ekspektasi",
    "minggu_iso",
    "ramal_panen_pasangan",
    "yield_baseline",
]
