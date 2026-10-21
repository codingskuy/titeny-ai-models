"""Uji metode harga_v1.0.0 (5 langkah) + fallback FR-104. Merah-hijau per langkah."""

from datetime import date, timedelta

import pytest

from titeny_models.harga import (
    InputHarga,
    baseline_musiman,
    bulatkan_500,
    jenis_hari,
    koreksi_logistik,
    koreksi_stok,
    koreksi_tren,
    potong_dan_bulatkan,
    ramal_harga_pasangan,
    status_data,
)

H = date(2026, 10, 5)  # Senin, "hari ini" saat job 04.00 berjalan


def seri(nilai, hari=30, akhir=None):
    """Seri harian H-hari..H-1; `nilai` konstanta atau fungsi(tanggal)."""
    akhir = akhir or H - timedelta(days=1)
    out = {}
    for k in range(hari):
        d = akhir - timedelta(days=k)
        out[d] = nilai(d) if callable(nilai) else nilai
    return out


# ---------- jenis_hari ----------
def test_jenis_hari():
    assert jenis_hari(date(2026, 10, 5)) == "biasa"  # Senin
    assert jenis_hari(date(2026, 10, 10)) == "akhir_pekan"  # Sabtu
    assert jenis_hari(date(2026, 10, 10), frozenset({date(2026, 10, 10)})) == "libur"
    assert jenis_hari(date(2026, 10, 7), frozenset({date(2026, 10, 7)})) == "libur"


# ---------- Langkah 1: baseline ----------
def test_baseline_median_14_hari_pada_jenis_hari_sama():
    harga = seri(lambda d: 12000 if d.weekday() >= 5 else 10000)
    target_biasa = date(2026, 10, 6)  # Selasa
    target_sabtu = date(2026, 10, 10)
    assert baseline_musiman(harga, H, target_biasa) == (10000, False)
    assert baseline_musiman(harga, H, target_sabtu) == (12000, False)


def test_baseline_hanya_memakai_jendela_14_hari():
    harga = seri(10000, 30)
    for k in range(15, 31):  # data lebih tua dari 14 hari tidak boleh ikut
        harga[H - timedelta(days=k)] = 99999
    assert baseline_musiman(harga, H, date(2026, 10, 6)) == (10000, False)


def test_baseline_jatuh_ke_median_semua_hari_bila_jenis_hari_tak_ada():
    harga = seri(lambda d: 10000, 14)
    libur = frozenset({date(2026, 10, 6)})  # tak ada libur di 14 hari terakhir
    nilai, jatuh = baseline_musiman(harga, H, date(2026, 10, 6), libur)
    assert nilai == 10000 and jatuh is True


# ---------- Langkah 2: tren ----------
def test_tren_nol_pada_seri_datar():
    nilai, lereng = koreksi_tren(10000.0, seri(10000, 21), H, 3)
    assert lereng == pytest.approx(0.0, abs=1e-12)
    assert nilai == pytest.approx(10000.0)


def test_tren_naik_diteruskan_per_langkah():
    # naik 1%/hari dari 10000 (lereng relatif ~ 1% / rerata)
    harga = seri(lambda d: 10000 + 100 * (d - (H - timedelta(days=21))).days, 21)
    n1, lereng = koreksi_tren(10000.0, harga, H, 1)
    n3, _ = koreksi_tren(10000.0, harga, H, 3)
    assert 0 < lereng < 0.08
    assert n3 > n1 > 10000.0


def test_tren_dibatasi_8_persen_per_hari():
    harga = seri(lambda d: 1000 * 2 ** ((d - (H - timedelta(days=21))).days / 3), 21)
    nilai, lereng = koreksi_tren(10000.0, harga, H, 1)
    assert lereng == pytest.approx(0.08)
    assert nilai == pytest.approx(10800.0)
    harga_turun = seri(lambda d: 100000 - 4500 * (d - (H - timedelta(days=21))).days, 21)
    nilai2, lereng2 = koreksi_tren(10000.0, harga_turun, H, 1)
    assert lereng2 == pytest.approx(-0.08)
    assert nilai2 == pytest.approx(9200.0)


