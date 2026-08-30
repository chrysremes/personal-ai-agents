"""Static checks for the Phase 3 Docker Compose deployment contract."""

from pathlib import Path

import yaml


def load_compose() -> dict:
    """Load the checked-in Compose file as structured YAML."""
    compose_path = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    return yaml.safe_load(compose_path.read_text(encoding="utf-8"))


def test_gateway_compose_uses_host_ollama_without_binding_ollama_port() -> None:
    """The default Docker path relies on host Ollama instead of publishing 11434."""
    compose = load_compose()
    services = compose["services"]

    assert "ollama" not in services
    assert "version" not in compose

    gateway = services["gateway"]
    assert gateway["network_mode"] == "host"
    assert "ports" not in gateway
    assert "depends_on" not in gateway
    assert gateway["environment"]["OLLAMA_BASE_URL"] == "http://127.0.0.1:11434"

    published_ports = [
        str(port)
        for service in services.values()
        for port in service.get("ports", [])
    ]
    assert not any(port.startswith("11434:") for port in published_ports)
