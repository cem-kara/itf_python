# -*- coding: utf-8 -*-
import os
import json
import logging
import gspread
from pathlib import Path
from typing import Optional

# Google Auth Kütüphaneleri
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Loglama Ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("GoogleService")

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# --- AYARLARI JSON'DAN YÜKLEME ---
def db_ayarlarini_yukle():
    """ayarlar.json dosyasından veritabanı yapılandırmasını okur."""
    # Bu dosyanın (google_baglanti.py) olduğu klasörü bulur
    mevcut_dizin = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(mevcut_dizin, 'ayarlar.json')
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # JSON içindeki "veritabani_yapisi" bölümünü döndürür
            return data.get("veritabani_yapisi", {})
    except Exception as e:
        logger.error(f"ayarlar.json dosyası yüklenemedi: {e}")
        return {}

# Ayarları hafızaya al
DB_CONFIG = db_ayarlarini_yukle()

# =============================================================================
# GOOGLE DRIVE SERVİSİ (DOSYA YÜKLEME İÇİN)
# =============================================================================
class GoogleDriveService:
    def __init__(self):
        self.creds = self._get_credentials()
        self.service = build('drive', 'v3', credentials=self.creds)

    def _get_credentials(self):
        creds = None
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists('credentials.json'):
                    raise FileNotFoundError("credentials.json dosyası bulunamadı.")
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
        return creds

    def upload_file(self, file_path: str, parent_folder_id: str = None, custom_name: str = None) -> Optional[str]:
        try:
            if not os.path.exists(file_path):
                return None
            path_obj = Path(file_path)
            dosya_adi = custom_name if custom_name else path_obj.name
            file_metadata = {'name': dosya_adi, 'parents': [parent_folder_id] if parent_folder_id else []}
            media = MediaFileUpload(str(path_obj), resumable=True)
            
            file = self.service.files().create(
                body=file_metadata, media_body=media, fields='id, webViewLink'
            ).execute()
            
            self.service.permissions().create(
                fileId=file.get('id'), body={'role': 'reader', 'type': 'anyone'}
            ).execute()
            return file.get('webViewLink')
        except Exception as e:
            logger.error(f"Drive yükleme hatası: {e}")
            return None

# =============================================================================
# GOOGLE SHEETS SERVİSİ
# =============================================================================
_sheets_client = None

def _get_sheets_client():
    """Gspread istemcisini (client) tekil (singleton) olarak döndürür."""
    global _sheets_client
    if not _sheets_client:
        creds = None
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                 flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                 creds = flow.run_local_server(port=0)
            with open('token.json', 'w') as token:
                token.write(creds.to_json())

        _sheets_client = gspread.authorize(creds)
    return _sheets_client

def veritabani_getir(vt_tipi: str, sayfa_adi: str):
    """
    Belirtilen veritabanı tipine ve sayfa adına göre Worksheet nesnesi döner.
    Artık ayarlar.json dosyasındaki yapılandırmayı kullanır.
    
    Args:
        vt_tipi: 'personel', 'sabit', 'user' vb. (ayarlar.json içindeki anahtarlar)
        sayfa_adi: Sayfanın (tab) adı (örn: 'user_login')
    """
    try:
        client = _get_sheets_client()
        
        # 1. ayarlar.json'dan dosya adını bul
        if vt_tipi in DB_CONFIG:
            spreadsheet_name = DB_CONFIG[vt_tipi]["dosya"]
        else:
            # Eğer json'da yoksa eski usul yedek (hardcoded) harita
            db_map = {
                'personel': 'itf_personel_vt',
                'sabit':    'itf_sabit_vt',
                'cihaz':    'itf_cihaz_vt',
                'user':     'itf_user_vt'
            }
            spreadsheet_name = db_map.get(vt_tipi)
            
        if not spreadsheet_name:
            logger.error(f"'{vt_tipi}' tipi için ayarlar.json içinde tanım bulunamadı.")
            return None

        # 2. Google Sheet dosyasını açmayı dene
        try:
            sh = client.open(spreadsheet_name)
        except gspread.SpreadsheetNotFound:
            logger.error(f"Spreadsheet '{spreadsheet_name}' bulunamadı. Lütfen dosya adını ve paylaşım yetkilerini kontrol edin.")
            return None

        # 3. İstenen sayfayı (Worksheet) aç
        ws = sh.worksheet(sayfa_adi)
        return ws
        
    except gspread.WorksheetNotFound:
        logger.error(f"'{spreadsheet_name}' dosyası içinde '{sayfa_adi}' isimli bir sayfa bulunamadı.")
        return None
    except Exception as e:
        logger.error(f"Veritabanı bağlantı hatası ({vt_tipi}/{sayfa_adi}): {e}")
        return None

if __name__ == "__main__":
    # Basit Bağlantı Testi
    print("Bağlantı testi yapılıyor...")
    ws = veritabani_getir('user', 'user_login')
    if ws:
        print("BAŞARILI! Veriler çekildi:")
        print(ws.get_all_records())
    else:
        print("BAŞARISIZ! Lütfen yukarıdaki hata mesajlarını okuyun.")