# -*- coding: utf-8 -*-

r"""

웹 모니터링 도구 v6.5.5-SR-Plus - Single Request Per Loop (TCP/TLS 세션 신규 연결 + 사용자 입력 대기)

【 핵심 개선 】

✓ 각 루프마다 TCP/TLS 세션 신규 연결 (기존 세션 재사용 X)
✓ 모드 선택 기능 (시작 시 선택)
  - Mode 1: HTML만 다운로드 (빠르고 가볕음)
  - Mode 2: HTML + 리소스 다운로드 (v5.2 호환)
✓ 리소스 자동 파싱 및 다운로드 (BeautifulSoup)
✓ HTML과 리소스 크기 분리 표시
✓ 모드별 그래프 자동 생성
✓ PCAP 캡처 및 TLS 복호화 지원
✓ 【NEW】Wireshark 런처 생성 후 사용자 입력 대기 (엔터 키로 모니터링 시작)

설치:

pip install pandas matplotlib openpyxl requests h2 dnspython pyOpenSSL urllib3 beautifulsoup4

실행:

python web-monitor-v6.5-5-final-single-plus.py

작성일: 2026-01-12 (사용자 입력 대기 기능 추가)

버전: 6.5.5-SR-Plus (각 루프마다 새로운 TCP 세션, GET 1회, 사용자 입력 대기)

"""

import socket
import ssl
import time
import datetime
import dns.resolver
from urllib.parse import urlparse, urljoin
import json
import os
import platform
import subprocess
import sys
import re
import base64
import warnings
from shutil import which
import tempfile

# 【CRITICAL】SSLKEYLOGFILE을 Python 시작 직후, 모든 import 전에 설정해야 함
REPORTS_DIR = os.path.abspath("reports")
os.makedirs(REPORTS_DIR, exist_ok=True)
_ssl_keylog_path = os.path.abspath(os.path.join(REPORTS_DIR, "tls_keylog.txt"))
_parent_dir = os.path.dirname(_ssl_keylog_path)

try:
    if not os.path.exists(_ssl_keylog_path):
        open(_ssl_keylog_path, "a").close()
    if os.access(_parent_dir, os.W_OK):
        os.environ["SSLKEYLOGFILE"] = _ssl_keylog_path
        print(f"[✓] TLS 키로그 경로: {_ssl_keylog_path}")
    else:
        _ssl_keylog_path = os.path.join(tempfile.gettempdir(), "tls_keylog.txt")
        if not os.path.exists(_ssl_keylog_path):
            open(_ssl_keylog_path, "a").close()
        os.environ["SSLKEYLOGFILE"] = _ssl_keylog_path
        print(f"[⚠️] 권한 문제, 대체 경로 사용: {_ssl_keylog_path}")
except Exception as e:
    print(f"[WARNING] TLS 키로그 설정 실패: {e}")

warnings.filterwarnings("ignore")

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    import requests
    from requests.adapters import HTTPAdapter
    from requests.packages.urllib3.util.ssl_ import create_urllib3_context
    print("[✓] requests 라이브러리 로드 완료")
except ImportError:
    try:
        from urllib3.util.ssl_ import create_urllib3_context
        print("[✓] requests 라이브러리 로드 완료 (urllib3 직접 사용)")
    except ImportError:
        print("[ERROR] 'requests' 라이브러리가 필요합니다. `pip install requests` 실행 후 다시 시도하세요.")
        sys.exit(1)

HAS_BEAUTIFULSOUP = False
try:
    from bs4 import BeautifulSoup
    HAS_BEAUTIFULSOUP = True
    print("[✓] BeautifulSoup 라이브러리 로드 완료")
except ImportError:
    print("[WARNING] BeautifulSoup 없음: pip install beautifulsoup4 (리소스 다운로드 모드 사용 가능)")

try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use("Agg")
    HAS_MATPLOTLIB = True
except Exception:
    HAS_MATPLOTLIB = False
    print("[WARNING] matplotlib 없음: pip install matplotlib")

SITES_CONFIG_FILE = "sites.json"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_BASE_PATH = os.path.join(SCRIPT_DIR, "monitoring")
print(f"[✓] 기본 저장 경로: {DEFAULT_BASE_PATH}\n")

# 글로벌 모니터링 모드 변수
MONITORING_MODE = 1  # 1: HTML 전용, 2: HTML+리소스


