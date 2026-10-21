"""Uji backtest walk-forward: tanpa kebocoran masa depan, gerbang kandidat, CLI."""

import json
from dataclasses import replace
from datetime import date, timedelta

import pytest

from titeny_models.backtest import (
    backtest_demand,
    backtest_harga,
    jalankan_backtest,
    ringkas_harga,
)
from titeny_models.demand import InputDemand
from titeny_models.harga import InputHarga, ramal_harga_pasangan
from titeny_models.sintetis import tulis_fixture

T = date(2026, 10, 5)  # hari pertama tanpa data; data terakhir 4 Okt


def seri_naik(awal, hari, dasar=10000.0, naik=20.0):
    return {awal + timedelta(days=k): dasar + naik * k for k in range(hari)}


def masukan(komoditas="cmd_cabai_merah", pasar="psr_a", hari=120):
    awal = T - timedelta(days=hari)
    return InputHarga(
        komoditas_id=komoditas,
        pasar_id=pasar,
        hari_ini=T,
        harga=seri_naik(awal, hari),
        stok={awal + timedelta(days=k): 100.0 for k in range(hari)},
        biaya_logistik={awal + timedelta(days=k): 1000.0 for k in range(hari)},
    )


def test_baris_backtest_hanya_memakai_aktual_yang_tersedia():
    baris = backtest_harga([masukan()], T, hari=10)
    assert baris
    for b in baris:
        h = int(b["horizon"][2:])
        origin = date.fromisoformat(b["origin"])
        assert origin + timedelta(days=h) < T  # aktual harus sebelum T
    # H+7 hanya untuk origin <= T-8 -> 3 dari 10 origin; H+1 untuk 9 origin
    assert sum(b["horizon"] == "H+7" for b in baris) == 3
    assert sum(b["horizon"] == "H+1" for b in baris) == 9


def test_tanpa_kebocoran_masa_depan():
    m = masukan()
    normal = backtest_harga([m], T, hari=15)
    # rusak semua data pada/ setelah origin pertama + 1 hari; prediksi tiap origin tak boleh berubah
    asal0 = T - timedelta(days=15)
    rusak = {d: (v * 1000 if d >= asal0 + timedelta(days=1) else v) for d, v in m.harga.items()}
    # prediksi origin pertama harus identik karena hanya data < asal0 yang boleh terbaca
    p1 = ramal_harga_pasangan(replace(m, hari_ini=asal0))
    p2 = ramal_harga_pasangan(replace(m, hari_ini=asal0, harga=rusak))
    assert [x.harga_prediksi for x in p1] == [x.harga_prediksi for x in p2]
    assert normal  # backtest tetap menghasilkan baris


def test_ringkasan_mape_per_komoditas_dan_target():
    baris = backtest_harga([masukan("cmd_a", "p1"), masukan("cmd_b", "p1")], T, hari=20)
    r = ringkas_harga(baris)
    assert set(r["mape_h1_per_komoditas"]) == {"cmd_a", "cmd_b"}
    assert r["mape_h1_median"] is not None and r["mape_h7_rata_makro"] is not None
    assert r["bias_h7"]["n"] > 0 and set(r["target"]) == {"h1_median_le_8", "h1_tidak_ada_gt_15", "h7_le_12"}


def test_gerbang_kandidat_end_to_end(tmp_path):
    data = tmp_path / "data"
    tulis_fixture(data, T - timedelta(days=100), 100)
    keluar = tmp_path / "out"

    def sama(m):  # kandidat identik dengan versi berjalan -> tidak ada penurunan MAPE -> tidak naik
        return ramal_harga_pasangan(m)

    r = jalankan_backtest(data, keluar, T, hari=8, kandidat_harga=sama, tanggal_backtest=date(2026, 10, 21))
    kep = r["kandidat_harga"]["keputusan_naik_versi"]
    assert kep["naik"] is False and "< 0,5" in kep["alasan"]
    assert r["sumber_data"] == "SINTETIS" and r["tanggal_backtest"] == "2026-10-21"
    assert (keluar / "backtest.csv").exists() and (keluar / "backtest_demand.csv").exists()
    assert r["panen"]["status"].startswith("tidak dibacktest")
    assert json.loads((keluar / "ringkasan_backtest.json").read_text())["hari"] == 8


def test_gerbang_menolak_kandidat_yang_memburukkan_komoditas(tmp_path):
    data = tmp_path / "data"
    tulis_fixture(data, T - timedelta(days=100), 100)

    def buruk(m):
        hasil = ramal_harga_pasangan(m)
        if hasil is None or m.komoditas_id != "cmd_cabai_merah":
            return hasil
        return [
            replace(p, harga_prediksi=int(p.harga_prediksi * 1.5)) for p in hasil
        ]  # +50% hanya satu komoditas

    r = jalankan_backtest(data, tmp_path / "o", T, hari=8, kandidat_harga=buruk)
    kep = r["kandidat_harga"]["keputusan_naik_versi"]
    assert kep["naik"] is False and kep["memburuk"] == ["cmd_cabai_merah"]


def test_backtest_demand_h30_butuh_origin_cukup_tua():
    awal = T - timedelta(days=120)
    volume = {awal + timedelta(days=k): 100.0 for k in range(120)}
    m = InputDemand(komoditas_id="cmd_tomat", zona="z", hari_ini=T, volume=volume)
    baris = backtest_demand([m], T, hari=40)
    h30 = [b for b in baris if b["horizon"] == "H+30"]
    h7 = [b for b in baris if b["horizon"] == "H+7_total_kg"]
    assert len(h30) == 40 - 30 and len(h7) == 40 - 7
    assert all(b["aktual"] == pytest.approx(3000.0) for b in h30)
    assert all(b["prediksi"] == pytest.approx(3000.0) for b in h30)  # seri datar -> prediksi tepat
