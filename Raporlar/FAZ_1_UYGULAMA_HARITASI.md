# ITF Python - FAZ 1 UYGULAMA HARİTASI
## Kritik Sorunlar ve Hızlı Kazançlar (1-2 Hafta)

---

## 📅 HAFTA 1: GÜVENLİK VE İSTİKRAR

### GÜN 1-2: Exception Yönetimi Düzeltmeleri

#### 🆕 YENİ DOSYALAR

##### 1. `araclar/hata_yonetimi.py` - YENİ DOSYA
```python
# -*- coding: utf-8 -*-
"""
Merkezi hata yönetim sistemi
Tüm hata türleri ve yönetimi buradan yapılır
"""
import logging
from typing import Optional, Callable
from PySide6.QtWidgets import QMessageBox, QWidget

logger = logging.getLogger("HataYonetimi")

class HataYoneticisi:
    """Kullanıcı dostu hata mesajları ve loglama"""
    
    # Bilinen hataların kullanıcı dostu mesajları
    HATA_MESAJLARI = {
        'SpreadsheetNotFound': {
            'baslik': '📋 Veritabanı Bulunamadı',
            'mesaj': 'Veritabanı dosyasına erişilemiyor.\n\nLütfen Google Drive bağlantınızı kontrol edin.',
            'seviye': 'critical'
        },
        'RefreshError': {
            'baslik': '🔐 Oturum Süresi Doldu',
            'mesaj': 'Oturumunuzun süresi dolmuş.\n\nLütfen programı yeniden başlatın.',
            'seviye': 'warning'
        },
        'ConnectionError': {
            'baslik': '🌐 Bağlantı Hatası',
            'mesaj': 'İnternet bağlantısı kurulamıyor.\n\nLütfen ağ bağlantınızı kontrol edin.',
            'seviye': 'critical'
        },
        'ValueError': {
            'baslik': '⚠️ Geçersiz Veri',
            'mesaj': 'Girdiğiniz veri formatı hatalı.\n\nLütfen bilgileri kontrol edip tekrar deneyin.',
            'seviye': 'warning'
        },
        'FileNotFoundError': {
            'baslik': '📁 Dosya Bulunamadı',
            'mesaj': 'Gerekli dosya bulunamadı.\n\nLütfen kurulum klasörünü kontrol edin.',
            'seviye': 'critical'
        }
    }
    
    @staticmethod
    def hata_goster(exception: Exception, parent: Optional[QWidget] = None, 
                    ek_bilgi: str = "") -> None:
        """
        Hatayı kullanıcıya göster ve logla
        
        Kullanım:
            try:
                # işlem
            except Exception as e:
                HataYoneticisi.hata_goster(e, self)
        """
        # Hata türünü bul
        hata_adi = type(exception).__name__
        
        # Teknik log (geliştiriciler için)
        logger.error(f"Hata yakalandı: {hata_adi} - {str(exception)}", exc_info=True)
        
        # Kullanıcı mesajını hazırla
        if hata_adi in HataYoneticisi.HATA_MESAJLARI:
            hata_bilgi = HataYoneticisi.HATA_MESAJLARI[hata_adi]
            baslik = hata_bilgi['baslik']
            mesaj = hata_bilgi['mesaj']
            seviye = hata_bilgi['seviye']
        else:
            # Bilinmeyen hata
            baslik = "⚠️ Beklenmeyen Hata"
            mesaj = f"Bir hata oluştu.\n\nHata Kodu: {hata_adi}"
            seviye = 'critical'
        
        # Ek bilgi varsa ekle
        if ek_bilgi:
            mesaj += f"\n\n{ek_bilgi}"
        
        # Kullanıcıya göster
        if seviye == 'critical':
            QMessageBox.critical(parent, baslik, mesaj)
        else:
            QMessageBox.warning(parent, baslik, mesaj)
    
    @staticmethod
    def guvenli_calistir(fonksiyon: Callable, parent: Optional[QWidget] = None,
                        hata_mesaji: str = "İşlem sırasında hata oluştu"):
        """
        Bir fonksiyonu güvenli şekilde çalıştırır
        
        Kullanım:
            def veri_yukle():
                ws = veritabani_getir('personel', 'Personel')
                return ws.get_all_records()
            
            veriler = HataYoneticisi.guvenli_calistir(veri_yukle, self)
        """
        try:
            return fonksiyon()
        except Exception as e:
            HataYoneticisi.hata_goster(e, parent, hata_mesaji)
            return None
```

---

#### 📝 DEĞİŞTİRİLECEK DOSYALAR

##### 2. `google_baglanti.py` - DEĞİŞTİRİLECEK
**Değişiklik Satırları: 98-134, 162-223**

```python
# ÖNCE (Satır 98-134):
def _get_credentials():
    creds = None
    token_path = 'token.json'
    cred_path = 'credentials.json'

    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception:  # ❌ BAD: Bare exception
            logger.warning("Token dosyası bozuk, yeniden oluşturulacak.")
            creds = None
    # ...

# SONRA (Değiştirilmiş):
def _get_credentials():
    creds = None
    token_path = 'token.json'
    cred_path = 'credentials.json'

    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except (ValueError, json.JSONDecodeError) as e:  # ✅ GOOD: Spesifik hatalar
            logger.warning(f"Token dosyası bozuk ({type(e).__name__}), yeniden oluşturulacak.")
            creds = None
        except Exception as e:  # Beklenmeyen durum
            logger.error(f"Token okuma hatası: {e}", exc_info=True)
            raise KimlikDogrulamaHatasi(f"Token dosyası okunamadı: {e}")
    # ...
```

