import requests
import csv
import shutil
import os
import json
import time  # Untuk mengukur latency
from concurrent.futures import ThreadPoolExecutor, as_completed

def check_proxy_single(ip, port, api_url_template):
    """
    Mengecek satu proxy dan mengembalikan status + latency (jika diperlukan).
    """
    try:
        start_time = time.time()
        api_url = api_url_template.format(ip=ip, port=port)
        response = requests.get(api_url, timeout=60)
        latency = int((time.time() - start_time) * 1000)  # Latency dalam ms
        data = response.json()
        status = data[0].get("proxyip", False)
        
        if status:
            print(f"{ip}:{port} is ALIVE ({latency}ms)")
            return (ip, port, latency, None)
        else:
            print(f"{ip}:{port} is DEAD")
            return (None, None, None, f"{ip}:{port} is DEAD")
    except Exception as e:
        return (None, None, None, f"Error: {str(e)}")

def clean_row(row):
    """
    Membersihkan baris CSV: menghapus koma terakhir dan latency jika ada.
    Contoh:
      Input: "1.1.1.1,8080,US,Verizon,100ms" 
      Output: ["1.1.1.1", "8080", "US", "Verizon"]
    """
    # Hilangkan elemen kosong dan strip whitespace
    cleaned = [col.strip() for col in row if col.strip()]
    
    # Jika ada lebih dari 4 kolom (ada latency), ambil hanya 4 kolom pertama
    if len(cleaned) > 4:
        cleaned = cleaned[:4]
    return cleaned

def generate_grouped_json(proxy_data, output_file='alive_proxies_grouped.json'):
    """
    Kelompokkan proxy hidup berdasarkan CC dan ISP (tanpa latency).
    """
    grouped = {}
    for row in proxy_data:
        ip, port, cc, isp = row[:4]  # Pastikan hanya ambil 4 kolom
        if cc not in grouped:
            grouped[cc] = {}
        if isp not in grouped[cc]:
            grouped[cc][isp] = []
        grouped[cc][isp].append(f"{ip}:{port}")

    # Beri label a-z untuk setiap ISP dalam CC
    final_structure = {}
    for cc in sorted(grouped.keys()):
        final_structure[cc] = {}
        isps = sorted(grouped[cc].keys())
        for idx, isp in enumerate(isps):
            letter = chr(97 + idx)  # a, b, c...
            final_structure[cc][letter] = {
                "name": isp,
                "proxies": grouped[cc][isp]
            }

    # Simpan ke JSON
    with open(output_file, 'w') as f:
        json.dump(final_structure, f, indent=2)
    print(f"File JSON disimpan: {output_file}")

def main():
    input_file = os.getenv('IP_FILE', 'zzzzkavhjdzzzz')
    output_file = 'zzzzkavhjdzzzz.tmp'
    error_file = 'error.txt'
    api_url_template = os.getenv('API_URL', 'https://proxyip-check.vercel.app/{ip}:{port}')

    alive_proxies = []  # Format: [[ip, port, cc, isp], ...]
    error_logs = []

    # Baca file input dan bersihkan setiap baris
    try:
        with open(input_file, "r") as f:
            reader = csv.reader(f)
            rows = [clean_row(row) for row in reader if row]
        print(f"Memproses {len(rows)} baris (setelah dibersihkan).")
    except FileNotFoundError:
        print(f"File {input_file} tidak ditemukan.")
        return

    # Check proxy dengan ThreadPool
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for row in rows:
            if len(row) >= 2:  # Minimal ip,port
                ip, port = row[0], row[1]
                futures.append(executor.submit(check_proxy_single, ip, port, api_url_template))

        for future in as_completed(futures):
            ip, port, _, error = future.result()  # Abaikan latency (kolom ke-3)
            if ip and port:
                # Cari row asli (tanpa latency) yang sesuai
                for row in rows:
                    if row[0] == ip and row[1] == port:
                        alive_proxies.append(row[:4])  # Simpan hanya ip,port,cc,isp
                        break
            if error:
                error_logs.append(error)

    # Simpan hasil ke file CSV (tanpa latency)
    try:
        with open(output_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(alive_proxies)
        print(f"File sementara disimpan: {output_file}")
    except Exception as e:
        print(f"Gagal menyimpan {output_file}: {e}")
        return

    # Ganti file input dengan output
    try:
        shutil.move(output_file, input_file)
        print(f"File {input_file} telah diperbarui (tanpa latency).")
    except Exception as e:
        print(f"Gagal mengganti file: {e}")

    # Buat file JSON
    generate_grouped_json(alive_proxies)

if __name__ == "__main__":
    main()
