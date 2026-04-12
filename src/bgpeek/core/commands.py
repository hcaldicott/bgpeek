"""Vendor-specific CLI command builders for network devices."""

from __future__ import annotations

from bgpeek.models.query import QueryType

# Mapping: (platform, query_type) → command template.
# {target} is replaced with the actual IP/prefix.
_COMMAND_TABLE: dict[tuple[str, QueryType], str] = {
    # --- Juniper Junos ---
    ("juniper_junos", QueryType.BGP_ROUTE): "show route protocol bgp table inet.0 {target} detail",
    ("juniper_junos", QueryType.PING): "ping {target} count 5",
    ("juniper_junos", QueryType.TRACEROUTE): "traceroute {target}",
    # --- Cisco IOS / IOS-XE ---
    ("cisco_ios", QueryType.BGP_ROUTE): "show bgp ipv4 unicast {target}",
    ("cisco_ios", QueryType.PING): "ping {target} repeat 5",
    ("cisco_ios", QueryType.TRACEROUTE): "traceroute {target}",
    ("cisco_xe", QueryType.BGP_ROUTE): "show bgp ipv4 unicast {target}",
    ("cisco_xe", QueryType.PING): "ping {target} repeat 5",
    ("cisco_xe", QueryType.TRACEROUTE): "traceroute {target}",
    # --- Cisco IOS-XR ---
    ("cisco_xr", QueryType.BGP_ROUTE): "show bgp ipv4 unicast {target}",
    ("cisco_xr", QueryType.PING): "ping {target} count 5",
    ("cisco_xr", QueryType.TRACEROUTE): "traceroute {target}",
    # --- Arista EOS ---
    ("arista_eos", QueryType.BGP_ROUTE): "show ip bgp {target}",
    ("arista_eos", QueryType.PING): "ping ip {target} repeat 5",
    ("arista_eos", QueryType.TRACEROUTE): "traceroute {target}",
    # --- Huawei VRP ---
    ("huawei", QueryType.BGP_ROUTE): "display bgp routing-table {target}",
    ("huawei", QueryType.PING): "ping -c 5 {target}",
    ("huawei", QueryType.TRACEROUTE): "tracert {target}",
}


class UnsupportedPlatformError(ValueError):
    """Raised when no command mapping exists for a platform + query type."""

    def __init__(self, platform: str, query_type: QueryType) -> None:
        self.platform = platform
        self.query_type = query_type
        super().__init__(f"no command defined for ({platform}, {query_type.value})")


def build_command(platform: str, query_type: QueryType, target: str) -> str:
    """Return the CLI command string for a given platform, query type, and target."""
    key = (platform, query_type)
    template = _COMMAND_TABLE.get(key)
    if template is None:
        raise UnsupportedPlatformError(platform, query_type)
    return template.format(target=target)


def supported_platforms() -> list[str]:
    """Return sorted list of platforms that have at least one command mapping."""
    return sorted({platform for platform, _ in _COMMAND_TABLE})