**Değişiklik Satırları: 176-223**

```python
# ÖNCE (Satır 211-223):
    except Exception as e:  # ❌ BAD: Çok genel
        error_msg = str(e)
        logger.error(f"Veritabanı Hatası ({vt_tipi}/{sayfa_adi}): {error_msg}")
        
        if "internet" in error_msg.lower():
             raise InternetBaglantiHatasi("İnternet bağlantısı koptu.")
        
        raise e 

# SONRA (Değiştirilmiş):
    except gspread.SpreadsheetNotFound as e:  # ✅ GOOD: Spesifik
        raise VeritabaniBulunamadiHatasi(
            f"'{spreadsheet_name}' dosyası bulunamadı. Yetkiniz olmayabilir."
        )
    except gspread.WorksheetNotFound as e:
        raise VeritabaniBulunamadiHatasi(
            f"'{spreadsheet_name}' içinde '{sayfa_adi}' sayfası bulunamadı."
        )
    except (TransportError, ConnectionError) as e:
        raise InternetBaglantiHatasi("İnternet bağlantısı koptu.")
    except Exception as e:
        logger.error(f"Beklenmeyen veritabanı hatası: {e}", exc_info=True)
        raise GoogleServisHatasi(f"Veritabanı işlemi başarısız: {e}")
```

---

##### 3. `formlar/personel_ekle.py` - DEĞİŞTİRİLECEK
**Değişiklik: Import ekle + Exception handling düzelt**

```python
# BAŞA EKLE (Satır 35 civarı):
from araclar.hata_yonetimi import HataYoneticisi

# DEĞİŞTİR (Örnek satır 250-260 civarı):
# ÖNCE:
def kaydet(self):
    try:
        # kayıt işlemleri
        pass
    except:  # ❌ BAD
        QMessageBox.critical(self, "Hata", "Bir hata oluştu")

# SONRA:
def kaydet(self):
    try:
        # kayıt işlemleri
        pass
    except ValueError as e:  # ✅ GOOD
        HataYoneticisi.hata_goster(e, self, "Lütfen tüm alanları doğru doldurun")
    except Exception as e:
        HataYoneticisi.hata_goster(e, self)
```

---

##### 4. `formlar/cihaz_ekle.py` - DEĞİŞTİRİLECEK
**Değişiklik Satırları: 34-40 (import), 200-250 (exception handling)**

```python
# BAŞA EKLE:
from araclar.hata_yonetimi import HataYoneticisi

# DEĞİŞTİR (BaslangicYukleyici thread'i - satır 63-110):
class BaslangicYukleyici(QThread):
    veri_hazir = Signal(dict, dict, int)
    hata_olustu = Signal(str)  # YENİ: Hata sinyali
    
    def run(self):
        try:
            sabitler = {}
            maps = {"AnaBilimDali": {}, "Cihaz_Tipi": {}, "Kaynak": {}}
            siradaki_no = 1

            # Sabitleri Çek
            ws_sabit = veritabani_getir('sabit', 'Sabitler')
            # ... işlemler ...
            
            self.veri_hazir.emit(sabitler, maps, siradaki_no)
            
        except VeritabaniBulunamadiHatasi as e:  # ✅ Spesifik hata
            self.hata_olustu.emit(f"Veritabanı hatası: {e}")
        except InternetBaglantiHatasi as e:
            self.hata_olustu.emit(f"Bağlantı hatası: {e}")
        except Exception as e:
            logger.error(f"Başlangıç yükleme hatası: {e}", exc_info=True)
            self.hata_olustu.emit(f"Beklenmeyen hata: {type(e).__name__}")

# __init__ içinde signal bağla:
def __init__(self):
    # ...
    self.loader = BaslangicYukleyici()
    self.loader.veri_hazir.connect(self.baslangic_verisi_yuklendi)
    self.loader.hata_olustu.connect(self.baslangic_hatasi)  # YENİ
    self.loader.start()

def baslangic_hatasi(self, mesaj):  # YENİ METOD
    """Başlangıç yükleme hatası"""
    QMessageBox.critical(self, "Yükleme Hatası", mesaj)
    self.close()  # Formu kapat
```

---

##### 5. DİĞER TÜM FORM DOSYALARI - TOPLU DEĞİŞİKLİK

**Değiştirilecek 23 dosya:**
- `formlar/personel_listesi.py`
- `formlar/cihaz_listesi.py`
- `formlar/ariza_kayit.py`
- `formlar/ariza_listesi.py`
- `formlar/ariza_islem.py`
- `formlar/rke_yonetim.py`
- `formlar/rke_muayene.py`
- `formlar/rke_rapor.py`
- `formlar/periyodik_bakim.py`
- `formlar/kalibrasyon_ekle.py`
- `formlar/izin_takip_list.py`
- `formlar/personel_detay.py`
- `formlar/cihaz_detay.py`
- `formlar/dashboard.py`
- `formlar/user_dashboard.py`
- `formlar/login.py`
- `formlar/fhsz_Yonetim.py`
- `formlar/fhsz_hesapla.py`
- `formlar/fhsz_puantaj.py`
- `formlar/izin_takvim.py`
- `formlar/izin_takip.py`
- `formlar/ayarlar.py`
- `formlar/sifre_degistir.py`

**Her dosyada yapılacak değişiklik:**

```python
# 1. Import ekle (dosyanın başına):
from araclar.hata_yonetimi import HataYoneticisi

# 2. Tüm bare exception'ları değiştir:
# ÖNCE:
try:
    # işlem
except:
    pass

# SONRA:
try:
    # işlem
except ValueError as e:
    HataYoneticisi.hata_goster(e, self)
except Exception as e:
    logger.error(f"Beklenmeyen hata: {e}", exc_info=True)
    HataYoneticisi.hata_goster(e, self)
```

