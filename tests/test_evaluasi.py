"""Uji metrik evaluasi (BR-301): MAPE, bias over/under, target, gerbang naik versi, pemicu tinjauan."""

import pytest

from titeny_models.evaluasi import (
    bias_ringkas,
    keputusan_naik_versi,
    mape,
    periksa_target,
    tinjauan_bias,
)


def test_mape_nilai_manual():
    assert mape([100, 200], [110, 180]) == pytest.approx(10.0)  # (10% + 10%) / 2
    assert mape([100], [100]) == 0.0


def test_mape_mengabaikan_aktual_nol_dan_kosong_none():
    assert mape([0, 100], [5, 90]) == pytest.approx(10.0)
    assert mape([], []) is None
    assert mape([0], [1]) is None


def test_mape_panjang_beda_ditolak():
    with pytest.raises(ValueError):
        mape([1, 2], [1])


def test_bias_over_dan_under_dilaporkan_terpisah():
    b = bias_ringkas([100, 100, 100, 100], [110, 120, 90, 80])
    assert b["bias_rata_pct"] == pytest.approx(0.0)  # +10 +20 -10 -20
    assert b["rata_over_pct"] == pytest.approx(15.0)
    assert b["rata_under_pct"] == pytest.approx(-15.0)
    assert b["porsi_over"] == pytest.approx(0.5)
    assert b["n"] == 4


def test_bias_tanpa_titik_over_atau_under():
    b = bias_ringkas([100, 100], [110, 120])
    assert b["rata_under_pct"] is None and b["porsi_over"] == 1.0
    assert bias_ringkas([], [])["n"] == 0


@pytest.mark.parametrize(
    "riwayat,diharapkan",
    [
        ([6.0, 5.1], True),
        ([6.0, 5.0], False),  # tepat 5% belum memicu (> 5)
        ([4.0, 9.0], False),  # hanya 1 minggu
        ([9.0, 4.0, 6.0, 7.0], True),  # dua minggu TERAKHIR berturut-turut
        ([9.0], False),
        ([], False),
        ([6.0, None], False),
    ],
)
def test_tinjauan_bias_overpredict_2_minggu_berturut(riwayat, diharapkan):
    assert tinjauan_bias(riwayat) is diharapkan


def test_periksa_target_lulus_dan_gagal():
    ok = periksa_target(
        mape_h1_per_komoditas={"a": 5.0, "b": 7.0, "c": 9.0},
        mape_h7_per_komoditas={"a": 8.0, "b": 10.0, "c": 11.0},
    )
    assert ok["h1_median_le_8"] and ok["h1_tidak_ada_gt_15"] and ok["h7_le_12"]
    gagal = periksa_target(
        mape_h1_per_komoditas={"a": 9.0, "b": 9.5, "c": 16.0},
        mape_h7_per_komoditas={"a": 13.0, "b": 14.0, "c": 15.0},
    )
    assert not gagal["h1_median_le_8"] and not gagal["h1_tidak_ada_gt_15"] and not gagal["h7_le_12"]


def test_periksa_target_batas_tepat():
    r = periksa_target({"a": 8.0, "b": 8.0, "c": 15.0}, {"a": 12.0})
    assert r["h1_median_le_8"] and r["h1_tidak_ada_gt_15"] and r["h7_le_12"]  # batas inklusif


def test_naik_versi_butuh_turun_05_poin_dan_tak_ada_memburuk_2_poin():
    berjalan = {"a": 10.0, "b": 10.0}
    # rata-rata turun 1,0 poin; tidak ada yang memburuk > 2
    assert keputusan_naik_versi(berjalan, {"a": 8.0, "b": 10.0}).naik is True
    # turun tepat 0,5 -> boleh (>= 0,5)
    assert keputusan_naik_versi(berjalan, {"a": 9.0, "b": 10.0}).naik is True
    # turun 0,4 -> tidak
    t = keputusan_naik_versi(berjalan, {"a": 9.2, "b": 10.0})
    assert t.naik is False and "0,5" in t.alasan
    # rata-rata turun besar tetapi satu komoditas memburuk 2,5 poin -> tolak
    m = keputusan_naik_versi(berjalan, {"a": 2.0, "b": 12.5})
    assert m.naik is False and m.memburuk == ["b"]
    # memburuk tepat 2,0 poin masih diizinkan (> 2 yang menolak)
    assert keputusan_naik_versi({"a": 10.0, "b": 10.0}, {"a": 4.0, "b": 12.0}).naik is True


def test_naik_versi_komoditas_tak_sama_ditolak():
    with pytest.raises(ValueError):
        keputusan_naik_versi({"a": 1.0}, {"b": 1.0})
