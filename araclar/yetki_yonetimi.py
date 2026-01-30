# -*- coding: utf-8 -*-
import sys
import os
import logging
from araclar.ortak_araclar import show_toast
from araclar.log_yonetimi import LogYoneticisi

# Standart Logger tanımı
logger = logging.getLogger(__name__)

# --- YOL AYARLARI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

try:
    from google_baglanti import veritabani_getir
except ImportError:
    logger.critical("HATA: google_baglanti modülü bulunamadı.")
    def veritabani_getir(t, s): return None

class YetkiYoneticisi:
    """
    Kullanıcı rollerine göre formlardaki nesneleri (buton, menü vb.) 
    gizleyen veya pasif yapan merkezi sınıf.
    """
    
    # Hafızada tutulacak yetki haritası
    _yetki_cache = {} 
    _aktif_rol = "viewer"

    @staticmethod
    def yetkileri_yukle(aktif_rol):
        """
        Veritabanından o role ait kısıtlamaları çeker.
        """
        YetkiYoneticisi._aktif_rol = aktif_rol
        YetkiYoneticisi._yetki_cache = {}

        try:
            # Not: Veritabanı sekme adınızın 'Rol_Yetkileri' olduğundan emin olun
            ws = veritabani_getir('sabit', 'Rol_Yetkileri')
            
            if not ws:
                logger.error("Yetki tablosuna ulaşılamadı.")
                return

            records = ws.get_all_records()
            count = 0
            
            for row in records:
                db_rol = str(row.get('Rol', '')).strip()
                
                if db_rol == aktif_rol:
                    f_kod = str(row.get('Form_Kodu', '')).strip()
                    o_adi = str(row.get('Oge_Adi', '')).strip()
                    islem = str(row.get('Islem', '')).strip().upper()

                    if not f_kod or not o_adi:
                        continue

                    if f_kod not in YetkiYoneticisi._yetki_cache:
                        YetkiYoneticisi._yetki_cache[f_kod] = {}
                    
                    YetkiYoneticisi._yetki_cache[f_kod][o_adi] = islem
                    count += 1
            
            logger.info(f"Yetkiler yüklendi. Rol: {aktif_rol}, Kural Sayısı: {count}")
            
        except Exception as e:
            logger.error(f"Yetki yükleme hatası: {e}", exc_info=True)

    @staticmethod
    def form_yetkilerini_uygul(form_instance, form_kodu):
        """
        Bir forma yetki kurallarını uygular.
        """
        if form_kodu not in YetkiYoneticisi._yetki_cache:
            return 

        kurallar = YetkiYoneticisi._yetki_cache[form_kodu]

        for oge_adi, islem in kurallar.items():
            if hasattr(form_instance, oge_adi):
                widget = getattr(form_instance, oge_adi)
                try:
                    if islem == 'GIZLE':
                        widget.setVisible(False)
                    elif islem == 'PASIF':
                        widget.setEnabled(False)
                    
                    logger.debug(f"Yetki uygulandı: {form_kodu} -> {oge_adi} ({islem})")
                except Exception as e:
                    logger.error(f"Yetki uygulama hatası ({oge_adi}): {e}")
            else:
                logger.warning(f"Yetki kuralı var ama widget bulunamadı: {form_kodu} -> {oge_adi}")

    @staticmethod
    def uygula(form_instance, form_kodu):
        """
        Geriye uyumluluk için eklenmiştir. 
        main.py içindeki YetkiYoneticisi.uygula çağrılarının hata vermesini engeller.
        """
        YetkiYoneticisi.form_yetkilerini_uygul(form_instance, form_kodu)