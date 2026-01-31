# -*- coding: utf-8 -*-
import os
from datetime import datetime

try:
    from docxtpl import DocxTemplate, InlineImage
    from docx.shared import Mm
except ImportError:
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
                raise Exception(f"Şablon bulunamadı: {tam_sablon_yolu}")

            doc = DocxTemplate(tam_sablon_yolu)

            # Resim İşleme
            if resimler:
                for etiket, dosya_yolu in resimler.items():
                    if dosya_yolu and os.path.exists(dosya_yolu):
                        # Resmi 35mm genişliğe sabitle (İhtiyaca göre parametre yapılabilir)
                        img_obj = InlineImage(doc, dosya_yolu, width=Mm(35))
                        veri_sozlugu[etiket] = img_obj
                    else:
                        veri_sozlugu[etiket] = "" # Resim yoksa boş bırak

            # Render ve Kayıt
            doc.render(veri_sozlugu)
            doc.save(cikti_yolu)
            return True

        except Exception as e:
            print(f"Rapor oluşturma hatası: {e}")
            return False