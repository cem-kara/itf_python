# -*- coding: utf-8 -*-
import os
import json
import logging
import socket
import gspread
from pathlib import Path
from typing import Optional

# PySide6 Sinyalleri için
from PySide6.QtCore import QObject, Signal

# Google Auth Kütüphaneleri
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.exceptions import TransportError, RefreshError

# Yeni Standartlar: Toast bildirimi
from araclar.ortak_araclar import show_toast

# Loglama Ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("GoogleService")

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# =============================================================================
# 1. ÖZEL HATA SINIFLARI (Exception Classes)
# =============================================================================
class GoogleServisHatasi(Exception):
    """Google servisleri ile ilgili genel hata."""
    pass

class InternetBaglantiHatasi(GoogleServisHatasi):
    """İnternet bağlantısı yoksa fırlatılır."""
    pass

class KimlikDogrulamaHatasi(GoogleServisHatasi):
    """Token/Credentials hatalarında fırlatılır."""
    pass

class VeritabaniBulunamadiHatasi(GoogleServisHatasi):
    """Dosya veya Sayfa bulunamazsa fırlatılır."""
    pass

# =============================================================================
# 2. HATA BİLDİRİM SİNYALCISI (Singleton)
# =============================================================================
class GoogleBaglantiSinyalleri(QObject):
    hata_olustu = Signal(str, str) 

    _instance = None
    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = GoogleBaglantiSinyalleri()
        return cls._instance

# =============================================================================
# 3. YARDIMCI ARAÇLAR
# =============================================================================
def db_ayarlarini_yukle():
    """ayarlar.json dosyasından veritabanı yapılandırmasını okur."""
    mevcut_dizin = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(mevcut_dizin, 'ayarlar.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("veritabani_yapisi", {})
    except Exception as e:
        logger.error(f"ayarlar.json okunamadı: {e}")
        return {}

def internet_kontrol():
    """
    Standart HTTP portu üzerinden internet bağlantısını kontrol eder.
    Kurumsal ağlarda 8.8.8.8:53 engellenebileceği için bu yöntem daha güvenilirdir.
    """
    try:
        host = "www.google.com"
        port = 80
        socket.create_connection((host, port), timeout=3)
        return True
    except OSError:
        return False

# Ayarları hafızaya al
DB_CONFIG = db_ayarlarini_yukle()

# =============================================================================
# 4. KİMLİK DOĞRULAMA YÖNETİMİ
# =============================================================================
def _get_credentials():
    """Kimlik doğrulama sürecini yönetir ve geçerli credentials döner."""
    creds = None
    token_path = 'token.json'
    cred_path = 'credentials.json'

    # 1. Token var mı kontrol et
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception:
            logger.warning("Token dosyası bozuk, yeniden oluşturulacak.")
            creds = None
    
    # 2. Token geçersizse veya yoksa
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                if not internet_kontrol():
                    raise InternetBaglantiHatasi("Token yenilemek için internet bağlantısı gerekli.")
                creds.refresh(Request())
            except (TransportError, RefreshError) as e:
                logger.error(f"Token yenileme hatası: {e}")
                raise KimlikDogrulamaHatasi("Oturum süresi doldu ve yenilenemedi. Lütfen tekrar giriş yapın.")
        else:
            if not os.path.exists(cred_path):
                raise FileNotFoundError("credentials.json dosyası bulunamadı! Program dizinini kontrol edin.")
            
            flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)
            # Local server açarak yetki iste
            creds = flow.run_local_server(port=0)
        
        # 3. Yeni token'ı kaydet
        with open(token_path, 'w') as token:
            token.write(creds.to_json())

    return creds

# =============================================================================
# 5. GOOGLE SHEETS SERVİSİ
# =============================================================================
_sheets_client = None

def _get_sheets_client():
    """Gspread istemcisini (client) tekil (singleton) olarak döndürür."""
    global _sheets_client
    
    if not internet_kontrol():
        # Sinyal gönderilirken Toast ile kullanıcıya da bilgi veriliyor
        GoogleBaglantiSinyalleri.get_instance().hata_olustu.emit("Bağlantı Hatası", "İnternet bağlantısı algılanamadı.")
        show_toast("İnternet bağlantısı yok!", type="error")
        raise InternetBaglantiHatasi("İnternet bağlantısı yok.")

    if not _sheets_client:
        try:
            creds = _get_credentials()
            _sheets_client = gspread.authorize(creds)
        except Exception as e:
            msg = f"Google Sheets yetkilendirme hatası: {str(e)}"
            logger.error(msg)
            show_toast("Kimlik doğrulama başarısız!", type="error")
            raise KimlikDogrulamaHatasi(msg)
            
    return _sheets_client

