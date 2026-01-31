# araclar/cache_yonetimi.py (YENİ DOSYA)
from datetime import datetime, timedelta
from typing import Optional, Any, Dict
import threading

class VeritabaniOnbellegi:
    """
    Thread-safe, TTL destekli önbellek sistemi.
    Redis benzeri ancak local hafıza tabanlı.
    """
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl_cache: Dict[str, datetime] = {}
        self._lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        """Önbellekten veri al. TTL dolmuşsa None döner."""
        with self._lock:
            if key not in self._cache:
                return None
            
            # TTL kontrolü
            if key in self._ttl_cache:
                if datetime.now() > self._ttl_cache[key]:
                    # Süresi dolmuş
                    del self._cache[key]
                    del self._ttl_cache[key]
                    return None
            
            return self._cache[key]
    
    def set(self, key: str, value: Any, ttl_seconds: int = 300):
        """Veriyi önbelleğe al. Varsayılan TTL: 5 dakika"""
        with self._lock:
            self._cache[key] = value
            self._ttl_cache[key] = datetime.now() + timedelta(seconds=ttl_seconds)
    
    def invalidate(self, key: str):
        """Belirli bir anahtarı geçersiz kıl"""
        with self._lock:
            self._cache.pop(key, None)
            self._ttl_cache.pop(key, None)
    
    def invalidate_pattern(self, pattern: str):
        """Belirli bir pattern'e uyan tüm anahtarları temizle"""
        with self._lock:
            keys_to_remove = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_remove:
                self._cache.pop(key, None)
                self._ttl_cache.pop(key, None)
    
    def clear(self):
        """Tüm önbelleği temizle"""
        with self._lock:
            self._cache.clear()
            self._ttl_cache.clear()

# Global singleton instance
_cache_instance = VeritabaniOnbellegi()

def get_cache() -> VeritabaniOnbellegi:
    return _cache_instance


# google_baglanti.py içinde kullanım:
def veritabani_getir_cached(vt_tipi: str, sayfa_adi: str, use_cache=True):
    """Önbellek destekli veritabanı getirme"""
    cache_key = f"{vt_tipi}:{sayfa_adi}"
    
    if use_cache:
        cached_data = get_cache().get(cache_key)
        if cached_data:
            logger.info(f"✅ Cache HIT: {cache_key}")
            return cached_data
    
    logger.info(f"❌ Cache MISS: {cache_key} - Veritabanından çekiliyor...")
    ws = veritabani_getir(vt_tipi, sayfa_adi)
    data = ws.get_all_records()
    
    # Cache'e kaydet (5 dakika TTL)
    get_cache().set(cache_key, data, ttl_seconds=300)
    
    return data

# Form içinde kullanım:
class PersonelListesiPenceresi(QWidget):
    def veri_yukle(self):
        # Cache kullanarak veri çek
        personeller = veritabani_getir_cached('personel', 'Personel', use_cache=True)
        self.tabloyu_doldur(personeller)
    
    def yeni_personel_eklendi(self):
        # Veri değişti, cache'i temizle
        get_cache().invalidate('personel:Personel')
        self.veri_yukle()  # Yeniden yükle