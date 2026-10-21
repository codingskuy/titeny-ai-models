"""Uji model card: wajib memuat versi, metrik eval, tanggal backtest; tidak mengarang angka."""

from datetime import date, timedelta

from titeny_models.backtest import jalankan_backtest
from titeny_models.kartu_model import kartu_demand, kartu_harga, kartu_panen, tulis_kartu
from titeny_models.sintetis import tulis_fixture

T = date(2026, 10, 5)


def ringkasan(tmp_path):
    data = tmp_path / "data"
    tulis_fixture(data, T - timedelta(days=100), 100)
    return jalankan_backtest(data, tmp_path / "bt", T, hari=8, tanggal_backtest=date(2026, 10, 21))


def test_kartu_memuat_versi_metrik_dan_tanggal(tmp_path):
    r = ringkasan(tmp_path)
    harga, demand, panen = kartu_harga(r), kartu_demand(r), kartu_panen(r)
    assert "`harga_v1.0.0`" in harga and "2026-10-21" in harga and "MAPE H+1, median" in harga
    assert f"{r['harga']['mape_h1_median']:.2f}%" in harga  # angka disalin dari hasil nyata
    assert "`demand_v1.0.0`" in demand and "MAPE H+30" in demand and "hanya pantau" in demand
    assert "`panen_v1.0.0`" in panen and "2026-10-21" in panen


def test_kartu_menandai_data_sintetis_dan_panen_belum_dievaluasi(tmp_path):
    r = ringkasan(tmp_path)
    for teks in (kartu_harga(r), kartu_demand(r), kartu_panen(r)):
        assert "SINTETIS" in teks and "BUKAN data pasar nyata" in teks
    panen = kartu_panen(r)
    assert "Belum dievaluasi" in panen and "%" not in panen.split("## Metrik evaluasi")[1].split("Target")[0]


def test_kartu_tanpa_demand_tidak_mengarang(tmp_path):
    r = ringkasan(tmp_path)
    r.pop("demand")
    assert "Belum dievaluasi" in kartu_demand(r)


def test_tulis_kartu_tiga_berkas(tmp_path):
    berkas = tulis_kartu(ringkasan(tmp_path), tmp_path / "kartu")
    assert sorted(b.name for b in berkas) == ["demand_v1.0.0.md", "harga_v1.0.0.md", "panen_v1.0.0.md"]
    assert all(b.read_text().startswith("# Model card:") for b in berkas)
