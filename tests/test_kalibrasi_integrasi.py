"""Integrasi kalibrasi: harga/demand/panen berrentang, hindcast, artefak, pemicu kalibrasi ulang di job mape."""

import json
from datetime import date, timedelta

import numpy as np
import pytest

from titeny_models.backtest import backtest_harga
from titeny_models.demand import InputDemand, ramal_demand_pasangan
from titeny_models.harga import InputHarga, ramal_harga_pasangan
from titeny_models.hindcast import kalibrasi_harga_pasangan
from titeny_models.jobs import main
from titeny_models.kalibrasi import Kalibrasi, cakupan_walk_forward, rentang_harga
from titeny_models.kalibrasi_store import ambil_atau_hitung, baca_artefak
from titeny_models.panen import InputPanen, ramal_panen_pasangan
from titeny_models.sintetis import tulis_fixture

H = date(2026, 10, 5)


def seri_derau(hari=160, dasar=10000.0, sd=0.03, seed=7):
    rng = np.random.default_rng(seed)
    awal = H - timedelta(days=hari)
    return {awal + timedelta(days=k): float(dasar * (1 + rng.normal(0, sd))) for k in range(hari)}


def masukan(**kw):
    dasar = {
        "komoditas_id": "cmd_x",
        "pasar_id": "psr_y",
        "hari_ini": H,
        "harga": seri_derau(),
        "sampel_lapak": 6,
    }
    dasar.update(kw)
    return InputHarga(**dasar)


# ---------- harga berrentang ----------
def test_harga_dengan_kalibrasi_rentang_kepercayaan_dan_alasan():
    kal = {f"H+{i}": Kalibrasi(p10=-0.05, p90=0.08, n=30) for i in range(1, 8)}
    hasil = ramal_harga_pasangan(masukan(kalibrasi=kal, mape_14h=5.0))
    for p in hasil:
        assert (p.rentang_bawah, p.rentang_atas) == rentang_harga(p.harga_prediksi, kal[p.horizon])
        assert p.rentang_bawah < p.harga_prediksi < p.rentang_atas
        assert p.kepercayaan == "tinggi" and "rentang_belum_dikalibrasi" not in p.alasan_singkat
    assert {p.kepercayaan for p in ramal_harga_pasangan(masukan(kalibrasi=kal, mape_14h=20.0))} == {"rendah"}
    assert {
        p.kepercayaan for p in ramal_harga_pasangan(masukan(kalibrasi=kal, mape_14h=10.0, sampel_lapak=4))
    } == {"sedang"}
    assert {
        p.kepercayaan for p in ramal_harga_pasangan(masukan(kalibrasi=kal, mape_14h=3.0, sampel_lapak=2))
    } == {"rendah"}


def test_horizon_tanpa_kalibrasi_tetap_titik_dan_rendah():
    kal = {"H+1": Kalibrasi(p10=-0.05, p90=0.08, n=30)}
    hasil = {p.horizon: p for p in ramal_harga_pasangan(masukan(kalibrasi=kal, mape_14h=5.0))}
    assert hasil["H+1"].rentang_bawah < hasil["H+1"].rentang_atas
    assert hasil["H+2"].rentang_bawah == hasil["H+2"].rentang_atas and hasil["H+2"].kepercayaan == "rendah"


# ---------- hindcast ----------
def test_hindcast_menghasilkan_kalibrasi_7_horizon_dan_mape_14h():
    kal, mape14 = kalibrasi_harga_pasangan(masukan())
    assert set(kal) == {f"H+{i}" for i in range(1, 8)}
    assert all(k.n == 30 and k.p10 < 0 < k.p90 for k in kal.values())  # derau simetris
    assert 0.0 < mape14 < 15.0


def test_hindcast_data_pendek_tidak_mengarang_kalibrasi():
    awal = H - timedelta(days=9)
    pendek = {awal + timedelta(days=k): 10000.0 for k in range(9)}
    kal, _ = kalibrasi_harga_pasangan(masukan(harga=pendek))
    assert kal == {}  # < 10 residual per horizon


