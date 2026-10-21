"""Prediksi panen (klasifikasi sederhana, contoh awal)."""

import argparse


def ramal_panen(komoditas: str, hari: int = 30) -> dict:
    siap = {"padi": 12, "jagung": 20, "cabai": 25}.get(komoditas, 15)
    return {"komoditas": komoditas, "siap_dalam_hari": siap, "jendela_hari": hari}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--komoditas", default="padi")
    p.add_argument("--hari", type=int, default=30)
    a = p.parse_args()
    print(ramal_panen(a.komoditas, a.hari))
