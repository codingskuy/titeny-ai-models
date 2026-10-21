from titeny_models import katalog


def test_cakupan_terkunci():
    assert len(katalog.KOMODITAS_HARGA) == 12
    assert len(katalog.PASAR) == 8
    assert len(katalog.KOMODITAS_PANEN) == 6
    assert len(katalog.KABUPATEN) == 5
    assert len(katalog.ZONA_RUTE) == 8
    assert katalog.HORIZON_HARGA == ("H+1", "H+2", "H+3", "H+4", "H+5", "H+6", "H+7")


def test_semua_id_unik_dan_sesuai_pola_openapi():
    import re

    assert len(set(katalog.KOMODITAS_HARGA)) == 12
    assert len(set(katalog.PASAR)) == 8
    assert all(re.fullmatch(r"cmd_[a-z_]+", c) for c in katalog.KOMODITAS_HARGA)
    assert all(re.fullmatch(r"psr_[a-z0-9_]+", p) for p in katalog.PASAR)
    assert all(re.fullmatch(r"kab_[a-z_]+", k) for k in katalog.KABUPATEN)
    assert set(katalog.KOMODITAS_PANEN) <= {"cmd_padi", "cmd_jagung"} | set(katalog.KOMODITAS_HARGA)
