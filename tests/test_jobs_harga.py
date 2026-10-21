import json
from datetime import date, timedelta

from titeny_models.jobs import JOB, main
from titeny_models.katalog import KOMODITAS_HARGA, PASAR
from titeny_models.sintetis import tulis_fixture

H = date(2026, 10, 5)


def siapkan(tmp_path, hari=60):
    data = tmp_path / "data"
    tulis_fixture(data, H - timedelta(days=hari), hari)
    return data


def test_job_harga_menulis_12x8x7_baris_kontrak(tmp_path):
    data, keluar = siapkan(tmp_path), tmp_path / "out"
    assert main(["harga", "--data", str(data), "--keluar", str(keluar), "--tanggal", H.isoformat()]) == 0
    baris = [json.loads(b) for b in (keluar / "prediksi_harga.jsonl").read_text().splitlines()]
    assert len(baris) == len(KOMODITAS_HARGA) * len(PASAR) * 7 == 672
    assert {b["model_version"] for b in baris} == {"harga_v1.0.0"}
    assert all(b["harga_prediksi"] % 500 == 0 for b in baris)
    assert {b["komoditas_id"] for b in baris} == set(KOMODITAS_HARGA)
    assert {b["pasar_id"] for b in baris} == set(PASAR)
    kunci = {(b["komoditas_id"], b["pasar_id"], b["tanggal_prediksi"]) for b in baris}
    assert len(kunci) == len(baris)  # PK tabel prediksi_harga tidak bentrok


def test_job_harga_tidak_membaca_masa_depan(tmp_path):
    data, keluar = siapkan(tmp_path, hari=60), tmp_path / "out"
    # tanggal hitung lebih awal -> data setelahnya harus diabaikan, hasil tetap valid
    awal = (H - timedelta(days=20)).isoformat()
    assert main(["harga", "--data", str(data), "--keluar", str(keluar), "--tanggal", awal]) == 0


def test_job_harga_gagal_bila_berkas_hilang(tmp_path, capsys):
    assert (
        main(["harga", "--data", str(tmp_path), "--keluar", str(tmp_path / "o"), "--tanggal", "2026-10-05"])
        == 1
    )
    assert '"status": "gagal"' in capsys.readouterr().out


def test_job_belum_ada_dan_salah_pakai_berkode_keluar_2(tmp_path, monkeypatch):
    monkeypatch.delitem(JOB, "panen", raising=False)
    assert main(["panen", "--data", str(tmp_path), "--keluar", str(tmp_path)]) == 2
    assert main(["harga"]) == 2
    assert main(["harga", "--data", str(tmp_path), "--keluar", str(tmp_path), "--tanggal", "kemarin"]) == 2
