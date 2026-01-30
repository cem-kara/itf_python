# -*- coding: utf-8 -*-
import bcrypt  # Yeni bağımlılık
import logging

# Logger tanımı (Standart teknik ekleme)
logger = logging.getLogger(__name__)

class GuvenlikAraclari:
    @staticmethod
    def sifrele(sifre):
        """
        Verilen şifreyi bcrypt algoritması ile tuzlayarak (salt) hashler.
        """
        if not sifre: 
            return ""
        
        try:
            # Şifreyi byte'a çevir
            sifre_bytes = str(sifre).encode('utf-8')
            
            # Salt (tuz) oluştur ve hashle
            salt = bcrypt.gensalt()
            hash_obj = bcrypt.hashpw(sifre_bytes, salt)
            
            # Veritabanına kaydedilmek üzere string olarak döndür
            return hash_obj.decode('utf-8')
        except Exception as e:
            logger.error(f"Şifreleme sırasında hata oluştu: {e}")
            return ""

    @staticmethod
    def dogrula(girilen_sifre, kayitli_hash):
        """
        Girilen düz şifrenin hash'i ile kayıtlı bcrypt hash'ini güvenli şekilde karşılaştırır.
        """
        if not girilen_sifre or not kayitli_hash:
            return False
            
        try:
            # Girdileri byte formatına çevir
            girilen_bytes = str(girilen_sifre).encode('utf-8')
            kayitli_bytes = str(kayitli_hash).encode('utf-8')
            
            # bcrypt.checkpw zamanlama saldırılarına karşı güvenli karşılaştırma yapar
            return bcrypt.checkpw(girilen_bytes, kayitli_bytes)
        except Exception as e:
            logger.error(f"Şifre doğrulama sırasında hata oluştu: {e}")
            return False

# ESKİ SHA-256 MANTIĞI (Yasa gereği açıklama satırı olarak korundu)
# def sifrele_old(sifre):
#     sifre_bytes = str(sifre).encode('utf-8')
#     return hashlib.sha256(sifre_bytes).hexdigest()