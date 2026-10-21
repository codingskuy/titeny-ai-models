"""Penyimpanan kalibrasi per versi: `artefak/<model_version>/residual_p90.json` (artefak wajib TECHSTACK).

Format: {"model_version": ..., "pasangan": {"<komoditas>|<unit>": {"dihitung": "YYYY-MM-DD", "horizon": {"H+1": {p10,p90,n}}}}}.
Kalibrasi dipakai ulang selama umurnya < `UMUR_MAKS_HARI`; kedaluwarsa atau dipaksa (cakupan < 60%) -> dihitung ulang.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path

from .hindcast import muat_kalibrasi, simpan_kalibrasi
from .kalibrasi import Kalibrasi

UMUR_MAKS_HARI = 7


def baca_artefak(path: Path, model_version: str) -> dict:
    if path.exists():
        data = json.loads(path.read_text())
        if data.get("model_version") == model_version:
            return data
    return {"model_version": model_version, "pasangan": {}}


def tulis_artefak(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sementara = path.with_suffix(".json.tmp")
    sementara.write_text(json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True))
    sementara.replace(path)


def ambil_atau_hitung(
    artefak: dict,
    kunci: str,
    hari_ini: date,
    hitung: Callable[[], dict[str, Kalibrasi]],
    paksa: bool = False,
) -> tuple[dict[str, Kalibrasi], bool]:
    """(kalibrasi per horizon, apakah dihitung baru). Hasil dicatat ke `artefak` (di memori)."""
    entri = artefak["pasangan"].get(kunci)
    if entri and not paksa:
        umur = (hari_ini - date.fromisoformat(entri["dihitung"])).days
        if 0 <= umur < UMUR_MAKS_HARI:
            return muat_kalibrasi(entri["horizon"]), False
    kal = hitung()
    artefak["pasangan"][kunci] = {"dihitung": hari_ini.isoformat(), "horizon": simpan_kalibrasi(kal)}
    return kal, True