def veritabani_getir(vt_tipi: str, sayfa_adi: str):
    """
    Belirtilen veritabanı ve sayfayı getirir. Hata durumunda Exception fırlatır.
    
    Args:
        vt_tipi: ayarlar.json anahtarı ('personel', 'cihaz' vb.)
        sayfa_adi: Sheet içindeki sekme adı
    
    Returns:
        gspread.Worksheet: Başarılı ise worksheet nesnesi.
        
    Raises:
        GoogleServisHatasi: Bağlantı sağlanamazsa.
    """
    spreadsheet_name = None
    
    try:
        client = _get_sheets_client()
        
        # 1. Dosya adını bul
        if vt_tipi in DB_CONFIG:
            spreadsheet_name = DB_CONFIG[vt_tipi]["dosya"]
        else:
            # Yedek harita (Config bozuksa)
            db_map = {
                'personel': 'itf_personel_vt',
                'sabit':    'itf_sabit_vt',
                'cihaz':    'itf_cihaz_vt',
                'user':     'itf_user_vt',
                'rke':      'itf_rke_vt'
            }
            spreadsheet_name = db_map.get(vt_tipi)
            
        if not spreadsheet_name:
            raise ValueError(f"'{vt_tipi}' için veritabanı tanımı bulunamadı.")

        # 2. Dosyayı Aç
        sh = client.open(spreadsheet_name) # spreadsheet_name DB_CONFIG'den gelir
        ws = sh.worksheet(sayfa_adi)
        return ws

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Veritabanı Hatası ({vt_tipi}/{sayfa_adi}): {error_msg}")
        
        if "internet" in error_msg.lower():
             show_toast("Bağlantı koptu!", type="error")
             raise InternetBaglantiHatasi("İnternet bağlantısı koptu.")
        
        raise e

# =============================================================================
# 6. GOOGLE DRIVE SERVİSİ
# =============================================================================
class GoogleDriveService:
    def __init__(self):
        try:
            self.creds = _get_credentials()
            self.service = build('drive', 'v3', credentials=self.creds)
        except Exception as e:
            logger.error(f"Drive servisi başlatılamadı: {e}")
            raise GoogleServisHatasi(f"Drive bağlantı hatası: {e}")

    def upload_file(self, file_path: str, parent_folder_id: str = None, custom_name: str = None) -> Optional[str]:
        if not os.path.exists(file_path):
            logger.warning(f"Dosya yok: {file_path}")
            return None

        try:
            path_obj = Path(file_path)
            dosya_adi = custom_name if custom_name else path_obj.name
            
            file_metadata = {
                'name': dosya_adi, 
                'parents': [parent_folder_id] if parent_folder_id else []
            }
            
            media = MediaFileUpload(str(path_obj), resumable=True)
            
            # Yükleme işlemi
            file = self.service.files().create(
                body=file_metadata, 
                media_body=media, 
                fields='id, webViewLink'
            ).execute()
            
            # Herkese okuma izni ver (Opsiyonel, güvenlik politikasına göre değişir)
            self.service.permissions().create(
                fileId=file.get('id'), 
                body={'role': 'reader', 'type': 'anyone'}
            ).execute()
            
            show_toast("Dosya Drive'a yüklendi", type="success")
            return file.get('webViewLink')

        except Exception as e:
            logger.error(f"Drive yükleme hatası: {e}")
            show_toast("Dosya yüklenemedi!", type="error")
            raise GoogleServisHatasi(f"Dosya yüklenemedi: {e}")

if __name__ == "__main__":
    # Test Bloğu
    print("--- Bağlantı Testi ---")
    try:
        if internet_kontrol():
            print("✅ İnternet: VAR")
        else:
            print("❌ İnternet: YOK")
            
        print("Spreadsheet bağlantısı deneniyor...")
        ws = veritabani_getir('user', 'user_login')
        print(f"✅ Başarılı! Kayıt sayısı: {len(ws.get_all_values())}")
        
    except Exception as hata:
        print(f"❌ HATA YAKALANDI: {type(hata).__name__}")
        print(f"Mesaj: {hata}")