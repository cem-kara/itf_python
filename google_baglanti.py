# -*- coding: utf-8 -*-
import os
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

# İzinler (Scopes)
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# =============================================================================
# GOOGLE DRIVE SERVİSİ (RESİM YÜKLEME İÇİN)
# =============================================================================
class GoogleDriveService:
    def __init__(self):
        """Drive servisini ve API bağlantısını başlatır."""
        self.creds = self._get_credentials()
        
        # --- HATA ALDIĞINIZ KISIM BURASIYDI (EKLENDİ) ---
        # self.service nesnesi oluşturulmazsa 'has no attribute service' hatası alırsınız.
        self.service = build('drive', 'v3', credentials=self.creds)

    def _get_credentials(self):
        """Token alır veya yeniler."""
        creds = None
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists('credentials.json'):
                    logger.error("credentials.json dosyası bulunamadı!")
                    raise FileNotFoundError("credentials.json dosyası eksik.")
                
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
        return creds

    def upload_file(self, file_path: str, parent_folder_id: str = None, custom_name: str = None) -> Optional[str]:
        """
        Dosyayı Google Drive'a yükler ve görüntüleme linkini döner.
        """
        try:
            if not os.path.exists(file_path):
                logger.error(f"Yüklenecek dosya bulunamadı: {file_path}")
                return None

            path_obj = Path(file_path)
            
            # Eğer özel isim verildiyse onu kullan, yoksa dosyanın kendi adını al
            dosya_adi = custom_name if custom_name else path_obj.name

            file_metadata = {
                'name': dosya_adi,
                'parents': [parent_folder_id] if parent_folder_id else []
            }

            media = MediaFileUpload(str(path_obj), resumable=True)
            
            logger.info(f"Drive'a yükleniyor: {dosya_adi}")
            
            # API Çağrısı
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink'
            ).execute()
            
            # İzinleri ayarla (Linki olan herkes görüntüleyebilir)
            self.service.permissions().create(
                fileId=file.get('id'),
                body={'role': 'reader', 'type': 'anyone'}
            ).execute()

            return file.get('webViewLink')

        except Exception as e:
            logger.error(f"Drive yükleme hatası: {e}")
            return None

# =============================================================================
# GOOGLE SHEETS SERVİSİ (VERİTABANI İÇİN)
# =============================================================================
# Global değişken, her seferinde tekrar login olmamak için
_sheets_client = None

def _get_sheets_client():
    global _sheets_client
    if not _sheets_client:
        # Drive için kullandığımız credentials yapısını Sheets için de kullanıyoruz
        # (Token zaten token.json içinde var)
        creds = None
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
        if not creds or not creds.valid:
             # Eğer token yoksa/geçersizse DriveService sınıfındaki auth akışı çalışmalıydı.
             # Burada basitçe yeniden yetkilendirme yapabiliriz veya DriveService'i çağırabiliriz.
             # Ancak kodun basitliği için burada tekrar kontrol ediyoruz.
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                 # Credentials.json ile akış (Main flow'da zaten yapılmış olması beklenir)
                 flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                 creds = flow.run_local_server(port=0)
            
            with open('token.json', 'w') as token:
                token.write(creds.to_json())

        _sheets_client = gspread.authorize(creds)
    return _sheets_client

def veritabani_getir(vt_tipi: str, sayfa_adi: str):
    """
    Belirtilen veritabanı tipine ve sayfa adına göre Worksheet nesnesi döner.
    
    Args:
        vt_tipi: 'personel' | 'sabit' | 'cihaz'
        sayfa_adi: 'Personel', 'Sabitler' vb.
    """
    try:
        client = _get_sheets_client()
        
        # Veritabanı Dosya Adları Eşleşmesi
        db_map = {
            'personel': 'itf_personel_vt',
            'sabit':    'itf_sabit_vt',
            'cihaz':    'itf_cihaz_vt'
        }
        
        spreadsheet_name = db_map.get(vt_tipi, 'itf_personel_vt') # Varsayılan
        
        # Dosyayı aç
        sh = client.open(spreadsheet_name)
        # Sayfayı seç
        ws = sh.worksheet(sayfa_adi)
        return ws
        
    except Exception as e:
        logger.error(f"Veritabanı bağlantı hatası ({vt_tipi}/{sayfa_adi}): {e}")
        return None

if __name__ == "__main__":
    print("Google Bağlantı Modülü Testi...")
    # Test için
    # service = GoogleDriveService()
    # print("Drive Servisi Hazır.")