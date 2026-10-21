"""Uji panen_v1.0.0 (BR-203): luas x yield x cuaca x musim, bulat 50 kg."""

from datetime import date, timedelta

import pytest

from titeny_models.panen import (
    InputPanen,
    awal_minggu,
    bulatkan_50,
    faktor_cuaca,
    luas_ekspektasi,
    minggu_iso,
    ramal_panen_pasangan,
    yield_baseline,
)

H = date(2026, 10, 5)  # Senin


def test_bulatkan_50():
    assert bulatkan_50(0) == 0
    assert bulatkan_50(24.9) == 0
    assert bulatkan_50(25) == 50
    assert bulatkan_50(12524) == 12500
    assert bulatkan_50(12525) == 12550


@pytest.mark.parametrize(
    "hujan,peringatan,faktor",
    [
        (100, None, 1.00),
        (300, None, 1.00),  # batas: "> 300 mm"
        (300.1, None, 0.85),
        (50, "banjir", 0.85),
        (50, "kekeringan", 0.90),
        (400, "kekeringan", 0.90),  # peringatan eksplisit menang atas ambang hujan
    ],
)
def test_faktor_cuaca(hujan, peringatan, faktor):
    assert faktor_cuaca(hujan, peringatan) == faktor


def test_yield_baseline_median_3_musim_terakhir():
    assert yield_baseline([9000, 5000, 5200, 5400]) == 5200  # hanya 3 terakhir
    assert yield_baseline([5000]) == 5000
    assert yield_baseline([]) is None


def test_yield_baseline_perubahan_maks_20_persen_per_tahun():
    assert yield_baseline([8000, 8000, 8000], baseline_tahun_lalu=5000) == pytest.approx(6000)
    assert yield_baseline([2000, 2000, 2000], baseline_tahun_lalu=5000) == pytest.approx(4000)
    assert yield_baseline([5200, 5200, 5200], baseline_tahun_lalu=5000) == 5200


def test_minggu_iso_dan_awal_minggu():
    assert awal_minggu(date(2026, 10, 7)) == date(2026, 10, 5)
    assert minggu_iso(date(2026, 10, 12)) == "2026-W42"
    assert minggu_iso(H) == "2026-W41"  # sesuai contoh TownHall


def test_luas_ekspektasi_padi_jendela_90_120_hari():
    minggu = H + timedelta(days=7)  # minggu target [12 Okt .. 18 Okt]
    # tanam 105 hari sebelum awal minggu: seluruh jendela panen (+90..+120) menutup minggu itu sebagian
    tanam_di_dalam = [(minggu - timedelta(days=105), 30.0)]
    tanam_di_luar = [(minggu - timedelta(days=200), 99.0), (minggu - timedelta(days=10), 99.0)]
    dalam = luas_ekspektasi(tanam_di_dalam, "cmd_padi", minggu)
    assert dalam == pytest.approx(30.0 * 7 / 31)  # 7 dari 31 hari kemungkinan panen jatuh di minggu itu
    assert luas_ekspektasi(tanam_di_luar, "cmd_padi", minggu) == 0.0


def test_luas_ekspektasi_sayur_jendela_60_75_hari():
    minggu = H + timedelta(days=7)
    assert luas_ekspektasi([(minggu - timedelta(days=65), 10.0)], "cmd_cabai_merah", minggu) > 0
    assert luas_ekspektasi([(minggu - timedelta(days=100), 10.0)], "cmd_cabai_merah", minggu) == 0.0


def masukan(**kw):
    awal = H - timedelta(days=130)
    dasar = {
        "komoditas_id": "cmd_padi",
        "kabupaten_id": "kab_karawang",
        "hari_ini": H,
        "tanam": [(awal + timedelta(days=k), 5.0) for k in range(130)],
        "yield_musim": [5000.0, 5000.0, 5000.0],
        "jumlah_catatan": 24,
        "hujan_30h_mm": 120.0,
        "peringatan": None,
    }
    dasar.update(kw)
    return InputPanen(**dasar)


def test_kontrak_4_minggu_kelipatan_50():
    hasil = ramal_panen_pasangan(masukan())
    assert [p.minggu for p in hasil] == [minggu_iso(H + timedelta(days=7 * k)) for k in range(1, 5)]
    for p in hasil:
        d = p.as_dict()
        assert d["jenis"] == "panen" and d["model_version"] == "panen_v1.0.0"
        assert d["panen_prediksi_kg"] % 50 == 0 and d["panen_prediksi_kg"] > 0
        assert d["kepercayaan"] in {"tinggi", "sedang", "rendah"}
        assert set(d) == {
            "jenis", "komoditas_id", "kabupaten_id", "minggu", "panen_prediksi_kg",
            "rentang_bawah_kg", "rentang_atas_kg", "kepercayaan", "model_version", "dihitung_pada",
        }  # fmt: skip


def test_panen_sama_dengan_luas_x_yield_x_cuaca_x_musim():
    normal = ramal_panen_pasangan(masukan(faktor_musim=1.0))
    hujan = ramal_panen_pasangan(masukan(hujan_30h_mm=350.0))
    kering = ramal_panen_pasangan(masukan(peringatan="kekeringan"))
    musim = ramal_panen_pasangan(masukan(faktor_musim=1.1))
    for n, h, k, m in zip(normal, hujan, kering, musim):
        assert abs(h.panen_prediksi_kg - 0.85 * n.panen_prediksi_kg) <= 50
        assert abs(k.panen_prediksi_kg - 0.90 * n.panen_prediksi_kg) <= 50
        assert abs(m.panen_prediksi_kg - 1.10 * n.panen_prediksi_kg) <= 50


def test_nilai_manual_satu_minggu():
    # 5 ha/hari ditanam tiap hari; minggu target menerima 7 hari panen per tanam di jendela 31 hari:
    # luas_minggu = sum_k 5 * (overlap_k / 31) = 5 * 7 = 35 ha (jendela penuh) -> 35 x 5000 = 175000 kg
    hasil = ramal_panen_pasangan(masukan())
    assert hasil[0].panen_prediksi_kg == 175000


def test_catatan_kurang_dari_10_baris_kepercayaan_rendah():
    hasil = ramal_panen_pasangan(masukan(jumlah_catatan=9))
    assert all(p.kepercayaan == "rendah" for p in hasil)
    assert all(p.kepercayaan != "rendah" for p in ramal_panen_pasangan(masukan(jumlah_catatan=10)))


def test_tanpa_riwayat_yield_tidak_diramal():
    assert ramal_panen_pasangan(masukan(yield_musim=[])) is None
