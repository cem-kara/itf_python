# formlar/kunye_motoru.py
import os
import qrcode
from docxtpl import DocxTemplate, InlineImage
from docx2pdf import convert
from docx.shared import Mm
import logging

# Loglama
logger = logging.getLogger("KunyeMotoru")

class KunyeOlusturucu:
    def __init__(self, sablon_yolu):
        self.sablon_yolu = sablon_yolu
        self.gecici_docx = "temp_kunye.docx"
        self.gecici_pdf = "temp_kunye.pdf"
        self.gecici_qr = "temp_qr.png"

    def qr_kod_olustur(self, veri):
        """Cihaz verilerini içeren bir QR kod üretir."""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=2,
        )
        # QR Kod içeriği: Özet bilgi
        info_str = f"ID: {veri.get('cihaz_id')}\nMarka: {veri.get('marka')}\nModel: {veri.get('model')}\nSeri: {veri.get('seri_no')}"
        qr.add_data(info_str)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(self.gecici_qr)
        return self.gecici_qr

    def belge_olustur(self, veri_sozlugu, cikis_klasoru=None):
        """
        Word şablonunu doldurur, QR ekler ve PDF'e çevirir.
        Geriye PDF dosyasının yolunu döndürür.
        """
        try:
            doc = DocxTemplate(self.sablon_yolu)
            
            # QR Kodu oluştur ve sözlüğe ekle (Resim olarak)
            self.qr_kod_olustur(veri_sozlugu)
            
            # Word içine resmi gömmek için InlineImage nesnesi
            # Şablonda {{qr_kodu}} yazan yere resim gelir.
            qr_img = InlineImage(doc, self.gecici_qr, width=Mm(30))
            veri_sozlugu['qr_kodu'] = qr_img
            
            # Şablonu render et (Jinja2 motoru)
            doc.render(veri_sozlugu)
            
            # Geçici Docx olarak kaydet
            doc.save(self.gecici_docx)
            
            # PDF'e Dönüştür
            try:
                convert(self.gecici_docx, self.gecici_pdf)
                sonuc_dosyasi = self.gecici_pdf
            except Exception as e:
                logger.error(f"PDF Dönüşüm Hatası (Word kurulu mu?): {e}")
                # PDF yapamazsa DOCX döndürsün
                sonuc_dosyasi = self.gecici_docx

            return sonuc_dosyasi

        except Exception as e:
            logger.error(f"Künye oluşturma hatası: {e}")
            return None

    def temizle(self):
        """Geçici dosyaları siler."""
        for f in [self.gecici_docx, self.gecici_pdf, self.gecici_qr]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except: pass