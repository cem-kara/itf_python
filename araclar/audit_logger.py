# araclar/audit_logger.py (YENİ)
import sqlite3
from datetime import datetime
from typing import Optional

class AuditLogger:
    """Tüm kritik işlemleri logla"""
    
    def __init__(self, db_path='logs/audit.db'):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    kullanici TEXT NOT NULL,
                    islem_tipi TEXT NOT NULL,
                    tablo TEXT,
                    kayit_id TEXT,
                    detay TEXT,
                    ip_adresi TEXT,
                    basarili INTEGER DEFAULT 1
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_log(timestamp)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_kullanici ON audit_log(kullanici)')
    
    def log(self, kullanici: str, islem_tipi: str, tablo: str = None, 
            kayit_id: str = None, detay: str = None, basarili: bool = True):
        """Audit kaydı oluştur"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO audit_log 
                (timestamp, kullanici, islem_tipi, tablo, kayit_id, detay, basarili)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().isoformat(),
                kullanici,
                islem_tipi,
                tablo,
                kayit_id,
                detay,
                1 if basarili else 0
            ))
    
    def get_kullanici_loglari(self, kullanici: str, limit: int = 100):
        """Kullanıcının son işlemleri"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT timestamp, islem_tipi, tablo, detay 
                FROM audit_log 
                WHERE kullanici = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (kullanici, limit))
            return cursor.fetchall()

# main.py içinde global instance:
audit_logger = AuditLogger()

# Kullanım örnekleri:
class PersonelEkle(QWidget):
    def kaydet(self):
        # ... kayıt işlemi ...
        
        audit_logger.log(
            kullanici=self.kullanici_adi,
            islem_tipi='PERSONEL_EKLEME',
            tablo='Personel',
            kayit_id=yeni_sicil_no,
            detay=f"Yeni personel: {ad_soyad}"
        )

class CihazSil(QWidget):
    def sil(self):
        try:
            # ... silme işlemi ...
            audit_logger.log(
                kullanici=self.kullanici_adi,
                islem_tipi='CIHAZ_SILME',
                tablo='Cihazlar',
                kayit_id=cihaz_id,
                basarili=True
            )
        except Exception as e:
            audit_logger.log(
                kullanici=self.kullanici_adi,
                islem_tipi='CIHAZ_SILME',
                detay=str(e),
                basarili=False
            )