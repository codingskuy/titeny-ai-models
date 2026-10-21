# titeny-ai-models

Model AI **inti** divisi **Titeny (AI Insight)**, org **Coding-Skuy**. Berisi model **prediksi harga** dan **prediksi panen**.

Ekosistem: [Titeny-TownHall](https://github.com/Coding-Skuy/Titeny-TownHall).

## Prasyarat (versi dipin)

- Python 3.12.7
- scikit-learn 1.5.2
- pandas 2.2.3
- numpy 2.1.3
- onnx 1.20.0, onnxruntime 1.20.0

## Cara pakai

```sh
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                      # uji (harus hijau)
ruff check . && ruff format --check .

# Data SINTETIS (bukan data nyata) -> job harga -> JSON-lines kolom tabel prediksi_harga
python -m titeny_models.sintetis --keluar /tmp/titeny-data --akhir 2026-10-05 --hari 60
python -m titeny_models.jobs harga --data /tmp/titeny-data --keluar /tmp/titeny-out --tanggal 2026-10-05
python -m titeny_models.jobs panen --data /tmp/titeny-data --keluar /tmp/titeny-out --tanggal 2026-10-05
python -m titeny_models.jobs demand --data /tmp/titeny-data --keluar /tmp/titeny-out --tanggal 2026-10-05
```

Evaluasi (data SINTETIS di sini; ganti data nyata di produksi):

```sh
python -m titeny_models.sintetis --keluar /tmp/d200 --akhir 2026-10-05 --hari 200
python -m titeny_models.backtest --data /tmp/d200 --keluar /tmp/bt --akhir 2026-10-05            # backtest 90 hari
python -m titeny_models.kartu_model --ringkasan /tmp/bt/ringkasan_backtest.json --keluar model-card
python -m titeny_models.jobs mape --data /tmp/d --keluar /tmp/o --tanggal 2026-10-04              # skor mingguan (Minggu)
```

Urutan: `harga` (04.00) dan `panen` (Senin 03.00) sebelum `demand` (04.30); `demand` membaca
`prediksi_harga.jsonl` (wajib) dan `prediksi_panen.jsonl` (opsional; tanpa itu sinyal `seimbang`) dari `--keluar`.

Job terjadwal (`titeny-infra-devops`) memanggil `python -m titeny_models.jobs <harga|demand|panen|mape>`;
kode keluar 0 = sukses, 1 = gagal, 2 = salah pakai. Env: `TITENY_DATA_DIR`, `TITENY_OUT_DIR`, `TITENY_TANGGAL`.

## Struktur

```text
src/titeny_models/katalog.py   # 12 komoditas, 8 pasar, 6x5 panen, 8 zona, versi model
src/titeny_models/harga.py     # harga_v1.0.0: metode 5 langkah + fallback FR-104
src/titeny_models/panen.py     # panen_v1.0.0: luas x yield x cuaca x musim, 6x5, M+1..M+4
src/titeny_models/demand.py    # demand_v1.0.0: baseline 28h x hari besar x elastisitas, H+7/H+30
src/titeny_models/sinyal.py    # surplus/seimbang/defisit + rekomendasi maks 3 aksi per zona
src/titeny_models/evaluasi.py  # MAPE, bias, target, gerbang naik versi
src/titeny_models/backtest.py  # backtest walk-forward 90 hari (berjalan vs kandidat)
src/titeny_models/kalibrasi.py   # P10-P90, kepercayaan, cakupan, pemicu kalibrasi ulang
src/titeny_models/hindcast.py    # residual walk-forward -> kalibrasi per pasangan
src/titeny_models/kalibrasi_store.py  # artefak residual_p90.json per versi
src/titeny_models/skor_mingguan.py  # skor MAPE mingguan dari arsip prediksi + alarm
src/titeny_models/kartu_model.py    # pembangkit model card
model-card/                    # kartu harga/panen/demand (dari data SINTETIS, ditandai)
src/titeny_models/muat*.py     # pemuat CSV agregat (tanpa koneksi DB)
src/titeny_models/jobs.py      # titik masuk job terjadwal
src/titeny_models/sintetis.py  # fixture SINTETIS deterministik
tests/                         # uji merah-hijau per langkah
```

Keluaran model dikonsumsi oleh `titeny-backend-service` pada titik `/insight/harga` dan oleh dasbor `titeny-web`.
