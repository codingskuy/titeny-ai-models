"""Uji demand_v1.0.0 (BR-203): baseline 28h x faktor hari besar x elastisitas, batas +-30%."""

from datetime import date, timedelta

import pytest

from titeny_models.demand import (
    InputDemand,
    elastisitas_faktor,
    faktor_hari_besar,
    ramal_demand_pasangan,
    status_data_demand,
)

H = date(2026, 10, 5)


def seri(nilai, hari=40, akhir=None):
    akhir = akhir or H - timedelta(days=1)
    return {akhir - timedelta(days=k): nilai for k in range(hari)}


@pytest.mark.parametrize(
    "komoditas,hari_besar,faktor",
    [
        ("cmd_tomat", None, 1.00),
        ("cmd_tomat", "puasa", 1.18),
        ("cmd_cabai_merah", "lebaran", 1.35),
        ("cmd_daging_sapi", "lebaran", 1.35),
        ("cmd_beras_medium", "lebaran", 1.10),
        ("cmd_tomat", "lebaran", 1.00),
        ("cmd_beras_medium", "natal_tahun_baru", 1.12),
        ("cmd_cabai_rawit", "natal_tahun_baru", 1.12),
    ],
)
def test_faktor_hari_besar(komoditas, hari_besar, faktor):
    assert faktor_hari_besar(komoditas, hari_besar) == faktor


@pytest.mark.parametrize(
    "komoditas,rasio,faktor",
    [
        ("cmd_beras_medium", 1.10, 0.96),  # +10% harga -> -4% pangan pokok
        ("cmd_tomat", 1.10, 0.93),  # +10% harga -> -7% sayur
        ("cmd_tomat", 0.90, 1.07),  # simetris
        ("cmd_tomat", 1.00, 1.00),
        ("cmd_beras_medium", 1.20, 0.92),
    ],
)
def test_elastisitas(komoditas, rasio, faktor):
    assert elastisitas_faktor(komoditas, rasio) == pytest.approx(faktor)


def masukan(**kw):
    dasar = {
        "komoditas_id": "cmd_tomat", "zona": "bekasi_utara", "hari_ini": H,
        "volume": seri(100.0), "hari_besar": {}, "rasio_harga": 1.0,
    }  # fmt: skip
    dasar.update(kw)
    return InputDemand(**dasar)


def test_baseline_datar_total_7_dan_30_hari():
    h7, h30 = ramal_demand_pasangan(masukan())
    assert (h7.horizon, h30.horizon) == ("H+7_total_kg", "H+30")
    assert h7.demand_prediksi_kg == pytest.approx(700.0)
    assert h30.demand_prediksi_kg == pytest.approx(3000.0)
    assert h7.model_version == "demand_v1.0.0" and h7.tanggal == H


def test_baseline_memakai_28_hari_terakhir():
    volume = seri(100.0, 28)
    for k in range(28, 40):
        volume[H - timedelta(days=1 + k)] = 9999.0  # lebih tua dari 28 hari
    assert ramal_demand_pasangan(masukan(volume=volume))[0].demand_prediksi_kg == pytest.approx(700.0)


def test_faktor_hari_besar_hanya_pada_hari_di_horizon():
    puasa = {H + timedelta(days=k): "puasa" for k in range(1, 8)}
    h7, _ = ramal_demand_pasangan(masukan(hari_besar=puasa))
    assert h7.demand_prediksi_kg == pytest.approx(700.0 * 1.18)
    sebagian = {H + timedelta(days=k): "puasa" for k in range(1, 4)}  # 3 dari 7 hari
    h7b, _ = ramal_demand_pasangan(masukan(hari_besar=sebagian))
    assert h7b.demand_prediksi_kg == pytest.approx(100 * (4 + 3 * 1.18))


