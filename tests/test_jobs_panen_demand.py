"""Uji job panen + demand pada fixture SINTETIS (bukan data nyata)."""

import json
from datetime import date, timedelta

import pytest

from titeny_models.jobs import main
from titeny_models.katalog import (
    KABUPATEN,
    KOMODITAS_HARGA,
    KOMODITAS_PANEN,
    ZONA_DEMAND,
)
from titeny_models.sintetis import tulis_fixture

H = date(2026, 10, 5)


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    d = tmp_path_factory.mktemp("data")
    tulis_fixture(d, H - timedelta(days=60), 60)
    return d


def baca(path):
    return [json.loads(b) for b in path.read_text().splitlines()]


def jalankan(jenis, data, keluar):
    return main([jenis, "--data", str(data), "--keluar", str(keluar), "--tanggal", H.isoformat()])


def test_job_panen_6x5x4_baris_dan_kepercayaan_rendah_untuk_catatan_sedikit(data, tmp_path):
    assert jalankan("panen", data, tmp_path) == 0
    baris = baca(tmp_path / "prediksi_panen.jsonl")
    assert len(baris) == len(KOMODITAS_PANEN) * len(KABUPATEN) * 4 == 120
    assert all(b["panen_prediksi_kg"] % 50 == 0 and b["model_version"] == "panen_v1.0.0" for b in baris)
    assert {b["minggu"] for b in baris} == {"2026-W42", "2026-W43", "2026-W44", "2026-W45"}
    rendah = {(b["komoditas_id"], b["kabupaten_id"]) for b in baris if b["kepercayaan"] == "rendah"}
    assert rendah == {("cmd_tomat", "kab_malang")}  # satu-satunya pasangan dengan < 10 catatan di fixture


def test_job_demand_butuh_harga_lebih_dulu(data, tmp_path, capsys):
    assert jalankan("demand", data, tmp_path) == 1
    assert "job harga harus lebih dulu" in capsys.readouterr().out


def test_job_demand_12x16x2_baris_sinyal_dan_rekomendasi(data, tmp_path):
    assert jalankan("harga", data, tmp_path) == 0
    assert jalankan("panen", data, tmp_path) == 0
    assert jalankan("demand", data, tmp_path) == 0
    baris = baca(tmp_path / "prediksi_demand.jsonl")
    assert len(baris) == len(KOMODITAS_HARGA) * len(ZONA_DEMAND) * 2 == 384
    assert {b["horizon"] for b in baris} == {"H+7_total_kg", "H+30"}
    assert {b["sinyal"] for b in baris} <= {"surplus", "seimbang", "defisit"}
    assert all(b["model_version"] == "demand_v1.0.0" and b["demand_prediksi_kg"] >= 0 for b in baris)
    assert all(1 <= len(b["rekomendasi"]) <= 3 for b in baris)
    kunci = {(b["komoditas_id"], b["zona"], b["horizon"], b["tanggal"]) for b in baris}
    assert len(kunci) == len(baris)  # PK tabel prediksi_demand tidak bentrok
    # catatan panen sedikit -> sinyal netral + rekomendasi generik pada pasangan itu
    malang = [b for b in baris if b["komoditas_id"] == "cmd_tomat" and b["zona"] == "psr_surabaya_01"]
    assert malang and all(b["sinyal"] == "seimbang" and "belum cukup" in b["rekomendasi"][0] for b in malang)

    rekom = baca(tmp_path / "rekomendasi.jsonl")
    assert len(rekom) == len(ZONA_DEMAND)
    assert all(len(r["teks"]) <= 3 and r["status"] == "baru" for r in rekom)


def test_job_demand_tanpa_panen_tetap_jalan_dengan_sinyal_seimbang(data, tmp_path):
    assert jalankan("harga", data, tmp_path) == 0
    assert jalankan("demand", data, tmp_path) == 0
    assert {b["sinyal"] for b in baca(tmp_path / "prediksi_demand.jsonl")} == {"seimbang"}
