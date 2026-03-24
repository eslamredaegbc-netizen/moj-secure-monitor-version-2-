from __future__ import annotations

from typing import Dict, Iterable, List

from monitoring_app.config import SOURCE_LABELS
from monitoring_app.models import SearchOptions, SearchResult
from monitoring_app.services.media_service import PageMediaService
from monitoring_app.utils.text import dedupe_urls, extract_domain


class MultiSourceSearchService:
    def __init__(self) -> None:
        self.media_service = PageMediaService()

    def run(self, query: str, options: SearchOptions) -> List[SearchResult]:
        unique_urls = set()
        collected: List[SearchResult] = []

        for raw_result in self._collect_results(query, options):
            unique_key = (raw_result.url or raw_result.title).strip().lower()
            if not unique_key or unique_key in unique_urls:
                continue
            unique_urls.add(unique_key)

            enrichment = self.media_service.enrich_result(
                raw_result.url,
                fetch_full_text=options.fetch_full_text,
                enable_ocr=options.enable_ocr,
                enable_video_transcript=options.enable_video_transcript,
                source_type=raw_result.source_type,
            )
            raw_result.content_text = str(enrichment.get("content_text", ""))
            raw_result.transcript = str(enrichment.get("transcript", ""))
            raw_result.ocr_text = str(enrichment.get("ocr_text", ""))
            raw_result.media_urls = list(enrichment.get("media_urls", []))
            collected.append(raw_result)

        return collected

    def _collect_results(self, query: str, options: SearchOptions) -> Iterable[SearchResult]:
        base_query = f"{query} {options.google_dork}".strip()

        if "web" in options.enabled_sources:
            yield from self._search_text(base_query, options.max_results_per_source, "web")
        if "news" in options.enabled_sources:
            yield from self._search_news(base_query, options.max_results_per_source)
        if "x" in options.enabled_sources:
            for x_domain in ("x.com", "twitter.com"):
                x_query = f"site:{x_domain} {base_query}".strip()
                yield from self._search_text(x_query, max(2, options.max_results_per_source // 2), "x")
        if "youtube" in options.enabled_sources:
            youtube_query = f"{base_query} site:youtube.com".strip()
            yield from self._search_videos(youtube_query, options.max_results_per_source)
        if "official" in options.enabled_sources:
            domains = options.official_domains or ["gov.eg", "gov.sa", "gov"]
            for domain in domains[:5]:
                official_query = f"site:{domain} {base_query}".strip()
                yield from self._search_text(official_query, max(2, options.max_results_per_source // 2), "official")
        if "direct" in options.enabled_sources:
            yield from self._load_direct_urls(options.direct_urls)
        if "images" in options.enabled_sources or options.search_images:
            yield from self._search_images(base_query, max(2, options.max_results_per_source // 2))

    def _search_text(self, query: str, max_results: int, source_type: str) -> Iterable[SearchResult]:
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = ddgs.text(query, max_results=max_results, region="wt-wt", safesearch="moderate")
                for item in results:
                    yield SearchResult(
                        source_type=source_type,
                        source_name=SOURCE_LABELS[source_type],
                        title=item.get("title", "").strip(),
                        url=item.get("href", "").strip(),
                        snippet=item.get("body", "").strip(),
                        domain=extract_domain(item.get("href", "")),
                        raw_payload=dict(item),
                    )
        except Exception:
            return

    def _search_news(self, query: str, max_results: int) -> Iterable[SearchResult]:
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = ddgs.news(query, max_results=max_results, region="wt-wt", safesearch="moderate")
                for item in results:
                    url = item.get("url", "").strip()
                    yield SearchResult(
                        source_type="news",
                        source_name=SOURCE_LABELS["news"],
                        title=item.get("title", "").strip(),
                        url=url,
                        snippet=item.get("body", "").strip(),
                        domain=extract_domain(url),
                        published_at=item.get("date", "") or "",
                        author=item.get("source", "") or "",
                        raw_payload=dict(item),
                    )
        except Exception:
            return

    def _search_videos(self, query: str, max_results: int) -> Iterable[SearchResult]:
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = ddgs.videos(query, max_results=max_results, region="wt-wt", safesearch="moderate")
                for item in results:
                    url = item.get("content", "").strip() or item.get("url", "").strip()
                    images = item.get("images", {})
                    if isinstance(images, dict):
                        media_urls = dedupe_urls([images.get("large", ""), images.get("small", "")])
                    elif isinstance(images, list):
                        media_urls = dedupe_urls(images)
                    elif isinstance(images, str):
                        media_urls = dedupe_urls([images])
                    else:
                        media_urls = []
                    yield SearchResult(
                        source_type="youtube",
                        source_name=SOURCE_LABELS["youtube"],
                        title=item.get("title", "").strip(),
                        url=url,
                        snippet=item.get("description", "").strip(),
                        domain=extract_domain(url),
                        published_at=item.get("published", "") or "",
                        author=item.get("publisher", "") or "",
                        media_urls=media_urls,
                        raw_payload=dict(item),
                    )
        except Exception:
            return

    def _search_images(self, query: str, max_results: int) -> Iterable[SearchResult]:
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = ddgs.images(query, max_results=max_results, safesearch="moderate")
                for item in results:
                    image_url = item.get("image", "").strip()
                    source_url = item.get("url", "").strip() or image_url
                    yield SearchResult(
                        source_type="images",
                        source_name=SOURCE_LABELS["images"],
                        title=item.get("title", "").strip() or "صورة مرتبطة بالبحث",
                        url=image_url or source_url,
                        snippet=item.get("source", "").strip(),
                        domain=extract_domain(source_url),
                        media_urls=dedupe_urls([image_url, item.get("thumbnail", "")]),
                        raw_payload=dict(item),
                    )
        except Exception:
            return

    def _load_direct_urls(self, urls: List[str]) -> Iterable[SearchResult]:
        for url in dedupe_urls(urls):
            yield SearchResult(
                source_type="direct",
                source_name=SOURCE_LABELS["direct"],
                title=f"رابط مباشر: {extract_domain(url) or url}",
                url=url,
                snippet="تمت إضافة هذا الرابط يدويًا إلى عملية الرصد.",
                domain=extract_domain(url),
                raw_payload={"mode": "direct"},
            )