def test_batas_plus_minus_30_persen():
    lebaran = {H + timedelta(days=k): "lebaran" for k in range(1, 8)}
    atas, _ = ramal_demand_pasangan(masukan(komoditas_id="cmd_cabai_merah", hari_besar=lebaran))
    assert atas.demand_prediksi_kg == pytest.approx(700.0 * 1.30)  # 1,35 dipotong ke 1,30
    bawah, _ = ramal_demand_pasangan(masukan(rasio_harga=2.0))  # harga +100% -> -40% -> dipotong -30%
    assert bawah.demand_prediksi_kg == pytest.approx(700.0 * 0.70)


def test_elastisitas_dipakai_pada_demand():
    h7, _ = ramal_demand_pasangan(masukan(rasio_harga=1.10))
    assert h7.demand_prediksi_kg == pytest.approx(700.0 * 0.93)


def test_fallback_s3_kosong_1_hari_rerata_7_hari_berlabel_estimasi():
    volume = seri(100.0, 40, akhir=H - timedelta(days=2))
    for k in range(2, 9):
        volume[H - timedelta(days=k)] = 200.0  # 7 hari terakhir yang ada
    assert status_data_demand(volume, H) == ("estimasi", 1)
    h7, _ = ramal_demand_pasangan(masukan(volume=volume))
    assert h7.label == "estimasi"
    assert h7.demand_prediksi_kg == pytest.approx(7 * 200.0)


def test_s3_kosong_3_hari_dihentikan():
    assert ramal_demand_pasangan(masukan(volume=seri(100.0, 40, akhir=H - timedelta(days=4)))) is None


def test_sinyal_dan_rentang_belum_diisi_pada_keluaran_dasar():
    d = ramal_demand_pasangan(masukan())[0].as_dict()
    assert d["rentang_bawah_kg"] is None and d["rentang_atas_kg"] is None  # kalibrasi: TTN-AI-005
    assert d["jenis"] == "demand" and d["zona"] == "bekasi_utara"


def test_terapkan_sinyal_level_kabupaten_dan_pembagian_selisih():
    from titeny_models.demand import terapkan_sinyal

    # dua zona di bawah kab_karawang: 600 + 400 = 1000 kg demand H+7
    baris = []
    for zona, v in (("bekasi_utara", 600.0), ("bekasi_selatan", 400.0)):
        baris.append(ramal_demand_pasangan(masukan(zona=zona, volume=seri(v / 7)))[0])
    surplus = terapkan_sinyal(baris, {("cmd_tomat", "kab_karawang", "H+7_total_kg"): 1500.0})
    assert [b.sinyal for b in surplus] == ["surplus", "surplus"]
    assert "300 kg" in " ".join(surplus[0].rekomendasi)  # 500 selisih x 60%
    assert "200 kg" in " ".join(surplus[1].rekomendasi)  # 500 selisih x 40%
    defisit = terapkan_sinyal(baris, {("cmd_tomat", "kab_karawang", "H+7_total_kg"): 700.0})
    assert [b.sinyal for b in defisit] == ["defisit", "defisit"]
    seimbang = terapkan_sinyal(baris, {("cmd_tomat", "kab_karawang", "H+7_total_kg"): 1000.0})
    assert {b.sinyal for b in seimbang} == {"seimbang"}


def test_terapkan_sinyal_tanpa_panen_seimbang_dan_data_sedikit_generik():
    from titeny_models.demand import terapkan_sinyal
    from titeny_models.sinyal import GENERIK

    baris = ramal_demand_pasangan(masukan())
    tanpa = terapkan_sinyal(baris, {})
    assert {b.sinyal for b in tanpa} == {"seimbang"}
    kunci = {
        ("cmd_tomat", "kab_karawang", "H+7_total_kg"): 5000.0,
        ("cmd_tomat", "kab_karawang", "H+30"): 5000.0,
    }
    rendah = terapkan_sinyal(baris, kunci, frozenset({("cmd_tomat", "kab_karawang")}))
    assert all(b.sinyal == "seimbang" and b.rekomendasi == [GENERIK] for b in rendah)
