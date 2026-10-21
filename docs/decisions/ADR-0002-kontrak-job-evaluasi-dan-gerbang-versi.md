# ADR-0002 — Kontrak job (CSV masuk, JSON-lines keluar), definisi evaluasi, dan gerbang versi

- **Status**: Diusulkan (menunggu persetujuan manusia)
- **Tanggal**: 2026-10-21
- **Tiket**: TTN-AI-002..005 (#2..#5)

## Konteks

TownHall v1.0.0 mengunci metode dan ambang model, tetapi belum mengunci (a) bentuk masukan agregat dari `titeny-data-pipeline`, (b) jalur tulis prediksi ke DB `titeny`, dan (c) definisi rinci metrik (rata-rata antar komoditas, bias, cakupan). `titeny-infra-devops` (ADR-0002 di repo itu) mengasumsikan perintah `python -m titeny_models.jobs <harga|demand|panen|mape>` dengan kode keluar non-nol = gagal.

## Keputusan (usulan)

1. **Perintah job**: `python -m titeny_models.jobs <harga|demand|panen|mape> --data DIR --keluar DIR [--tanggal YYYY-MM-DD]` (env `TITENY_DATA_DIR`, `TITENY_OUT_DIR`, `TITENY_TANGGAL`); kode keluar 0 sukses, 1 gagal data, 2 salah pakai; log JSON-lines ke stdout.
2. **Masukan**: CSV agregat (skema di `sintetis.py` dan `sintetis_agro.py`) yang hanya memuat data sebelum tanggal hitung; tanpa koneksi ke DB sumber atau DB `titeny` dari modul model.
3. **Keluaran**: JSON-lines berbentuk kolom tabel `prediksi_harga`, `prediksi_panen`, `prediksi_demand`, `rekomendasi` (backend `migrations/004_insight.sql`); pemuatan ke DB `titeny` dilakukan pipeline/backend (di luar repo ini). Label non-kontrak (mis. `estimasi`) di berkas terpisah.
4. **Definisi evaluasi**: MAPE = rata-rata |a-p|/a (a > 0); MAPE per komoditas = rata-rata makro antar pasangan; "MAPE H+7 turun >= 0,5 poin" memakai rata-rata makro antar komoditas; bias over/under dilaporkan terpisah; tinjauan analis bila bias > +5% dua minggu berturut-turut; pager analis bila MAPE H+7 > 15% dua minggu berturut-turut.
5. **Gerbang versi**: kandidat naik versi hanya bila hasil backtest walk-forward 90 hari memenuhi syarat BR-206; keputusan dicatat di `ringkasan_backtest.json`; perubahan metode = versi baru + ADR.
6. **Arsip**: tiap job menulis `arsip/prediksi_<jenis>-YYYY-MM-DD.jsonl` (idempoten per hari) sebagai bahan job `mape`.

## Konsekuensi

- Pipeline/backend harus menyesuaikan skema CSV atau membuat adaptor; perubahan skema = bump versi + ADR baru.
- Model card dibangkitkan dari hasil jalan nyata; kartu yang dikomit saat ini berasal dari data SINTETIS dan wajib diganti backtest data nyata sebelum rilis.
