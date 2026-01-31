# config/settings.py (YENİ)
from dataclasses import dataclass
from typing import Optional
import os
from pathlib import Path

@dataclass
class DatabaseConfig:
    personel_file: str = "itf_personel_vt"
    cihaz_file: str = "itf_cihaz_vt"
    rke_file: str = "itf_rke_vt"
    cache_ttl_seconds: int = 300  # 5 dakika

@dataclass
class UIConfig:
    window_width: int = 1280
    window_height: int = 800
    theme: str = "dark"
    font_family: str = "Segoe UI"
    font_size: int = 10

@dataclass
class PerformanceConfig:
    enable_cache: bool = True
    batch_size: int = 100
    lazy_load_threshold: int = 500  # 500+ kayıt varsa lazy load
    thread_pool_size: int = 4

@dataclass
class SecurityConfig:
    session_timeout_minutes: int = 30
    max_login_attempts: int = 3
    password_min_length: int = 8
    enable_audit_log: bool = True

@dataclass
class AppConfig:
    """Ana konfigürasyon"""
    database: DatabaseConfig = DatabaseConfig()
    ui: UIConfig = UIConfig()
    performance: PerformanceConfig = PerformanceConfig()
    security: SecurityConfig = SecurityConfig()
    
    # Ortam değişkenleri
    env: str = os.getenv('APP_ENV', 'production')
    debug: bool = os.getenv('DEBUG', 'False').lower() == 'true'
    log_level: str = os.getenv('LOG_LEVEL', 'INFO')
    
    @classmethod
    def load_from_file(cls, config_path: Optional[Path] = None):
        """YAML veya JSON dosyasından yükle"""
        if config_path and config_path.exists():
            # TODO: YAML/JSON parse
            pass
        return cls()

# Kullanım:
config = AppConfig.load_from_file()

if config.performance.enable_cache:
    cache_manager = CacheManager(ttl=config.database.cache_ttl_seconds)