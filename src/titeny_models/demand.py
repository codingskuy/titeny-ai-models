"""Model demand `demand_v1.0.0` (BR-203, BR-204, FR-102): baseline 28h x faktor hari besar x elastisitas.

Per (komoditas, zona), horizon H+7 (`H+7_total_kg`) dan H+30, total kg selama horizon, batas +-30% vs
baseline 28 hari. Sinyal dihitung di `terapkan_sinyal` (level kabupaten <-> zona terdekat).

ASUMSI (dicatat di PR):
- `faktor_hari_besar` diterapkan per hari di horizon (hari bertanda puasa/lebaran/natal_tahun_baru dari S9);
  lebaran untuk komoditas selain cabai/daging/beras = 1,00; prioritas bila tumpang tindih: satu label per hari.
- Elastisitas dari rasio `harga prediksi H+7 / rata-rata harga 28 hari` (rata-rata lintas pasar per komoditas,
  karena belum ada pemetaan zona->pasar resmi): faktor = 1 - e x (rasio - 1) / 0,10, e = 0,04 (pokok) / 0,07 (sayur).
  Rasio yang sama dipakai untuk H+30 (hanya ada harga prediksi sampai H+7).
- `tanggal` = tanggal hitung H (PK tabel `prediksi_demand` = komoditas, zona, horizon, tanggal).
- Fallback: S3 kosong 1-2 hari -> rerata 7 hari + label `estimasi`; kosong >= 3 hari -> dihentikan (`None`).
- Zona tanpa model panen (komoditas di luar 6 panen) -> sinyal `seimbang`; kabupaten dengan catatan panen
  < 10 baris -> sinyal `seimbang` + rekomendasi generik.
- Rentang P10-P90 diisi TTN-AI-005 (sebelum itu `None`).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta

from .harga import WIB
from .katalog import (
    KABUPATEN_TERDEKAT,
    LEBARAN_BERAS,
    LEBARAN_CABAI_DAGING,
    PANGAN_POKOK,
    VERSI_DEMAND,
)
from .sinyal import GENERIK, klasifikasi_sinyal, rekomendasi_komoditas

JENDELA_BASELINE = 28
JENDELA_FALLBACK = 7
BATAS_PERUBAHAN = 0.30
HENTI_KOSONG_HARI = 3
ELASTISITAS_POKOK, ELASTISITAS_SAYUR = 0.04, 0.07
HORIZON = (("H+7_total_kg", 7), ("H+30", 30))


def faktor_hari_besar(komoditas_id: str, hari_besar: str | None) -> float:
    if hari_besar == "puasa":
        return 1.18
    if hari_besar == "natal_tahun_baru":
        return 1.12
    if hari_besar == "lebaran":
        if komoditas_id in LEBARAN_CABAI_DAGING:
            return 1.35
        if komoditas_id in LEBARAN_BERAS:
            return 1.10
    return 1.00


def elastisitas_faktor(komoditas_id: str, rasio_harga: float) -> float:
    """Tiap +10% harga -> demand -4% (pokok) atau -7% (sayur segar); simetris untuk penurunan harga."""
    e = ELASTISITAS_POKOK if komoditas_id in PANGAN_POKOK else ELASTISITAS_SAYUR
    return 1.0 - e * (rasio_harga - 1.0) / 0.10


def status_data_demand(volume: Mapping[date, float], hari_ini: date) -> tuple[str, int]:
    ada = [d for d in volume if d < hari_ini]
    if not ada:
        return "dihentikan", HENTI_KOSONG_HARI
    kosong = (hari_ini - timedelta(days=1) - max(ada)).days
    if kosong >= HENTI_KOSONG_HARI:
        return "dihentikan", kosong
    return ("estimasi" if kosong >= 1 else "normal"), kosong


@dataclass(frozen=True)
class InputDemand:
    komoditas_id: str
    zona: str
    hari_ini: date
    volume: Mapping[date, float]  # kg/hari, S3 (TitipO + lapak Pasaree)
    hari_besar: Mapping[date, str] = field(default_factory=dict)  # S9: puasa|lebaran|natal_tahun_baru
    rasio_harga: float = 1.0
    waktu_hitung: datetime | None = None


@dataclass(frozen=True)
class PrediksiDemand:
    komoditas_id: str
    zona: str
    horizon: str
    tanggal: date
    demand_prediksi_kg: float
    rentang_bawah_kg: float | None
    rentang_atas_kg: float | None
    sinyal: str
    rekomendasi: list[str]
    model_version: str
    dihitung_pada: datetime
    label: str | None = None  # `estimasi` (fallback); BUKAN bagian kontrak tabel -> tidak ada di as_dict

    def as_dict(self) -> dict:
        return {
            "jenis": "demand",
            "komoditas_id": self.komoditas_id,
            "zona": self.zona,
            "tanggal": self.tanggal.isoformat(),
            "horizon": self.horizon,
            "demand_prediksi_kg": round(self.demand_prediksi_kg, 2),
            "rentang_bawah_kg": self.rentang_bawah_kg,
            "rentang_atas_kg": self.rentang_atas_kg,
            "sinyal": self.sinyal,
            "rekomendasi": self.rekomendasi,
            "model_version": self.model_version,
            "dihitung_pada": self.dihitung_pada.isoformat(),
        }


def ramal_demand_pasangan(masuk: InputDemand) -> list[PrediksiDemand] | None:
    """[H+7, H+30] untuk satu (komoditas, zona); `None` bila S3 kosong >= 3 hari."""
    status, _ = status_data_demand(masuk.volume, masuk.hari_ini)
    if status == "dihentikan":
        return None
    jendela = JENDELA_FALLBACK if status == "estimasi" else JENDELA_BASELINE
    awal = masuk.hari_ini - timedelta(days=jendela)
    nilai = [v for d, v in masuk.volume.items() if awal <= d < masuk.hari_ini]
    harian = sum(nilai) / len(nilai)
    waktu = masuk.waktu_hitung or datetime.now(WIB)
    elastis = elastisitas_faktor(masuk.komoditas_id, masuk.rasio_harga)

    hasil = []
    for nama, n in HORIZON:
        total = sum(
            harian
            * faktor_hari_besar(masuk.komoditas_id, masuk.hari_besar.get(masuk.hari_ini + timedelta(days=k)))
            for k in range(1, n + 1)
        )
        total *= elastis
        dasar = harian * n
        total = max(dasar * (1 - BATAS_PERUBAHAN), min(dasar * (1 + BATAS_PERUBAHAN), total))
        hasil.append(
            PrediksiDemand(
                komoditas_id=masuk.komoditas_id,
                zona=masuk.zona,
                horizon=nama,
                tanggal=masuk.hari_ini,
                demand_prediksi_kg=total,
                rentang_bawah_kg=None,
                rentang_atas_kg=None,
                sinyal="seimbang",
                rekomendasi=[],
                model_version=VERSI_DEMAND,
                dihitung_pada=waktu,
                label="estimasi" if status == "estimasi" else None,
            )
        )
    return hasil


def terapkan_sinyal(
    prediksi: list[PrediksiDemand],
    panen_kg: Mapping[tuple[str, str, str], float],
    kabupaten_rendah: set[tuple[str, str]] | frozenset[tuple[str, str]] = frozenset(),
) -> list[PrediksiDemand]:
    """Isi `sinyal` + `rekomendasi` per baris demand.

    `panen_kg[(komoditas, kabupaten, horizon)]`: panen prediksi total pada horizon itu
    (H+7 = minggu M+1; H+30 = M+1..M+4). Demand dijumlah per (komoditas, horizon, kabupaten terdekat);
    selisih dibagi ke zona sebanding demand-nya. Kunci panen tak ada -> `seimbang`.
    """
    grup: dict[tuple[str, str, str], float] = defaultdict(float)
    for p in prediksi:
        grup[(p.komoditas_id, p.horizon, KABUPATEN_TERDEKAT.get(p.zona, ""))] += p.demand_prediksi_kg

    keluar = []
    for p in prediksi:
        kab = KABUPATEN_TERDEKAT.get(p.zona, "")
        kunci_panen = (p.komoditas_id, kab, p.horizon)
        if (p.komoditas_id, kab) in kabupaten_rendah and kunci_panen in panen_kg:
            keluar.append(replace(p, sinyal="seimbang", rekomendasi=[GENERIK]))
            continue
        if kunci_panen not in panen_kg:
            keluar.append(
                replace(
                    p,
                    sinyal="seimbang",
                    rekomendasi=rekomendasi_komoditas("seimbang", 0, p.komoditas_id, p.zona),
                )
            )
            continue
        total_demand = grup[(p.komoditas_id, p.horizon, kab)]
        panen = panen_kg[kunci_panen]
        sinyal = klasifikasi_sinyal(panen, total_demand)
        porsi = p.demand_prediksi_kg / total_demand if total_demand > 0 else 0.0
        keluar.append(
            replace(
                p,
                sinyal=sinyal,
                rekomendasi=rekomendasi_komoditas(
                    sinyal, abs(panen - total_demand) * porsi, p.komoditas_id, p.zona
                ),
            )
        )
    return keluar