def test_tren_dilewati_bila_data_kurang_dari_3_titik():
    nilai, lereng = koreksi_tren(10000.0, {H - timedelta(days=1): 11000}, H, 2)
    assert (nilai, lereng) == (10000.0, 0.0)


# ---------- Langkah 3: stok ----------
@pytest.mark.parametrize(
    "stok_terakhir,faktor",
    [(59, 1.04), (60, 1.0), (100, 1.0), (140, 1.0), (141, 0.96)],
)
def test_koreksi_stok_batas(stok_terakhir, faktor):
    # 29 hari bernilai X, hari terakhir menentukan rasio terhadap rerata 30 hari.
    # Dibuat rerata tepat 100: 29 hari = a, 1 hari = stok_terakhir -> a = (3000 - s) / 29
    a = (3000 - stok_terakhir) / 29
    stok = seri(a, 30)
    stok[H - timedelta(days=1)] = stok_terakhir
    nilai, rasio = koreksi_stok(10000.0, stok, H)
    assert rasio == pytest.approx(stok_terakhir / 100)
    assert nilai == pytest.approx(10000.0 * faktor)


def test_koreksi_stok_tanpa_data_tidak_mengubah():
    assert koreksi_stok(10000.0, {}, H) == (10000.0, None)


# ---------- Langkah 4: logistik ----------
def test_logistik_meneruskan_80_persen_selisih():
    biaya = seri(1000, 40)
    biaya[H - timedelta(days=1)] = 1500  # naik 500 IDR/kg vs bulan lalu
    nilai, selisih = koreksi_logistik(10000.0, biaya, H)
    assert selisih == 500
    assert nilai == pytest.approx(10000.0 + 0.8 * 500)


def test_logistik_turun_mengurangi_harga():
    biaya = seri(1000, 40)
    biaya[H - timedelta(days=1)] = 800
    nilai, selisih = koreksi_logistik(10000.0, biaya, H)
    assert selisih == -200 and nilai == pytest.approx(9840.0)


def test_logistik_tanpa_pembanding_bulan_lalu_tidak_mengubah():
    assert koreksi_logistik(10000.0, seri(1000, 10), H) == (10000.0, 0.0)


# ---------- Langkah 5: potong + bulatkan ----------
def test_bulatkan_500():
    assert bulatkan_500(10000) == 10000
    assert bulatkan_500(10249.9) == 10000
    assert bulatkan_500(10250) == 10500
    assert bulatkan_500(10499) == 10500
    assert bulatkan_500(0) == 0


def test_potong_batas_bawah_dan_atas():
    assert potong_dan_bulatkan(1.0, 10000) == 7000  # 0,70 x 10000
    assert potong_dan_bulatkan(99999, 10000) == 16000  # 1,60 x 10000
    assert potong_dan_bulatkan(10100, 10000) == 10000  # di dalam rentang -> bulat saja
    assert potong_dan_bulatkan(7000, 10000) == 7000
    assert potong_dan_bulatkan(16000, 10000) == 16000


def test_potong_menghasilkan_kelipatan_500():
    for x in (7123.4, 9999.9, 12345.6, 15999):
        assert potong_dan_bulatkan(x, 10000) % 500 == 0


# ---------- Fallback FR-104 ----------
def test_status_data_normal_kemarin_ada():
    assert status_data(seri(10000, 30), H) == ("normal", 0)


def test_status_data_kosong_1_hari_pakai_median_7_hari():
    harga = seri(10000, 30, akhir=H - timedelta(days=2))
    assert status_data(harga, H) == ("data_kemarin", 1)


