# Model card: Panen 6 komoditas x 5 kabupaten, M+1..M+4 `panen_v1.0.0`

> PERINGATAN: metrik di kartu ini dihitung dari data SINTETIS (fixture deterministik), BUKAN data pasar nyata. Angka hanya membuktikan alur backtest berjalan; bukan klaim akurasi produksi. Ganti dengan backtest data nyata sebelum rilis.

| Item | Nilai |
|---|---|
| Versi model | `panen_v1.0.0` |
| Tanggal backtest | 2026-10-21 |
| Data terakhir dipakai | 2026-10-04 |
| Jendela backtest | 90 hari, walk-forward (hanya data sebelum hari asal) |
| Sumber data | SINTETIS |

## Metode

Panen mingguan = luas panen ekspektasi (catatan tanam mundur 90-120 hari padi/jagung, 60-75 hari sayur) x yield baseline (median 3 musim) x faktor cuaca (1,00 / 0,85 hujan > 300 mm atau banjir / 0,90 kekeringan) x faktor musim; bulat 50 kg. Kabupaten terkunci: Karawang, Subang, Garut, Brebes, Malang.

## Metrik evaluasi

Belum dievaluasi: tidak dibacktest: aktual panen mingguan belum tersedia sebagai masukan. Target: MAPE total musim <= 20%. Skor per musim dihitung job `mape` (Minggu 23.00 WIB) begitu data aktual panen nyata tersedia.

## Kalibrasi rentang P10-P90

Belum dihitung pada ringkasan ini (lihat TTN-AI-005).

## Batasan

Kepercayaan `rendah` + rekomendasi generik bila catatan panen < 10 baris per kabupaten/musim.
