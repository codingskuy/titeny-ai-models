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
