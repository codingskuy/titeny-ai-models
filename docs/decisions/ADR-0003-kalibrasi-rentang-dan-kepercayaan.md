# ADR-0003 — Kalibrasi rentang P10-P90, label kepercayaan, dan kalibrasi ulang otomatis

- **Status**: Diusulkan (menunggu persetujuan manusia)
- **Tanggal**: 2026-10-21
- **Tiket**: TTN-AI-005 (#5)

## Konteks

BR-205/FR-103 mengunci: `rentang_bawah/atas` = P10/P90 residual 30 hari; kepercayaan `tinggi` (sampel >= 5 lapak dan MAPE_14h < 8%), `rendah` (sampel < 3 atau MAPE_14h > 15%), selain itu `sedang`; cakupan aktual 70-90%, di bawah 60% memicu kalibrasi ulang otomatis. TownHall tidak mendefinisikan residual (absolut/relatif), jendela "30 hari" untuk horizon panjang, perilaku pada sampel kecil, maupun bentuk "kalibrasi ulang".

## Keputusan (usulan)

1. **Residual relatif** = (aktual - prediksi) / prediksi; rentang = prediksi x (1 + P10) .. prediksi x (1 + P90); harga dibulatkan 500 IDR, panen 50 kg; rentang selalu memuat titik prediksi.
2. **"30 hari"** = 30 residual terbaru yang sudah dapat dievaluasi (target < hari hitung) per (komoditas, pasar/zona, horizon); kurang dari 10 titik -> tidak dikalibrasi (rentang = titik untuk harga, `null` untuk panen/demand; kepercayaan harga `rendah`).
3. **Sumber residual**: replay walk-forward model pada hari lampau (`hindcast`), tanpa kebocoran masa depan. Kalibrasi disimpan di `artefak/<model_version>/residual_p90.json`, dipakai ulang < 7 hari; MAPE_14h dihitung harian (H+1, 14 titik terbaru).
4. **Kepercayaan** mengikuti BR-205 persis; tanpa MAPE_14h tidak pernah `tinggi`; panen memakai aturan catatan < 10 baris (belum ada aktual mingguan untuk MAPE).
5. **Cakupan**: dilaporkan mingguan (job `mape`) dari rentang yang diarsipkan vs aktual; status `ok` (70-90), `di_bawah_target` (60-70), `kalibrasi_ulang` (< 60), `terlalu_lebar` (> 90).
6. **Kalibrasi ulang otomatis**: bila cakupan pasangan harga < 60% (minimal 5 titik) pada skor mingguan, job `mape` menghitung ulang kalibrasi pasangan itu sampai hari skor dan menimpa artefak. Demand: cakupan dilaporkan, kalibrasi ulang otomatis belum diterapkan (di luar lingkup tiket).

## Konsekuensi

- Pada backtest data sintetis, cakupan out-of-sample di bawah target (harga ~65%, demand ~56%): kuantil dari 30 residual yang berautokorelasi (terutama demand dengan jendela tumpang tindih) cenderung terlalu sempit. Perbaikan (jendela lebih panjang, penyesuaian sampel kecil) memerlukan keputusan manusia dan ADR baru; tidak dilakukan diam-diam.
- Artefak `residual_p90.json` bertambah ke direktori keluaran; retensi ditentukan infra.
