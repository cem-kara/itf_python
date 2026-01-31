# araclar/progress_manager.py (YENİ)
from PySide6.QtWidgets import QProgressDialog
from PySide6.QtCore import Qt

class ProgressManager:
    """Merkezi progress dialog yönetimi"""
    
    @staticmethod
    def create(parent, title, message, maximum=0):
        """
        Progress dialog oluştur
        maximum=0: Belirsiz süre (busy indicator)
        maximum>0: Belirli adımlı işlem
        """
        progress = QProgressDialog(message, "İptal", 0, maximum, parent)
        progress.setWindowTitle(title)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(500)  # 500ms'den uzun sürecekse göster
        
        if maximum == 0:
            progress.setRange(0, 0)  # Busy indicator
        
        return progress

# Kullanım:
class CihazListesi(QWidget):
    def veri_yukle(self):
        progress = ProgressManager.create(
            self,
            "Veriler Yükleniyor",
            "Cihaz listesi hazırlanıyor...",
            maximum=0
        )
        
        self.worker = VeriYukleyiciThread()
        self.worker.tamamlandi.connect(lambda: progress.close())
        self.worker.start()