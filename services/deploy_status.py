"""生产部署模板状态与校验。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import bootstrap


def deploy_root() -> Path:
    return bootstrap.project_root() / "deploy"


def _exists(rel: str) -> bool:
    return (deploy_root() / rel).is_file()


def helm_chart_dir() -> Path:
    return deploy_root() / "helm" / "ai-agent-matrix"


def helm_chart_status() -> dict[str, Any]:
    chart = helm_chart_dir()
    templates = chart / "templates"
    files = {
        "Chart.yaml": (chart / "Chart.yaml").is_file(),
        "values.yaml": (chart / "values.yaml").is_file(),
        "templates/deployment.yaml": (templates / "deployment.yaml").is_file(),
        "templates/service.yaml": (templates / "service.yaml").is_file(),
        "templates/configmap.yaml": (templates / "configmap.yaml").is_file(),
        "templates/pvc.yaml": (templates / "pvc.yaml").is_file(),
    }
    ready = all(files.values())
    return {
        "ok": ready,
        "chart_dir": str(chart),
        "files": files,
        "install_hint": "helm upgrade --install ai-agent-matrix ./deploy/helm/ai-agent-matrix",
    }


def deploy_manifest_status() -> dict[str, Any]:
    root = deploy_root()
    files = {
        "docker_compose_prod": _exists("docker-compose.prod.yml"),
        "k8s_deployment": _exists("k8s/deployment.yaml"),
        "k8s_service": _exists("k8s/service.yaml"),
        "k8s_configmap": _exists("k8s/configmap.yaml"),
        "env_prod_example": _exists("env.prod.example"),
        "helm_chart": helm_chart_dir().is_dir(),
        "systemd_unit": _exists("systemd/ai-agent-matrix.service"),
    }
    k8s_ready = all(files[k] for k in ("k8s_deployment", "k8s_service", "k8s_configmap"))
    docker_ready = files["docker_compose_prod"]
    helm = helm_chart_status()
    systemd_ready = files.get("systemd_unit", False)
    return {
        "ok": docker_ready or k8s_ready or helm.get("ok") or systemd_ready,
        "deploy_dir": str(root),
        "files": files,
        "docker_prod_ready": docker_ready,
        "k8s_ready": k8s_ready,
        "helm_ready": bool(helm.get("ok")),
        "systemd_ready": systemd_ready,
        "helm": helm,
        "hints": {
            "docker_prod": "python scripts/deploy_up.py --stack prod --build",
            "k8s": "kubectl apply -f deploy/k8s/",
            "helm": helm.get("install_hint"),
            "systemd": "sudo bash scripts/systemd_install.sh",
            "full_local": "python scripts/docker_up.py --stack full --build",
        },
    }


def validate_k8s_yaml() -> dict[str, Any]:
    """轻量 YAML 结构校验（不依赖 kubectl）。"""
    issues: list[str] = []
    for rel in ("k8s/deployment.yaml", "k8s/service.yaml", "k8s/configmap.yaml"):
        path = deploy_root() / rel
        if not path.is_file():
            issues.append(f"missing:{rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if "apiVersion:" not in text or "kind:" not in text:
            issues.append(f"invalid:{rel}")
        if rel == "k8s/deployment.yaml":
            if "/api/health/ready" not in text:
                issues.append("deployment:readiness should use /api/health/ready")
    return {"ok": not issues, "issues": issues}


def validate_helm_chart() -> dict[str, Any]:
    """轻量 Helm Chart 结构校验（不依赖 helm CLI）。"""
    issues: list[str] = []
    chart = helm_chart_dir()
    if not chart.is_dir():
        return {"ok": False, "issues": ["missing:helm/ai-agent-matrix"]}

    chart_yaml = chart / "Chart.yaml"
    if not chart_yaml.is_file():
        issues.append("missing:Chart.yaml")
    else:
        text = chart_yaml.read_text(encoding="utf-8")
        for key in ("apiVersion:", "name:", "version:"):
            if key not in text:
                issues.append(f"Chart.yaml missing {key}")

    values_yaml = chart / "values.yaml"
    if not values_yaml.is_file():
        issues.append("missing:values.yaml")

    for rel in (
        "templates/deployment.yaml",
        "templates/service.yaml",
        "templates/configmap.yaml",
        "templates/pvc.yaml",
    ):
        path = chart / rel
        if not path.is_file():
            issues.append(f"missing:{rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if "{{" not in text or "}}" not in text:
            issues.append(f"not_templated:{rel}")
        if rel == "templates/deployment.yaml" and "readiness" in text and "/api/health/ready" not in text:
            issues.append("helm:readiness should use /api/health/ready")

    return {"ok": not issues, "issues": issues, "chart_dir": str(chart)}
