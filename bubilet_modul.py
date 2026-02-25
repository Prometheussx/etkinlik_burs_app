import requests
from bs4 import BeautifulSoup
import datetime
import re
import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- TARİH AYARLARI ---
MONTH_MAP = {
    "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
    "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12
}

def parse_date_range(date_text):
    """Tarih metnini parse eder ve DD.MM.YYYY formatında döndürür."""
    if not date_text:
        return None
    
    cleaned_text = date_text.lower()
    
    # Gün isimlerini temizle
    days_to_remove = r"(pazartesi|salı|çarşamba|perşembe|cuma|cumartesi|pazar|pzt|sal|çar|per|cum|cmt|paz|cmrt)"
    cleaned_text = re.sub(days_to_remove, '', cleaned_text, flags=re.IGNORECASE)
    
    # Saat bilgilerini temizle
    cleaned_text = re.sub(r"\d{1,2}:\d{2}", '', cleaned_text)
    
    # Fazla boşlukları temizle
    cleaned_text = re.sub(r"[\s\/\.]+", ' ', cleaned_text).strip()
    
    now = datetime.datetime.now()
    current_year = now.year
    current_month = now.month
    parsed_dates = []
    
    month_pattern = r"(ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos|eylül|ekim|kasım|aralık)"
    
    # Ay-Gün formatı
    regex_month_first = f"{month_pattern}\\s*[-.]?\\s*(\\d{{1,2}})"
    matches_month_first = re.findall(regex_month_first, cleaned_text, re.IGNORECASE)
    
    # Gün-Ay formatı
    regex_day_first = f"(\\d{{1,2}})\\s*[-.]?\\s*{month_pattern}"
    matches_day_first = re.findall(regex_day_first, cleaned_text, re.IGNORECASE)
    
    final_matches = []
    
    if matches_month_first:
        for m_name, d_str in matches_month_first:
            final_matches.append((int(d_str), m_name))
    
    if matches_day_first:
        for d_str, m_name in matches_day_first:
            current_tuple = (int(d_str), m_name)
            is_duplicate = False
            for d, m in final_matches:
                if d == current_tuple[0] and m.lower().startswith(current_tuple[1].lower()[:3]):
                    is_duplicate = True
                    break
            if not is_duplicate:
                final_matches.append(current_tuple)
    
    for day, month_str in final_matches:
        month_val = 0
        for k, v in MONTH_MAP.items():
            if month_str.lower().startswith(k[:3]):
                month_val = v
                break
        
        if month_val > 0:
            year = current_year
            if month_val < current_month:
                year += 1
            elif month_val == current_month and day < now.day:
                year += 1
            
            try:
                dt = datetime.date(year, month_val, day)
                parsed_dates.append(dt)
            except ValueError:
                continue
    
    if not parsed_dates:
        return date_text
    
    parsed_dates.sort()
    min_date = parsed_dates[0]
    max_date = parsed_dates[-1]
    fmt = "%d.%m.%Y"
    
    if min_date == max_date:
        return min_date.strftime(fmt)
    else:
        return f"{min_date.strftime(fmt)} - {max_date.strftime(fmt)}"

def url_hazirla(text):
    """Türkçe karakterleri URL uyumlu hale getirir."""
    tr_map = {
        'ç': 'c', 'Ç': 'c', 'ğ': 'g', 'Ğ': 'g', 'ı': 'i', 'İ': 'i',
        'ö': 'o', 'Ö': 'o', 'ş': 's', 'Ş': 's', 'ü': 'u', 'Ü': 'u', ' ': '-'
    }
    text = text.lower()
    for tr, eng in tr_map.items():
        text = text.replace(tr, eng)
    return text

def parse_event_card(card, base_url, city, category):
    """Tek bir etkinlik kartını parse eder."""
    try:
        link = base_url + card.get("href")
        
        image_tag = card.find("img")
        image_url = "Resim Yok"
        if image_tag:
            src = image_tag.get("src")
            if src and not src.startswith("data:"):
                image_url = src
            else:
                srcset = image_tag.get("srcset")
                if srcset:
                    image_url = srcset.split(',')[-1].strip().split(' ')[0]
        
        baslik = card.find("h3").text.strip() if card.find("h3") else "Başlık Yok"
        
        detaylar = card.find_all("p", class_="text-gray-500")
        mekan = detaylar[0].text.strip() if len(detaylar) > 0 else "Belirtilmemiş"
        
        raw_tarih = detaylar[1].text.strip() if len(detaylar) > 1 else "Belirtilmemiş"
        tarih = parse_date_range(raw_tarih)
        
        fiyat_tag = card.find("span", class_="text-[#00c656]")
        fiyat = fiyat_tag.text.strip() if fiyat_tag else "Belirsiz"
        
        return {
            "city": city,
            "category": category,
            "title": baslik,
            "venue": mekan,
            "date": tarih,
            "price": fiyat,
            "link": link,
            "image_url": image_url
        }
    except Exception as e:
        return None

