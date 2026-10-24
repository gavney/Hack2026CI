from backend.core.integrations.base import SourceAdapter
from backend.core.integrations.adapter_1c import Adapter1CEnterprise, generate_1c_client_bank_exchange
from backend.core.integrations.adapter_fns import AdapterFNSNalog
from backend.core.integrations.adapter_bank import AdapterBankCentroInvest
from backend.core.integrations.adapter_edo import AdapterEDO, AdapterMarketplaces

ADAPTER_REGISTRY = {
    "1c_enterprise": Adapter1CEnterprise(),
    "fns_nalog": AdapterFNSNalog(),
    "bank_centroinvest": AdapterBankCentroInvest(),
    "edo_diadoc": AdapterEDO(),
    "marketplaces": AdapterMarketplaces()
}

ALIASES = {
    "1c": "1c_enterprise",
    "fns": "fns_nalog",
    "bank": "bank_centroinvest",
    "edo": "edo_diadoc",
    "wb": "marketplaces",
    "ozon": "marketplaces"
}

def get_adapter(name: str):
    real_name = ALIASES.get(name, name)
    return ADAPTER_REGISTRY.get(real_name)