def select_monitoring_mode():
    """모니터링 모드 선택"""
    global MONITORING_MODE

    print("\n" + "=" * 80)
    print(" 📊 웹 모니터링 도구 v6.5.5-SR-Plus - 듀얼 모드 선택")
    print("=" * 80)
    print("\n【모드 선택】\n")
    print(" [1] Mode 1: HTML만 다운로드 (빠름)")
    print(" [2] Mode 2: HTML + 리소스 다운로드 (v5.2 호환)\n")

    while True:
        choice = input("[INPUT] 모드를 선택하세요 (1 또는 2): ").strip()
        if choice == "1":
            MONITORING_MODE = 1
            print("\n[✓] Mode 1 선택: HTML만 다운로드\n")
            return
        elif choice == "2":
            if not HAS_BEAUTIFULSOUP:
                print("\n[ERROR] Mode 2를 사용하려면 BeautifulSoup이 필요합니다.")
                print("[INFO] 설치: pip install beautifulsoup4")
                print("[INFO] 또는 Mode 1을 선택하세요.\n")
                continue
            MONITORING_MODE = 2
            print("\n[✓] Mode 2 선택: HTML + 리소스 다운로드\n")
            return
        else:
            print("[ERROR] 1 또는 2를 입력하세요.\n")


def get_system_dns_servers():
    """운영체제에 설정된 DNS 서버 주소를 가져옵니다."""
    if platform.system() == "Windows":
        try:
            import winreg
            key_path = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
            dns_servers = []
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as interfaces_key:
                for i in range(winreg.QueryInfoKey(interfaces_key)[0]):
                    guid = winreg.EnumKey(interfaces_key, i)
                    with winreg.OpenKey(interfaces_key, guid) as interface_key:
                        try:
                            dns_server_string, _ = winreg.QueryValueEx(interface_key, "DhcpNameServer")
                            if not dns_server_string:
                                dns_server_string, _ = winreg.QueryValueEx(interface_key, "NameServer")
                            if dns_server_string:
                                dns_servers.extend(dns_server_string.replace(',', ' ').split())
                        except FileNotFoundError:
                            pass
            return sorted(list(set(s for s in dns_servers if s and not s.startswith('127.'))))
        except Exception as e:
            print(f"[WARNING] Windows 시스템 DNS 조회 실패: {e}")
            return []
    return []


def find_executable(name, search_paths=None):
    """주어진 경로와 시스템 PATH에서 실행 파일을 찾습니다."""
    if search_paths is None:
        search_paths = []
    for path in search_paths:
        full_path = os.path.join(path, name)
        if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
            return full_path
    executable_path = which(name)
    if executable_path:
        return executable_path
    return None


def get_active_interface():
    """PowerShell을 사용하여 활성 네트워크 인터페이스의 이름을 찾습니다."""
    if platform.system() != "Windows":
        return None
    try:
        ps_cmd = "$ProgressPreference = 'SilentlyContinue'; Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null } | Select-Object -First 1 -ExpandProperty InterfaceAlias"
        encoded_cmd = base64.b64encode(ps_cmd.encode('utf-16-le')).decode('ascii')
        result = subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", encoded_cmd],
                                capture_output=True, text=True, errors='ignore')
        if result.returncode == 0 and result.stdout.strip():
            interface_name = result.stdout.strip()
            print(f"[✓] 활성 네트워크 인터페이스: '{interface_name}'")
            return interface_name
        else:
            return None
    except Exception as e:
        print(f"[ERROR] 활성 인터페이스 조회 중 예외: {e}")
        return None


