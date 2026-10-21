# CHANGELOG — titeny-ai-models

Format: satu seksi per rilis, terbaru di atas. Wajib diperbarui pada setiap commit `feat:` / `fix:` / `docs:`.

## [Belum dirilis]

### Ditambahkan
- TTN-AI-002: model `harga_v1.0.0` (metode 5 langkah, 12 komoditas x 8 pasar, H+1..H+7), fallback FR-104, `katalog`, pemuat CSV, job `python -m titeny_models.jobs harga`, fixture sintetis, uji per langkah. Rentang/kepercayaan menunggu TTN-AI-005.
- TTN-AI-003: model `panen_v1.0.0` (6 komoditas x 5 kabupaten, M+1..M+4), `demand_v1.0.0` (12 komoditas x 16 zona, H+7/H+30), sinyal surplus/seimbang/defisit, rekomendasi maks 3 aksi per zona, job `panen` dan `demand`, fixture sintetis panen/demand. Rentang P10-P90 menunggu TTN-AI-005.
- TTN-AI-004: `evaluasi` (MAPE, bias over/under, target, gerbang naik versi), `backtest` walk-forward 90 hari (harga + demand, berjalan vs kandidat), job `mape` (skor mingguan + arsip + alarm), `kartu_model` + `model-card/` (data sintetis, ditandai), ADR-0002 (usulan).
- Fondasi AI-dev v1.0.0: `AGENTS.md`, `CLAUDE.md`, `docs/decisions/ADR-0001-fondasi-teknis.md`, `versions/v1.0.0/docs/40-TECHSTACK.md` dan `60-BLAST-RADIUS.md` (versi lengkap, menggantikan ringkasan awal).

### Diubah
- Stub `ramal_harga` (contoh awal) diganti `ramal_harga_pasangan`; `pyproject.toml` memuat dev-deps (pytest, ruff) dan `pythonpath=src`.