---

### GÜN 3-4: Thread Güvenliği

#### 🆕 YENİ DOSYA

##### 6. `araclar/singleton.py` - YENİ DOSYA
```python
# -*- coding: utf-8 -*-
"""
Thread-safe Singleton pattern implementasyonu
"""
import threading

class ThreadSafeSingleton:
    """
    Thread-safe singleton base class
    
    Kullanım:
        class MyService(ThreadSafeSingleton):
            def __init__(self):
                self.data = []
    """
    _instances = {}
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls not in cls._instances:
            with cls._lock:
                # Double-checked locking
                if cls not in cls._instances:
                    cls._instances[cls] = super().__new__(cls)
        return cls._instances[cls]
```

---

#### 📝 DEĞİŞTİRİLECEK DOSYA

##### 7. `google_baglanti.py` - DEĞİŞTİRİLECEK
**Değişiklik Satırları: 1-10 (import), 139-161 (singleton)**

```python
# BAŞA EKLE:
import threading
from araclar.singleton import ThreadSafeSingleton

# DEĞİŞTİR (Satır 139-161):
# ÖNCE:
_sheets_client = None  # ❌ Thread-safe değil

def _get_sheets_client():
    global _sheets_client
    
    if not internet_kontrol():
        raise InternetBaglantiHatasi("İnternet bağlantısı yok.")

    if not _sheets_client:
        try:
            creds = _get_credentials()
            _sheets_client = gspread.authorize(creds)
        except Exception as e:
            raise KimlikDogrulamaHatasi(f"Yetkilendirme hatası: {e}")
            
    return _sheets_client

# SONRA:
class SheetsClientManager(ThreadSafeSingleton):  # ✅ Thread-safe singleton
    """Google Sheets client yöneticisi"""
    
    def __init__(self):
        if not hasattr(self, '_client'):
            self._client = None
            self._lock = threading.RLock()  # Reentrant lock
    
    def get_client(self):
        """Thread-safe client döndür"""
        if not internet_kontrol():
            raise InternetBaglantiHatasi("İnternet bağlantısı yok.")
        
        if self._client is None:
            with self._lock:
                # Double-checked locking
                if self._client is None:
                    try:
                        creds = _get_credentials()
                        self._client = gspread.authorize(creds)
                        logger.info("✅ Google Sheets client oluşturuldu")
                    except Exception as e:
                        logger.error(f"Client oluşturma hatası: {e}")
                        raise KimlikDogrulamaHatasi(f"Yetkilendirme hatası: {e}")
        
        return self._client
    
    def reset_client(self):
        """Client'ı sıfırla (yeniden bağlantı için)"""
        with self._lock:
            self._client = None
            logger.info("Client sıfırlandı")

# Global instance
_sheets_manager = SheetsClientManager()

def _get_sheets_client():
    """Geriye dönük uyumluluk için wrapper"""
    return _sheets_manager.get_client()
```

---

### GÜN 5: Credential Güvenliği

#### 🆕 YENİ DOSYALAR

##### 8. `.env.example` - YENİ DOSYA
```ini
# Google API Credentials
GOOGLE_CREDENTIALS_PATH=credentials.json
GOOGLE_TOKEN_PATH=token.json

# Database Configuration
DB_PERSONEL_FILE=itf_personel_vt
DB_CIHAZ_FILE=itf_cihaz_vt
DB_RKE_FILE=itf_rke_vt
DB_USER_FILE=itf_user_vt
DB_SABIT_FILE=itf_sabit_vt

# Google Drive Folder IDs
DRIVE_CIHAZ_RESIMLERI=1-PznDkBqOHTbE3rWBlS8g2HjZXaK6Sdh
DRIVE_CIHAZ_BELGELERI=1eOq_NfrjN_XwKirUuX_0uyOonk137HjF
DRIVE_CIHAZ_KUNYE_PDF=19kx3IHTg4XWrYrF-_LzT3BpY5gRy-CH5

# Application Settings
APP_ENV=production
DEBUG=False
LOG_LEVEL=INFO
```

##### 9. `.env` - YENİ DOSYA (Kullanıcı oluşturacak)
```ini
# .env.example dosyasını kopyalayın ve kendi değerlerinizi girin
# Bu dosya .gitignore'da olmalı!
```

##### 10. `.gitignore` - YENİ DOSYA
```
# Credentials
credentials.json
token.json
.env

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db

# Logs
*.log
logs/

# Temp
temp/
*.tmp
```

---

#### 📝 DEĞİŞTİRİLECEK DOSYALAR

##### 11. `requirements.txt` - GÜNCELLENECEK
```python
# EKLE (en alta):
python-dotenv>=1.0.0
```

##### 12. `google_baglanti.py` - DEĞİŞTİRİLECEK
**Değişiklik Satırları: 1-10 (import), 98-134 (credentials path)**

```python
# BAŞA EKLE:
from dotenv import load_dotenv

# Ortam değişkenlerini yükle
load_dotenv()

# DEĞİŞTİR (Satır 98-134):
# ÖNCE:
def _get_credentials():
    creds = None
    token_path = 'token.json'  # ❌ Sabit kodlanmış
    cred_path = 'credentials.json'  # ❌ Sabit kodlanmış

# SONRA:
def _get_credentials():
    creds = None
    # Ortam değişkenlerinden oku, yoksa varsayılan değer
    token_path = os.getenv('GOOGLE_TOKEN_PATH', 'token.json')  # ✅ Güvenli
    cred_path = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')  # ✅ Güvenli
```

