"""Uji sinyal surplus/seimbang/defisit + rekomendasi (BR-204)."""

import pytest

from titeny_models.sinyal import GENERIK, klasifikasi_sinyal, rekomendasi_komoditas, rekomendasi_zona


@pytest.mark.parametrize(
    "panen,demand,sinyal",
    [
        (1200, 1000, "surplus"),  # tepat 120% -> surplus (>=)
        (1199, 1000, "seimbang"),
        (1000, 1000, "seimbang"),
        (801, 1000, "seimbang"),
        (800, 1000, "defisit"),  # tepat 80% -> defisit (<=)
        (0, 1000, "defisit"),
        (500, 0, "surplus"),
        (0, 0, "seimbang"),
    ],
)
def test_ambang_sinyal(panen, demand, sinyal):
    assert klasifikasi_sinyal(panen, demand) == sinyal


def test_rekomendasi_surplus_defisit_seimbang_dibulatkan_100_kg():
    s = rekomendasi_komoditas("surplus", 2349.0, "cmd_tomat", "bekasi_utara")
    assert 1 <= len(s) <= 3 and "2300 kg" in " ".join(s) and "gudang Bekasi" in s[0]
    d = rekomendasi_komoditas("defisit", 951.0, "cmd_tomat", "bekasi_utara")
    assert d[0] == "Amankan pasokan dari Brebes/Malang; batasi promo; naikkan buffer stok 15%."
    assert "1000 kg" in " ".join(d)
    assert rekomendasi_komoditas("seimbang", 10.0, "cmd_tomat", "bekasi_utara") == [
        "Tahan pola distribusi; pantau ulang Senin."
    ]


def test_rekomendasi_generik_bila_data_panen_kurang():
    assert rekomendasi_komoditas("surplus", 5000.0, "cmd_tomat", "bekasi_utara", generik=True) == [GENERIK]


def test_rekomendasi_zona_maks_3_aksi_urut_selisih_terbesar():
    baris = [(f"cmd_{i}", "surplus" if i % 2 else "defisit", float(i * 100)) for i in range(1, 8)]
    teks = rekomendasi_zona(baris, "bekasi_utara")
    assert len(teks) == 3
    assert "cmd_7" in teks[0] or "700 kg" in teks[0]
