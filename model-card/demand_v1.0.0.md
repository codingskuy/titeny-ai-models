# Model card: Demand 12 komoditas x 16 zona, H+7/H+30 `demand_v1.0.0`

> PERINGATAN: metrik di kartu ini dihitung dari data SINTETIS (fixture deterministik), BUKAN data pasar nyata. Angka hanya membuktikan alur backtest berjalan; bukan klaim akurasi produksi. Ganti dengan backtest data nyata sebelum rilis.

| Item | Nilai |
|---|---|
| Versi model | `demand_v1.0.0` |
| Tanggal backtest | 2026-10-21 |
| Data terakhir dipakai | 2026-10-04 |
| Jendela backtest | 90 hari, walk-forward (hanya data sebelum hari asal) |
| Sumber data | SINTETIS |

## Metode

Baseline rata-rata 28 hari x faktor hari besar (puasa 1,18; lebaran 1,35/1,10; natal-tahun baru 1,12) x elastisitas harga (-4% pokok / -7% sayur per +10%), batas +-30% vs baseline. Sinyal surplus (>= 120%) / defisit (<= 80%) terhadap panen kabupaten terdekat.

## Metrik evaluasi (backtest)

| Metrik | Nilai | Batas | Status |
|---|---|---|---|
| MAPE H+7, rata-rata makro | 2.72% | <= 15% | lulus |
| MAPE H+30, rata-rata makro | 1.67% | <= 22% (hanya pantau) | lulus (pantau) |

Jumlah titik evaluasi: 27456. Backtest memakai `rasio_harga = 1,0` (elastisitas tidak diuji).

- Bias H+7: rata-rata 0.15%; over 2.84%; under -2.59%
- Bias H+30: rata-rata 0.16%; over 1.76%; under -1.58%

## Kalibrasi rentang P10-P90

Belum dihitung pada ringkasan ini (lihat TTN-AI-005).

## Batasan

Rekomendasi bersifat anjuran, tidak membuat pesanan otomatis; H+30 hanya dipantau (<= 22%).