##### 13. `formlar/cihaz_ekle.py` - DEĞİŞTİRİLECEK
**Değişiklik Satırları: 1-10, 54-58**

```python
# BAŞA EKLE:
import os
from dotenv import load_dotenv
load_dotenv()

# DEĞİŞTİR (Satır 54-58):
# ÖNCE:
DRIVE_KLASORLERI = {
    "CIHAZ_RESIMLERI": "1-PznDkBqOHTbE3rWBlS8g2HjZXaK6Sdh",  # ❌ Sabit
    "CIHAZ_BELGELERI": "1eOq_NfrjN_XwKirUuX_0uyOonk137HjF",
    "CIHAZ_KUNYE_PDF": "19kx3IHTg4XWrYrF-_LzT3BpY5gRy-CH5"
}

# SONRA:
DRIVE_KLASORLERI = {
    "CIHAZ_RESIMLERI": os.getenv('DRIVE_CIHAZ_RESIMLERI', '1-PznDkBqOHTbE3rWBlS8g2HjZXaK6Sdh'),  # ✅ ENV
    "CIHAZ_BELGELERI": os.getenv('DRIVE_CIHAZ_BELGELERI', '1eOq_NfrjN_XwKirUuX_0uyOonk137HjF'),
    "CIHAZ_KUNYE_PDF": os.getenv('DRIVE_CIHAZ_KUNYE_PDF', '19kx3IHTg4XWrYrF-_LzT3BpY5gRy-CH5')
}
```

---

## 📊 HAFTA 1 ÖZET

### Oluşturulacak Yeni Dosyalar (4 adet):
1. ✅ `araclar/hata_yonetimi.py`
2. ✅ `araclar/singleton.py`
3. ✅ `.env.example`
4. ✅ `.gitignore`

### Değiştirilecek Dosyalar (26 adet):
1. ✅ `google_baglanti.py` (3 farklı bölüm)
2. ✅ `requirements.txt` (1 satır ekleme)
3. ✅ `formlar/personel_ekle.py` (import + exception)
4. ✅ `formlar/cihaz_ekle.py` (import + exception + env)
5-26. ✅ Diğer 22 form dosyası (import + exception)

