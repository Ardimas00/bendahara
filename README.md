# Aplikasi Manajemen Keuangan Bendahara

Sebuah aplikasi web sederhana yang dibangun dengan Python, Flask, dan TinyDB untuk membantu bendahara mengelola dan melacak keuangan acara.

## Fitur Utama

- **Dashboard Keuangan:** Ringkasan total pemasukan, pengeluaran, dan saldo akhir secara real-time.
- **Manajemen Transaksi (CRUD):** Tambah, lihat, edit, dan hapus data transaksi dengan mudah.
- **Kategorisasi:** Kelompokkan setiap transaksi ke dalam kategori yang relevan (misal: Iuran Warga, Konsumsi, Sponsor).
- **Penyesuaian Transaksi (Ledger-Style):** Lakukan penambahan atau pengurangan pada transaksi yang sudah ada tanpa mengubah data aslinya, menciptakan jejak audit yang transparan.

## Teknologi yang Digunakan

- **Backend:** Python 3, Flask
- **Database:** TinyDB (disimpan di file JSON lokal)
- **Frontend:** HTML, Tailwind CSS
- **Environment:** `python-dotenv` untuk manajemen variabel lingkungan.
- **Keamanan:** CSRF protection (Flask-WTF), kode viewer opsional.

---

## Panduan Setup dan Instalasi

### Prasyarat

- Python 3.8 atau lebih baru.
- Node.js dan npm (untuk build Tailwind CSS).

### Langkah-langkah Instalasi

1.  **Clone Repositori (jika sudah di-hosting)**
    ```bash
    git clone <url-repositori-anda>
    cd nama-folder-proyek
    ```

2.  **Buat dan Aktifkan Virtual Environment**
    ```bash
    # Windows
    python -m venv venv
    .\venv\Scripts\activate

    # macOS / Linux
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependensi Python**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Install Dependensi Node.js**
    ```bash
    npm install
    ```

5.  **Konfigurasi Variabel Lingkungan**
    - Salin file `.env.example` menjadi `.env`:
      ```bash
      cp .env.example .env
      ```
    - Edit `.env` dan ganti `SECRET_KEY` dengan string acak yang panjang dan aman.
    - `TINYDB_PATH` menentukan lokasi file database (default: `data.json`).
    - `ADMIN_USERNAME` / `ADMIN_PASSWORD` digunakan saat membuat akun admin pertama kali.
    - `VIEWER_PASSWORD` (opsional): jika diisi, viewer wajib memasukkan kode.
    - `FLASK_DEBUG=false` untuk production; `ENABLE_ADMIN_TOOLS=true` hanya jika perlu tool migrasi.

---

## Menjalankan Aplikasi

Aplikasi ini memerlukan dua proses terminal yang berjalan secara bersamaan: satu untuk server Flask dan satu lagi untuk mem-build Tailwind CSS.

1.  **Terminal 1: Build Tailwind CSS**
    - Jalankan perintah berikut untuk memantau perubahan pada file `input.css` dan secara otomatis menghasilkan `output.css`.
    ```bash
    npm run build:css
    ```

2.  **Terminal 2: Jalankan Server Flask**
    - Pastikan virtual environment Anda sudah aktif.
    - Jalankan aplikasi dengan perintah:
    ```bash
    python run.py
    ```

3.  **Buka Aplikasi**
    - Buka browser Anda dan kunjungi alamat `http://127.0.0.1:5000`.
