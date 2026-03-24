from pathlib import Path

APP_NAME = "منصة الرصد الإعلامي لقطاع الإعلام"
OWNER_NAME = "قطاع التطوير التقني"
COPYRIGHT_NOTICE = "جميع الحقوق محفوظة لقطاع التطوير التقني"

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
EXPORTS_DIR = BASE_DIR / "exports"
DB_PATH = DATA_DIR / "monitoring.db"

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "Admin@123"
DEFAULT_FULL_NAME = "مدير النظام"

SOURCE_LABELS = {
    "web": "ويب عام",
    "news": "أخبار",
    "x": "X",
    "youtube": "YouTube",
    "official": "مواقع رسمية",
    "direct": "روابط مباشرة",
    "images": "صور",
}

CATEGORY_LABELS = [
    "شكوى",
    "استغاثة",
    "طلب مساعدة",
    "انتقاد",
    "إشادة",
    "خبر محايد",
    "غير ذي صلة",
    "مكرر",
]

DEFAULT_SOURCE_SELECTION = ["web", "news", "x", "youtube", "official"]

FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("C:/Windows/Fonts/tahoma.ttf"),
    Path("C:/Windows/Fonts/segoeui.ttf"),
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

