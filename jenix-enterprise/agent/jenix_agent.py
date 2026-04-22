#!/usr/bin/env python3
"""
JENIX Enterprise Agent v3.0
Cross-platform: Linux, macOS, Windows
"""

import asyncio
import json
import os
import platform
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import psutil
import websockets
import requests

SYSTEM = platform.system()  # 'Linux', 'Darwin', 'Windows'

# ── Config ──────────────────────────────────────────────────────────────────
CONFIG_PATHS = {
    'Linux':   '/etc/jenix/agent.conf',
    'Darwin':  '/etc/jenix/agent.conf',
    'Windows': r'C:\ProgramData\JENIX\agent.conf',
}
CONFIG_FILE = CONFIG_PATHS.get(SYSTEM, '/etc/jenix/agent.conf')

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}

config = load_config()
SERVER_URL  = config.get('server_url', os.environ.get('JENIX_SERVER', 'ws://localhost:8000'))
SERVER_HTTP = SERVER_URL.replace('ws://', 'http://').replace('wss://', 'https://')
NODE_ID     = config.get('node_id', str(uuid.uuid4()))
NODE_NAME   = config.get('node_name', socket.gethostname())
API_KEY     = config.get('api_key', os.environ.get('JENIX_API_KEY', ''))

# ── OS-specific collectors ───────────────────────────────────────────────────

def get_os_info():
    info = {
        'os_type':    SYSTEM,
        'os_name':    platform.system(),
        'os_version': platform.version(),
        'os_release': platform.release(),
        'hostname':   socket.gethostname(),
        'arch':       platform.machine(),
        'python':     platform.python_version(),
        'fqdn':       socket.getfqdn(),
    }
    if SYSTEM == 'Linux':
        try:
            with open('/etc/os-release') as f:
                for line in f:
                    if line.startswith('PRETTY_NAME='):
                        info['os_pretty'] = line.split('=', 1)[1].strip().strip('"')
        except Exception:
            pass
    elif SYSTEM == 'Darwin':
        try:
            result = subprocess.run(['sw_vers'], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                if 'ProductName' in line:
                    info['os_pretty'] = line.split(':', 1)[1].strip()
                if 'ProductVersion' in line:
                    info['os_version_mac'] = line.split(':', 1)[1].strip()
        except Exception:
            pass
    elif SYSTEM == 'Windows':
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r'SOFTWARE\Microsoft\Windows NT\CurrentVersion')
            info['os_pretty'] = winreg.QueryValueEx(key, 'ProductName')[0]
            info['os_build']  = winreg.QueryValueEx(key, 'CurrentBuildNumber')[0]
        except Exception:
            pass
    return info

def get_cpu_metrics():
    metrics = {
        'cpu_percent':     psutil.cpu_percent(interval=1),
        'cpu_count':       psutil.cpu_count(logical=True),
        'cpu_count_phys':  psutil.cpu_count(logical=False),
        'cpu_freq':        None,
        'cpu_temps':       [],
        'load_avg':        None,
    }
    try:
        freq = psutil.cpu_freq()
        if freq:
            metrics['cpu_freq'] = {'current': round(freq.current, 1),
                                   'min': round(freq.min, 1),
                                   'max': round(freq.max, 1)}
    except Exception:
        pass
    try:
        if SYSTEM != 'Windows':
            load = os.getloadavg()
            metrics['load_avg'] = {'1m': round(load[0], 2),
                                   '5m': round(load[1], 2),
                                   '15m': round(load[2], 2)}
    except Exception:
        pass
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for name, entries in temps.items():
                for e in entries[:2]:
                    metrics['cpu_temps'].append({'sensor': name,
                                                 'label': e.label,
                                                 'temp': round(e.current, 1)})
    except Exception:
        pass
    return metrics

def get_memory_metrics():
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    return {
        'ram_total':    vm.total,
        'ram_used':     vm.used,
        'ram_free':     vm.available,
        'ram_percent':  vm.percent,
        'swap_total':   sw.total,
        'swap_used':    sw.used,
        'swap_percent': sw.percent,
    }

