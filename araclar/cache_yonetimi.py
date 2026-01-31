# -*- coding: utf-8 -*-
import threading
import logging
from datetime import datetime, timedelta
from typing import Optional, Any, Dict

# Loglama
logger = logging.getLogger("CacheYonetimi")

class VeritabaniOnbellegi:
    """
    Thread-safe, TTL (Time-To-Live) destekli önbellek sistemi.
    Verileri belirli bir süre (varsayılan 5 dk) hafızada tutar.
    """
    
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        """Singleton Pattern: Tek bir önbellek örneği oluşturur."""
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(VeritabaniOnbellegi, cls).__new__(cls)
                    cls._instance._init_cache()
        return cls._instance

    def _init_cache(self):
        self._cache: Dict[str, Any] = {}
        self._ttl_cache: Dict[str, datetime] = {}
        # Cache erişimi için ayrı kilit (Singleton kilidiyle karışmasın)
        self._data_lock = threading.RLock()

    def get(self, key: str) -> Optional[Any]:
        """Önbellekten veri çeker. Süresi dolmuşsa None döner."""
        with self._data_lock:
            if key not in self._cache:
                return None
            
            # Süre kontrolü
            if key in self._ttl_cache:
                if datetime.now() > self._ttl_cache[key]:
                    logger.debug(f"Cache expired: {key}")
                    self.invalidate(key) # Temizle
                    return None
            
            logger.debug(f"Cache HIT: {key}")
            return self._cache[key]

    def set(self, key: str, value: Any, ttl_seconds: int = 300):
        """Veriyi önbelleğe yazar."""
        with self._data_lock:
            self._cache[key] = value
            self._ttl_cache[key] = datetime.now() + timedelta(seconds=ttl_seconds)
            logger.debug(f"Cache SET: {key} (TTL: {ttl_seconds}s)")

    def invalidate(self, key: str):
        """Belirli bir anahtarı siler."""
        with self._data_lock:
            self._cache.pop(key, None)
            self._ttl_cache.pop(key, None)

    def invalidate_pattern(self, pattern: str):
        """İsim desenine uyan (örn: 'personel:') tüm kayıtları siler."""
        with self._data_lock:
            keys_to_remove = [k for k in self._cache.keys() if pattern in k]
            for k in keys_to_remove:
                self.invalidate(k)
            if keys_to_remove:
                logger.info(f"Cache pattern '{pattern}' cleaned ({len(keys_to_remove)} items).")

    def clear_all(self):
        """Tüm önbelleği temizler."""
        with self._data_lock:
            self._cache.clear()
            self._ttl_cache.clear()
            logger.warning("All cache cleared.")

# Global erişim noktası
cache = VeritabaniOnbellegi()