def test_cakupan_walk_forward_derau_normal_di_rentang_target():
    baris = []
    for seed in range(6):  # 6 pasangan sintetis agar sampel cukup
        m = masukan(pasar_id=f"p{seed}", harga=seri_derau(seed=seed))
        baris += backtest_harga([m], H, 90)
    r = cakupan_walk_forward(baris, "pasar_id", lambda p, k: rentang_harga(int(p), k))
    assert r["n"] > 500
    assert 70.0 <= r["cakupan_pct"] <= 90.0, r  # P10-P90 residual ~ 80% pada derau normal


# ---------- artefak ----------
def test_artefak_dipakai_ulang_kedaluwarsa_dan_dipaksa(tmp_path):
    art = baca_artefak(tmp_path / "x.json", "harga_v1.0.0")
    panggilan = []

    def hitung():
        panggilan.append(1)
        return {"H+1": Kalibrasi(-0.1, 0.1, 30)}

    _, baru = ambil_atau_hitung(art, "k", H, hitung)
    assert baru and len(panggilan) == 1
    _, baru = ambil_atau_hitung(art, "k", H + timedelta(days=6), hitung)  # umur 6 hari: pakai ulang
    assert not baru and len(panggilan) == 1
    _, baru = ambil_atau_hitung(art, "k", H + timedelta(days=7), hitung)  # umur 7 hari: kedaluwarsa
    assert baru and len(panggilan) == 2
    _, baru = ambil_atau_hitung(art, "k", H + timedelta(days=8), hitung, paksa=True)
    assert baru and len(panggilan) == 3
    assert art["pasangan"]["k"]["horizon"]["H+1"]["n"] == 30


# ---------- demand dan panen ----------
def test_demand_dengan_kalibrasi_rentang_kg_memuat_titik():
    volume = {H - timedelta(days=k + 1): 100.0 for k in range(40)}
    kal = {"H+7_total_kg": Kalibrasi(-0.1, 0.2, 30)}
    h7, h30 = ramal_demand_pasangan(InputDemand("cmd_tomat", "z", H, volume, kalibrasi=kal))
    assert h7.rentang_bawah_kg == pytest.approx(630.0) and h7.rentang_atas_kg == pytest.approx(840.0)
    assert h30.rentang_bawah_kg is None and h30.rentang_atas_kg is None  # horizon tanpa kalibrasi


def test_panen_dengan_kalibrasi_kelipatan_50_dan_memuat_titik():
    awal = H - timedelta(days=130)
    masuk = InputPanen(
        "cmd_padi", "kab_karawang", H, [(awal + timedelta(days=k), 5.0) for k in range(130)],
        [5000.0, 5000.0, 5000.0], 24, kalibrasi=Kalibrasi(-0.13, 0.17, 30),
    )  # fmt: skip
    for p in ramal_panen_pasangan(masuk):
        assert p.rentang_bawah_kg % 50 == 0 and p.rentang_atas_kg % 50 == 0
        assert p.rentang_bawah_kg < p.panen_prediksi_kg < p.rentang_atas_kg
    tanpa = ramal_panen_pasangan(InputPanen(**{**masuk.__dict__, "kalibrasi": None}))
    assert all(p.rentang_bawah_kg is None for p in tanpa)


# ---------- job harga + artefak ----------
@pytest.fixture(scope="module")
def data(tmp_path_factory):
    d = tmp_path_factory.mktemp("kal")
    tulis_fixture(d, H - timedelta(days=100), 100)
    return d


