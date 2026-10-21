"""Sinyal surplus/seimbang/defisit dan rekomendasi otomatis (BR-204, model/20 bagian 5-6).

Teks rekomendasi terkunci (ditampilkan apa adanya); angka dibulatkan ke 100 kg; maks 3 aksi per zona.
ASUMSI: teks TownHall memuat angka contoh (mis. "500-800 kg"); di sini angka diganti selisih nyata
(dibulatkan 100 kg) pada aksi kedua agar teks terkunci tetap utuh.
"""

from __future__ import annotations

SURPLUS_TEKS = "Serap {n} kg ke gudang Bekasi sebelum Jumat; tawarkan ke 3 vendor zona utara."
DEFISIT_TEKS = "Amankan pasokan dari Brebes/Malang; batasi promo; naikkan buffer stok 15%."
SEIMBANG_TEKS = "Tahan pola distribusi; pantau ulang Senin."
GENERIK = "Data panen belum cukup; tahan pola distribusi dan pantau ulang Senin."
MAKS_AKSI_PER_ZONA = 3


def bulatkan_100(x: float) -> int:
    return int((abs(x) + 50) // 100) * 100


def klasifikasi_sinyal(panen_kg: float, demand_kg: float) -> str:
    """surplus bila panen >= 120% demand; defisit bila <= 80%; selain itu seimbang."""
    if panen_kg * 5 >= demand_kg * 6:  # >= 1,20 x demand (tanpa galat float)
        return "surplus" if panen_kg > 0 else "seimbang"
    if panen_kg * 5 <= demand_kg * 4:
        return "defisit"
    return "seimbang"


def rekomendasi_komoditas(
    sinyal: str, selisih_kg: float, komoditas_id: str, zona: str, generik: bool = False
) -> list[str]:
    """Daftar aksi (1-3) untuk satu komoditas di satu zona."""
    if generik:
        return [GENERIK]
    n = bulatkan_100(selisih_kg)
    if sinyal == "surplus":
        return [SURPLUS_TEKS.format(n=n), f"Selisih panen terhadap demand {komoditas_id} sekitar {n} kg."]
    if sinyal == "defisit":
        return [DEFISIT_TEKS, f"Kekurangan pasokan {komoditas_id} di zona {zona} sekitar {n} kg."]
    return [SEIMBANG_TEKS]


def rekomendasi_zona(baris: list[tuple[str, str, float]], zona: str) -> list[str]:
    """Maks 3 aksi per zona dari (komoditas_id, sinyal, selisih_kg), selisih terbesar lebih dulu."""
    aktif = sorted((b for b in baris if b[1] != "seimbang"), key=lambda b: -abs(b[2]))
    if not aktif:
        return [SEIMBANG_TEKS]
    teks = []
    for komoditas_id, sinyal, selisih in aktif[:MAKS_AKSI_PER_ZONA]:
        utama = rekomendasi_komoditas(sinyal, selisih, komoditas_id, zona)
        n = bulatkan_100(selisih)
        tambahan = f" Kekurangan sekitar {n} kg." if sinyal == "defisit" else ""
        teks.append(f"{komoditas_id}: {utama[0]}{tambahan}")
    return teks
