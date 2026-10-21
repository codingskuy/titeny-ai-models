"""Uji kalibrasi rentang P10-P90 dan label kepercayaan (BR-205, FR-103)."""

import pytest

from titeny_models.kalibrasi import (
    MIN_RESIDUAL,
    Kalibrasi,
    cakupan,
    hitung_kepercayaan,
    kalibrasi_dari_residual,
    perlu_kalibrasi_ulang,
    rentang_harga,
    rentang_kg,
    status_cakupan,
)


# ---------- kepercayaan: batas persis ----------
@pytest.mark.parametrize(
    "sampel,mape14,label",
    [
        (5, 7.99, "tinggi"),
        (5, 8.0, "sedang"),  # MAPE_14h < 8 (tegas)
        (4, 5.0, "sedang"),  # sampel >= 5 untuk tinggi
        (10, 5.0, "tinggi"),
        (3, 10.0, "sedang"),
        (2, 5.0, "rendah"),  # sampel < 3
        (0, 5.0, "rendah"),
        (6, 15.0, "sedang"),  # MAPE_14h > 15 (tegas)
        (6, 15.01, "rendah"),
        (3, 20.0, "rendah"),
        (2, 20.0, "rendah"),
        (5, 12.0, "sedang"),
    ],
)
def test_batas_kepercayaan(sampel, mape14, label):
    assert hitung_kepercayaan(sampel, mape14) == label


def test_kepercayaan_tanpa_mape_tidak_pernah_tinggi():
    assert hitung_kepercayaan(10, None) == "sedang"
    assert hitung_kepercayaan(2, None) == "rendah"


# ---------- kalibrasi dari residual ----------
def test_kalibrasi_p10_p90_residual_relatif():
    res = [i / 100 for i in range(-10, 11)]  # -0,10 .. +0,10 (21 titik)
    kal = kalibrasi_dari_residual(res)
    assert kal.n == 21
    assert kal.p10 == pytest.approx(-0.08)
    assert kal.p90 == pytest.approx(0.08)


def test_kalibrasi_butuh_minimal_residual():
    assert kalibrasi_dari_residual([0.01] * (MIN_RESIDUAL - 1)) is None
    assert kalibrasi_dari_residual([0.01] * MIN_RESIDUAL) is not None


def test_kalibrasi_hanya_30_residual_terbaru():
    lama = [5.0] * 20  # residual lama yang ekstrem
    baru = [0.01 * (i % 3 - 1) for i in range(30)]  # urut lama -> baru; 30 terakhir dipakai
    kal = kalibrasi_dari_residual(lama + baru)
    assert kal.n == 30 and kal.p90 < 1.0


def test_rentang_harga_kelipatan_500_dan_memuat_titik():
    kal = Kalibrasi(p10=-0.10, p90=0.20, n=30)
    bawah, atas = rentang_harga(42500, kal)
    assert (bawah, atas) == (38500, 51000)  # 42500 x 0,9 = 38250 -> 38500; x 1,2 = 51000
    assert bawah % 500 == 0 and atas % 500 == 0 and bawah <= 42500 <= atas


def test_rentang_selalu_memuat_titik_walau_residual_berbias():
    bias = Kalibrasi(p10=0.05, p90=0.10, n=30)  # semua residual positif: P10 > 0
    bawah, atas = rentang_harga(10000, bias)
    assert bawah <= 10000 <= atas
    neg = Kalibrasi(p10=-0.20, p90=-0.05, n=30)
    bawah, atas = rentang_harga(10000, neg)
    assert bawah <= 10000 <= atas


def test_rentang_tanpa_kalibrasi_sama_dengan_titik():
    assert rentang_harga(10000, None) == (10000, 10000)
    assert rentang_kg(1234.0, None) == (None, None)


def test_rentang_kg_tidak_negatif():
    bawah, atas = rentang_kg(100.0, Kalibrasi(p10=-1.5, p90=0.3, n=30))
    assert bawah == 0.0 and atas == pytest.approx(130.0)


# ---------- cakupan + pemicu ----------
def test_cakupan_persen():
    assert cakupan([5, 5, 5, 5], [4, 4, 6, 4], [6, 6, 7, 6]) == pytest.approx(75.0)  # 3 dari 4 di dalam
    assert cakupan([], [], []) is None


@pytest.mark.parametrize(
    "pct,status",
    [(95.0, "terlalu_lebar"), (90.0, "ok"), (70.0, "ok"), (69.9, "di_bawah_target"), (60.0, "di_bawah_target"),
     (59.9, "kalibrasi_ulang"), (0.0, "kalibrasi_ulang"), (None, "tidak_ada_data")],
)  # fmt: skip
def test_status_cakupan(pct, status):
    assert status_cakupan(pct) == status


def test_pemicu_kalibrasi_ulang_hanya_di_bawah_60():
    assert perlu_kalibrasi_ulang(59.99) is True
    assert perlu_kalibrasi_ulang(60.0) is False
    assert perlu_kalibrasi_ulang(None) is False
