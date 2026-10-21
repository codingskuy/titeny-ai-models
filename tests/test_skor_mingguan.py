"""Uji skor MAPE mingguan + job `mape` (arsip prediksi vs aktual)."""

import json
from datetime import date, timedelta

import pytest

from titeny_models.jobs import main
from titeny_models.sintetis import tulis_fixture
from titeny_models.skor_mingguan import (
    alarm_mape_h7,
    awal_minggu_skor,
    evaluasi_alarm,
    ringkas_minggu,
    skor_demand,
    skor_harga,
    skor_panen,
)

MINGGU = date(2026, 10, 4)  # Minggu; minggu skor 28 Sep .. 4 Okt


def pred_harga(target, horizon, harga, kom="cmd_a", psr="p1"):
    return {"komoditas_id": kom, "pasar_id": psr, "tanggal_prediksi": target.isoformat(), "horizon": horizon,
            "harga_prediksi": harga}  # fmt: skip


def test_minggu_skor_senin_sampai_minggu():
    assert awal_minggu_skor(MINGGU) == date(2026, 9, 28)


def test_skor_harga_hanya_titik_di_minggu_skor_dan_horizon_h1_h7():
    aktual = {("cmd_a", "p1"): {date(2026, 9, 30): 100.0, date(2026, 10, 1): 200.0, date(2026, 9, 20): 100.0}}
    arsip = [
        pred_harga(date(2026, 9, 30), "H+1", 110),  # +10%
        pred_harga(date(2026, 10, 1), "H+1", 180),  # -10%
        pred_harga(date(2026, 9, 20), "H+1", 500),  # di luar minggu skor -> diabaikan
        pred_harga(date(2026, 9, 30), "H+3", 999),  # horizon tidak dinilai
    ]
    hasil = skor_harga(arsip, aktual, MINGGU)
    assert len(hasil) == 1
    s = hasil[0]
    assert (s["horizon"], s["n"]) == ("H+1", 2)
    assert s["mape"] == pytest.approx(10.0)
    assert s["bias_pct"] == pytest.approx(0.0)
    assert s["rata_over_pct"] == pytest.approx(10.0) and s["rata_under_pct"] == pytest.approx(-10.0)


def test_skor_demand_menunggu_horizon_selesai_dan_aktual_lengkap():
    volume = {
        ("cmd_a", "z"): {date(2026, 9, 25) + timedelta(days=k): 100.0 for k in range(20)}
    }  # 25 Sep..14 Okt
    asal_h7 = date(2026, 9, 27)  # +7 = 4 Okt -> jatuh di minggu skor
    arsip = [
        {"komoditas_id": "cmd_a", "zona": "z", "tanggal": asal_h7.isoformat(), "horizon": "H+7_total_kg",
         "demand_prediksi_kg": 770.0},
        {"komoditas_id": "cmd_a", "zona": "z", "tanggal": "2026-09-20", "horizon": "H+7_total_kg",
         "demand_prediksi_kg": 1.0},  # selesai sebelum minggu skor
        {"komoditas_id": "cmd_a", "zona": "z", "tanggal": "2026-09-27", "horizon": "H+30",
         "demand_prediksi_kg": 1.0},  # H+30 belum selesai
    ]  # fmt: skip
    hasil = skor_demand(arsip, volume, MINGGU)
    assert len(hasil) == 1 and hasil[0]["horizon"] == "H+7_total_kg"
    assert hasil[0]["mape"] == pytest.approx(10.0)  # aktual 700 vs 770


def test_skor_panen_total_musim():
    hasil_mingguan = {
        ("cmd_padi", "kab_karawang"): {"2026-W40": ("2026-MT1", 1000.0), "2026-W41": ("2026-MT1", 1000.0)}
    }
    arsip = [
        {
            "komoditas_id": "cmd_padi",
            "kabupaten_id": "kab_karawang",
            "minggu": "2026-W40",
            "panen_prediksi_kg": 1100,
        },
        {
            "komoditas_id": "cmd_padi",
            "kabupaten_id": "kab_karawang",
            "minggu": "2026-W41",
            "panen_prediksi_kg": 1300,
        },
        {
            "komoditas_id": "cmd_padi",
            "kabupaten_id": "kab_karawang",
            "minggu": "2026-W42",
            "panen_prediksi_kg": 9999,
        },
    ]
    hasil = skor_panen(arsip, hasil_mingguan)
    assert len(hasil) == 1 and hasil[0]["n"] == 2
    assert hasil[0]["mape"] == pytest.approx(20.0)  # |2400 - 2000| / 2000


