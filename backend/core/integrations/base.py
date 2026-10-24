from datetime import date, datetime
from typing import Protocol, List, Dict, Any, Optional

class SourceAdapter(Protocol):
    adapter_name: str
    display_name: str
    description: str

    def fetch(self, company_id: str, since: Optional[date] = None) -> List[Dict[str, Any]]:
        """Fetches events from the external source"""
        ...

    def status(self, company_id: str) -> Dict[str, Any]:
        """Returns connection and sync status"""
        ...
