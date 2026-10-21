"""Katalog terkunci v1.0.0: komoditas, pasar, kabupaten, zona.

Sumber: BRD/20-prediksi.md (BR-201, BR-203), FSD/20-model-data.md.
ASUMSI (ditandai di PR): TownHall hanya memberi satu contoh ID per jenis
(`cmd_cabai_merah`, `psr_jakarta_timur_01`, `kab_karawang`, `bekasi_utara`).
ID lain diturunkan dengan pola yang sama dengan pola di openapi backend
(`^cmd_[a-z_]+$`, `^psr_[a-z0-9_]+$`, `^kab_[a-z_]+$`). Daftar 8 pasar dan 8 zona
perlu dikonfirmasi pemilik Pasaree/TitipO sebelum produksi.
"""

KOMODITAS_HARGA: tuple[str, ...] = (
    "cmd_beras_medium",
    "cmd_telur_ayam",
    "cmd_cabai_merah",
    "cmd_cabai_rawit",
    "cmd_bawang_merah",
    "cmd_bawang_putih",
    "cmd_minyak_goreng_curah",
    "cmd_gula_pasir",
    "cmd_daging_ayam",
    "cmd_daging_sapi",
    "cmd_tomat",
    "cmd_kangkung",
)

# 4 Jabodetabek, 2 Jawa Barat, 1 Jawa Tengah, 1 Jawa Timur (ASUMSI nama pasar).
PASAR: tuple[str, ...] = (
    "psr_jakarta_timur_01",
    "psr_jakarta_barat_01",
    "psr_bekasi_01",
    "psr_depok_01",
    "psr_bandung_01",
    "psr_cirebon_01",
    "psr_semarang_01",
    "psr_surabaya_01",
)

KOMODITAS_PANEN: tuple[str, ...] = (
    "cmd_padi",
    "cmd_jagung",
    "cmd_cabai_merah",
    "cmd_cabai_rawit",
    "cmd_bawang_merah",
    "cmd_tomat",
)

KABUPATEN: tuple[str, ...] = (
    "kab_karawang",
    "kab_subang",
    "kab_garut",
    "kab_brebes",
    "kab_malang",
)

# 8 zona rute TitipO (ASUMSI nama; contoh resmi hanya `bekasi_utara`).
ZONA_RUTE: tuple[str, ...] = (
    "bekasi_utara",
    "bekasi_selatan",
    "jakarta_timur",
    "jakarta_barat",
    "depok",
    "bogor",
    "tangerang",
    "bandung",
)

HORIZON_HARGA: tuple[str, ...] = tuple(f"H+{i}" for i in range(1, 8))

VERSI_HARGA = "harga_v1.0.0"
VERSI_PANEN = "panen_v1.0.0"
VERSI_DEMAND = "demand_v1.0.0"

# --- Pengelompokan untuk demand/sinyal (ASUMSI; TownHall hanya menyebut "pangan pokok" vs "sayur segar") ---
SAYUR_SEGAR: frozenset[str] = frozenset(
    {"cmd_cabai_merah", "cmd_cabai_rawit", "cmd_bawang_merah", "cmd_tomat", "cmd_kangkung"}
)
PANGAN_POKOK: frozenset[str] = frozenset(KOMODITAS_HARGA) - SAYUR_SEGAR
# Faktor lebaran 1,35 untuk cabai/daging, 1,10 untuk beras; komoditas lain tidak disebut -> 1,00 (ASUMSI).
LEBARAN_CABAI_DAGING: frozenset[str] = frozenset(
    {"cmd_cabai_merah", "cmd_cabai_rawit", "cmd_daging_ayam", "cmd_daging_sapi"}
)
LEBARAN_BERAS: frozenset[str] = frozenset({"cmd_beras_medium"})

# Level kabupaten <-> zona terdekat untuk sinyal (ASUMSI geografis; belum ada tabel resmi di TownHall).
KABUPATEN_TERDEKAT: dict[str, str] = {
    "bekasi_utara": "kab_karawang",
    "bekasi_selatan": "kab_karawang",
    "jakarta_timur": "kab_karawang",
    "jakarta_barat": "kab_karawang",
    "tangerang": "kab_karawang",
    "depok": "kab_garut",
    "bogor": "kab_garut",
    "bandung": "kab_subang",
    "psr_jakarta_timur_01": "kab_karawang",
    "psr_jakarta_barat_01": "kab_karawang",
    "psr_bekasi_01": "kab_karawang",
    "psr_depok_01": "kab_garut",
    "psr_bandung_01": "kab_subang",
    "psr_cirebon_01": "kab_brebes",
    "psr_semarang_01": "kab_brebes",
    "psr_surabaya_01": "kab_malang",
}

# Demand: 8 zona rute TitipO + 8 pasar Pasaree (BR-203).
ZONA_DEMAND: tuple[str, ...] = ZONA_RUTE + PASAR