def get_disk_metrics():
    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            io    = psutil.disk_io_counters(perdisk=True)
            dev   = part.device.replace('/dev/', '').replace('\\\\?\\', '')[:10]
            disk  = {
                'device':      part.device,
                'mountpoint':  part.mountpoint,
                'fstype':      part.fstype,
                'total':       usage.total,
                'used':        usage.used,
                'free':        usage.free,
                'percent':     usage.percent,
                'read_bytes':  0,
                'write_bytes': 0,
            }
            if io and dev in io:
                disk['read_bytes']  = io[dev].read_bytes
                disk['write_bytes'] = io[dev].write_bytes
            disks.append(disk)
        except (PermissionError, OSError):
            continue
    return disks

def get_network_metrics():
    interfaces = []
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()
    io    = psutil.net_io_counters(pernic=True)
    for name, stat in stats.items():
        iface = {
            'name':       name,
            'is_up':      stat.isup,
            'speed_mbps': stat.speed,
            'mtu':        stat.mtu,
            'addresses':  [],
            'bytes_sent': 0,
            'bytes_recv': 0,
        }
        if name in addrs:
            for a in addrs[name]:
                iface['addresses'].append({'family': str(a.family),
                                           'address': a.address,
                                           'netmask': a.netmask})
        if name in io:
            iface['bytes_sent'] = io[name].bytes_sent
            iface['bytes_recv'] = io[name].bytes_recv
        interfaces.append(iface)
    return interfaces

def get_processes(top_n=15):
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'username', 'status',
                                   'cpu_percent', 'memory_percent',
                                   'create_time', 'cmdline']):
        try:
            info = p.info
            info['memory_mb'] = round((psutil.Process(p.pid).memory_info().rss
                                        / 1024 / 1024), 1)
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda x: x.get('cpu_percent', 0), reverse=True)
    return procs[:top_n]

def get_services():
    """Get running services — OS aware."""
    services = []
    if SYSTEM == 'Linux':
        try:
            result = subprocess.run(
                ['systemctl', 'list-units', '--type=service',
                 '--state=loaded', '--no-pager', '--plain'],
                capture_output=True, text=True, timeout=10)
            for line in result.stdout.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 4:
                    services.append({'name':   parts[0].replace('.service',''),
                                     'load':   parts[1],
                                     'active': parts[2],
                                     'sub':    parts[3]})
        except Exception:
            pass
    elif SYSTEM == 'Darwin':
        try:
            result = subprocess.run(['launchctl', 'list'],
                                    capture_output=True, text=True, timeout=10)
            for line in result.stdout.splitlines()[1:]:
                parts = line.split('\t')
                if len(parts) == 3:
                    services.append({'pid':    parts[0],
                                     'status': parts[1],
                                     'name':   parts[2]})
        except Exception:
            pass
    elif SYSTEM == 'Windows':
        try:
            import win32service
            import win32con
            scm = win32service.OpenSCManager(None, None,
                                              win32con.SC_MANAGER_ENUMERATE_SERVICE)
            svcs = win32service.EnumServicesStatus(
                scm, win32service.SERVICE_WIN32,
                win32service.SERVICE_STATE_ALL)
            for svc in svcs:
                services.append({'name':   svc[0],
                                 'display': svc[1],
                                 'status':  svc[2][1]})
        except ImportError:
            # Fallback: sc query
            try:
                result = subprocess.run(['sc', 'query', 'type=', 'all'],
                                        capture_output=True, text=True, timeout=15)
                current = {}
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line.startswith('SERVICE_NAME:'):
                        current = {'name': line.split(':', 1)[1].strip()}
                    elif line.startswith('STATE') and current:
                        current['status'] = line
                        services.append(current)
                        current = {}
            except Exception:
                pass
    return services[:50]

def get_open_ports():
    ports = []
    try:
        for conn in psutil.net_connections(kind='inet'):
            if conn.status == 'LISTEN':
                ports.append({
                    'port':   conn.laddr.port,
                    'family': 'TCP',
                    'addr':   conn.laddr.ip,
                    'pid':    conn.pid,
                })
    except (psutil.AccessDenied, Exception):
        pass
    return sorted(ports, key=lambda x: x['port'])

