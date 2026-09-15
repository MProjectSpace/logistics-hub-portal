import json
from datetime import datetime
import requests
from bs4 BeautifulSoup

def scrape_pelindo_live_data():
    print("Menghubungkan langsung ke portal Pelindo...")
    
    # URL target webaccess pelindo/terminal
    TARGET_URL = "https://ibstpks.pelindo.co.id/webaccess/"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    open_stack_list = []
    estimated_berth_list = []

    try:
        # Melakukan request HTTP ke situs Pelindo
        response = requests.get(TARGET_URL, headers=headers, timeout=30)
        response.raise_for_status() # Cek apakah server merespon dengan baik (status 200)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Mencari semua baris tabel atau elemen data kapal di halaman
        rows = soup.find_all('tr')
        print(f"Ditemukan {len(rows)} baris elemen tabel di halaman web.")

        for index, row in enumerate(rows):
            cols = row.find_all(['td', 'th'])
            cols_text = [col.text.strip() for col in cols]
            
            # Filter baris yang memiliki informasi kapal (minimal nama kapal dan voyage/jadwal)
            if len(cols_text) >= 3:
                vessel_name = cols_text[0]
                # Abaikan baris header tabel
                if "vessel" in vessel_name.lower() or "nama" in vessel_name.lower() or not vessel_name:
                    continue
                
                row_data = {
                    "id": len(open_stack_list) + len(estimated_berth_list) + 1,
                    "vessel": vessel_name,
                    "voyage": cols_text[1] if len(cols_text) > 1 else "-",
                    "startOpen": cols_text[2] if len(cols_text) > 2 else "-",
                    "closingTime": cols_text[3] if len(cols_text) > 3 else "-",
                    "eta": cols_text[2] if len(cols_text) > 2 else "-",
                    "etb": cols_text[3] if len(cols_text) > 3 else "-",
                    "estDeparture": cols_text[4] if len(cols_text) > 4 else "-",
                    "terminal": "Terminal Pelindo"
                }

                # Klasifikasi sederhana berdasarkan teks kolom
                row_str = " ".join(cols_text).lower()
                if "open" in row_str or "stack" in row_str:
                    open_stack_list.append(row_data)
                else:
                    estimated_berth_list.append(row_data)

    except Exception as e:
        print(f"Terjadi kendala saat mengambil data dari web: {e}")

    # Jika karena proteksi jaringan server target membatasi request langsung, 
    # kita pastikan struktur JSON tetap terbentuk valid dengan log peringatan
    final_output = {
        "lastUpdated": datetime.now().strftime("%Y-%m-%d %H:%M:%S WIB"),
        "totalRecordsScraped": len(open_stack_list) + len(estimated_berth_list),
        "openStack": open_stack_list,
        "estimatedBerth": estimated_berth_list
    }

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(final_output, f, ensure_ascii=False, indent=4)
    
    print(f"Berhasil memproses! Total data tersimpan: {final_output['totalRecordsScraped']}")

if __name__ == "__main__":
    scrape_pelindo_live_data()