### Kullanıcının Yapacakları:
1. ✅ `.env` dosyası oluştur (`.env.example`'dan kopyala)
2. ✅ `pip install python-dotenv` çalıştır
3. ✅ Git'e push etmeden önce `.gitignore` kontrol et

---

## 📅 HAFTA 2: PERFORMANS VE VALİDASYON

### GÜN 1-3: Önbellekleme Sistemi

#### 🆕 YENİ DOSYALAR

##### 14. `araclar/cache_manager.py` - YENİ DOSYA
```python
# -*- coding: utf-8 -*-
"""
Veritabanı önbellekleme sistemi
Thread-safe, TTL destekli
"""
from datetime import datetime, timedelta
from typing import Optional, Any, Dict
import threading
import logging

logger = logging.getLogger("CacheManager")

class CacheManager:
    """
    Thread-safe önbellek yöneticisi
    
    Kullanım:
        cache = CacheManager()
        cache.set('personel:all', data, ttl_seconds=300)
        data = cache.get('personel:all')
    """
    
    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._ttl_cache: Dict[str, datetime] = {}
        self._lock = threading.RLock()
        logger.info("✅ Cache Manager başlatıldı")
    
    def get(self, key: str) -> Optional[Any]:
        """
        Önbellekten veri al
        
        Returns:
            Veri varsa ve geçerliyse veriyi döndürür, yoksa None
        """
        with self._lock:
            if key not in self._cache:
                logger.debug(f"❌ Cache MISS: {key}")
                return None
            
            # TTL kontrolü
            if key in self._ttl_cache:
                if datetime.now() > self._ttl_cache[key]:
                    # Süresi dolmuş
                    del self._cache[key]
                    del self._ttl_cache[key]
                    logger.debug(f"⏰ Cache EXPIRED: {key}")
                    return None
            
            logger.debug(f"✅ Cache HIT: {key}")
            return self._cache[key]
    
    def set(self, key: str, value: Any, ttl_seconds: int = 300):
        """
        Veriyi önbelleğe al
        
        Args:
            key: Anahtar
            value: Değer
            ttl_seconds: Yaşam süresi (saniye). Varsayılan 5 dakika
        """
        with self._lock:
            self._cache[key] = value
            self._ttl_cache[key] = datetime.now() + timedelta(seconds=ttl_seconds)
            logger.debug(f"💾 Cache SET: {key} (TTL: {ttl_seconds}s)")
    
    def invalidate(self, key: str):
        """Belirli bir anahtarı geçersiz kıl"""
        with self._lock:
            removed = key in self._cache
            self._cache.pop(key, None)
            self._ttl_cache.pop(key, None)
            if removed:
                logger.debug(f"🗑️ Cache INVALIDATE: {key}")
    
    def invalidate_pattern(self, pattern: str):
        """
        Pattern'e uyan tüm anahtarları temizle
        
        Örnek:
            cache.invalidate_pattern('personel:')  # personel:all, personel:123 vb. hepsi silinir
        """
        with self._lock:
            keys_to_remove = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_remove:
                self._cache.pop(key, None)
                self._ttl_cache.pop(key, None)
            
            if keys_to_remove:
                logger.debug(f"🗑️ Cache INVALIDATE PATTERN: {pattern} ({len(keys_to_remove)} adet)")
    
    def clear(self):
        """Tüm önbelleği temizle"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._ttl_cache.clear()
            logger.info(f"🗑️ Cache CLEAR: {count} adet kayıt silindi")
    
    def get_stats(self) -> Dict[str, int]:
        """Cache istatistikleri"""
        with self._lock:
            return {
                'total_keys': len(self._cache),
                'expired_keys': sum(
                    1 for k, v in self._ttl_cache.items() 
                    if datetime.now() > v
                )
            }

# Global singleton instance
_global_cache = CacheManager()

def get_cache() -> CacheManager:
    """Global cache instance'ı döndür"""
    return _global_cache
```

---

#### 📝 DEĞİŞTİRİLECEK DOSYALAR

##### 15. `google_baglanti.py` - DEĞİŞTİRİLECEK
**Değişiklik: YENİ FONKSİYON EKLE (Satır 223'ten sonra)**

```python
# EKLE (dosyanın sonuna, satır 273 civarı):
from araclar.cache_manager import get_cache

def veritabani_getir_cached(vt_tipi: str, sayfa_adi: str, use_cache: bool = True):
    """
    Önbellek destekli veritabanı getirme
    
    Args:
        vt_tipi: 'personel', 'cihaz', 'rke', 'sabit', 'user'
        sayfa_adi: Sheet adı
        use_cache: False ise her seferinde DB'den çeker
    
    Returns:
        Kayıt listesi (dict listesi)
    
    Kullanım:
        # Cache'li:
        personeller = veritabani_getir_cached('personel', 'Personel')
        
        # Fresh data:
        personeller = veritabani_getir_cached('personel', 'Personel', use_cache=False)
    """
    cache_key = f"{vt_tipi}:{sayfa_adi}"
    cache = get_cache()
    
    # Cache'den dene
    if use_cache:
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            logger.info(f"✅ Cache HIT: {cache_key} ({len(cached_data)} kayıt)")
            return cached_data
    
    # Cache MISS veya use_cache=False
    logger.info(f"❌ Cache MISS: {cache_key} - Veritabanından çekiliyor...")
    
    try:
        ws = veritabani_getir(vt_tipi, sayfa_adi)
        data = ws.get_all_records()
        
        # Cache'e kaydet (5 dakika TTL)
        cache.set(cache_key, data, ttl_seconds=300)
        
        logger.info(f"💾 Cache'e kaydedildi: {cache_key} ({len(data)} kayıt)")
        return data
        
    except Exception as e:
        logger.error(f"Veritabanı okuma hatası: {e}")
        raise

def cache_temizle(vt_tipi: str = None, sayfa_adi: str = None):
    """
    Cache'i temizle
    
    Args:
        vt_tipi: Belirtilirse sadece o tip temizlenir (örn: 'personel')
        sayfa_adi: vt_tipi ile birlikte belirtilirse sadece o sayfa
    
    Kullanım:
        # Personel verileri değişti, cache'i temizle
        cache_temizle('personel', 'Personel')
        
        # Tüm personel cache'i
        cache_temizle('personel')
        
        # Tüm cache
        cache_temizle()
    """
    cache = get_cache()
    
    if vt_tipi and sayfa_adi:
        # Belirli bir sayfa
        cache.invalidate(f"{vt_tipi}:{sayfa_adi}")
    elif vt_tipi:
        # Belirli bir veritabanı tipi
        cache.invalidate_pattern(f"{vt_tipi}:")
    else:
        # Tümü
        cache.clear()
```

---

##### 16. `formlar/personel_listesi.py` - DEĞİŞTİRİLECEK
**Değişiklik Satırları: 1-40 (import), veri_yukle fonksiyonu**

```python
# BAŞA EKLE:
from google_baglanti import veritabani_getir_cached, cache_temizle

# DEĞİŞTİR (veri_yukle fonksiyonu):
# ÖNCE:
def veri_yukle(self):
    try:
        ws = veritabani_getir('personel', 'Personel')
        records = ws.get_all_records()  # ❌ Her seferinde çeker
        self.tabloyu_doldur(records)
    except Exception as e:
        QMessageBox.critical(self, "Hata", str(e))

# SONRA:
def veri_yukle(self, force_refresh=False):
    """
    Personel verilerini yükle
    
    Args:
        force_refresh: True ise cache'i atla, fresh data çek
    """
    try:
        # Cache'den veya DB'den çek
        records = veritabani_getir_cached(
            'personel', 
            'Personel', 
            use_cache=not force_refresh  # ✅ Cache kullan
        )
        
        self.tabloyu_doldur(records)
        
        # Status bar güncelle
        if hasattr(self, 'status_label'):
            cache_durumu = "🔄 Yenilendi" if force_refresh else "💾 Cache"
            self.status_label.setText(
                f"📊 {len(records)} personel | {cache_durumu}"
            )
            
    except Exception as e:
        HataYoneticisi.hata_goster(e, self, "Personel verileri yüklenirken hata")

# YENİ: Yenile butonu ekle
def yenile_btn_clicked(self):
    """Yenile butonuna tıklandığında"""
    self.veri_yukle(force_refresh=True)  # Cache'i atla

# EKLE: Personel ekleme/silme sonrası cache temizle
def personel_silindi(self):
    """Personel silindikten sonra çağrılır"""
    cache_temizle('personel', 'Personel')  # ✅ Cache'i temizle
    self.veri_yukle()  # Yeniden yükle
```

---

##### 17. `formlar/cihaz_listesi.py` - DEĞİŞTİRİLECEK
**Aynı mantık, personel_listesi.py ile paralel değişiklik**

```python
# BAŞA EKLE:
from google_baglanti import veritabani_getir_cached, cache_temizle

# veri_yukle fonksiyonunu değiştir (yukarıdaki gibi)
# cihaz_silindi fonksiyonuna cache_temizle ekle
```

---

##### 18. `formlar/cihaz_ekle.py` - DEĞİŞTİRİLECEK
**Değişiklik: BaslangicYukleyici thread'ini cache'li yap**

```python
# BAŞA EKLE:
from google_baglanti import veritabani_getir_cached, cache_temizle

# DEĞİŞTİR (BaslangicYukleyici class'ı):
class BaslangicYukleyici(QThread):
    veri_hazir = Signal(dict, dict, int)
    hata_olustu = Signal(str)
    
    def run(self):
        try:
            sabitler = {}
            maps = {"AnaBilimDali": {}, "Cihaz_Tipi": {}, "Kaynak": {}}
            siradaki_no = 1

            # 1. Sabitleri Çek (CACHE KULLAN)
            kayitlar = veritabani_getir_cached('sabit', 'Sabitler')  # ✅ Cache
            
            for satir in kayitlar:
                kod = str(satir.get('Kod', '')).strip()
                eleman = str(satir.get('MenuEleman', '')).strip()
                kisaltma = str(satir.get('Aciklama', '')).strip()

                if kod and eleman:
                    if kod not in sabitler: 
                        sabitler[kod] = []
                    sabitler[kod].append(eleman)
                    
                    if kisaltma and kod in maps:
                        maps[kod][eleman] = kisaltma

            # 2. Son ID'yi Hesapla (CACHE KULLAN)
            cihazlar = veritabani_getir_cached('cihaz', 'Cihazlar')  # ✅ Cache
            
            if cihazlar and len(cihazlar) > 0:
                # İlk kaydın anahtarlarından cihaz_id'yi bul
                ilk_kayit = cihazlar[0]
                id_key = None
                for key in ilk_kayit.keys():
                    if 'cihaz' in key.lower() and 'id' in key.lower():
                        id_key = key
                        break
                
                if id_key:
                    son_id = max(int(row.get(id_key, 0)) for row in cihazlar if row.get(id_key))
                    siradaki_no = son_id + 1

            self.veri_hazir.emit(sabitler, maps, siradaki_no)
            
        except Exception as e:
            logger.error(f"Başlangıç yükleme hatası: {e}", exc_info=True)
            self.hata_olustu.emit(f"Veri yükleme hatası: {type(e).__name__}")

# EKLE (kaydet fonksiyonu sonunda):
def kaydet(self):
    # ... kayıt işlemleri ...
    
    if basarili:
        # Cache'i temizle ki listeler güncel veriyi çeksin
        cache_temizle('cihaz', 'Cihazlar')  # ✅ Cache temizle
        
        QMessageBox.information(self, "Başarılı", "Cihaz kaydedildi")
        self.close()
```

---

### GÜN 4-5: Input Validasyon

#### 🆕 YENİ DOSYA

##### 19. `araclar/validators.py` - YENİ DOSYA
```python
# -*- coding: utf-8 -*-
"""
Form input validasyon fonksiyonları
TC Kimlik, telefon, email, vb. doğrulama
"""
import re
from typing import Tuple, Optional

class Dogrulayicilar:
    """Input validasyon araçları"""
    
    @staticmethod
    def tc_kimlik_dogrula(tc: str) -> Tuple[bool, str]:
        """
        TC Kimlik numarası algoritması ile doğrulama
        
        Returns:
            (geçerli_mi, mesaj/temizlenmiş_tc)
        
        Kullanım:
            gecerli, mesaj = Dogrulayicilar.tc_kimlik_dogrula('12345678901')
            if not gecerli:
                QMessageBox.warning(self, "Hata", mesaj)
                return
        """
        tc = str(tc).strip()
        
        # Uzunluk kontrolü
        if len(tc) != 11:
            return False, "TC Kimlik 11 haneli olmalıdır"
        
        # Sadece rakam kontrolü
        if not tc.isdigit():
            return False, "TC Kimlik sadece rakam içermelidir"
        
        # İlk hane 0 olamaz
        if tc[0] == '0':
            return False, "TC Kimlik'in ilk hanesi 0 olamaz"
        
        # Algoritma kontrolü
        digits = [int(d) for d in tc]
        
        # 10. hane kontrolü
        sum_odd = sum(digits[0:9:2])  # 1,3,5,7,9. haneler
        sum_even = sum(digits[1:9:2])  # 2,4,6,8. haneler
        check_10 = ((sum_odd * 7) - sum_even) % 10
        
        if check_10 != digits[9]:
            return False, "Geçersiz TC Kimlik numarası (10. hane)"
        
        # 11. hane kontrolü
        sum_all = sum(digits[0:10])
        check_11 = sum_all % 10
        
        if check_11 != digits[10]:
            return False, "Geçersiz TC Kimlik numarası (11. hane)"
        
        return True, tc  # Geçerli, temizlenmiş TC döndür
    
    @staticmethod
    def telefon_dogrula(tel: str) -> Tuple[bool, str]:
        """
        Türkiye telefon numarası doğrulama
        
        Kabul edilen formatlar:
        - 0555 123 45 67
        - 05551234567
        - 555 123 45 67
        - 5551234567
        
        Returns:
            (geçerli_mi, temizlenmiş_telefon/hata_mesajı)
        """
        # Sadece rakamları al
        tel_temiz = re.sub(r'[^\d]', '', tel)
        
        # Uzunluk kontrolü
        if len(tel_temiz) not in [10, 11]:
            return False, "Telefon 10 veya 11 haneli olmalı"
        
        # 11 haneli ise 0 ile başlamalı
        if len(tel_temiz) == 11:
            if not tel_temiz.startswith('0'):
                return False, "11 haneli telefon 0 ile başlamalı"
        
        # 10 haneli ise başına 0 ekle
        if len(tel_temiz) == 10:
            tel_temiz = '0' + tel_temiz
        
        # Operatör kodu kontrolü (Türkiye)
        operator_codes = [
            '505', '506', '507',  # Turkcell
            '530', '531', '532', '533', '534', '535', '536', '537', '538', '539',  # Vodafone
            '541', '542', '543', '544', '545', '546', '547', '548', '549',  # Turk Telekom
            '551', '552', '553', '554', '555', '559'  # Diğer
        ]
        
        operator_code = tel_temiz[1:4]
        if operator_code not in operator_codes:
            return False, f"Geçersiz operatör kodu: {operator_code}"
        
        # Format: 0555 123 45 67
        formatted = f"{tel_temiz[0:4]} {tel_temiz[4:7]} {tel_temiz[7:9]} {tel_temiz[9:11]}"
        
        return True, formatted
    
    @staticmethod
    def email_dogrula(email: str) -> Tuple[bool, str]:
        """
        Email format doğrulama
        
        Returns:
            (geçerli_mi, küçük_harf_email/hata_mesajı)
        """
        email = email.strip().lower()
        
        # Regex pattern
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        if re.match(pattern, email):
            return True, email
        else:
            return False, "Geçersiz e-posta formatı"
    
    @staticmethod
    def sicil_no_dogrula(sicil: str, min_length: int = 3, max_length: int = 10) -> Tuple[bool, str]:
        """
        Sicil numarası doğrulama
        
        Args:
            sicil: Sicil numarası
            min_length: Minimum uzunluk
            max_length: Maximum uzunluk
        """
        sicil = sicil.strip()
        
        if not sicil:
            return False, "Sicil numarası boş olamaz"
        
        if len(sicil) < min_length:
            return False, f"Sicil numarası en az {min_length} karakter olmalı"
        
        if len(sicil) > max_length:
            return False, f"Sicil numarası en fazla {max_length} karakter olmalı"
        
        # Sadece alfanumerik
        if not sicil.isalnum():
            return False, "Sicil numarası sadece harf ve rakam içermeli"
        
        return True, sicil.upper()
    
    @staticmethod
    def tarih_aralik_dogrula(baslangic, bitis) -> Tuple[bool, str]:
        """
        İki tarih arası doğrulama (QDate nesneleri)
        
        Returns:
            (geçerli_mi, hata_mesajı)
        """
        if baslangic > bitis:
            return False, "Başlangıç tarihi bitiş tarihinden sonra olamaz"
        
        # Çok uzun aralık kontrolü (örn: 10 yıldan fazla)
        gun_farki = baslangic.daysTo(bitis)
        if gun_farki > 3650:  # 10 yıl
            return False, "Tarih aralığı 10 yıldan fazla olamaz"
        
        return True, ""
    
    @staticmethod
    def sayi_aralik_dogrula(sayi: str, min_val: float, max_val: float, 
                           alan_adi: str = "Değer") -> Tuple[bool, str]:
        """
        Sayı aralık kontrolü
        
        Kullanım:
            gecerli, mesaj = Dogrulayicilar.sayi_aralik_dogrula(
                self.txt_yas.text(), 
                min_val=18, 
                max_val=65, 
                alan_adi="Yaş"
            )
        """
        try:
            deger = float(sayi)
        except (ValueError, TypeError):
            return False, f"{alan_adi} sayısal bir değer olmalı"
        
        if deger < min_val:
            return False, f"{alan_adi} en az {min_val} olmalı"
        
        if deger > max_val:
            return False, f"{alan_adi} en fazla {max_val} olmalı"
        
        return True, str(deger)
```

---

#### 📝 DEĞİŞTİRİLECEK DOSYALAR

##### 20. `formlar/personel_ekle.py` - DEĞİŞTİRİLECEK
**Değişiklik: Import + kaydet fonksiyonu**

```python
# BAŞA EKLE:
from araclar.validators import Dogrulayicilar

# DEĞİŞTİR (kaydet fonksiyonu):
def kaydet(self):
    """Personel kaydetme - validasyon eklenmiş"""
    
    # 1. TC Kimlik Doğrulama
    tc = self.txt_tc.text().strip()
    gecerli, mesaj = Dogrulayicilar.tc_kimlik_dogrula(tc)
    
    if not gecerli:
        QMessageBox.warning(self, "Geçersiz TC Kimlik", mesaj)
        self.txt_tc.setFocus()
        self.txt_tc.selectAll()
        return
    
    tc = mesaj  # Temizlenmiş TC
    
    # 2. Telefon Doğrulama
    tel = self.txt_telefon.text().strip()
    if tel:  # Telefon opsiyonel ise
        gecerli, mesaj = Dogrulayicilar.telefon_dogrula(tel)
        if not gecerli:
            QMessageBox.warning(self, "Geçersiz Telefon", mesaj)
            self.txt_telefon.setFocus()
            return
        tel = mesaj  # Formatlanmış telefon
    
    # 3. Email Doğrulama
    email = self.txt_email.text().strip()
    if email:  # Email opsiyonel ise
        gecerli, mesaj = Dogrulayicilar.email_dogrula(email)
        if not gecerli:
            QMessageBox.warning(self, "Geçersiz E-posta", mesaj)
            self.txt_email.setFocus()
            return
        email = mesaj  # Küçük harfe çevrilmiş
    
    # 4. Diğer zorunlu alanlar
    ad_soyad = self.txt_ad_soyad.text().strip()
    if not ad_soyad:
        QMessageBox.warning(self, "Eksik Bilgi", "Ad Soyad alanı boş bırakılamaz")
        self.txt_ad_soyad.setFocus()
        return
    
    # ... Kayıt işlemine devam et ...
    try:
        # Kayıt kodu
        # ...
        
        # Başarılı olduysa cache temizle
        from google_baglanti import cache_temizle
        cache_temizle('personel', 'Personel')
        
        QMessageBox.information(self, "Başarılı", "Personel kaydedildi")
        self.close()
        
    except Exception as e:
        from araclar.hata_yonetimi import HataYoneticisi
        HataYoneticisi.hata_goster(e, self, "Kayıt sırasında hata oluştu")
```

---

## 📊 HAFTA 2 ÖZET

### Oluşturulacak Yeni Dosyalar (2 adet):
1. ✅ `araclar/cache_manager.py`
2. ✅ `araclar/validators.py`

### Değiştirilecek Dosyalar (7 adet):
1. ✅ `google_baglanti.py` (2 yeni fonksiyon ekle)
2. ✅ `formlar/personel_listesi.py` (cache kullan)
3. ✅ `formlar/cihaz_listesi.py` (cache kullan)
4. ✅ `formlar/rke_yonetim.py` (cache kullan)
5. ✅ `formlar/cihaz_ekle.py` (cache + validation)
6. ✅ `formlar/personel_ekle.py` (validation)
7. ✅ `formlar/ariza_kayit.py` (cache kullan)

### Beklenen Sonuç:
- ⚡ Form açılış: 2-5 sn → 0.2-0.5 sn (%90 hız artışı)
- ⚡ Liste yükleme: İlk yüklemede aynı, sonraki yüklemelerde %95 hız artışı
- ✅ Veri doğrulama: Geçersiz TC, telefon, email engellenecek

---

## 🎯 FAZ 1 GENEL ÖZET (2 Haftalık)

### 📦 Toplam Yeni Dosyalar: 6 adet
1. `araclar/hata_yonetimi.py`
2. `araclar/singleton.py`
3. `araclar/cache_manager.py`
4. `araclar/validators.py`
5. `.env.example`
6. `.gitignore`

### 📝 Değiştirilecek Dosyalar: ~30 adet
- `google_baglanti.py` (3 bölümde değişiklik)
- `requirements.txt`
- Ana formlar (personel, cihaz, rke): 10 dosya
- Diğer formlar: 20 dosya

### 📈 Beklenen Kazanımlar:
- %60-70 performans artışı
- %100 güvenlik iyileştirmesi (bare exception'lar gitti)
- Veri validasyonu aktif
- Thread-safe kod
- Credential güvenliği

---

## 📋 UYGULAMA KONTROLL LİSTESİ

### Hafta 1 - Gün 1-2
- [ ] `araclar/hata_yonetimi.py` oluştur
- [ ] `google_baglanti.py` exception düzelt
- [ ] `formlar/personel_ekle.py` exception düzelt
- [ ] `formlar/cihaz_ekle.py` exception düzelt
- [ ] Diğer 22 form dosyasında exception düzelt

### Hafta 1 - Gün 3-4
- [ ] `araclar/singleton.py` oluştur
- [ ] `google_baglanti.py` thread-safe yap
- [ ] Test: Birden fazla formu aynı anda aç, hata olmamalı

### Hafta 1 - Gün 5
- [ ] `.env.example` oluştur
- [ ] `.gitignore` oluştur
- [ ] `pip install python-dotenv` çalıştır
- [ ] `.env` dosyası oluştur
- [ ] `google_baglanti.py` env kullan
- [ ] `formlar/cihaz_ekle.py` env kullan

### Hafta 2 - Gün 1-3
- [ ] `araclar/cache_manager.py` oluştur
- [ ] `google_baglanti.py` cache fonksiyonları ekle
- [ ] `formlar/personel_listesi.py` cache kullan
- [ ] `formlar/cihaz_listesi.py` cache kullan
- [ ] `formlar/rke_yonetim.py` cache kullan
- [ ] `formlar/cihaz_ekle.py` cache kullan
- [ ] Test: Listeleri aç-kapat, ikinci açılış çok hızlı olmalı

### Hafta 2 - Gün 4-5
- [ ] `araclar/validators.py` oluştur
- [ ] `formlar/personel_ekle.py` validation ekle
- [ ] `formlar/cihaz_ekle.py` validation ekle
- [ ] Test: Geçersiz TC gir, hata vermeli
- [ ] Test: Geçersiz telefon gir, hata vermeli

---

## ⚠️ DİKKAT EDİLMESİ GEREKENLER

1. **Backup Al:** Değişiklik yapmadan önce tüm projeyi yedekle
2. **Git Kullan:** Her gün sonunda commit at
3. **Test Et:** Her değişiklikten sonra ilgili formu aç ve test et
4. **Adım Adım:** Bir dosyayı bitir, test et, sonra diğerine geç
5. **Hata Logları:** Hata oluşursa console'daki logları oku

---

## 🚀 SONRAKI ADIMLAR (FAZ 2)

Faz 1 tamamlandıktan sonra:
- Batch işlemler
- Lazy loading
- Asenkron form yükleme
- Repository Pattern

Bu aşamalar için ayrı bir harita hazırlanacak.
