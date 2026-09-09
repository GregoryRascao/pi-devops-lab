# Raspberry Pi system monitoring project
# Feature branch test
import socket
from datetime import datetime
import subprocess
import time
import json
import pathlib
import logging
from collections.abc import Callable
from typing import TypeVar, TypedDict

T = TypeVar("T")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", filename="monitor.log")

class MemoryInfo(TypedDict):
    total: int | None      # RAM totale en Mo
    usage: int | None      # Pourcentage d'utilisation de la RAM
    status: str            # Statut (OK, WARNING, CRITICAL, UNKNOWN)

class DiskInfo(TypedDict):
    usage: int | None      # Pourcentage d'utilisation du disque
    status: str            # Statut (OK, WARNING, CRITICAL, UNKNOWN)

class CpuInfo(TypedDict):
    usage: int | None      # Pourcentage d'utilisation du CPU
    status: str            # Statut (OK, WARNING, CRITICAL, UNKNOWN)

class SystemInfo(TypedDict):
    hostname: str
    ip: str | None
    memory: MemoryInfo
    disk: DiskInfo
    cpu: CpuInfo
    uptime: float | None
    os: str | None
    timestamp: str

def get_timestamp() -> str:
    """Retourne l'heure et le jour."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return timestamp

def safe_get(func: Callable[[], T]) -> T | None:
    """Exécute une fonction de collecte et intercepte uniquement les erreurs système connues."""
    try:
        return func()
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"[-] Erreur système gérée pour {func.__name__} : {e}")
        return None


def get_hostname() -> str:
    return socket.gethostname()


def get_ip() -> str | None:
    result = subprocess.run(
        ["ip", "-o", "-4", "addr", "show"],
        capture_output=True,
        text=True,
        check=True,
    )
    for line in result.stdout.splitlines():
        parts = line.split()
        if "inet" in parts:
            ip = parts[parts.index("inet") + 1].split("/")[0]
            if not ip.startswith("127."):
                return ip
    return None


def get_memory() -> int | None:
    """Retourne la RAM totale en Mo."""
    result = subprocess.run(
        ["free", "-m"], capture_output=True, text=True, check=True
    )
    for line in result.stdout.splitlines():
        if line.startswith("Mem:"):
            parts = line.split()
            return int(parts[1])
    return None

def get_memory_usage() -> int | None:
    """Retourne le pourcentage d'utilisation de la RAM."""
    result = subprocess.run(
        ["free", "-m"], capture_output=True, text=True, check=True
    )
    for line in result.stdout.splitlines():
        if line.startswith("Mem:"):
            parts = line.split()
            total_memory = int(parts[1])
            available_memory = int(parts[6])
            used_memory = total_memory - available_memory
            return int((used_memory / total_memory) * 100)
    return None


def get_disk() -> int | None:
    """Retourne le pourcentage d'utilisation du disque racine."""
    result = subprocess.run(
        ["df", "-m", "/"], capture_output=True, text=True, check=True
    )
    for line in result.stdout.splitlines():
        if "/dev/" in line:
            parts = line.split()
            return int(parts[4].rstrip("%"))
    return None


def get_uptime() -> float | None:
    with open("/proc/uptime", "r") as file:
        content = file.read()
        return float(content.split()[0])


def get_os() -> str | None:
    with open("/etc/os-release", "r") as file:
        for line in file:
            clean_line = line.strip()
            if clean_line.startswith("PRETTY_NAME="):
                return clean_line.removeprefix("PRETTY_NAME=").strip('"')
    return None

def get_cpu_stats() -> list[int]:
    """Lit la première ligne de /proc/stat pour obtenir les statistiques CPU."""
    with open("/proc/stat", "r") as file:
        first_line = file.readline()
        return [int(value) for value in first_line.split()[1:]]

def get_cpu_usage() -> int | None:
    first_stats = get_cpu_stats()
    time.sleep(1)  # Attendre une seconde pour obtenir la prochaine lecture
    second_stats = get_cpu_stats()

    idle_time = second_stats[3] - first_stats[3]

    total_time = sum(second_stats) - sum(first_stats)
    if total_time == 0:
        return None

    used_time = total_time - idle_time
    cpu_usage = (used_time / total_time) * 100

    return int(cpu_usage)


