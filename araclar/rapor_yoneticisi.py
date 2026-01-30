# -*- coding: utf-8 -*-
import os
import logging # ZORUNLU EKLEME
from datetime import datetime
from araclar.ortak_araclar import show_toast # Yeni bildirim sistemi

# Logger tanımı
logger = logging.getLogger(__name__)

try:
    from docxtpl import DocxTemplate, InlineImage
    from docx.shared import Mm
except ImportError:
    logger.critical("docx-tpl kütüphanesi sistemde yüklü değil! Raporlama çalışmayacak.")
    # Sıfır Silme Yasası gereği eski print korunmuştur
    print("docx-tpl kütüphanesi eksik.")

class RaporYoneticisi:
    def __init__(self, sablon_klasoru_yolu):
        """
        Tüm rapor işlemleri için merkezi yönetici.
        sablon_klasoru_yolu: Word şablonlarının olduğu ana klasör.
        """
        self.sablon_dir = sablon_klasoru_yolu

    def word_olustur(self, sablon_adi, veri_sozlugu, cikti_yolu, resimler=None):
        """
        Word dosyasını oluşturur ve kaydeder.
        
        Args:
            sablon_adi (str): 'ozluk_sablon.docx' gibi.
            veri_sozlugu (dict): {{Degisken}} alanları için veri.
            cikti_yolu (str): Oluşturulacak dosyanın tam yolu.
            resimler (dict): {'Worddeki_Etiket': 'Resim_Dosya_Yolu'} formatında.
        
        Returns:
            bool: Başarılı ise True.
        """
        try:
            tam_sablon_yolu = os.path.join(self.sablon_dir, sablon_adi)
            
            if not os.path.exists(tam_sablon_yolu):
                error_msg = f"Şablon bulunamadı: {sablon_adi}"
                logger.error(error_msg)
                show_toast(error_msg, type="error")
                return False

            doc = DocxTemplate(tam_sablon_yolu)

            # Resim İşleme
            if resimler:
                for etiket, dosya_yolu in resimler.items():
                    if dosya_yolu and os.path.exists(dosya_yolu):
                        img_obj = InlineImage(doc, dosya_yolu, width=Mm(35))
                        veri_sozlugu[etiket] = img_obj
                    else:
                        logger.warning(f"Rapor resmi bulunamadı, atlanıyor: {dosya_yolu}")

            # Dosyayı oluştur
            doc.render(veri_sozlugu)
            doc.save(cikti_yolu)
            
            logger.info(f"Rapor başarıyla oluşturuldu: {cikti_yolu}")
            show_toast("Rapor Başarıyla Oluşturuldu", type="success")
            return True

        except Exception as e:
            error_detail = f"Rapor oluşturma hatası: {str(e)}"
            logger.error(error_detail, exc_info=True)
            show_toast("Rapor oluşturulamadı!", type="error")
            return False