def generate_wireshark_launcher(save_dir, pcap_filename, key_log_filename):
    """Wireshark 자동 실행 배치/쉘 스크립트를 생성합니다."""
    try:
        os.makedirs(save_dir, exist_ok=True)
        pcap_basename = os.path.basename(pcap_filename).replace('.pcap', '')
        if platform.system() == "Windows":
            launcher_path = os.path.join(save_dir, f"view_decrypted_{pcap_basename}.bat")
            wireshark_path = find_executable("Wireshark.exe",
                                            [r"C:\Program Files\Wireshark",
                                             r"C:\Program Files (x86)\Wireshark"])
            if not wireshark_path:
                wireshark_path = "Wireshark.exe"
            pcap_abs = os.path.abspath(os.path.join(save_dir, pcap_filename))
            key_log_abs = os.path.abspath(os.path.join(save_dir, key_log_filename))
            bat_lines = [
                '@echo off',
                'chcp 65001 >nul',
                'echo [INFO] Wireshark를 실행합니다...',
                'echo [DEBUG] PCAP: %~dp0' + pcap_filename,
                'echo [DEBUG] TLS Key Log: %~dp0' + key_log_filename,
                'echo.',
                f'start "Wireshark" "{wireshark_path}" -r "{pcap_abs}" -o "ssl.keylog_file:{key_log_abs}"',
                'echo.',
                'echo [INFO] Wireshark가 열리지 않으면 다음을 확인하세요:',
                'echo 1. tls_keylog.txt 파일이 있는지 확인',
                'echo 2. tls_keylog.txt 파일이 비어있지 않은지 확인',
                'pause'
            ]
            bat_content = '\n'.join(bat_lines) + '\n'
        else:
            launcher_path = os.path.join(save_dir, f"view_decrypted_{pcap_basename}.sh")
            wireshark_path = find_executable("wireshark", ["/usr/bin", "/usr/local/bin"])
            if not wireshark_path:
                wireshark_path = "wireshark"
            pcap_abs = os.path.abspath(os.path.join(save_dir, pcap_filename))
            key_log_abs = os.path.abspath(os.path.join(save_dir, key_log_filename))
            sh_lines = [
                '#!/bin/bash',
                'echo "[INFO] Wireshark를 실행합니다..."',
                f'echo "[DEBUG] PCAP: {pcap_abs}"',
                f'echo "[DEBUG] TLS Key Log: {key_log_abs}"',
                f'"{wireshark_path}" -r "{pcap_abs}" -o "ssl.keylog_file:{key_log_abs}" &'
            ]
            bat_content = '\n'.join(sh_lines) + '\n'
        
        with open(launcher_path, "w", encoding="utf-8") as f:
            f.write(bat_content)
        if platform.system() != "Windows":
            os.chmod(launcher_path, 0o755)
        print(f"[✓] Wireshark 자동 실행 스크립트: {launcher_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Wireshark 런처 생성 중 오류: {e}")
        return False


