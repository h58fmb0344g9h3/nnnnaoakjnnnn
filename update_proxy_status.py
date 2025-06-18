import requests
import csv
import shutil
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import ipaddress  # Untuk mengurutkan IP

def bersihkan_isp(isp):
    """Membersihkan teks ISP: 
    - Hapus titik dan koma
    - Ganti underscore dengan spasi
    - Biarkan dash (-) tetap"""
    isp = isp.replace('.', '').replace(',', '')  # Hapus titik dan koma
    isp = isp.replace('_', ' ')  # Ganti underscore dengan spasi
    return isp.strip()

def ip_sort_key(ip_str):
    """Fungsi untuk mengurutkan alamat IP secara numerik (IPv4 saja)"""
    try:
        ip = ipaddress.IPv4Address(ip_str)  # Hanya IPv4
        return ip
    except ipaddress.AddressValueError:
        return ip_str  # Jika bukan IPv4, urutkan sebagai string

def is_valid_ipv4(ip_str):
    """Cek apakah string adalah IPv4 valid"""
    try:
        ipaddress.IPv4Address(ip_str)
        return True
    except ipaddress.AddressValueError:
        return False

def check_proxy_single(ip, port, api_url_template):
    """Mengecek satu proxy menggunakan API."""
    try:
        # Format URL API untuk satu proxy
        api_url = api_url_template.format(ip=ip, port=port)
        response = requests.get(api_url, timeout=60)
        response.raise_for_status()
        data = response.json()

        # Ambil status proxyip
        status = data[0].get("proxyip", False)
        if status:
            print(f"{ip}:{port} is ALIVE")
            return (ip, port, None)  # Format: (ip, port, None)
        else:
            print(f"{ip}:{port} is DEAD")
            return (None, None, f"{ip}:{port} is DEAD")  # Format: (None, None, error_message)
    except requests.exceptions.RequestException as e:
        error_message = f"Error checking {ip}:{port}: {e}"
        print(error_message)
        return (None, None, error_message)
    except ValueError as ve:
        error_message = f"Error parsing JSON for {ip}:{port}: {ve}"
        print(error_message)
        return (None, None, error_message)


def generate_grouped_json(proxy_data, output_file='alive_proxies_grouped.json'):
    """
    Mengelompokkan proxy hidup berdasarkan CC dan ISP,
    lalu memberikan singkatan alfabet a-z untuk setiap ISP dalam tiap CC.
    """
    grouped = {}

    # Kelompokkan berdasarkan cc dan isp
    for row in proxy_data:
        ip, port, cc, isp = row
        # Bersihkan ISP untuk JSON juga
        isp_clean = bersihkan_isp(isp)
        if cc not in grouped:
            grouped[cc] = {}
        if isp_clean not in grouped[cc]:
            grouped[cc][isp_clean] = []
        grouped[cc][isp_clean].append(f"{ip}:{port}")

    # Beri abjad a-z per grup isp dalam tiap cc
    final_structure = {}
    for cc in sorted(grouped.keys()):  # Urutkan berdasarkan countryCode
        final_structure[cc] = {}
        isps = sorted(grouped[cc].keys())  # urutkan ISP
        for idx, isp in enumerate(isps):
            letter = chr(97 + idx)  # a, b, c...
            final_structure[cc][letter] = {
                "name": isp,
                "proxies": grouped[cc][isp]
            }

    # Simpan ke file JSON
    try:
        with open(output_file, 'w') as f:
            json.dump(final_structure, f, indent=2)
        print(f"File JSON berhasil dibuat: {output_file}")
    except Exception as e:
        print(f"Error saat menyimpan file JSON: {e}")


def main():
    input_file = os.getenv('IP_FILE', 'zzzzkavhjdzzzz')
    output_file = 'zzzzkavhjdzzzz.tmp'
    error_file = 'error.txt'
    api_url_template = os.getenv('API_URL', 'https://proxyip-check.vercel.app/{ip}:{port}')

    alive_proxies = []  # Menyimpan proxy yang aktif dengan format [ip, port, cc, isp]
    error_logs = []  # Menyimpan pesan error
    seen_proxies = set()  # Untuk deteksi duplikat (ip, port)

    try:
        # Gunakan encoding 'latin-1' untuk file CSV
        with open(input_file, "r", encoding='latin-1') as f:
            reader = csv.reader(f)
            rows = []
            for row in reader:
                # Hanya proses baris dengan 4 kolom dan IP valid
                if len(row) >= 4 and is_valid_ipv4(row[0].strip()):
                    # Bersihkan kolom ISP: hapus titik/koma, ganti _ dengan spasi
                    row[3] = bersihkan_isp(row[3])
                    rows.append(row)
                elif len(row) >= 4:
                    print(f"Baris diabaikan (IP tidak valid): {row[0]}:{row[1]}")
        print(f"Memproses {len(rows)} baris valid dari file input.")
    except FileNotFoundError:
        print(f"File {input_file} tidak ditemukan.")
        return
    except Exception as e:
        print(f"Error membaca file: {e}")
        return

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for row in rows:
            if len(row) >= 4:
                ip, port = row[0].strip(), row[1].strip()
                
                # Cek duplikat IP:PORT
                proxy_id = f"{ip}:{port}"
                if proxy_id in seen_proxies:
                    print(f"Duplikat ditemukan dan dilewati: {ip}:{port}")
                    continue
                    
                seen_proxies.add(proxy_id)
                futures.append(executor.submit(check_proxy_single, ip, port, api_url_template))

        for future in as_completed(futures):
            ip, port, error = future.result()
            if ip and port:
                # Cari baris yang sesuai dari file input
                for row in rows:
                    if row[0].strip() == ip and row[1].strip() == port:
                        alive_proxies.append(row)  # Simpan seluruh baris (ip, port, cc, isp)
                        break
            if error:
                error_logs.append(error)

    # Urutkan berdasarkan IP (IPv4 saja)
    alive_proxies.sort(key=lambda row: ip_sort_key(row[0].strip()))

    # Tulis proxy yang aktif ke file output sementara
    try:
        # Gunakan encoding yang sama untuk output
        with open(output_file, "w", newline="", encoding='latin-1') as f:
            writer = csv.writer(f)
            writer.writerows(alive_proxies)
        print(f"File output {output_file} telah diperbarui.")
    except Exception as e:
        print(f"Error menulis ke {output_file}: {e}")
        return

    # Tulis error ke file error.txt
    if error_logs:
        try:
            with open(error_file, "w", encoding='utf-8') as f:
                for error in error_logs:
                    f.write(error + "\n")
            print(f"Beberapa error telah dicatat di {error_file}.")
        except Exception as e:
            print(f"Error menulis ke {error_file}: {e}")
            return

    # Ganti file input dengan file output
    try:
        shutil.move(output_file, input_file)
        print(f"{input_file} telah diperbarui dengan proxy yang ALIVE.")
    except Exception as e:
        print(f"Error menggantikan {input_file}: {e}")

    # Buat file JSON berdasarkan kelompok cc+isp
    generate_grouped_json(alive_proxies)


if __name__ == "__main__":
    main()
