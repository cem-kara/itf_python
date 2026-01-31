# tests/test_personel_service.py (YENİ)
import unittest
from unittest.mock import Mock, patch
from services.personel_service import PersonelService

class TestPersonelService(unittest.TestCase):
    
    def setUp(self):
        """Her test öncesi çalışır"""
        self.mock_repo = Mock()
        self.mock_logger = Mock()
        self.service = PersonelService(self.mock_repo, self.mock_logger)
    
    def test_personel_ekle_basarili(self):
        """Başarılı personel ekleme senaryosu"""
        # Arrange
        form_data = {
            'tc_kimlik': '12345678901',
            'ad_soyad': 'Ahmet Yılmaz',
            'bolum': 'Radyoloji'
        }
        self.mock_repo.get_by_tc.return_value = None  # TC kayıtlı değil
        self.mock_repo.create.return_value = True
        
        # Act
        success, message = self.service.personel_ekle(form_data)
        
        # Assert
        self.assertTrue(success)
        self.assertIn('başarıyla', message)
        self.mock_repo.create.assert_called_once()
        self.mock_logger.log_action.assert_called_once()
    
    def test_personel_ekle_duplicate_tc(self):
        """Aynı TC ile ekleme denemesi"""
        # Arrange
        form_data = {'tc_kimlik': '12345678901', 'ad_soyad': 'Test', 'bolum': 'Test'}
        self.mock_repo.get_by_tc.return_value = {'tc_kimlik': '12345678901'}  # Zaten var
        
        # Act
        success, message = self.service.personel_ekle(form_data)
        
        # Assert
        self.assertFalse(success)
        self.assertIn('kayıtlı', message.lower())
        self.mock_repo.create.assert_not_called()  # Create çağrılmamalı
    
    def test_tc_kimlik_validasyonu(self):
        """TC Kimlik doğrulama"""
        from araclar.validators import Dogrulayicilar
        
        # Geçerli TC
        valid, msg = Dogrulayicilar.tc_kimlik_dogrula('10000000146')
        self.assertTrue(valid)
        
        # Geçersiz (10 hane)
        valid, msg = Dogrulayicilar.tc_kimlik_dogrula('1000000014')
        self.assertFalse(valid)

if __name__ == '__main__':
    unittest.main()