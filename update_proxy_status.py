import requests
import csv
import shutil
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

def check_proxy_batch(ip_port_list, api_url_template):
    """
    Mengecek batch proxy (50 IP:Port sekaligus) menggunakan API.
    """
    try:
        # Format IP:Port untuk batch request
        ip_port_str = ",".join(ip_port_list)
        api_url = api_url_template.format(ip_port_str)

        # Kirim request ke API
        response = requests.get(api_url, timeout=60)
        response.raise_for_status()
        data = response.json()

        # Proses hasil
        results = []
        for item in data:
            ip_port = item.get("ip", "")  # Ambil IP:Port dari respons
            status = item.get("proxyip", False)  # Ambil status proxyip
            if status:
                print(f"{ip_port} is ALIVE")
                results.append((ip_port, None))  # Format: (ip:port, None)
            else:
                print(f"{ip_port} is DEAD")
                results.append((None, f"{ip_port} is DEAD"))  # Format: (None, error_message)

        return results
    except requests.exceptions.RequestException as e:
        error_message = f"Error checking batch: {e}"
        print(error_message)
        return [(None, error_message) for _ in ip_port_list]
    except ValueError as ve:
        error_message = f"Error parsing JSON for batch: {ve}"
        print(error_message)
        return [(None, error_message) for _ in ip_port_list]

def main():
    input_file = os.getenv('IP_FILE', 'f74bjd2h2ko99f3j5')
    output_file = 'f74bjd2h2ko99f3j5'
    error_file = 'error.txt'
    api_url_template = os.getenv('API_URL', 'https://proxyip-check.vercel.app/{ip_port_list}')

    alive_proxies = []  # Menyimpan proxy yang aktif dengan format [ip, port, cc, isp]
    error_logs = []  # Menyimpan pesan error

    try:
        with open(input_file, "r") as f:
            reader = csv.reader(f)
            rows = list(reader)
    except FileNotFoundError:
        print(f"File {input_file} tidak ditemukan.")
        return

    # Format IP:Port untuk batch request
    ip_port_list = [f"{row[0].strip()}:{row[1].strip()}" for row in rows if len(row) >= 2]

    # Bagi menjadi batch 50 IP:Port per request
    batch_size = 50
    batches = [ip_port_list[i:i + batch_size] for i in range(0, len(ip_port_list), batch_size]

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(check_proxy_batch, batch, api_url_template): batch for batch in batches}

        for future in as_completed(futures):
            results = future.result()
            for result in results:
                ip_port, error = result
                if ip_port:
                    # Cari baris yang sesuai dari file input
                    for row in rows:
                        if f"{row[0].strip()}:{row[1].strip()}" == ip_port:
                            alive_proxies.append(row)  # Simpan seluruh baris (ip, port, cc, isp)
                            break
                if error:
                    error_logs.append(error)

    # Tulis proxy yang aktif ke file output
    try:
        with open(output_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(alive_proxies)
    except Exception as e:
        print(f"Error menulis ke {output_file}: {e}")
        return

    # Tulis error ke file error.txt
    if error_logs:
        try:
            with open(error_file, "w") as f:
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

if __name__ == "__main__":
    main()