def get_windows_event_logs(n=20):
    """Windows-specific: fetch recent System + Security events."""
    if SYSTEM != 'Windows':
        return []
    try:
        import win32evtlog
        events = []
        for log_type in ['System', 'Application']:
            hand = win32evtlog.OpenEventLog(None, log_type)
            flags = win32evtlog.EVENTLOG_BACKWARDS_READ | \
                    win32evtlog.EVENTLOG_SEQUENTIAL_READ
            records = win32evtlog.ReadEventLog(hand, flags, 0)
            for r in records[:n]:
                events.append({
                    'log':        log_type,
                    'event_id':   r.EventID & 0xFFFF,
                    'type':       r.EventType,
                    'source':     r.SourceName,
                    'time':       str(r.TimeGenerated),
                    'message':    str(r.StringInserts)[:200] if r.StringInserts else '',
                })
        return events
    except Exception:
        return []

def get_macos_system_info():
    """macOS-specific extras."""
    if SYSTEM != 'Darwin':
        return {}
    info = {}
    try:
        result = subprocess.run(['system_profiler', 'SPHardwareDataType', '-json'],
                                capture_output=True, text=True, timeout=15)
        data = json.loads(result.stdout)
        hw = data.get('SPHardwareDataType', [{}])[0]
        info['model']        = hw.get('machine_model', '')
        info['cpu_model']    = hw.get('cpu_type', '')
        info['memory_slots'] = hw.get('physical_memory', '')
        info['serial']       = hw.get('serial_number', '')
    except Exception:
        pass
    return info

def collect_all_metrics():
    """Collect full metrics snapshot."""
    return {
        'timestamp':  datetime.utcnow().isoformat(),
        'node_id':    NODE_ID,
        'node_name':  NODE_NAME,
        'os_info':    get_os_info(),
        'cpu':        get_cpu_metrics(),
        'memory':     get_memory_metrics(),
        'disks':      get_disk_metrics(),
        'network':    get_network_metrics(),
        'processes':  get_processes(),
        'services':   get_services(),
        'ports':      get_open_ports(),
        'windows_events': get_windows_event_logs() if SYSTEM == 'Windows' else [],
        'macos_info': get_macos_system_info() if SYSTEM == 'Darwin' else {},
    }

# ── Command executor ─────────────────────────────────────────────────────────

def execute_command(cmd, shell=True):
    """Execute a command cross-platform."""
    if SYSTEM == 'Windows':
        shell = True
    try:
        proc = subprocess.Popen(
            cmd, shell=shell,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        output = []
        for line in proc.stdout:
            output.append(line.rstrip())
        proc.wait()
        return {'exit_code': proc.returncode, 'output': output}
    except Exception as e:
        return {'exit_code': -1, 'output': [str(e)]}

# ── WebSocket client ─────────────────────────────────────────────────────────

async def run_agent():
    ws_url = f"{SERVER_URL}/ws/agent/{NODE_ID}"
    print(f"[JENIX] Connecting to {ws_url}")
    while True:
        try:
            async with websockets.connect(
                ws_url,
                extra_headers={'X-API-Key': API_KEY, 'X-Node-Name': NODE_NAME},
                ping_interval=30, ping_timeout=10,
            ) as ws:
                print(f"[JENIX] Connected. Node: {NODE_NAME} ({NODE_ID}) OS: {SYSTEM}")
                # Register
                await ws.send(json.dumps({
                    'type': 'register',
                    'node_id': NODE_ID,
                    'node_name': NODE_NAME,
                    'os_type': SYSTEM,
                    'os_info': get_os_info(),
                }))
                # Metric sender
                async def send_metrics():
                    while True:
                        try:
                            metrics = collect_all_metrics()
                            await ws.send(json.dumps({'type': 'metrics', 'data': metrics}))
                        except Exception as e:
                            print(f"[JENIX] Metric error: {e}")
                        await asyncio.sleep(10)

                metric_task = asyncio.create_task(send_metrics())
                # Command receiver
                try:
                    async for message in ws:
                        msg = json.loads(message)
                        if msg.get('type') == 'command':
                            cmd    = msg.get('command', '')
                            cmd_id = msg.get('command_id', '')
                            print(f"[JENIX] Executing: {cmd}")
                            result = execute_command(cmd)
                            await ws.send(json.dumps({
                                'type': 'command_result',
                                'command_id': cmd_id,
                                'data': result,
                            }))
                finally:
                    metric_task.cancel()
        except Exception as e:
            print(f"[JENIX] Disconnected: {e}. Retrying in 10s...")
            await asyncio.sleep(10)

if __name__ == '__main__':
    asyncio.run(run_agent())
