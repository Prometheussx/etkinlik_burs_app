import requests
from bs4 import BeautifulSoup
import datetime
import re

# --- AYARLAR ---
BASE_URL = "https://biletinial.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

CATEGORIES = {
    "sinema": "sinema",
    "tiyatro": "tiyatro",
    "muzik": "muzik",
    "opera": "opera-bale",
    "egitim": "egitim",
    "standup": "stand-up"
}

# Türkçe aylar ve sayısal karşılıkları
MONTH_MAP = {
    "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
    "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12
}

def parse_date_range(date_text):
    """
    Karmaşık tarih metinlerini (Örn: "Kasım - 28 Ocak - 31") doğru ayrıştırır.
    Şu anki tarihe göre yıl ataması yapar (Gelecek yıl kontrolü).
    En erken ve en geç tarihi döndürür.
    """
    if not date_text:
        return None

    # Şu anki zaman bilgisi
    now = datetime.datetime.now()
    current_year = now.year
    current_month = now.month
    
    parsed_dates = []

    # Regex ile Ay isimlerini yakalamak için pattern (büyük küçük harf duyarsız olması için flag kullanacağız)
    # Bu pattern tüm Türkçe ay isimlerini içerir.
    month_pattern = r"(ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos|eylül|ekim|kasım|aralık)"

    # --- STRATEJİ 1: "Ay Adı [ayraç] Gün" Formatı (Örn: Kasım - 28, Kasım 28) ---
    # Bu format, senin örneğindeki hatayı çözen kısımdır.
    # Pattern açıklaması: Ay ismi + (boşluk veya tire) + Sayı
    regex_month_first = f"{month_pattern}\s*[-.]?\s*(\d{{1,2}})"
    matches_month_first = re.findall(regex_month_first, date_text.lower(), re.IGNORECASE)

    # --- STRATEJİ 2: "Gün [ayraç] Ay Adı" Formatı (Örn: 28 Kasım) ---
    # Standart yazım şekli
    regex_day_first = f"(\d{{1,2}})\s*[-.]?\s*{month_pattern}"
    matches_day_first = re.findall(regex_day_first, date_text.lower(), re.IGNORECASE)

    # Hangi format daha çok sonuç verdiyse veya metin yapısına göre birleştirme mantığı
    # Burada çakışmayı önlemek için basit bir önceliklendirme yapacağız.
    # Eğer "Ay - Gün" formatı (senin örneğin) varsa öncelik onundur.
    
    final_matches = []

    # Veriyi işlenebilir formata (Gün, Ay İsmi) çevirip listeye atalım
    if matches_month_first:
        for m_name, d_str in matches_month_first:
            final_matches.append((int(d_str), m_name))
    
    # Eğer ilk strateji sonuç vermediyse veya ek tarihler varsa ikinciyi kontrol et
    # Not: Aynı metinde iki formatın karışık olması nadirdir ama yine de ekleyelim
    if matches_day_first and not final_matches:
        for d_str, m_name in matches_day_first:
            final_matches.append((int(d_str), m_name))
            
    # Eğer hala boşsa ve karışık durum varsa (Matches month first kısmi yakaladıysa vs)
    if not final_matches and matches_day_first:
         for d_str, m_name in matches_day_first:
            final_matches.append((int(d_str), m_name))


    # --- TARİHLERİ OLUŞTURMA VE YIL HESABI ---
    for day, month_str in final_matches:
        # Ay ismini sayıya çevir
        # Türkçe karakter sorunu olmaması için map içinde geziyoruz
        month_val = 0
        cleaned_month = month_str.lower().replace('ı', 'i') # basit normalizasyon
        
        # Tam eşleşme veya başlangıç eşleşmesi (örn: "kas" -> kasım)
        for k, v in MONTH_MAP.items():
            if month_str.startswith(k[:3]): 
                month_val = v
                break
        
        if month_val > 0:
            year = current_year
            
            # --- KRİTİK YIL MANTIĞI ---
            # Mevcut ay (Örn: 11-Kasım) ve Gelen Veri (Örn: 1-Ocak)
            # Etkinlik ayı, şu anki aydan küçükse, etkinlik önümüzdeki yıldır.
            if month_val < current_month:
                year += 1
            
            # Ayrıca: Eğer ay aynıysa (Kasım) ama gün geçmişse (Bugün 27, Etkinlik 10 Kasım),
            # Bu genellikle bir sonraki yılın etkinliğidir (Senede bir olanlar vb.)
            # Ancak sinema/tiyatroda genelde geçmiş etkinlik listelenmez, o yüzden gün kontrolünü
            # opsiyonel bırakıyoruz, ama ay kontrolü şart.
            
            try:
                dt = datetime.date(year, month_val, day)
                parsed_dates.append(dt)
            except ValueError:
                continue

    if not parsed_dates:
        return date_text # Parse edilemedi

    # Sıralama: En erken tarih en başa, en geç en sona
    parsed_dates.sort()
    
    min_date = parsed_dates[0]
    max_date = parsed_dates[-1]
    
    fmt = "%d.%m.%Y"
    
    if min_date == max_date:
        return min_date.strftime(fmt)
    else:
        return f"{min_date.strftime(fmt)} - {max_date.strftime(fmt)}"