def test_status_data_kosong_3_hari_atau_lebih_dihentikan():
    assert status_data(seri(10000, 30, akhir=H - timedelta(days=4)), H) == ("dihentikan", 3)
    assert status_data(seri(10000, 30, akhir=H - timedelta(days=10)), H)[0] == "dihentikan"
    assert status_data({}, H)[0] == "dihentikan"


# ---------- Pipeline + kontrak output ----------
def masukan(**kw):
    dasar = {
        "komoditas_id": "cmd_cabai_merah",
        "pasar_id": "psr_jakarta_timur_01",
        "hari_ini": H,
        "harga": seri(10000, 30),
        "stok": seri(100, 30),
        "biaya_logistik": seri(1000, 40),
        "sampel_lapak": 6,
    }
    dasar.update(kw)
    return InputHarga(**dasar)


def test_kontrak_output_7_horizon_dan_tipe():
    hasil = ramal_harga_pasangan(masukan())
    assert [p.horizon for p in hasil] == [f"H+{i}" for i in range(1, 8)]
    for i, p in enumerate(hasil, start=1):
        d = p.as_dict()
        assert set(d) == {
            "komoditas_id",
            "pasar_id",
            "tanggal_prediksi",
            "horizon",
            "harga_prediksi",
            "rentang_bawah",
            "rentang_atas",
            "kepercayaan",
            "alasan_singkat",
            "model_version",
            "dihitung_pada",
        }
        assert d["model_version"] == "harga_v1.0.0"
        assert isinstance(d["harga_prediksi"], int) and d["harga_prediksi"] % 500 == 0
        assert d["rentang_bawah"] <= d["harga_prediksi"] <= d["rentang_atas"]
        assert d["kepercayaan"] in {"tinggi", "sedang", "rendah"}
        assert d["tanggal_prediksi"] == (H + timedelta(days=i)).isoformat()
        assert d["alasan_singkat"]


def test_seri_datar_menghasilkan_harga_datar():
    assert {p.harga_prediksi for p in ramal_harga_pasangan(masukan())} == {10000}


def test_semua_hasil_dalam_batas_potong_30_hari():
    # tren sangat tajam tetap dipotong ke 1,60 x median 30 hari
    harga = seri(lambda d: 1000 * 2 ** ((d - (H - timedelta(days=21))).days / 3), 30)
    med30 = sorted(harga.values())[len(harga) // 2 - 1 : len(harga) // 2 + 1]
    med30 = sum(med30) / 2
    for p in ramal_harga_pasangan(masukan(harga=harga)):
        assert 0.70 * med30 - 250 <= p.harga_prediksi <= 1.60 * med30 + 250


def test_fallback_data_kemarin_berlabel():
    harga = seri(10000, 30, akhir=H - timedelta(days=2))
    hasil = ramal_harga_pasangan(masukan(harga=harga))
    assert hasil is not None
    assert all("data_kemarin" in p.alasan_singkat for p in hasil)


def test_pasangan_dihentikan_bila_kosong_3_hari():
    harga = seri(10000, 30, akhir=H - timedelta(days=4))
    assert ramal_harga_pasangan(masukan(harga=harga)) is None


def test_alasan_memuat_koreksi_stok():
    stok = seri(100, 30)
    stok[H - timedelta(days=1)] = 40
    hasil = ramal_harga_pasangan(masukan(stok=stok))
    assert all("stok_gudang_" in p.alasan_singkat for p in hasil)


def test_tanpa_kalibrasi_rentang_sama_dengan_titik_dan_kepercayaan_rendah():
    # P10/P90 residual diisi tiket TTN-AI-005; sebelum itu tidak boleh mengarang rentang.
    for p in ramal_harga_pasangan(masukan()):
        assert p.rentang_bawah == p.rentang_atas == p.harga_prediksi
        assert p.kepercayaan == "rendah"
        assert "rentang_belum_dikalibrasi" in p.alasan_singkat