def get_status(usage: int | None, warning: int = 80, critical: int = 90) -> str:
    """Retourne le statut (OK, WARNING, CRITICAL, UNKNOWN) en fonction d'un pourcentage d'utilisation et des seuils personnalisés."""
    if usage is None:
        return "UNKNOWN"
    if usage >= critical:
        return "CRITICAL"
    if usage >= warning:
        return "WARNING"
    return "OK"

def system_info() -> SystemInfo:
    memory_usage = safe_get(get_memory_usage)
    memory_status = get_status(memory_usage, warning=75, critical=90)

    disk_usage = safe_get(get_disk)
    disk_status = get_status(disk_usage, warning=85, critical=95)

    cpu_usage = safe_get(get_cpu_usage)
    cpu_status = get_status(cpu_usage)

    return {
        "timestamp": get_timestamp(),
        "hostname": safe_get(get_hostname),
        "ip": safe_get(get_ip),
        "memory": {
            "total": safe_get(get_memory),
            "usage": memory_usage,
            "status": memory_status,
        },
        "disk": {
            "usage": disk_usage,
            "status": disk_status,
        },
        "cpu": {
            "usage": cpu_usage,
            "status": cpu_status,
        },
        "uptime": safe_get(get_uptime),
        "os": safe_get(get_os),
    }

def get_trend(difference: int | None) -> str:
    """Retourne un emoji représentant la tendance de l'utilisation d'une ressource."""
    if difference is None:
        return "❓"  # Inconnu
    elif difference > 0:
        return "📈"  # Augmentation
    elif difference < 0:
        return "📉"  # Diminution
    else:
        return "➖"  # Aucune variation

def compare_resource(previous, current, resource) -> int | None:
    previous_usage = previous[resource]["usage"]
    current_usage = current[resource]["usage"]
    if previous_usage is None or current_usage is None:
        return None

    return current_usage - previous_usage


def print_difference(resource: str, current: int | None, difference: int | None, status: str) -> None:
    """Affiche la différence d'utilisation d'une ressource avec un emoji et un message."""
    trend = get_trend(difference)

    if current is None:
        current_str = "N/A"
    else:
        current_str = f"{current:4}%"

    if difference is None:
        difference_str = "N/A"
    else:
        difference_str = f"{difference:+4}%"

    print(f"{resource:8} {current_str:>6} {difference_str:>6} {trend} {status}")


def calculate_average(history: list, resource: str) -> float | None:
    usages = []

    for item in history:
        usage = item[resource]["usage"]

        if usage is not None:
            usages.append(usage)

    if not usages:
        return None

    return sum(usages) / len(usages)

def check_alert(status, resource, current_usage):
    if status != "OK":
        if status == "WARNING":
            logging.warning(f"{resource.upper()} status is {status} with usage at {current_usage}%")
        elif status == "CRITICAL":
            logging.critical(f"{resource.upper()} status is {status} with usage at {current_usage}%")
        else:
            logging.error(f"{resource.upper()} status is {status} with usage at {current_usage}%")


def main() -> None:
    logging.info("Starting system monitoring")
    info = system_info()
    print(json.dumps(info, indent=4))

    file_path = pathlib.Path("system_info.json")

    if file_path.exists():
        with open("system_info.json", "r") as f:
            history = json.load(f)
    else:
        history = []

    history.append(info)
    if len(history) > 10:
        history = history[1:]

    resources = ["cpu", "memory", "disk"]

    # Initialisation de previous et current
    previous = history[-2] if len(history) >= 2 else None
    current = history[-1]

    for resource in resources:
        # Calcul et affichage de la moyenne
        average = calculate_average(history, resource)
        if average is not None:
            print(f"{resource.upper():8} Moyenne : {average:.2f}%")
        else:
            print(f"{resource.upper():8} Moyenne : N/A")

        # Affichage de la différence uniquement si previous et current sont disponibles
        if previous is not None and current is not None:
            current_usage = current[resource]["usage"]
            difference = compare_resource(previous, current, resource)
            current_status = current[resource]["status"]
            check_alert(current_status, resource, current_usage)
            print_difference(resource.upper(), current_usage, difference, current_status)

    with open("system_info.json", "w") as f:
        json.dump(history, f, indent=4)


if __name__ == "__main__":
    main()