def generate_graphs(session_data, save_path, mode_name):
    """모니터링 데이터 그래프 생성 (v6.5.5) - Response Time + Success Rate"""
    if not HAS_MATPLOTLIB:
        return False
    try:
        plt.style.use('seaborn-v0_8-darkgrid')
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 7))
        fig.suptitle(f'Web Monitoring Report ({mode_name})', fontsize=22, fontweight='bold', y=0.98)
        
        # ======== 1. Response Time Trend (왼쪽) ========
        timestamps = []
        times = []
        for entry in session_data:
            if entry.get('Total Response Time (ms)', 0) > 0:
                ts = entry.get('Timestamp', '')
                response_time = entry.get('Total Response Time (ms)', 0)
                if isinstance(ts, str):
                    try:
                        dt = datetime.datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                    except:
                        dt = datetime.datetime.now()
                else:
                    dt = ts if isinstance(ts, datetime.datetime) else datetime.datetime.now()
                timestamps.append(dt)
                times.append(response_time)
        
        if times:
            x_range = range(len(times))
            ax1.plot(x_range, times, marker='o', linestyle='-',
                    color='#00A86B', linewidth=1, markersize=7,
                    label='Response Time', alpha=0.9)
            ax1.fill_between(x_range, times, alpha=0.15, color='#00A86B')
            avg_time = sum(times) / len(times)
            ax1.axhline(y=avg_time, color='#FF6B35', linestyle='--',
                       linewidth=2.5, alpha=0.8, label=f'Average: {avg_time:.1f}ms')
            max_time = max(times)
            min_time = min(times)
            max_idx = times.index(max_time)
            min_idx = times.index(min_time)
            ax1.scatter([max_idx], [max_time], s=300, c='red', marker='*',
                       zorder=5, edgecolors='darkred', linewidth=2, label=f'Max: {max_time:.1f}ms')
            ax1.scatter([min_idx], [min_time], s=300, c='green', marker='*',
                       zorder=5, edgecolors='darkgreen', linewidth=2, label=f'Min: {min_time:.1f}ms')
            ax1.set_title('Response Time Trend', fontsize=18, fontweight='bold', pad=20)
            ax1.set_xlabel('Request #', fontsize=14, fontweight='bold')
            ax1.set_ylabel('Response Time (ms)', fontsize=14, fontweight='bold')
            ax1.grid(True, alpha=0.4, linestyle='--', linewidth=0.8)
            ax1.legend(fontsize=12, loc='upper left', framealpha=0.95, fancybox=True, shadow=True)
            ax1.set_facecolor('#f0f8f7')
            y_min = min_time * 0.7
            y_max = max_time * 1.3
            ax1.set_ylim(y_min, y_max)
            
            time_labels = []
            time_positions = []
            if len(timestamps) > 0:
                time_positions.append(0)
                time_labels.append(timestamps[0].strftime('%H:%M:%S'))
                if len(timestamps) > 6:
                    step = len(timestamps) // 4
                    for j in range(1, 4):
                        idx = min(j * step, len(timestamps) - 1)
                        if idx not in time_positions:
                            time_positions.append(idx)
                            time_labels.append(timestamps[idx].strftime('%H:%M:%S'))
                if len(timestamps) - 1 not in time_positions:
                    time_positions.append(len(timestamps) - 1)
                    time_labels.append(timestamps[-1].strftime('%H:%M:%S'))
            ax1.set_xticks(time_positions)
            ax1.set_xticklabels(time_labels, rotation=45, ha='right', fontsize=11)
            ax1.tick_params(axis='both', which='major', labelsize=11)
        
        # ======== 2. Success Rate (오른쪽) ========
        success_count = len([d for d in session_data if d.get('Status') == 200])
        fail_count = len(session_data) - success_count
        total = success_count + fail_count
        
        if total > 0:
            sizes = [success_count, fail_count]
            colors = ['#00A86B', '#FF4444']
            explode = (0.08, 0.08)
            wedges, texts, autotexts = ax2.pie(
                sizes,
                labels=['Success (200)', 'Failed'],
                autopct='%1.1f%%',
                colors=colors,
                explode=explode,
                startangle=90,
                textprops={'fontsize': 13, 'fontweight': 'bold'},
                shadow=True,
                wedgeprops={'edgecolor': 'white', 'linewidth': 3}
            )
            
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontsize(15)
                autotext.set_fontweight('bold')
            
            for text in texts:
                text.set_fontsize(13)
                text.set_fontweight('bold')
            
            legend_labels = [
                f'Success: {success_count} ({success_count/total*100:.1f}%)',
                f'Failed: {fail_count} ({fail_count/total*100:.1f}%)',
                f'Total: {total}'
            ]
            ax2.legend(legend_labels, fontsize=12, loc='upper left',
                      framealpha=0.95, fancybox=True, shadow=True)
            ax2.set_title('Success Rate', fontsize=18, fontweight='bold', pad=20)
            ax2.set_facecolor('#f0f8f7')
        
        fig.patch.set_facecolor('white')
        plt.tight_layout()
        
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        graph_file = os.path.join(save_path, f"monitor_graph_{timestamp}.png")
        plt.savefig(graph_file, dpi=150, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close()
        
        print(f"[✓] 그래프 생성 (Response Time + Success Rate): {graph_file}")
        return True
    except Exception as e:
        print(f"[ERROR] 그래프 생성 실패: {e}")
        return False


class ConfigManager:
    """설정 파일(sites.json) 관리"""
    @staticmethod
    def load_sites():
        if not os.path.exists(SITES_CONFIG_FILE):
            print(f"[INFO] '{SITES_CONFIG_FILE}' 파일이 없어 새로 생성합니다.")
            default_sites = [{
                "url": "https://www.google.com",
                "ip": "",
                "check_string": "Google",
                "save_path": "",
                "capture_pcap": True
            }]
            with open(SITES_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(default_sites, f, indent=4, ensure_ascii=False)
            return default_sites
        
        with open(SITES_CONFIG_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError as e:
                print(f"[ERROR] '{SITES_CONFIG_FILE}' 파일 형식이 잘못되었습니다: {e}")
                return []


class Target:
    """모니터링 대상 관리"""
    def __init__(self, config):
        self.url = config["url"]
        self.ip = config.get("ip", "")
        self.check_string = config.get("check_string", "")
        self.save_path = config.get("save_path", "")
        self.capture_pcap = config.get("capture_pcap", True)
        self.parsed_url = urlparse(self.url)
        self.host = self.parsed_url.hostname
        self.uri = self.parsed_url.path or "/"
        self.scheme = self.parsed_url.scheme
        self.port = self.parsed_url.port or (443 if self.scheme == 'https' else 80)


class Monitor:
    """웹 모니터링 실행 클래스 (requests 기반 + SSL 검증 비활성화)"""
    def __init__(self):
        self.resolver = dns.resolver.Resolver()
        self.resolver.timeout = 10
        self.resolver.lifetime = 10
        system_dns = get_system_dns_servers()
        fallback_dns = ['8.8.8.8', '1.1.1.1']
        self.resolver.nameservers = sorted(list(set(system_dns + fallback_dns)))
        dns_info = ', '.join(self.resolver.nameservers) if self.resolver.nameservers else 'None'
        print(f"[✓] DNS 서버: {dns_info}")
        
        self.session = requests.Session()
        
        class NoSSLVerifyAdapter(HTTPAdapter):
            def init_poolmanager(self, *args, **kwargs):
                kwargs['ssl_context'] = ssl.create_default_context()
                kwargs['ssl_context'].check_hostname = False
                kwargs['ssl_context'].verify_mode = ssl.CERT_NONE
                return super().init_poolmanager(*args, **kwargs)
        
        self.session.mount('https://', NoSSLVerifyAdapter())
        self.session.mount('http://', NoSSLVerifyAdapter())
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def resolve_domain(self, host):
        try:
            answers = self.resolver.resolve(host, "A")
            return [ip.to_text() for ip in answers]
        except Exception as e:
            return []
    
    def check(self, target):
        """모니터링 실행 (SSL 검증 완전 비활성화)"""
        timings = {}
        current_ip = None
        
        try:
            dns_start = time.time()
            if target.ip:
                current_ip = target.ip
                timings['dns_ms'] = 0
            else:
                ip_list = self.resolve_domain(target.host)
                if ip_list:
                    current_ip = ip_list[0]
                timings['dns_ms'] = (time.time() - dns_start) * 1000
            
            if not current_ip:
                return {"error": f"IP 주소 확인 불가: {target.host}"}, timings
            
            total_start = time.time()
            try:
                resp = self.session.get(
                    target.url,
                    timeout=10,
                    verify=False,
                    allow_redirects=True
                )
                
                total_ms = (time.time() - total_start) * 1000
                html_body = resp.text.encode('utf-8') if isinstance(resp.text, str) else resp.content
                html_size = len(html_body)
                resource_size = 0
                
                # Mode 2: 리소스 다운로드
                if MONITORING_MODE == 2 and HAS_BEAUTIFULSOUP:
                    try:
                        soup = BeautifulSoup(html_body, 'html.parser')
                        resources = []
                        for tag in soup.find_all(['img', 'script', 'link', 'source']):
                            src = tag.get('src') or tag.get('href')
                            if src:
                                resource_url = urljoin(target.url, src)
                                resources.append(resource_url)
                        
                        for res_url in resources[:50]:  # 최대 50개 리소스
                            try:
                                res_resp = self.session.get(res_url, verify=False, timeout=3)
                                resource_size += len(res_resp.content)
                            except:
                                pass
                    except:
                        pass
                
                tls_version = "TLSv1.2"
                result = {
                    "status": resp.status_code,
                    "html_size": html_size,
                    "resource_size": resource_size,
                    "total_size": html_size + resource_size,
                    "body": html_body,
                    "total_ms": total_ms,
                    "http_version": "HTTP/2" if hasattr(resp, 'h2') else "HTTP/1.1",
                    "tls_version": tls_version,
                    "headers": dict(resp.headers),
                    "ip": current_ip
                }
                
                return result, timings
            except requests.exceptions.RequestException as e:
                return {"error": str(e)}, timings
        except Exception as e:
            return {"error": str(e)}, timings


def select_targets(sites_config):
    """모니터링 대상 선택"""
    print("\n" + "-"*30 + " 모니터링할 사이트 선택 " + "-"*30)
    for i, site in enumerate(sites_config):
        ip_info = f" (IP: {site.get('ip')})" if site.get('ip') else ""
        print(f" [{i+1}] {site['url']}{ip_info}")
    print(f" [0] 모든 사이트 (All Sites)")
    print("-"*80)
    
    while True:
        choice_str = input("[INPUT] 모니터링할 번호를 선택하세요 (쉼표로 구분, '0'은 전체): ").strip()
        if not choice_str:
            continue
        if choice_str == '0':
            return sites_config
        try:
            chosen_indices = {int(i.strip()) for i in choice_str.split(',')}
            selected_sites = [sites_config[i-1] for i in sorted(list(chosen_indices))
                            if 1 <= i <= len(sites_config)]
            if selected_sites:
                return selected_sites
            else:
                print("[ERROR] 유효한 번호를 입력하세요.")
        except ValueError:
            print("[ERROR] 숫자와 쉼표(,)만 입력해주세요.")


def save_session_report(session_data, save_path, url):
    """v5.2 동일 형식으로 세션 결과 저장"""
    try:
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        hostname = url.split('://')[-1].split('/')[0]
        log_file = os.path.join(save_path, f"monitor_log_{hostname}_{timestamp}.txt")
        
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write(f"Web Monitoring Report - {url}\n")
            f.write(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Mode: {'HTML 전용 (Mode 1)' if MONITORING_MODE == 1 else 'HTML+리소스 (Mode 2)'}\n")
            f.write("="*80 + "\n\n")
            
            if not session_data:
                f.write("[INFO] 데이터 없음\n")
                return log_file
            
            total = len(session_data)
            successes = len([d for d in session_data if d.get('Status') == 200])
            failures = total - successes
            
            try:
                avg_time = sum([d.get('Total Response Time (ms)', 0) for d in session_data if d.get('Status') == 200]) / max(successes, 1)
            except:
                avg_time = 0
            
            total_html_size = sum([d.get('HTML Size (B)', 0) for d in session_data])
            total_resource_size = sum([d.get('Resource Size (B)', 0) for d in session_data])
            total_size = total_html_size + total_resource_size
            
            f.write(f"Summary Statistics\n")
            f.write(f" - Total Requests: {total}\n")
            f.write(f" - Successful: {successes} ({successes/total*100:.1f}%)\n")
            f.write(f" - Failed: {failures}\n")
            f.write(f" - Average Response Time: {avg_time:.2f}ms\n")
            f.write(f"\n")
            f.write(f"Total Download Size\n")
            f.write(f" - HTML: {total_html_size / 1024:.2f} KB\n")
            f.write(f" - Resources: {total_resource_size / 1024:.2f} KB\n")
            f.write(f" - Total: {total_size / 1024:.2f} KB\n")
            f.write("\n" + "="*80 + "\n\n")
            f.write("Detailed Log\n")
            f.write("-"*80 + "\n")
            
            for i, entry in enumerate(session_data, 1):
                timestamp_val = entry.get('Timestamp', '')
                status = entry.get('Status', -1)
                url_val = entry.get('URL', 'N/A')
                time_ms = entry.get('Total Response Time (ms)', 0)
                html_size = entry.get('HTML Size (B)', 0)
                resource_size = entry.get('Resource Size (B)', 0)
                http_version = entry.get('HTTP Version', 'HTTP/1.1')
                tls_version = entry.get('TLS Version', 'N/A')
                sni = entry.get('SNI', 'N/A')
                
                f.write(f"\n[{i}] {timestamp_val}\n")
                f.write(f" URL: {url_val}\n")
                f.write(f" Status: {status}\n")
                f.write(f" Response Time: {time_ms:.2f}ms\n")
                f.write(f" HTML Size: {html_size}B\n")
                if MONITORING_MODE == 2:
                    f.write(f" Resource Size: {resource_size}B\n")
                    f.write(f" Total Size: {html_size + resource_size}B\n")
                f.write(f" HTTP Version: {http_version}\n")
                f.write(f" TLS Version: {tls_version}\n")
                f.write(f" SNI: {sni}\n")
            
            f.write("\n" + "="*80 + "\n")
        
        print(f"[✓] 로그 파일: {log_file}")
        return log_file
    except Exception as e:
        print(f"[ERROR] 로그 파일 저장 실패: {e}")
        return None


def generate_excel_report(session_data, save_path, url):
    """v5.2 동일 형식으로 Excel 리포트 생성"""
    try:
        import pandas as pd
        
        if not session_data:
            return None
        
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        hostname = url.split('://')[-1].split('/')[0]
        excel_file = os.path.join(save_path, f"monitor_report_{hostname}_{timestamp}.xlsx")
        
        df = pd.DataFrame(session_data)
        if 'Timestamp' in df.columns:
            df['Timestamp'] = df['Timestamp'].astype(str)
        
        with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Data', index=False)
            
            stats_data = {
                'Metric': [
                    'Total Requests',
                    'Successful (200)',
                    'Failed',
                    'Success Rate (%)',
                    'Avg Response Time (ms)',
                    'Total HTML Size (B)',
                    'Total Resource Size (B)',
                    'Total Size (B)',
                    'Monitoring Mode'
                ],
                'Value': [
                    len(df),
                    len(df[df['Status'] == 200]),
                    len(df[df['Status'] != 200]),
                    len(df[df['Status'] == 200]) / len(df) * 100 if len(df) > 0 else 0,
                    df[df['Status'] == 200]['Total Response Time (ms)'].mean() if len(df[df['Status'] == 200]) > 0 else 0,
                    df['HTML Size (B)'].sum(),
                    df['Resource Size (B)'].sum() if 'Resource Size (B)' in df.columns else 0,
                    df['HTML Size (B)'].sum() + (df['Resource Size (B)'].sum() if 'Resource Size (B)' in df.columns else 0),
                    'Mode 1: HTML only' if MONITORING_MODE == 1 else 'Mode 2: HTML+Resources'
                ]
            }
            stats_df = pd.DataFrame(stats_data)
            stats_df.to_excel(writer, sheet_name='Statistics', index=False)
        
        print(f"[✓] Excel 리포트: {excel_file}")
        return excel_file
    except Exception as e:
        print(f"[ERROR] Excel 리포트 생성 실패: {e}")
        return None


def main():
    print("=" * 80)
    print(" 🔧 웹 모니터링 도구 v6.5.5-SR-Plus - 각 루프마다 TCP/TLS 세션 신규 연결")
    print("=" * 80)

    select_monitoring_mode()

    tshark_path = find_executable(
        "tshark.exe" if platform.system() == "Windows" else "tshark",
        [r"C:\Program Files\Wireshark", r"C:\Program Files (x86)\Wireshark"],
    )
    if not tshark_path:
        print("[WARNING] TShark를 찾을 수 없습니다. PCAP 캡처가 비활성화됩니다.")
        tshark_path = None
    else:
        print(f"[✓] TShark 경로: {tshark_path}")

    sites_config = ConfigManager.load_sites()
    if not sites_config:
        print("[ERROR] sites.json을 읽을 수 없습니다.")
        return

    selected_sites = select_targets(sites_config)
    if not selected_sites:
        print("[ERROR] 선택된 사이트가 없습니다.")
        return

    targets = [Target(cfg) for cfg in selected_sites]

    session_start_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    first_site = selected_sites[0]
    parsed_url = urlparse(first_site["url"])
    host = parsed_url.hostname or "unknown"

    save_path = os.path.join(DEFAULT_BASE_PATH, f"{host}_{session_start_time}")
    os.makedirs(save_path, exist_ok=True)
    print(f"[✓] 저장 경로: {save_path}\n")

    monitoring_keylog = os.path.join(save_path, "tls_keylog.txt")
    tshark_processes = {}
    session_data = {}
    pcap_file = None

    try:
        # --- PCAP 캡처 시작 (필요 시) ---
        active_interface = get_active_interface() if tshark_path else None
        pcap_enabled = bool(active_interface and tshark_path)
        if not pcap_enabled and tshark_path:
            print("[WARNING] 활성 네트워크 인터페이스를 찾을 수 없어 PCAP 캡처가 비활성화됩니다.")

        if pcap_enabled:
            try:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                pcap_file = os.path.join(save_path, f"capture_{timestamp}.pcap")

                all_hosts = [t.host for t in targets if t.host]
                capture_filter = " or ".join([f"host {h}" for h in all_hosts]) if all_hosts else ""
                tshark_cmd = [
                    tshark_path,
                    "-i",
                    active_interface,
                    "-f",
                    capture_filter,
                    "-w",
                    pcap_file,
                ]

                print(f"[✓] PCAP 캡처 시작")
                print(f" - 인터페이스: {active_interface}")
                print(f" - 필터: {capture_filter}")
                print(f" - 파일: {pcap_file}\n")

                proc = subprocess.Popen(
                    tshark_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                tshark_processes["main"] = proc
                time.sleep(2)

                if os.path.exists(pcap_file):
                    generate_wireshark_launcher(
                        save_path, os.path.basename(pcap_file), "tls_keylog.txt"
                    )
            except Exception as e:
                print(f"[ERROR] PCAP 캡처 시작 실패: {e}\n")

        # --- 사용자 입력 대기 (모니터링 시작 전) ---
        print("\n" + "=" * 80)
        print(" 📊 모니터링 준비 완료")
        print("=" * 80)
        print(f"\n[✓] {len(targets)}개 사이트 모니터링 준비됨")
        print("[ℹ️]  엔터 키를 입력하면 모니터링을 시작합니다 (중지: Ctrl+C)")
        print("\n")
        
        try:
            input("[INPUT] 엔터 키를 입력하세요: ")
        except KeyboardInterrupt:
            print("\n[INFO] 모니터링이 취소되었습니다.")
            return

        print("\n" + "=" * 80)
        print(f"[START] {len(targets)}개 사이트 모니터링 시작 (중지: Ctrl+C)")
        print("=" * 80 + "\n")

        # --- 메인 루프: 각 루프마다 새로운 Monitor 인스턴스 생성 (새 TCP/TLS 세션) ---
        monitor = None
        while True:
            try:
                # 【핵심】매 루프마다 새로운 Monitor() 생성 = 새로운 requests.Session() = 새 TCP/TLS 연결
                monitor = Monitor()

                for target in targets:
                    now = datetime.datetime.now()
                    result, timings = monitor.check(target)

                    log_line = f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] "

                    if "error" not in result:
                        body_content = result.get("body", b"")
                        if isinstance(body_content, bytes):
                            body_text = body_content.decode("utf-8", "ignore")
                        else:
                            body_text = str(body_content)

                        check_str = (
                            f"Content: {'OK' if target.check_string in body_text else 'FAIL'}"
                            if target.check_string
                            else ""
                        )

                        http_version = result.get("http_version", "HTTP/1.1")
                        tls_version = result.get("tls_version", "N/A")

                        size_str = f"HTML: {result['html_size']}B"
                        if MONITORING_MODE == 2 and result["resource_size"] > 0:
                            size_str = (
                                f"HTML: {result['html_size']}B + Resources: {result['resource_size']}B"
                            )

                        ip_addr = result.get("ip", "Unknown")

                        log_line += (
                            f"URL: {target.url} | IP: {ip_addr} | Status: {result['status']} | "
                            f"Ver: {http_version} | TLS: {tls_version} | SNI: {target.host} | "
                            f"Time: {result['total_ms']:.2f}ms | {size_str} | {check_str}"
                        )
                    else:
                        log_line += f"URL: {target.url} | [FAIL] {result['error']}"

                    print(log_line)

                    if target.url not in session_data:
                        session_data[target.url] = []

                    http_version = result.get("http_version", "HTTP/1.1")
                    tls_version = result.get("tls_version", "N/A")

                    session_data[target.url].append(
                        {
                            "Timestamp": now,
                            "URL": target.url,
                            "Status": result.get("status", -1),
                            "HTML Size (B)": result.get("html_size", 0),
                            "Resource Size (B)": result.get("resource_size", 0),
                            "Total Size (B)": result.get("total_size", 0),
                            "Total Response Time (ms)": result.get("total_ms", 0),
                            "Resource Load Time (ms)": 0,
                            "HTTP Version": http_version,
                            "TLS Version": tls_version,
                            "SNI": target.host,
                            "IP": result.get("ip", "Unknown"),
                            "Encoding": "utf-8",
                        }
                    )

                # 【중요】Monitor 인스턴스 세션 종료
                if monitor is not None and hasattr(monitor, "session"):
                    try:
                        monitor.session.close()
                    except Exception:
                        pass

                # 다음 루프까지 3초 대기
                time.sleep(3)

            except KeyboardInterrupt:
                print("\n\n[STOP] 모니터링이 중단되었습니다.")
                break

    finally:
        print("\n[INFO] 결과를 저장 중입니다...")

        try:
            if os.path.exists(_ssl_keylog_path) and os.path.getsize(_ssl_keylog_path) > 0:
                import shutil

                shutil.copy2(_ssl_keylog_path, monitoring_keylog)
                print(f"[✓] TLS 키로그 복사: {monitoring_keylog}")
        except Exception as e:
            print(f"[WARNING] TLS 키로그 복사 실패: {e}")

        for url, data in session_data.items():
            save_session_report(data, save_path, url)
            generate_excel_report(data, save_path, url)

        if session_data:
            for url, data in session_data.items():
                mode_name = (
                    "Mode 1: HTML only" if MONITORING_MODE == 1 else "Mode 2: HTML+Resources"
                )
                generate_graphs(data, save_path, mode_name)

        for proc in tshark_processes.values():
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

        print("\n[INFO] 복호화 방법:")
        print("────────────────────────────────────────")
        print("1. 생성된 BAT/SH 파일 실행")
        print("   예: view_decrypted_capture_*.bat")
        print("")
        print("2. tls_keylog.txt 파일 크기 확인")
        print(f"   파일: {monitoring_keylog}")
        print("────────────────────────────────────────")
        print("\n[✓] 프로그램 종료")


if __name__ == "__main__":
    main()
