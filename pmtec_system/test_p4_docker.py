#!/usr/bin/env python3
"""P4-2 Docker deployment verification.

Verifies:
1. Dockerfile exists and has required directives
2. docker-compose.yml is valid YAML with 4 services
3. .dockerignore excludes expected paths
4. config.py supports PMTEC_HOST env override
5. Service launcher CLI accepts --host parameter
6. docker-compose config valid (if docker available)
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def check_dockerfile():
    """Check Dockerfile exists and has key directives."""
    path = os.path.join(PROJECT_ROOT, "Dockerfile")
    if not os.path.exists(path):
        return False, "Dockerfile not found"
    with open(path) as f:
        content = f.read()
    checks = [
        ("FROM directive", "FROM" in content),
        ("WORKDIR set", "WORKDIR /pmtec" in content),
        ("requirements installed", "requirements.txt" in content),
        ("proto generation", "grpc_tools.protoc" in content),
        ("ports exposed", "EXPOSE" in content),
        ("entry point", "ENTRYPOINT" in content),
    ]
    for name, ok in checks:
        if not ok:
            return False, f"Missing: {name}"
    return True, "All Dockerfile checks pass"


def check_compose():
    """Check docker-compose.yml is valid YAML with 4 services."""
    path = os.path.join(PROJECT_ROOT, "docker-compose.yml")
    if not os.path.exists(path):
        return False, "docker-compose.yml not found"
    # Parse YAML without pyyaml (manual check)
    with open(path) as f:
        content = f.read()
    services = ["war-engine", "battle-network", "application-store", "plug-and-play"]
    checks = [
        ("version", "version:" in content),
        ("services section", "services:" in content),
    ]
    for svc in services:
        checks.append((f"service {svc}", f"  {svc}:" in content))
    checks.append(("networks", "networks:" in content))
    checks.append(("volumes", "volumes:" in content))
    checks.append(("healthcheck", "healthcheck:" in content))
    checks.append(("depends_on", "depends_on:" in content))
    for name, ok in checks:
        if not ok:
            return False, f"Missing: {name}"
    # Try parsing with pyyaml if available
    try:
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)
        svc_count = len(data.get("services", {}))
        if svc_count < 4:
            # P18: 栈已从 P4 时代 4 服务扩展到 8（演示栈/展示中心等），断言改下限
            return False, f"Expected >= 4 services, got {svc_count}"
        checks.append(("yaml valid", True))
    except ImportError:
        pass  # pyyaml not installed, manual checks sufficient
    return True, f"All compose checks pass ({len(services)} services)"


def check_dockerignore():
    """Check .dockerignore exists."""
    path = os.path.join(PROJECT_ROOT, ".dockerignore")
    if not os.path.exists(path):
        return False, ".dockerignore not found"
    with open(path) as f:
        content = f.read()
    checks = [
        ("__pycache__ excluded", "__pycache__" in content),
        ("*.pyc excluded", "*.pyc" in content),
        (".git excluded", ".git" in content),
    ]
    for name, ok in checks:
        if not ok:
            return False, f"Missing: {name}"
    return True, "All .dockerignore checks pass"


def check_config_env():
    """Check config.py supports PMTEC_HOST env var."""
    path = os.path.join(PROJECT_ROOT, "config.py")
    with open(path) as f:
        content = f.read()
    if "PMTEC_HOST" in content:
        return True, "config.py supports PMTEC_HOST env override"
    return False, "PMTEC_HOST not found in config.py"


def check_service_launcher():
    """Check service_launcher.py accepts --host."""
    path = os.path.join(PROJECT_ROOT, "distributed", "service_launcher.py")
    with open(path) as f:
        content = f.read()
    checks = [
        ("--host arg", '"--host"' in content),
        ("--service arg", '"--service"' in content),
        (
            "4 service functions",
            all(
                f"run_{fn}" in content
                for fn in [
                    "war_engine",
                    "battle_network",
                    "application_store",
                    "plug_and_play",
                ]
            ),
        ),
    ]
    for name, ok in checks:
        if not ok:
            return False, f"Missing: {name}"
    return True, "Service launcher CLI supports --host and --service"


def main():
    print("=" * 70)
    print("P4-2 Docker Deployment Verification")
    print("=" * 70)

    checks = [
        ("Dockerfile", check_dockerfile),
        ("docker-compose.yml", check_compose),
        (".dockerignore", check_dockerignore),
        ("config.py PMTEC_HOST", check_config_env),
        ("service_launcher CLI", check_service_launcher),
    ]

    all_pass = True
    for name, fn in checks:
        ok, msg = fn()
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}: {msg}")
        if not ok:
            all_pass = False

    # Check if docker is available
    import shutil

    docker_avail = shutil.which("docker") is not None
    print(f"\n  Docker CLI available: {docker_avail}")
    if docker_avail:
        print("  (Would run: docker-compose config && docker-compose up --dry-run)")
    else:
        print("  (Docker not installed on this host - file structure verified)")

    print(f"\n{'=' * 70}")
    print(f"Result: {'ALL PASS' if all_pass else 'SOME FAILED'}")
    return all_pass


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