def test_job_harga_rentang_nyata_dan_artefak_residual_p90(data, tmp_path, capsys):
    assert main(["harga", "--data", str(data), "--keluar", str(tmp_path), "--tanggal", H.isoformat()]) == 0
    log = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert log["dikalibrasi_baru"] == 96 and log["tanpa_kalibrasi"] == 0
    baris = [json.loads(b) for b in (tmp_path / "prediksi_harga.jsonl").read_text().splitlines()]
    assert all(b["rentang_bawah"] <= b["harga_prediksi"] <= b["rentang_atas"] for b in baris)
    assert all(b["rentang_bawah"] % 500 == 0 and b["rentang_atas"] % 500 == 0 for b in baris)
    assert sum(b["rentang_bawah"] < b["rentang_atas"] for b in baris) > 0.8 * len(baris)
    assert {b["kepercayaan"] for b in baris} <= {"tinggi", "sedang", "rendah"}
    art = json.loads((tmp_path / "artefak" / "harga_v1.0.0" / "residual_p90.json").read_text())
    assert art["model_version"] == "harga_v1.0.0" and len(art["pasangan"]) == 96

    # run kedua pada tanggal sama memakai ulang artefak (tanpa hitung ulang)
    assert main(["harga", "--data", str(data), "--keluar", str(tmp_path), "--tanggal", H.isoformat()]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["dikalibrasi_baru"] == 0


# ---------- job mape: cakupan + kalibrasi ulang otomatis ----------
MINGGU = date(2026, 10, 4)


def tulis_arsip_sempit(keluar, bawah, atas, kom="cmd_cabai_merah", psr="psr_jakarta_timur_01"):
    arsip = keluar / "arsip"
    arsip.mkdir(parents=True)
    baris = [
        {"komoditas_id": kom, "pasar_id": psr, "tanggal_prediksi": (MINGGU - timedelta(days=k)).isoformat(),
         "horizon": "H+1", "harga_prediksi": 45000, "rentang_bawah": bawah, "rentang_atas": atas}
        for k in range(6)
    ]  # fmt: skip
    (arsip / "prediksi_harga-2026-10-01.jsonl").write_text("".join(json.dumps(b) + "\n" for b in baris))


def test_cakupan_di_bawah_60_memicu_kalibrasi_ulang_otomatis(data, tmp_path, capsys):
    tulis_arsip_sempit(tmp_path, 1000, 2000)  # rentang jauh di bawah aktual -> cakupan 0%
    assert (
        main(["mape", "--data", str(data), "--keluar", str(tmp_path), "--tanggal", MINGGU.isoformat()]) == 0
    )
    r = json.loads((tmp_path / "ringkasan_mape.json").read_text())
    assert r["harga"]["cakupan_pct"] == 0.0 and r["harga"]["status_cakupan"] == "kalibrasi_ulang"
    assert [(k["komoditas_id"], k["pasar_id"]) for k in r["kalibrasi_ulang"]] == [
        ("cmd_cabai_merah", "psr_jakarta_timur_01")
    ]
    art = baca_artefak(tmp_path / "artefak" / "harga_v1.0.0" / "residual_p90.json", "harga_v1.0.0")
    entri = art["pasangan"]["cmd_cabai_merah|psr_jakarta_timur_01"]
    assert entri["dihitung"] == MINGGU.isoformat() and "H+1" in entri["horizon"]  # dikalibrasi ulang
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["kalibrasi_ulang"] == 1


def test_cakupan_tinggi_tidak_memicu_kalibrasi_ulang(data, tmp_path):
    tulis_arsip_sempit(tmp_path, 1, 10_000_000)  # selalu mencakup
    assert (
        main(["mape", "--data", str(data), "--keluar", str(tmp_path), "--tanggal", MINGGU.isoformat()]) == 0
    )
    r = json.loads((tmp_path / "ringkasan_mape.json").read_text())
    assert r["harga"]["cakupan_pct"] == 100.0 and r["harga"]["status_cakupan"] == "terlalu_lebar"
    assert r["kalibrasi_ulang"] == []
    assert not (tmp_path / "artefak").exists()


def test_titik_kurang_dari_5_tidak_memicu_kalibrasi_ulang(data, tmp_path):
    tulis_arsip_sempit(tmp_path, 1000, 2000)
    berkas = tmp_path / "arsip" / "prediksi_harga-2026-10-01.jsonl"
    berkas.write_text("".join(berkas.read_text().splitlines(keepends=True)[:4]))  # hanya 4 titik
    assert (
        main(["mape", "--data", str(data), "--keluar", str(tmp_path), "--tanggal", MINGGU.isoformat()]) == 0
    )
    assert json.loads((tmp_path / "ringkasan_mape.json").read_text())["kalibrasi_ulang"] == []


def test_ringkasan_backtest_memuat_cakupan_out_of_sample(data, tmp_path):
    from titeny_models.backtest import jalankan_backtest

    r = jalankan_backtest(data, tmp_path, H, hari=40, tanggal_backtest=date(2026, 10, 21))
    for blok in (r["harga"]["kalibrasi"], r["demand"]["kalibrasi"]):
        assert set(blok) == {"n", "cakupan_pct", "status"}
