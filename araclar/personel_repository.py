# repositories/personel_repository.py (YENİ)
class PersonelRepository:
    """Personel veri erişim katmanı"""
    
    def __init__(self, cache_service, sheets_service):
        self.cache = cache_service
        self.sheets = sheets_service
    
    def get_all(self, use_cache=True):
        cache_key = 'personel:all'
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cached
        
        ws = self.sheets.get_worksheet('personel', 'Personel')
        data = ws.get_all_records()
        self.cache.set(cache_key, data, ttl_seconds=300)
        return data
    
    def get_by_tc(self, tc_kimlik):
        ws = self.sheets.get_worksheet('personel', 'Personel')
        cell = ws.find(tc_kimlik)
        if cell:
            return ws.row_values(cell.row)
        return None
    
    def create(self, personel_data):
        ws = self.sheets.get_worksheet('personel', 'Personel')
        ws.append_row(personel_data)
        self.cache.invalidate_pattern('personel:')  # Cache temizle
        return True

# Form içinde kullanım:
class PersonelEkle(QWidget):
    def __init__(self, personel_repo):
        self.repo = personel_repo
    
    def kaydet(self):
        data = self.formu_oku()
        self.repo.create(data)  # ✅ Clean API