def slow_smooth_scroll_with_collection(driver, base_url, city, category):
    """
    Her scroll adımında etkinlikleri toplar ve tekil bir sözlükte saklar.
    """
    print("⏳ Sayfa açıldı, 10 saniye bekleniyor...")
    time.sleep(10)
    
    print("🔄 Yavaş scroll başlıyor (etkinlikler kaydediliyor)...\n")
    
    # TEKİL etkinlikleri saklamak için (link bazlı)
    unique_events = {}
    
    last_height = driver.execute_script("return document.body.scrollHeight")
    current_position = 0
    scroll_step = 500
    scroll_count = 0
    
    while True:
        # Aşağı kaydır
        current_position += scroll_step
        driver.execute_script(f"window.scrollTo(0, {current_position});")
        scroll_count += 1
        
        # Şu anki HTML'i parse et
        soup = BeautifulSoup(driver.page_source, "html.parser")
        cards = soup.find_all("a", class_="group block")
        
        # Her kartı işle ve unique_events'e ekle
        for card in cards:
            event_data = parse_event_card(card, base_url, city, category)
            if event_data and event_data["link"]:
                # Link'i anahtar olarak kullan (tekil)
                unique_events[event_data["link"]] = event_data
        
        print(f"   Scroll {scroll_count}: {len(cards)} kart görüldü | "
              f"💾 Benzersiz: {len(unique_events)} etkinlik")
        
        # 2 saniye bekle
        time.sleep(2)
        
        # Sayfa boyutunu kontrol et
        new_height = driver.execute_script("return document.body.scrollHeight")
        
        # Eğer sayfa sonuna geldiyse dur
        if current_position >= new_height:
            print("\n✅ Sayfa sonuna gelindi!")
            break
        
        # Eğer sayfa büyüdüyse, devam et
        if new_height > last_height:
            last_height = new_height
    
    print("⏳ Sayfa sonunda 10 saniye bekleniyor...")
    time.sleep(10)
    
    # Son kontrol
    soup = BeautifulSoup(driver.page_source, "html.parser")
    cards = soup.find_all("a", class_="group block")
    for card in cards:
        event_data = parse_event_card(card, base_url, city, category)
        if event_data and event_data["link"]:
            unique_events[event_data["link"]] = event_data
    
    print(f"\n🎯 TOPLAM BENZERSİZ ETKİNLİK: {len(unique_events)}")
    
    return list(unique_events.values())

def run_bubilet(category, city):
    """Selenium kullanarak TÜM benzersiz etkinlikleri çeker."""
    base_url = "https://www.bubilet.com.tr"
    
    sehir_slug = url_hazirla(city)
    kategori_slug = url_hazirla(category)
    url = f"{base_url}/{sehir_slug}/etiket/{kategori_slug}"
    
    # Selenium ayarları
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    driver = None
    
    try:
        print(f"🌐 Bağlantı kuruluyor: {url}")
        print(f"📍 Şehir: {city} | Kategori: {category}")
        print("="*60 + "\n")
        
        # WebDriver'ı başlat
        driver = webdriver.Chrome(options=chrome_options)
        
        # Bot algılamasını önle
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        driver.get(url)
        
        # İlk etkinliklerin yüklenmesini bekle
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a.group.block"))
        )
        
        # Scroll yaparak etkinlikleri topla
        extracted_events = slow_smooth_scroll_with_collection(driver, base_url, city, category)
        
        print("\n" + "="*60)
        print(f"✅ BAŞARIYLA TAMAMLANDI!")
        print(f"🎉 Toplam {len(extracted_events)} benzersiz etkinlik çekildi!")
        print(f"{'='*60}\n")
        
        return {
            "source": "Bubilet",
            "city": city,
            "category": category,
            "event_count": len(extracted_events),
            "events": extracted_events
        }
    
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"❌ HATA OLUŞTU: {str(e)}")
        print(f"{'='*60}\n")
        
        return {
            "status": "error",
            "message": str(e)
        }
    
    finally:
        # WebDriver'ı kapat
        if driver:
            driver.quit()
            print("🔒 Browser kapatıldı\n")

# ----------------------------------------------------- 
## 🚀 Örnek Kullanım
# ----------------------------------------------------- 
if __name__ == "__main__":
    print("\n" + "🎭 BUBİLET ETKİNLİK SCRAPER 🎭".center(60))
    print("="*60 + "\n")
    
    result = run_bubilet("tiyatro", "eskişehir")
    
    import json
    
    if result.get("status") != "error":
        print("\n📋 SONUÇ ÖZETİ:")
        print("="*60)
        print(f"Kaynak    : {result['source']}")
        print(f"Şehir     : {result['city']}")
        print(f"Kategori  : {result['category']}")
        print(f"Toplam    : {result['event_count']} etkinlik")
        print("="*60)
        
        # İlk 5 etkinliği göster
        if result['events']:
            print("\n📌 İLK 5 ETKİNLİK ÖRNEĞİ:")
            for i, event in enumerate(result['events'][:5], 1):
                print(f"\n{i}. {event['title']}")
                print(f"   📍 {event['venue']}")
                print(f"   📅 {event['date']}")
                print(f"   💰 {event['price']}")
        
        # JSON olarak kaydet
        output_file = f"bubilet_{result['city']}_{result['category']}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Veriler kaydedildi: {output_file}")
    else:
        print(f"❌ Hata: {result['message']}")
    
    print("\n" + "="*60)