import requests
import csv
import shutil
import os
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

def clean_isp(isp):
    """
    Membersihkan nama ISP dengan menghapus tanda baca dan karakter khusus.
    Contoh:
      "PT. Telkom, Indonesia" -> "PT Telkom Indonesia"
      "Google, LLC." -> "Google LLC"
    """
    if not isp:
        return "UNKNOWN"
    
    # Daftar karakter yang akan dihapus
    chars_to_remove = [',', '.', ';', ':', '!', '?', '@', '#', '$', '%', '&', '*', '(', ')']
    
    # Hapus karakter khusus dan multiple spaces
    cleaned = isp
    for char in chars_to_remove:
        cleaned = cleaned.replace(char, ' ')
    
    # Hapus spasi berlebih dan strip whitespace
    cleaned = ' '.join(cleaned.split()).strip()
    
    return cleaned

def check_proxy_single(proxy_data, api_url_template):
    """
    Mengecek satu proxy dan mengembalikan data yang diformat (ip, port, cc, isp).
    """
    try:
        ip = proxy_data["ip"]
        port = str(proxy_data["port"])
        api_url = api_url_template.format(ip=ip, port=port)
        
        start_time = time.time()
        response = requests.get(api_url, timeout=60)
        latency = int((time.time() - start_time) * 1000)  # Latency dalam ms
        scan_result = response.json()[0]

        if scan_result.get("proxyip", False):
            print(f"{ip}:{port} is ALIVE ({latency}ms)")
            # Ambil country (cc) dari input atau hasil scan
            cc = scan_result.get("countryCode", proxy_data.get("country", "UNKNOWN"))
            # Ambil isp dari org hasil scan dan bersihkan
            isp = clean_isp(scan_result.get("org", "UNKNOWN"))
            return (ip, port, cc, isp, None)
        else:
            print(f"{ip}:{port} is DEAD")
            return (None, None, None, None, f"{ip}:{port} is DEAD")
    except Exception as e:
        return (None, None, None, None, f"Error checking {ip}:{port}: {str(e)}")

def read_ndjson_file(file_path):
    """
    Membaca file NDJSON (Newline-Delimited JSON).
    """
    proxies = []
    with open(file_path, 'r') as f:
        for line in f:
            if line.strip():
                try:
                    proxies.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"Error parsing line: {line.strip()}. Error: {e}")
    return proxies

def sort_and_deduplicate(proxy_list):
    """
    Urutkan IP secara numerik dan hapus duplikat (IP + Port sama).
    """
    unique_proxies = {}
    for proxy in proxy_list:
        ip, port, cc, isp, error = proxy
        key = (ip, port)
        if key not in unique_proxies:
            unique_proxies[key] = (ip, port, cc, isp, error)

    sorted_proxies = sorted(
        unique_proxies.values(),
        key=lambda x: (
            [int(part) for part in x[0].split('.')],
            int(x[1])
        )
    )
    return sorted_proxies

def generate_grouped_json(proxy_data, output_file='alive_proxies_grouped.json'):
    """
    Kelompokkan proxy hidup berdasarkan CC dan ISP.
    """
    grouped = {}
    for ip, port, cc, isp, _ in proxy_data:
        if cc not in grouped:
            grouped[cc] = {}
        if isp not in grouped[cc]:
            grouped[cc][isp] = []
        grouped[cc][isp].append(f"{ip}:{port}")

    final_structure = {}
    for cc in sorted(grouped.keys()):
        final_structure[cc] = {}
        isps = sorted(grouped[cc].keys())
        for idx, isp in enumerate(isps):
            letter = chr(97 + idx)
            final_structure[cc][letter] = {
                "name": isp,
                "proxies": grouped[cc][isp]
            }

    with open(output_file, 'w') as f:
        json.dump(final_structure, f, indent=2)
    print(f"File JSON disimpan: {output_file}")

def main():
    input_file = os.getenv('IP_FILE', 'zzzzkavhjdzzzz')
    output_file = 'zzzzkavhjdzzzz.tmp'
    error_file = 'error.txt'
    api_url_template = os.getenv('API_URL', 'https://proxyip-check.vercel.app/{ip}:{port}')

    alive_proxies = []
    error_logs = []

    # Baca file input NDJSON
    try:
        proxies_data = read_ndjson_file(input_file)
        print(f"Memproses {len(proxies_data)} proxy dari file input.")
    except Exception as e:
        print(f"Gagal membaca {input_file}: {e}")
        return

    # Check proxy dengan ThreadPool
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(check_proxy_single, proxy, api_url_template) for proxy in proxies_data]
        
        for future in as_completed(futures):
            ip, port, cc, isp, error = future.result()
            if ip and port:
                alive_proxies.append((ip, port, cc, isp, None))
            if error:
                error_logs.append(error)

    # Hapus duplikat dan urutkan IP
    alive_proxies = sort_and_deduplicate(alive_proxies)

    # Simpan hasil ke CSV
    try:
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows([row[:4] for row in alive_proxies])
        print(f"File sementara disimpan: {output_file}")
    except Exception as e:
        print(f"Gagal menyimpan {output_file}: {e}")
        return

    # Ganti file input dengan output
    try:
        shutil.move(output_file, input_file)
        print(f"File {input_file} diperbarui.")
    except Exception as e:
        print(f"Gagal mengganti file: {e}")

    # Simpan error
    if error_logs:
        with open(error_file, 'w') as f:
            f.write("\n".join(error_logs))
        print(f"Error dicatat di {error_file}")

    # Buat file JSON
    generate_grouped_json(alive_proxies)

if __name__ == "__main__":
    main()