@pytest.mark.parametrize(
    "riwayat,hasil",
    [
        ([16.0, 15.1], True),
        ([16.0, 15.0], False),
        ([20.0], False),
        ([10.0, 20.0, 18.0], True),
        ([None, 20.0], False),
    ],
)
def test_alarm_mape_h7_dua_minggu_berturut(riwayat, hasil):
    assert alarm_mape_h7(riwayat) is hasil


def test_evaluasi_alarm_bias_over_dua_minggu():
    def r(minggu, h7, bias):
        return {
            "minggu": minggu,
            "harga": {"mape_h7": h7, "bias_pct": bias},
            "demand": {"mape_h7": 1.0, "bias_pct": 0.0},
        }

    a = evaluasi_alarm([r("2026-W39", 5.0, 6.0)], r("2026-W40", 5.0, 5.5))
    assert a["tinjauan_analis"] == {"harga": True, "demand": False} and a["pager_analis"] is False
    b = evaluasi_alarm([r("2026-W39", 5.0, 6.0)], r("2026-W40", 5.0, 4.0))
    assert b["tinjauan_analis"]["harga"] is False


def test_ringkas_minggu_memuat_makro_dan_bias_berbobot():
    skor = [
        {"jenis": "harga", "horizon": "H+1", "mape": 4.0, "bias_pct": 2.0, "n": 1},
        {"jenis": "harga", "horizon": "H+1", "mape": 6.0, "bias_pct": 8.0, "n": 3},
        {"jenis": "harga", "horizon": "H+7", "mape": 10.0, "bias_pct": 0.0, "n": 1},
    ]
    r = ringkas_minggu(skor, MINGGU)
    assert r["minggu"] == "2026-W40" and r["harga"]["mape_h1"] == pytest.approx(5.0)
    assert r["harga"]["mape_h7"] == 10.0 and r["harga"]["n"] == 5
    assert r["harga"]["bias_pct"] == pytest.approx((2 * 1 + 8 * 3 + 0) / 5)
    assert r["demand"]["mape_h7"] is None


def test_job_mape_end_to_end_dengan_arsip(tmp_path):
    data, keluar = tmp_path / "data", tmp_path / "out"
    tulis_fixture(data, date(2026, 10, 5) - timedelta(days=100), 100)  # data sampai 4 Okt
    for k in range(14, 0, -1):  # job harga harian 21 Sep .. 4 Okt (arsip menumpuk)
        asal = date(2026, 10, 5) - timedelta(days=k)
        assert (
            main(["harga", "--data", str(data), "--keluar", str(keluar), "--tanggal", asal.isoformat()]) == 0
        )
    assert len(list((keluar / "arsip").glob("prediksi_harga-*.jsonl"))) == 14

    assert main(["mape", "--data", str(data), "--keluar", str(keluar), "--tanggal", MINGGU.isoformat()]) == 0
    ringkasan = json.loads((keluar / "ringkasan_mape.json").read_text())
    assert ringkasan["minggu"] == "2026-W40" and ringkasan["harga"]["n"] > 0
    assert ringkasan["harga"]["mape_h1"] is not None and ringkasan["harga"]["mape_h7"] is not None
    assert ringkasan["pager_analis"] is False
    baris = [json.loads(b) for b in (keluar / "skor_mape_mingguan.jsonl").read_text().splitlines()]
    assert {b["horizon"] for b in baris} == {"H+1", "H+7"} and all(
        b["model_version"] == "harga_v1.0.0" for b in baris
    )
    assert (keluar / "arsip" / "ringkasan_mape-2026-W40.json").exists()

    # idempoten: ulang job menghasilkan ringkasan yang sama
    assert main(["mape", "--data", str(data), "--keluar", str(keluar), "--tanggal", MINGGU.isoformat()]) == 0
    assert json.loads((keluar / "ringkasan_mape.json").read_text())["harga"] == ringkasan["harga"]


def test_job_mape_gagal_tanpa_arsip(tmp_path, capsys):
    data = tmp_path / "data"
    tulis_fixture(data, date(2026, 10, 5) - timedelta(days=60), 60)
    assert (
        main(["mape", "--data", str(data), "--keluar", str(tmp_path / "o"), "--tanggal", MINGGU.isoformat()])
        == 1
    )
    assert "tidak ada titik" in capsys.readouterr().out
