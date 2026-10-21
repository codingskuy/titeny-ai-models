# Model card: Harga 12 komoditas x 8 pasar, H+1..H+7 `harga_v1.0.0`

> PERINGATAN: metrik di kartu ini dihitung dari data SINTETIS (fixture deterministik), BUKAN data pasar nyata. Angka hanya membuktikan alur backtest berjalan; bukan klaim akurasi produksi. Ganti dengan backtest data nyata sebelum rilis.

| Item | Nilai |
|---|---|
| Versi model | `harga_v1.0.0` |
| Tanggal backtest | 2026-10-21 |
| Data terakhir dipakai | 2026-10-04 |
| Jendela backtest | 90 hari, walk-forward (hanya data sebelum hari asal) |
| Sumber data | SINTETIS |

## Metode

Tanpa deep learning, 5 langkah per (komoditas, pasar): baseline median 14 hari pada `jenis_hari` sama; koreksi tren regresi linier 21 hari (+-8%/hari); koreksi stok +-4%; koreksi logistik 80%; potong 0,70-1,60x median 30 hari lalu bulatkan ke 500 IDR. Fallback: median 7 hari (data kemarin) bila S1 kosong 1-2 hari; pasangan dihentikan bila >= 3 hari.

## Metrik evaluasi (backtest)

| Metrik | Nilai | Target | Status |
|---|---|---|---|
| MAPE H+1, median 12 komoditas | 2.60% | <= 8% | lulus |
| MAPE H+1, komoditas terburuk | 5.09% | <= 15% | lulus |
| MAPE H+7, rata-rata makro | 3.68% | <= 12% | lulus |

Jumlah titik evaluasi: 57792.

### Bias H+7 (over/under dilaporkan terpisah)

- Bias rata-rata: 0.35%; porsi overpredict: 50.43%
- Rata-rata over: 3.99%; rata-rata under: -3.64%
- Overpredict > 5% dua minggu berturut-turut memicu tinjauan analis.

### MAPE per komoditas

| Komoditas | H+1 | H+7 |
|---|---|---|
| `cmd_bawang_merah` | 3.43% | 4.08% |
| `cmd_bawang_putih` | 2.15% | 2.49% |
| `cmd_beras_medium` | 2.54% | 2.95% |
| `cmd_cabai_merah` | 3.94% | 4.68% |
| `cmd_cabai_rawit` | 4.63% | 5.36% |
| `cmd_daging_ayam` | 2.16% | 2.59% |
| `cmd_daging_sapi` | 2.16% | 2.59% |
| `cmd_gula_pasir` | 2.65% | 3.06% |
| `cmd_kangkung` | 5.09% | 5.29% |
| `cmd_minyak_goreng_curah` | 2.47% | 2.88% |
| `cmd_telur_ayam` | 2.35% | 2.83% |
| `cmd_tomat` | 4.58% | 5.32% |

## Kalibrasi rentang P10-P90

Belum dihitung pada ringkasan ini (lihat TTN-AI-005).

## Batasan

Di atas H+7 dipotong; tanpa teks bebas/sentimen; naik versi hanya bila backtest 90 hari menunjukkan MAPE H+7 turun >= 0,5 poin dan tidak ada komoditas memburuk > 2 poin (BR-206).
