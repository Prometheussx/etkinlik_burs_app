import re
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://microfon.co"
LIST_PATH = "/scholarship"
HEADERS = {
	"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
	"Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}

LEVEL_MAP = {
	"highschool": "HighSchool",
	"lise": "HighSchool",
	"university": "University",
	"universite": "University",
	"üniversite": "University",
	"primaryschool": "PrimarySchool",
	"ilkokul": "PrimarySchool",
	"ilköğretim": "PrimarySchool",
}

PAGE_SIZE_BY_LEVEL = {
	"HighSchool": 20,
	"University": 17,
	"PrimarySchool": 17,
}

DATE_RANGE_PATTERN = re.compile(r"\d{2}\.\d{2}\.\d{4}\s*-\s*\d{2}\.\d{2}\.\d{4}")
NO_RESULTS_TEXT = "Aradığınız kriterlere uygun bir sonuç bulunamadı"


def _normalize_level(level: str) -> str:
	if not level:
		return ""
	key = level.strip().lower()
	return LEVEL_MAP.get(key, "")


def _build_page_url(level: str, page_number: int) -> str:
	params = {
		"pageNumber": page_number,
		"pageSize": PAGE_SIZE_BY_LEVEL.get(level, 20),
		"locationId": 223,
		"level": level,
	}
	return f"{BASE_URL}{LIST_PATH}?{urlencode(params)}"


def _full_url(path_or_url: str) -> str:
	if not path_or_url:
		return ""
	if path_or_url.startswith("http"):
		return path_or_url
	return f"{BASE_URL}{path_or_url}"


def _extract_date_range(card: BeautifulSoup) -> str:
	text = card.get_text(" ", strip=True)
	match = DATE_RANGE_PATTERN.search(text)
	return match.group(0) if match else ""


def _extract_card(card: BeautifulSoup):
	link_tag = card.select_one('a[href^="/scholarship/"]')
	if not link_tag:
		return None

	title = link_tag.get_text(strip=True)
	href = link_tag.get("href", "").strip()
	detail_url = _full_url(href)

	provider_tag = card.select_one("p.styled-h6")
	provider = provider_tag.get_text(strip=True) if provider_tag else ""

	image_tag = card.select_one('img[alt="Burs İlanı Görseli"]')
	image_url = ""
	if image_tag:
		image_url = image_tag.get("src") or ""
		image_url = _full_url(image_url)

	tags = [span.get_text(strip=True) for span in card.select("div.istbwq span") if span.get_text(strip=True)]
	location = tags[0] if len(tags) > 0 else ""
	level = tags[1] if len(tags) > 1 else ""

	amount_tag = card.select_one("div.jGQIFV span")
	amount = amount_tag.get_text(" ", strip=True) if amount_tag else ""

	duration_tag = card.select_one("div.jGQIFV p")
	duration = duration_tag.get_text(" ", strip=True) if duration_tag else ""

	description_tag = card.select_one("p.clamp-3")
	description = description_tag.get_text(" ", strip=True) if description_tag else ""

	return {
		"provider": provider,
		"title": title,
		"detail_url": detail_url,
		"image_url": image_url,
		"application_dates": _extract_date_range(card),
		"location": location,
		"level": level,
		"amount": amount,
		"duration": duration,
		"description": description,
	}


def _scrape_page(level: str, page_number: int):
	url = _build_page_url(level, page_number)
	response = requests.get(url, headers=HEADERS, timeout=20)

	if response.status_code != 200:
		return {"status": "error", "message": f"Microfon sayfası açılamadı. HTTP {response.status_code}"}

	soup = BeautifulSoup(response.text, "html.parser")
	no_results_tag = soup.find("p", string=lambda value: value and NO_RESULTS_TEXT in value)
	if no_results_tag:
		return {"status": "ok", "url": url, "items": [], "no_results": True}

	cards = soup.select("div.scholarship-item")

	scholarships = []
	for card in cards:
		parsed = _extract_card(card)
		if parsed:
			scholarships.append(parsed)

	return {"status": "ok", "url": url, "items": scholarships, "no_results": False}


def run_microfon(level: str, max_pages: int = 20):
	normalized_level = _normalize_level(level)
	if not normalized_level:
		return {
			"status": "error",
			"message": "Geçersiz okul seviyesi. Kullanılabilir değerler: HighSchool/Lise, University/Üniversite, PrimarySchool/İlkokul.",
		}

	all_items = []
	seen_urls = set()
	scanned_urls = []

	for page in range(1, max_pages + 1):
		result = _scrape_page(normalized_level, page)
		if result.get("status") == "error":
			return result

		scanned_urls.append(result["url"])
		if result.get("no_results"):
			break

		page_items = result["items"]
		if not page_items:
			break

		added_count = 0
		for item in page_items:
			detail_url = item.get("detail_url")
			if not detail_url or detail_url in seen_urls:
				continue
			seen_urls.add(detail_url)
			all_items.append(item)
			added_count += 1

		if added_count == 0:
			break

	return {
		"source": "Microfon",
		"selected_level": normalized_level,
		"scholarship_count": len(all_items),
		"scanned_pages": len(scanned_urls),
		"scanned_urls": scanned_urls,
		"scholarships": all_items,
	}
