# araclar/validators.py (YENİ)
import re
from typing import Tuple

class Dogrulayicilar:
    
    @staticmethod
    def tc_kimlik_dogrula(tc: str) -> Tuple[bool, str]:
        """
        TC Kimlik numarası algoritması ile doğrulama
        Returns: (geçerli_mi, hata_mesaji)
        """
        tc = tc.strip()
        
        # Uzunluk kontrolü
        if len(tc) != 11:
            return False, "TC Kimlik 11 haneli olmalıdır"
        
        # Sadece rakam kontrolü
        if not tc.isdigit():
            return False, "Sadece rakam içermelidir"
        
        # İlk hane 0 olamaz
        if tc[0] == '0':
            return False, "İlk hane 0 olamaz"
        
        # Algoritma kontrolü
        digits = [int(d) for d in tc]
        
        # 10. hane kontrolü
        sum_odd = sum(digits[0:9:2])  # 1,3,5,7,9
        sum_even = sum(digits[1:9:2])  # 2,4,6,8
        if ((sum_odd * 7) - sum_even) % 10 != digits[9]:
            return False, "Geçersiz TC Kimlik numarası"
        
        # 11. hane kontrolü
        if sum(digits[0:10]) % 10 != digits[10]:
            return False, "Geçersiz TC Kimlik numarası"
        
        return True, "Geçerli"
    
    @staticmethod
    def telefon_dogrula(tel: str) -> Tuple[bool, str]:
        """0555 123 45 67 veya 05551234567 formatı"""
        tel = re.sub(r'[^\d]', '', tel)  # Sadece rakamları al
        
        if len(tel) not in [10, 11]:
            return False, "Telefon 10-11 haneli olmalı"
        
        if len(tel) == 11 and not tel.startswith('0'):
            return False, "11 haneli telefon 0 ile başlamalı"
        
        if len(tel) == 10:
            tel = '0' + tel
        
        # Başlangıç kontrolü (Türkiye operatörleri)
        if not tel[1:4] in ['505', '506', '507', '530', '531', '532', '533', 
                            '534', '535', '536', '537', '538', '539', '541', 
                            '542', '543', '544', '545', '546', '547', '548', 
                            '549', '551', '552', '553', '554', '555', '559']:
            return False, "Geçersiz operatör kodu"
        
        return True, tel  # Temizlenmiş format döndür
    
    @staticmethod
    def email_dogrula(email: str) -> Tuple[bool, str]:
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if re.match(pattern, email):
            return True, email.lower()
        return False, "Geçersiz e-posta formatı"

# Kullanım:
class PersonelEkle(QWidget):
    def kaydet(self):
        tc = self.txt_tc.text()
        gecerli, mesaj = Dogrulayicilar.tc_kimlik_dogrula(tc)
        
        if not gecerli:
            show_error("Hata", mesaj, self)
            self.txt_tc.setFocus()
            return
        
        # Devam et...