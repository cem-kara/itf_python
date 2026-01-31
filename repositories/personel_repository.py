# -*- coding: utf-8 -*-
import logging
from typing import List, Dict, Optional, Any

# Proje içi modüller
try:
    from google_baglanti import veritabani_getir, veritabani_getir_cached
    from araclar.cache_yonetimi import cache
except ImportError:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from google_baglanti import veritabani_getir, veritabani_getir_cached
    from araclar.cache_yonetimi import cache

logger = logging.getLogger("PersonelRepository")

class PersonelRepository:
    """
    Personel verilerine erişim sağlayan katman.
    Google Sheets işlemlerini soyutlar.
    """
    
    def __init__(self):
        self.vt_tipi = 'personel'
        self.sayfa_adi = 'Personel'

    def get_all(self, force_refresh: bool = False) -> List[Dict]:
        """Tüm personel listesini getirir (Cache destekli)."""
        try:
            return veritabani_getir_cached(self.vt_tipi, self.sayfa_adi, force_refresh=force_refresh)
        except Exception as e:
            logger.error(f"Personel listesi alınamadı: {e}")
            return []

    def get_by_tc(self, tc_kimlik: str) -> Optional[Dict]:
        """TC Kimlik numarasına göre personel arar."""
        tum_personel = self.get_all()
        for p in tum_personel:
            if str(p.get('Kimlik_No', '')).strip() == str(tc_kimlik).strip():
                return p
        return None

    def create(self, personel_data: List) -> bool:
        """Yeni personel ekler."""
        try:
            ws = veritabani_getir(self.vt_tipi, self.sayfa_adi)
            ws.append_row(personel_data)
            self._invalidate_cache()
            return True
        except Exception as e:
            logger.error(f"Personel ekleme hatası: {e}")
            raise e

    # -------------------------------------------------------------------------
    # 🔴 GÜNCELLENEN UPDATE METODU (SORUN ÇÖZÜMÜ)
    # -------------------------------------------------------------------------
    def update(self, tc_kimlik: str, guncel_veri: Dict[str, Any]) -> bool:
        """
        Personel bilgisini günceller.
        Args:
            tc_kimlik: Güncellenecek personelin TC'si
            guncel_veri: {'SütunAdı': 'YeniDeğer', ...} şeklinde sözlük
        """
        try:
            # 1. Worksheet nesnesini al (Cache KULLANMA, direkt API)
            ws = veritabani_getir(self.vt_tipi, self.sayfa_adi)
            
            # 2. TC Kimlik Numarasının bulunduğu hücreyi bul
            # Not: Bu işlem API kotası harcar ama güvenlidir.
            cell = ws.find(str(tc_kimlik))
            
            if not cell:
                logger.warning(f"Güncelleme başarısız: {tc_kimlik} bulunamadı.")
                return False
            
            # 3. Sütun Başlıklarını Al (Hangi sütun kaçıncı sırada?)
            # 1. satırı başlık olarak kabul ediyoruz
            headers = ws.row_values(1)
            
            # 4. Her bir güncellenecek alan için işlem yap
            updates = []
            for col_name, new_value in guncel_veri.items():
                if col_name in headers:
                    # Sütun indeksini bul (1 tabanlı indeksleme için +1)
                    col_index = headers.index(col_name) + 1
                    
                    # Hücreyi güncelle
                    # update_cell(row, col, val)
                    ws.update_cell(cell.row, col_index, new_value)
                    logger.info(f"{tc_kimlik} -> {col_name} güncellendi: {new_value}")
                else:
                    logger.warning(f"Sütun bulunamadı: {col_name}")

            # 5. İşlem bitti, cache'i temizle
            self._invalidate_cache()
            return True

        except Exception as e:
            logger.error(f"Güncelleme hatası ({tc_kimlik}): {e}")
            return False

    def delete(self, tc_kimlik: str) -> bool:
        """Personeli siler."""
        try:
            ws = veritabani_getir(self.vt_tipi, self.sayfa_adi)
            cell = ws.find(str(tc_kimlik))
            if cell:
                ws.delete_rows(cell.row)
                self._invalidate_cache()
                return True
            return False
        except Exception as e:
            logger.error(f"Silme hatası: {e}")
            return False

    def _invalidate_cache(self):
        """Bu repository ile ilgili cache'i temizler."""
        if cache:
            cache.invalidate_pattern(f"{self.vt_tipi}:{self.sayfa_adi}")
            logger.info("Personel cache temizlendi.")
    
    # ... (Mevcut kodlar) ...

    def izin_gecmisi_getir(self, tc_kimlik: str) -> List[Dict]:
        """Belirli bir personelin izin geçmişini getirir."""
        try:
            tum_izinler = veritabani_getir_cached(self.vt_tipi, 'izin_giris', force_refresh=True)
            
            # Personelin izinlerini filtrele
            personel_izinleri = [
                izin for izin in tum_izinler 
                if str(izin.get('personel_id', '')).strip() == str(tc_kimlik).strip()
            ]
            return personel_izinleri
        except Exception as e:
            logger.error(f"İzin geçmişi alma hatası: {e}")
            return []

    def izin_ekle(self, izin_verisi: List) -> bool:
        """Yeni izin kaydı ekler."""
        try:
            ws = veritabani_getir(self.vt_tipi, 'izin_giris')
            ws.append_row(izin_verisi)
            self._invalidate_cache() # Cache temizle
            return True
        except Exception as e:
            logger.error(f"İzin ekleme hatası: {e}")
            raise e

    def bakiye_guncelle(self, tc_kimlik: str, kolon_adi: str, miktar: int, islem: str = "dus") -> bool:
        """
        Personelin izin bakiyesini günceller.
        islem: 'dus' (kullanılanı artır), 'iade' (kullanılanı azalt)
        """
        try:
            ws = veritabani_getir(self.vt_tipi, 'izin_bilgi')
            cell = ws.find(str(tc_kimlik))
            
            if not cell:
                logger.warning(f"Bakiye güncelleme için personel bulunamadı: {tc_kimlik}")
                return False
                
            headers = ws.row_values(1)
            if kolon_adi not in headers:
                logger.error(f"Bakiye sütunu bulunamadı: {kolon_adi}")
                return False
                
            col_idx = headers.index(kolon_adi) + 1
            mevcut_deger = int(ws.cell(cell.row, col_idx).value or 0)
            
            yeni_deger = mevcut_deger + miktar if islem == "dus" else max(0, mevcut_deger - miktar)
            
            ws.update_cell(cell.row, col_idx, yeni_deger)
            
            # Eğer Yıllık veya Şua izniyse, Kalan hakkı da güncellemek gerekir
            # (Bu mantık Service katmanında daha detaylı yönetilebilir ama basitçe burada da yapılabilir)
            # Şimdilik sadece "Kullanılan"ı güncelliyoruz.
            
            return True
        except Exception as e:
            logger.error(f"Bakiye güncelleme hatası: {e}")
            return False

    def izin_durum_guncelle(self, kayit_id: str, yeni_durum: str) -> bool:
        """İzin kaydının durumunu (örn: İptal Edildi) günceller."""
        try:
            ws = veritabani_getir(self.vt_tipi, 'izin_giris')
            # ID genelde 1. sütundadır ama başlık kontrolü daha iyi
            cell = ws.find(str(kayit_id))
            
            if cell:
                headers = ws.row_values(1)
                col_idx = headers.index('Durum') + 1
                ws.update_cell(cell.row, col_idx, yeni_durum)
                self._invalidate_cache()
                return True
            return False
        except Exception as e:
            logger.error(f"İzin durum güncelleme hatası: {e}")
            return False