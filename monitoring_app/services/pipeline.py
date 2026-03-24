from __future__ import annotations

from typing import Dict, List

from monitoring_app.models import SearchOptions, SearchResult
from monitoring_app.services.case_service import CaseManagementService
from monitoring_app.services.content_analysis import ContentAnalysisService
from monitoring_app.services.source_service import MultiSourceSearchService
from monitoring_app.storage import DatabaseManager


class MonitoringPipeline:
    def __init__(self, repository: DatabaseManager) -> None:
        self.repository = repository
        self.analysis_service = ContentAnalysisService()
        self.search_service = MultiSourceSearchService()
        self.case_service = CaseManagementService(self.analysis_service)

    def execute_search(self, query: str, options: SearchOptions) -> Dict[str, object]:
        results = self.search_service.run(query, options)
        analyzed_results: List[SearchResult] = [self.analysis_service.analyze_result(result, query) for result in results]

        search_id = self.repository.create_search(query, options, len(analyzed_results))
        existing_cases = self.repository.list_case_anchors()
        cases = self.case_service.build_cases(analyzed_results, existing_cases)
        for case in cases:
            case_id = self.repository.save_case_bundle(search_id, case)
            case.case_id = case_id
            for result in case.results:
                result.case_id = case_id

        return {
            "search_id": search_id,
            "results": analyzed_results,
            "cases": cases,
        }
