from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import biletinial_modul
import bubilet_modul
import burs_microfon
# import sqlite3 <-- KALDIRILDI

app = FastAPI(title="Etkinlik Toplayıcı API", description="Biletinial ve Bubilet Bot Entegrasyonu")

# İstek Gövdesi Modelleri (Request Body)
class ScrapeRequest(BaseModel):
    city: str
    category: str


class ScholarshipRequest(BaseModel):
    level: str

@app.get("/")
def home():
    return {"message": "Etkinlik API çalışıyor. /docs adresine giderek test edebilirsiniz."}

# --- BİLETİNİAL ENDPOINT ---
@app.post("/scrape/biletinial")
def scrape_biletinial(request: ScrapeRequest):
    """
    Biletinial.com sitesini tarar.
    Kategoriler: sinema, tiyatro, muzik, opera, egitim
    Şehir: istanbul, ankara, izmir vb.
    """
    try:
        # Modüldeki fonksiyonu çağır
        # result artık veritabanına kaydetmek yerine anlık çekilen veriyi döndürecek.
        result = biletinial_modul.run_biletinial(request.category, request.city)
        if "status" in result and result["status"] == "error":
            raise HTTPException(status_code=404, detail=result["message"])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- BUBİLET ENDPOINT ---
@app.post("/scrape/bubilet")
def scrape_bubilet(request: ScrapeRequest):
    """
    Bubilet.com.tr sitesini tarar.
    Kategoriler: konser, tiyatro, festival, stand-up
    Şehir: istanbul, ankara, izmir vb.
    """
    try:
        # Modüldeki fonksiyonu çağır
        # result artık veritabanına kaydetmek yerine anlık çekilen veriyi döndürecek.
        result = bubilet_modul.run_bubilet(request.category, request.city)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/scrape/microfon")
def scrape_microfon(request: ScholarshipRequest):
    """
    Microfon burs ilanlarını okul seviyesine göre tarar.
    Seviye örnekleri: HighSchool/Lise, University/Üniversite, PrimarySchool/İlkokul
    """
    try:
        result = burs_microfon.run_microfon(request.level)
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("message", "Microfon verisi alınamadı."))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