def scrape_events_from_city(target_url, city_name, category_slug):
    extracted_data = [] 
    
    try:
        response = requests.get(target_url, headers=HEADERS, timeout=15)
        if response.status_code != 200: 
            return {"status_code": response.status_code, "error": "Sayfa bulunamadı."}

        soup = BeautifulSoup(response.content, "html.parser")
        container = soup.find("div", {"class": "kategori__etkinlikler"})
        
        if not container: 
            return extracted_data
        
        event_items = container.find_all("li")
        
        for item in event_items:
            try:
                h3 = item.find("h3")
                if not h3 or not h3.find("a"): continue
                title = h3.find("a").get("title").strip()
                
                figure = item.find("figure")
                img_url = ""
                event_full_link = ""
                if figure:
                    if figure.find("img"):
                        img_tag = figure.find("img")
                        img_url = img_tag.get("data-src") or img_tag.get("src")
                    link_tag = figure.find("a")
                    if link_tag and link_tag.get("href"):
                        href_val = link_tag.get("href")
                        event_full_link = f"{BASE_URL}{href_val}" if href_val.startswith("/") else href_val
                
                # --- DATE TEXT ALMA ---
                raw_date_text = ""
                date_p = item.find("p", class_="dates")
                if date_p:
                    raw_date_text = date_p.get_text(separator=" ", strip=True)
                else:
                    address_tag = item.find("address")
                    if address_tag:
                        next_span = address_tag.find_next_sibling("span")
                        if next_span:
                            raw_date_text = next_span.get_text(separator=" ", strip=True)

                # --- YENİ PARSE FONKSİYONU ---
                formatted_date = parse_date_range(raw_date_text)
                
                venue_name = None
                event_city_name = city_name 
                address_tag = item.find("address")
                
                if address_tag:
                    address_text = address_tag.get_text(strip=True)
                    if address_text == "Birden fazla mekanda":
                        venue_name = "Birden fazla mekanda"
                    else:
                        city_b_tag = address_tag.find("b")
                        if city_b_tag:
                            event_city_name = city_b_tag.get_text(strip=True)
                        venue_small_tag = address_tag.find("small")
                        if venue_small_tag:
                            venue_name = venue_small_tag.get_text(strip=True)

                extracted_data.append({
                    "category": category_slug, 
                    "city": event_city_name,
                    "venue": venue_name,
                    "title": title, 
                    "link": event_full_link,
                    "date": formatted_date, 
                    "image_url": img_url
                })

            except Exception:
                continue
    except Exception as e:
        return {"status_code": 500, "error": str(e)}
    
    return extracted_data

# --- API ---
def run_biletinial(category_key, city_search):
    cat_slug = CATEGORIES.get(category_key, "sinema")
    city_slug = city_search.lower()
    target_url = f"{BASE_URL}/tr-tr/{cat_slug}/{city_slug}"

    results = scrape_events_from_city(target_url, city_search, cat_slug)
    
    if isinstance(results, dict) and 'error' in results:
        return {"status": "error", "message": results.get("error")}

    return {
        "source": "Biletinial",
        "category": cat_slug,
        "city": city_search.title(),
        "event_count": len(results),
        "events": results
    }