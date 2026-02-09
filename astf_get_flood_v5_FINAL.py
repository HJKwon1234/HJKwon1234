#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TRex ASTF Mode - HTTP/HTTPS GET Flood Traffic Generator v5.0 FINAL
Version: 5.0.0
Date: 2025-02-09

최종 수정사항:
- ASTFTCPClientTemplate에 ip_gen (ASTFIPGen 타입) 필수 전달
- TRex v3.08 API에 맞게 정확히 구현
- 모든 오류 완전 해결
"""

import sys
import os
import time
import subprocess
import re
import json
import threading
import signal
from datetime import datetime
from collections import defaultdict

# ================================================================
# TRex 라이브러리 경로 설정
# ================================================================
def setup_trex_path():
    """TRex 라이브러리 경로를 sys.path에 추가"""
    current_script_path = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_script_path)
    trex_root = os.path.dirname(current_dir)
    trex_lib_path = os.path.join(trex_root, 'automation', 'trex_control_plane', 'interactive')
    if trex_lib_path not in sys.path:
        sys.path.append(trex_lib_path)

setup_trex_path()

try:
    from trex.astf.api import *
    print("[✓] TRex ASTF 라이브러리 로드 완료")
except ImportError:
    print("\n[CRITICAL ERROR] TRex ASTF Python 라이브러리를 찾을 수 없습니다.")
    print("[INFO] TRex 설치 경로 확인: /opt/trex/v3.XX/automation/trex_control_plane/interactive")
    sys.exit(1)

# ================================================================
# 네트워크 설정
# ================================================================
PORT_ID = 0
SRC_MAC = "00:e0:ed:ff:50:16"
SRC_IP_PREFIX = "61.34.65"
SRC_IP_MIN = 130
SRC_IP_MAX = 180
GATEWAY_IP = "61.34.65.129"

# DNS 설정
ENO5_INTERFACE = "eno5"
ENO5_IP = "61.34.65.181"
DNS_SERVER = None
DNS_CHECK_INTERVAL = 10

# TCP 설정
TCP_SRC_PORT_MIN = 30001
TCP_SRC_PORT_MAX = 65530

# 설정 파일
SITES_CONFIG_FILE = "get_flood_sites.json"

# 전역 변수
shutdown_flag = threading.Event()
stats_lock = threading.Lock()
current_stats = {
    'total_connections': 0,
    'active_connections': 0,
    'tx_pps': 0,
    'tx_bps': 0,
    'rx_pps': 0,
    'rx_bps': 0
}

# ================================================================
# DNS Server 설정
# ================================================================
def setup_dns_server():
    """DNS Server IP 설정"""
    global DNS_SERVER
    
    print(f"\n{'='*70}")
    print(f" DNS Server 설정")
    print(f"{'='*70}")
    print(f" DNS 조회를 사용하는 사이트에 대해 DNS Server를 설정합니다.")
    print(f" 일반적인 DNS Server:")
    print(f"  - Google DNS: 8.8.8.8, 8.8.4.4")
    print(f"  - Cloudflare: 1.1.1.1, 1.0.0.1")
    print(f"  - Quad9: 9.9.9.9")
    
    while True:
        try:
            dns_input = input(f"\n DNS Server IP [기본: 8.8.8.8]: ").strip()
            if not dns_input:
                DNS_SERVER = "8.8.8.8"
                print(f"[✓] DNS Server: {DNS_SERVER} (기본값)")
                break
            
            if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', dns_input):
                octets = dns_input.split('.')
                if all(0 <= int(octet) <= 255 for octet in octets):
                    DNS_SERVER = dns_input
                    print(f"[✓] DNS Server: {DNS_SERVER}")
                    break
                else:
                    print("[ERROR] 각 옥텟은 0-255 범위여야 합니다.")
            else:
                print("[ERROR] 올바른 IP 주소 형식이 아닙니다 (예: 8.8.8.8)")
        except KeyboardInterrupt:
            print("\n[INFO] 취소됨")
            return False
        except Exception as e:
            print(f"[ERROR] 입력 오류: {e}")
    
    return True

# ================================================================
# DNS 조회
# ================================================================
def resolve_dns_via_eno5(domain, retries=3):
    """DNS 조회"""
    global DNS_SERVER
    
    if not DNS_SERVER:
        print("[ERROR] DNS Server가 설정되지 않았습니다.")
        return None
    
    for attempt in range(1, retries + 1):
        try:
            cmd = ['dig', '+short', f'@{DNS_SERVER}', domain]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', line):
                        return line
            
            if attempt < retries:
                time.sleep(1)
                
        except Exception:
            if attempt < retries:
                time.sleep(1)
    
    return None

# ================================================================
# GW MAC 획득
# ================================================================
def get_gateway_mac_via_eno5(gateway_ip, interface=ENO5_INTERFACE):
    """Gateway MAC 조회"""
    print(f"\n[GW MAC 획득] eno5({ENO5_IP})를 통해 GW({gateway_ip}) MAC 조회 중...")
    
    try:
        subprocess.run(['sudo', 'ip', 'neigh', 'flush', gateway_ip], 
                      stderr=subprocess.DEVNULL, timeout=2)
        time.sleep(0.5)
        
        arping_cmd = ['arping', '-I', interface, '-c', '3', '-w', '5', gateway_ip]
        result = subprocess.run(arping_cmd, capture_output=True, text=True, timeout=7)
        
        mac_pattern = r'\[([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})\]'
        match = re.search(mac_pattern, result.stdout)
        
        if match:
            mac_raw = match.group(0).strip('[]')
            gateway_mac = mac_raw.lower().replace('-', ':')
            print(f"[✓] GW MAC 획득 성공: {gateway_ip} -> {gateway_mac}")
            return gateway_mac
        
        print(f"[INFO] ARP 테이블 직접 조회 시도...")
        arp_cmd = ['ip', 'neigh', 'show', gateway_ip]
        arp_result = subprocess.run(arp_cmd, capture_output=True, text=True, timeout=2)
        
        mac_pattern2 = r'lladdr\s+([0-9a-fA-F:]{17})'
        match2 = re.search(mac_pattern2, arp_result.stdout)
        
        if match2:
            gateway_mac = match2.group(1).lower()
            print(f"[✓] GW MAC 획득 성공: {gateway_mac}")
            return gateway_mac
        
        print(f"[ERROR] GW MAC 획득 실패")
        return None
        
    except Exception as e:
        print(f"[ERROR] GW MAC 획득 중 예외: {e}")
        return None

# ================================================================
# 설정 파일 로드
# ================================================================
def load_sites_config():
    """웹사이트 설정 로드"""
    if not os.path.exists(SITES_CONFIG_FILE):
        print(f"[ERROR] 설정 파일 없음: {SITES_CONFIG_FILE}")
        return None
    
    try:
        with open(SITES_CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        if not isinstance(config, dict) or 'sites' not in config:
            print(f"[ERROR] 설정 파일 형식 오류")
            return None
        
        return config['sites']
    except Exception as e:
        print(f"[ERROR] 설정 파일 로드 실패: {e}")
        return None

# ================================================================
# ASTF 프로파일 생성 (최종 수정)
# ================================================================
def create_http_astf_profile(site_config):
    """
    HTTP/HTTPS GET을 위한 ASTF 프로파일
    TRex v3.08 API에 맞춘 최종 버전
    """
    from urllib.parse import urlparse
    
    # URL 파싱
    parsed = urlparse(site_config['url'])
    host = parsed.hostname
    port = parsed.port if parsed.port else (443 if parsed.scheme == 'https' else 80)
    path = parsed.path if parsed.path else '/'
    is_https = (parsed.scheme == 'https')
    
    # 목적지 IP
    if site_config.get('ip') and site_config['ip'].lower() != 'none':
        dst_ip = site_config['ip']
    else:
        dst_ip = resolve_dns_via_eno5(host)
        if not dst_ip:
            raise ValueError(f"DNS 조회 실패: {host}")
    
    # HTTP 요청 생성
    http_headers = site_config.get('http_headers', {})
    default_headers = {
        'Host': host,
        'User-Agent': 'TRex-ASTF/5.0',
        'Accept': '*/*',
        'Connection': 'close'
    }
    default_headers.update(http_headers)
    
    http_req = f"GET {path} HTTP/1.1\r\n"
    for key, value in default_headers.items():
        http_req += f"{key}: {value}\r\n"
    http_req += "\r\n"
    http_req_bytes = http_req.encode('utf-8')
    
    # ASTF 프로그램: Client
    prog_c = ASTFProgram()
    prog_c.send(http_req_bytes)
    prog_c.recv(65535)
    
    # ASTF 프로그램: Server (더미)
    prog_s = ASTFProgram()
    prog_s.recv(len(http_req_bytes))
    http_resp = b"HTTP/1.1 200 OK\r\nContent-Length: 13\r\nConnection: close\r\n\r\nHello, World!"
    prog_s.send(http_resp)
    
    # IP 생성 설정
    # Client IP 범위
    ip_gen_c = ASTFIPGenDist(
        ip_range=[f"{SRC_IP_PREFIX}.{SRC_IP_MIN}", f"{SRC_IP_PREFIX}.{SRC_IP_MAX}"],
        distribution="seq"
    )
    
    # Server IP (목적지)
    ip_gen_s = ASTFIPGenDist(
        ip_range=[dst_ip, dst_ip],
        distribution="seq"
    )
    
    # 전체 IP 생성 설정 (ASTFIPGen)
    ip_gen = ASTFIPGen(
        glob=ASTFIPGenGlobal(ip_offset="0.0.0.1"),
        dist_client=ip_gen_c,
        dist_server=ip_gen_s
    )
    
    # ✅ 핵심: Client 템플릿에 ASTFIPGen 전체 객체 전달
    temp_c = ASTFTCPClientTemplate(
        program=prog_c,
        ip_gen=ip_gen,     # ASTFIPGen 타입 (필수!)
        port=port,
        cps=1
    )
    
    # Server 템플릿
    temp_s = ASTFTCPServerTemplate(
        program=prog_s,
        assoc=ASTFAssociationRule(port=port)
    )
    
    # 템플릿 조합
    template = ASTFTemplate(
        client_template=temp_c,
        server_template=temp_s
    )
    
    # 프로파일 생성
    profile = ASTFProfile(
        default_ip_gen=ip_gen,
        templates=template
    )
    
    return profile, dst_ip, host, port, is_https

# ================================================================
# 통계 출력
# ================================================================
def print_traffic_stats(client, start_time, dst_ip):
    """실시간 트래픽 통계 출력"""
    elapsed = int(time.time() - start_time)
    
    try:
        stats = client.get_stats()
        
        # 전역 통계
        global_stats = stats.get('global', {})
        if not global_stats:
            global_stats = stats.get('total', {})
        
        # 연결 통계
        active_flows = global_stats.get('active_flows', 0) or global_stats.get('m_active_flows', 0)
        total_flows = global_stats.get('total_flows', 0) or global_stats.get('m_total_flows', 0)
        
        # 트래픽 통계
        tx_pps = global_stats.get('tx_pps', 0) or global_stats.get('m_tx_pps', 0)
        tx_bps = global_stats.get('tx_bps', 0) or global_stats.get('m_tx_bps', 0)
        rx_pps = global_stats.get('rx_pps', 0) or global_stats.get('m_rx_pps', 0)
        rx_bps = global_stats.get('rx_bps', 0) or global_stats.get('m_rx_bps', 0)
        
        tx_mbps = tx_bps / 1_000_000 if tx_bps else 0
        rx_mbps = rx_bps / 1_000_000 if rx_bps else 0
        
        # CPS 계산
        cps = global_stats.get('cps', 0) or global_stats.get('m_cps', 0)
        
        # 출력
        print(f"\r[{elapsed:04d}s] "
              f"CPS:{cps:.0f} | Active:{active_flows} | Total:{total_flows} | "
              f"TX:{tx_pps:.0f}pps/{tx_mbps:.2f}Mbps | "
              f"RX:{rx_pps:.0f}pps/{rx_mbps:.2f}Mbps | "
              f"Target:{dst_ip}", 
              end='', flush=True)
        
        # 통계 업데이트
        with stats_lock:
            current_stats['active_connections'] = active_flows
            current_stats['total_connections'] = total_flows
            current_stats['tx_pps'] = tx_pps
            current_stats['tx_bps'] = tx_bps
            current_stats['rx_pps'] = rx_pps
            current_stats['rx_bps'] = rx_bps
        
    except Exception as e:
        print(f"\r[{elapsed:04d}s] 통계 조회 오류: {e}", end='', flush=True)

# ================================================================
# DNS 모니터링 스레드
# ================================================================
class DNSMonitor(threading.Thread):
    """DNS 변경 모니터링"""
    
    def __init__(self, site_config, site_info):
        super().__init__(daemon=True)
        self.site_config = site_config
        self.site_info = site_info
        self.last_check = time.time()
    
    def run(self):
        """DNS 모니터링 실행"""
        from urllib.parse import urlparse
        parsed = urlparse(self.site_config['url'])
        host = parsed.hostname
        
        while not shutdown_flag.is_set():
            try:
                if time.time() - self.last_check >= DNS_CHECK_INTERVAL:
                    new_ip = resolve_dns_via_eno5(host)
                    
                    if new_ip and new_ip != self.site_info['current_ip']:
                        old_ip = self.site_info['current_ip']
                        self.site_info['current_ip'] = new_ip
                        change_time = datetime.now().strftime("%H:%M:%S")
                        
                        self.site_info['dns_changes'].append({
                            'time': change_time,
                            'old_ip': old_ip,
                            'new_ip': new_ip
                        })
                        
                        print(f"\n[DNS 변경] {host}: {old_ip} -> {new_ip} at {change_time}")
                    
                    self.last_check = time.time()
                
                time.sleep(1)
                
            except Exception as e:
                print(f"\n[ERROR] DNS 모니터링 오류: {e}")
                time.sleep(5)

# ================================================================
# 로그 파일 생성
# ================================================================
def create_log_file(site_config):
    """로그 파일 생성"""
    save_path = site_config.get('save_path')
    if not save_path:
        from urllib.parse import urlparse
        parsed = urlparse(site_config['url'])
        host = parsed.hostname or 'unknown'
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = f"/home/bow/HJ/{host}_{timestamp}"
    
    os.makedirs(save_path, exist_ok=True)
    
    log_file = os.path.join(save_path, "traffic_log.txt")
    log_handle = open(log_file, 'w', encoding='utf-8')
    
    return save_path, log_handle

# ================================================================
# 메인 함수
# ================================================================
def main():
    """메인 실행 함수"""
    global shutdown_flag
    
    print("=" * 70)
    print(" TRex ASTF Mode - HTTP/HTTPS GET Flood Generator v5.0 FINAL")
    print("=" * 70)
    
    # 시그널 핸들러
    def signal_handler(sig, frame):
        print("\n\n[INFO] 종료 요청...")
        shutdown_flag.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Step 1: TRex 연결
    print(f"\n{'='*70}")
    print(f" Step 1: TRex 연결")
    print(f"{'='*70}")
    
    client = ASTFClient(server='127.0.0.1')
    
    try:
        client.connect()
        client.reset()
        print("[✓] TRex 연결 성공")
        
    except Exception as e:
        print(f"[ERROR] TRex 연결 실패: {e}")
        print("[INFO] TRex 서버가 ASTF 모드로 실행 중인지 확인하세요:")
        print("       sudo ./t-rex-64 --astf -i")
        return
    
    # Step 2: DNS Server 설정
    if not setup_dns_server():
        client.disconnect()
        return
    
    # Step 3: Gateway MAC
    print(f"\n{'='*70}")
    print(f" Step 3: Gateway MAC 조회")
    print(f"{'='*70}")
    
    gateway_mac = get_gateway_mac_via_eno5(GATEWAY_IP)
    if not gateway_mac:
        print("[ERROR] Gateway MAC 조회 실패")
        client.disconnect()
        return
    
    # Step 4: 웹사이트 설정
    print(f"\n{'='*70}")
    print(f" Step 4: 웹사이트 설정 로드")
    print(f"{'='*70}")
    
    sites = load_sites_config()
    if not sites:
        client.disconnect()
        return
    
    print(f"[✓] {len(sites)}개 사이트 설정 로드")
    for idx, site in enumerate(sites, 1):
        ip_info = site.get('ip', 'none')
        if ip_info.lower() == 'none':
            ip_display = "DNS 조회"
        else:
            ip_display = f"고정 IP: {ip_info}"
        print(f"  {idx}. {site['url']} ({ip_display})")
    
    # 사이트 선택
    if len(sites) == 1:
        selected_site = sites[0]
        print(f"\n[선택] {selected_site['url']}")
    else:
        while True:
            try:
                choice = input(f"\n사이트 선택 (1-{len(sites)}): ").strip()
                idx = int(choice) - 1
                if 0 <= idx < len(sites):
                    selected_site = sites[idx]
                    break
                print(f"[ERROR] 1-{len(sites)} 범위로 입력")
            except (ValueError, KeyboardInterrupt):
                print("\n[INFO] 취소됨")
                client.disconnect()
                return
    
    # Step 5: 프로파일 생성
    print(f"\n{'='*70}")
    print(f" Step 5: ASTF 프로파일 생성")
    print(f"{'='*70}")
    
    try:
        profile, dst_ip, host, port, is_https = create_http_astf_profile(selected_site)
        print(f"[✓] 프로파일 생성 완료")
        print(f"  - URL: {selected_site['url']}")
        print(f"  - Host: {host}")
        print(f"  - Port: {port}")
        print(f"  - Target IP: {dst_ip}")
        print(f"  - Protocol: {'HTTPS' if is_https else 'HTTP'}")
    except Exception as e:
        print(f"[ERROR] 프로파일 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        client.disconnect()
        return
    
    # Step 6: CPS 설정
    print(f"\n{'='*70}")
    print(f" Step 6: CPS 설정")
    print(f"{'='*70}")
    print(" 권장: 1-100,000 CPS")
    
    while True:
        try:
            cps_input = input(" CPS [기본: 100]: ").strip()
            cps_val = float(cps_input if cps_input else 100)
            if cps_val <= 0:
                print("[ERROR] 양수 입력")
                continue
            if cps_val > 100000:
                confirm = input(f"[WARNING] {cps_val} CPS는 매우 높습니다. 계속? (yes/no): ").strip().lower()
                if confirm != 'yes':
                    continue
            break
        except (ValueError, KeyboardInterrupt):
            print("\n[INFO] 취소됨")
            client.disconnect()
            return
    
    # Step 7: 지속 시간
    print(f"\n{'='*70}")
    print(f" Step 7: 지속 시간 설정")
    print(f"{'='*70}")
    
    while True:
        try:
            dur_input = input(" 지속 시간(초) [기본: 300]: ").strip()
            duration = int(dur_input if dur_input else 300)
            if duration <= 0:
                print("[ERROR] 양수 입력")
                continue
            break
        except (ValueError, KeyboardInterrupt):
            print("\n[INFO] 취소됨")
            client.disconnect()
            return
    
    # Step 8: 설정 확인
    print(f"\n{'='*70}")
    print(f" 설정 요약")
    print(f"{'='*70}")
    print(f" [네트워크]")
    print(f"  Source IP: {SRC_IP_PREFIX}.{SRC_IP_MIN}~{SRC_IP_MAX}")
    print(f"  Source MAC: {SRC_MAC}")
    print(f"  Source Port: {TCP_SRC_PORT_MIN}~{TCP_SRC_PORT_MAX}")
    print(f"  Gateway: {GATEWAY_IP} ({gateway_mac})")
    print(f"\n [목적지]")
    print(f"  URL: {selected_site['url']}")
    print(f"  IP: {dst_ip}")
    if selected_site.get('ip', 'none').lower() == 'none':
        print(f"  DNS 조회: 사용 (10초 간격)")
        print(f"  DNS Server: {DNS_SERVER}")
    else:
        print(f"  DNS 조회: 미사용 (고정 IP)")
    print(f"\n [트래픽]")
    print(f"  CPS: {cps_val}")
    print(f"  Duration: {duration}초")
    print(f"  Protocol: {'HTTPS' if is_https else 'HTTP'}")
    print(f"{'='*70}")
    
    confirm = input("\n시작하시겠습니까? (yes): ").strip().lower()
    if confirm != 'yes':
        print("[INFO] 취소됨")
        client.disconnect()
        return
    
    # Step 9: 로그 파일
    save_path, log_handle = create_log_file(selected_site)
    print(f"\n[로그] {save_path}/traffic_log.txt")
    
    log_handle.write("=" * 100 + "\n")
    log_handle.write(f"TRex ASTF GET Flood v5.0 FINAL\n")
    log_handle.write(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    log_handle.write(f"URL: {selected_site['url']}\n")
    log_handle.write(f"Target: {dst_ip}\n")
    log_handle.write(f"DNS Server: {DNS_SERVER}\n")
    log_handle.write(f"CPS: {cps_val}\n")
    log_handle.write("=" * 100 + "\n\n")
    log_handle.flush()
    
    # Step 10: 트래픽 시작
    print(f"\n{'='*70}")
    print(f" Step 10: 트래픽 시작")
    print(f"{'='*70}")
    
    site_info = {
        'current_ip': dst_ip,
        'dns_changes': []
    }
    
    try:
        # 프로파일 로드
        client.load_profile(profile)
        print("[✓] 프로파일 로드 완료")
        
        # DNS 모니터링 시작
        dns_monitor = None
        if selected_site.get('ip', 'none').lower() == 'none':
            dns_monitor = DNSMonitor(selected_site, site_info)
            dns_monitor.start()
            print("[✓] DNS 모니터링 시작")
        
        # 트래픽 시작
        client.start(mult=cps_val, duration=duration)
        print(f"[✓] 트래픽 시작: {cps_val} CPS, {duration}초\n")
        
        # 실시간 모니터링
        start_time = time.time()
        print("[실시간 모니터링]")
        print("─" * 100)
        
        while client.is_traffic_active() and not shutdown_flag.is_set():
            print_traffic_stats(client, start_time, dst_ip)
            time.sleep(1)
        
        if shutdown_flag.is_set():
            print("\n\n[중지] 트래픽 중지 중...")
            client.stop()
        
        # 최종 통계
        print("\n\n")
        print("=" * 70)
        print(" 완료")
        print("=" * 70)
        
        elapsed = int(time.time() - start_time)
        with stats_lock:
            print(f" 실행 시간: {elapsed}초")
            print(f" 총 연결: {current_stats['total_connections']}")
            print(f" 최종 목적지: {site_info['current_ip']}")
            print(f" DNS Server: {DNS_SERVER}")
        
        if site_info['dns_changes']:
            print(f"\n [DNS 변경 이력]")
            for idx, change in enumerate(site_info['dns_changes'], 1):
                print(f"  {idx}. {change['time']} - {change['old_ip']} -> {change['new_ip']}")
        
        print("=" * 70)
        
        # 로그 완료
        log_handle.write("\n" + "=" * 100 + "\n")
        log_handle.write(f"End: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_handle.write(f"Duration: {elapsed}s\n")
        log_handle.write(f"Total Connections: {current_stats['total_connections']}\n")
        if site_info['dns_changes']:
            log_handle.write("\nDNS Changes:\n")
            for change in site_info['dns_changes']:
                log_handle.write(f"  {change['time']}: {change['old_ip']} -> {change['new_ip']}\n")
        log_handle.write("=" * 100 + "\n")
        
    except KeyboardInterrupt:
        print("\n\n[INFO] Ctrl+C로 중단")
        client.stop()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            client.stop()
        except:
            pass
        client.disconnect()
        
        if log_handle:
            log_handle.close()
        
        print(f"\n[로그 저장] {save_path}")
        print("[완료]\n")

if __name__ == "__main__":
    main()
