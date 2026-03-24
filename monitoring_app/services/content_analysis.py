from __future__ import annotations

from collections import Counter
from typing import Dict, List, Tuple

from rapidfuzz import fuzz

from monitoring_app.models import SearchResult
from monitoring_app.utils.text import compact_text, normalize_text, overlap_ratio


CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "استغاثة": [
        "استغاثه",
        "انقذوا",
        "انقاذ",
        "استنجد",
        "استنجاد",
        "صرخه",
        "عاجل",
        "طارئ",
        "حرج",
        "urgent",
        "emergency",
    ],
    "طلب مساعدة": [
        "طلب مساعده",
        "نحتاج دعم",
        "نحتاج مساعده",
        "يرجو المساعده",
        "بحاجه الى",
        "دعم عاجل",
        "help",
        "support needed",
    ],
    "شكوى": [
        "شكوى",
        "شكاوى",
        "يشتكي",
        "يتضرر",
        "معاناه",
        "تظلم",
        "تضرر",
        "complaint",
    ],
    "انتقاد": [
        "انتقاد",
        "ينتقد",
        "قصور",
        "فشل",
        "تقصير",
        "سوء",
        "اخفاق",
        "critic",
        "failure",
    ],
    "إشادة": [
        "اشاده",
        "يشيد",
        "يشكر",
        "ممتاز",
        "نجاح",
        "رائع",
        "مبادره مميزه",
        "praise",
        "thank",
    ],
    "خبر محايد": [
        "اعلن",
        "صرح",
        "افتتح",
        "تقرير",
        "بيان",
        "news",
        "report",
        "official statement",
    ],
}

RISK_BASE = {
    "استغاثة": 90,
    "طلب مساعدة": 75,
    "شكوى": 70,
    "انتقاد": 60,
    "خبر محايد": 35,
    "إشادة": 10,
    "غير ذي صلة": 0,
    "مكرر": 5,
}

RISK_SIGNALS = {
    "high": ["وفاه", "اصابه", "فساد", "تسريب", "تعطل", "انقطاع", "حريق", "حادث", "crisis"],
    "medium": ["عاجل", "طارئ", "استغاثه", "احتجاج", "غضب", "شكوى", "critical"],
}


class ContentAnalysisService:
    def analyze_result(self, result: SearchResult, query: str) -> SearchResult:
        text = normalize_text(result.combined_text)
        relevance = max(overlap_ratio(query, result.combined_text), fuzz.token_set_ratio(query, result.combined_text) / 100)
        category, confidence, matched_signals = self._classify(text, relevance)
        risk_score = self._calculate_risk(text, category, relevance)

        result.classification = category
        result.classification_confidence = round(confidence, 2)
        result.risk_score = risk_score
        result.relevance_score = round(min(relevance, 1.0), 2)
        result.matched_signals = matched_signals
        return result

    def _classify(self, text: str, relevance: float) -> Tuple[str, float, List[str]]:
        if not text:
            return "غير ذي صلة", 0.1, ["نص محدود"]

        scores: Dict[str, float] = {}
        matched_signals: Dict[str, List[str]] = {}
        for category, keywords in CATEGORY_KEYWORDS.items():
            hits = [keyword for keyword in keywords if keyword in text]
            if hits:
                scores[category] = len(hits) * 1.6
                matched_signals[category] = hits

        if relevance < 0.12 and not scores:
            return "غير ذي صلة", 0.22, ["ارتباط منخفض بالبحث"]

        if not scores:
            confidence = min(0.74, 0.35 + (relevance * 0.5))
            return "خبر محايد", confidence, ["سياق خبري دون مؤشرات تصنيف حادة"]

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        category, top_score = ranked[0]
        if category == "استغاثة" and "طلب مساعده" in text:
            top_score += 1.0
        if category == "إشادة" and any(word in text for word in ("شكوى", "انتقاد", "فشل")):
            top_score -= 0.8

        if top_score <= 0:
            return "خبر محايد", 0.4, ["إشارات متداخلة"]

        confidence = min(0.97, 0.38 + (top_score * 0.09) + (relevance * 0.25))
        return category, confidence, matched_signals.get(category, [])

    def _calculate_risk(self, text: str, category: str, relevance: float) -> int:
        risk = RISK_BASE.get(category, 20)
        high_hits = sum(1 for keyword in RISK_SIGNALS["high"] if keyword in text)
        medium_hits = sum(1 for keyword in RISK_SIGNALS["medium"] if keyword in text)
        risk += high_hits * 9
        risk += medium_hits * 5
        risk += int(relevance * 10)
        return max(0, min(100, risk))

    def summarize_cluster(self, results: List[SearchResult]) -> str:
        if not results:
            return ""
        snippets = []
        for item in results[:4]:
            combined = item.snippet or item.content_text or item.title
            if combined:
                snippets.append(compact_text(combined, 180))
        if not snippets:
            return "لا توجد تفاصيل كافية لتوليد ملخص لهذه القضية."
        summary = " | ".join(dict.fromkeys(snippets))
        return compact_text(summary, 520)

    def dominant_category(self, results: List[SearchResult]) -> str:
        categories = [item.classification for item in results if item.classification != "مكرر"]
        if not categories:
            return "خبر محايد"
        return Counter(categories).most_common(1)[0][0]

    def average_confidence(self, results: List[SearchResult]) -> float:
        relevant = [item.classification_confidence for item in results if item.classification_confidence]
        if not relevant:
            return 0.0
        return round(sum(relevant) / len(relevant), 2)

    @staticmethod
    def similarity(left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        return fuzz.token_set_ratio(left, right) / 100
