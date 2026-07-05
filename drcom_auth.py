#!/usr/bin/env python3
import re
import socket
import struct
import time
from hashlib import md5
import sys
import os
import random
import logging
import subprocess
import urllib.request
import urllib.error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_dotenv(path):
    try:
        with open(path, 'r') as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
    except FileNotFoundError:
        pass


load_dotenv(os.path.join(BASE_DIR, '.env'))


def env_str(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def env_int(name, default, base=10):
    value = os.environ.get(name)
    if value is None or value == '':
        return default
    return int(value, base)


def env_bytes(name, default=None, required=False):
    value = env_str(name, default, required)
    return value.encode()


def parse_mac(value):
    value = value.strip().lower().replace(':', '').replace('-', '')
    if not re.fullmatch(r'[0-9a-f]{12}', value):
        raise RuntimeError('DRCOM_REGISTERED_MAC must be a 12-digit hex MAC address')
    return int(value, 16)


WIFI_SSID = env_str('DRCOM_WIFI_SSID', required=True)
WIFI_IFACE = env_str('DRCOM_WIFI_IFACE', required=True)
DRCOM_SERVER = env_str('DRCOM_SERVER', required=True)
USERNAME = env_bytes('DRCOM_USERNAME', required=True)
PASSWORD = env_bytes('DRCOM_PASSWORD', required=True)
HOST_NAME = env_bytes('DRCOM_HOST_NAME', 'linux-host')
HOST_OS = env_bytes('DRCOM_HOST_OS', 'Linux')
CONTROLCHECKSTATUS = bytes.fromhex(env_str('DRCOM_CONTROLCHECKSTATUS', '20'))
ADAPTERNUM = bytes.fromhex(env_str('DRCOM_ADAPTERNUM', '03'))
IPDOG = bytes.fromhex(env_str('DRCOM_IPDOG', '01'))
PRIMARY_DNS = env_str('DRCOM_PRIMARY_DNS', '10.10.10.10')
DHCP_SERVER = env_str('DRCOM_DHCP_SERVER', '0.0.0.0')
AUTH_VERSION = bytes.fromhex(env_str('DRCOM_AUTH_VERSION', '6800'))
KEEP_ALIVE_VERSION = bytes.fromhex(env_str('DRCOM_KEEP_ALIVE_VERSION', 'dc02'))
REGISTERED_MAC = parse_mac(env_str('DRCOM_REGISTERED_MAC', required=True))
CHECK_INTERVAL = env_int('DRCOM_CHECK_INTERVAL', 30)
WIFI_RETRY_INTERVAL = env_int('DRCOM_WIFI_RETRY_INTERVAL', 5)
MAX_WIFI_RETRIES = env_int('DRCOM_MAX_WIFI_RETRIES', 20)
KEEP_ALIVE_INTERVAL = env_int('DRCOM_KEEP_ALIVE_INTERVAL', 10)
SOCKET_TIMEOUT = env_int('DRCOM_SOCKET_TIMEOUT', 10)
MAX_UDP_RETRIES = env_int('DRCOM_MAX_UDP_RETRIES', 3)
ONLINE_CHECK_INTERVAL = env_int('DRCOM_ONLINE_CHECK_INTERVAL', 10)
ONLINE_CHECK_TIMEOUT = env_int('DRCOM_ONLINE_CHECK_TIMEOUT', 5)
ONLINE_CHECK_FAILS = max(1, env_int('DRCOM_ONLINE_CHECK_FAILS', 1))
ONLINE_CHECK_URLS = [
    url.strip()
    for url in env_str(
        'DRCOM_ONLINE_CHECK_URLS',
        'http://connectivitycheck.platform.hicloud.com/generate_204,'
        'http://connectivitycheck.gstatic.com/generate_204'
    ).split(',')
    if url.strip()
]
IP_CACHE_FILE = env_str('DRCOM_IP_CACHE_FILE', os.path.join(BASE_DIR, '.drcom_ip_cache'))

LOG_FILE = env_str('DRCOM_LOG_FILE', os.path.join(BASE_DIR, 'drcom_auth.log'))

handlers = [logging.StreamHandler(sys.stdout)]
try:
    handlers.append(logging.FileHandler(LOG_FILE))
except PermissionError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=handlers
)
log = logging.getLogger('jlu-drcom')


class ReauthRequired(Exception):
    pass


def md5sum(s):
    m = md5()
    m.update(s)
    return m.digest()


def dump(n):
    s = '%x' % n
    if len(s) & 1:
        s = '0' + s
    return bytes.fromhex(s)


def ror(md5_val, pwd):
    ret = b''
    for i in range(len(pwd)):
        x = md5_val[i] ^ pwd[i]
        ret += (((x << 3) & 0xFF) + (x >> 5)).to_bytes(1, 'big')
    return ret


def checksum(s):
    ret = 1234
    for i in re.findall(b'....', s):
        ret ^= int(i[::-1].hex(), 16)
    ret = (1968 * ret) & 0xffffffff
    return struct.pack('<I', ret)


def save_cached_ip(ip):
    try:
        with open(IP_CACHE_FILE, 'w') as f:
            f.write(ip)
    except Exception:
        pass


def load_cached_ip():
    try:
        with open(IP_CACHE_FILE, 'r') as f:
            ip = f.read().strip()
        if re.match(r'\d+\.\d+\.\d+\.\d+', ip):
            return ip
    except Exception:
        pass
    return None


def is_wifi_connected():
    try:
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'DEVICE,STATE', 'device', 'status'],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.strip().split('\n'):
            parts = line.split(':')
            if len(parts) >= 2 and parts[0] == WIFI_IFACE:
                state = parts[1].lower()
                return state in ('已连接', 'connected', 'activated')
    except Exception:
        pass
    return False


def connect_wifi():
    try:
        connections = subprocess.run(
            ['nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show'],
            capture_output=True, text=True, timeout=10
        )
        conn_name = None
        for line in connections.stdout.strip().split('\n'):
            parts = line.split(':')
            if len(parts) >= 2 and WIFI_SSID in parts[0] and 'wifi' in parts[1]:
                conn_name = parts[0]
                break
        if not conn_name:
            log.error(f"未找到WiFi配置: {WIFI_SSID}")
            return False
        log.info(f"正在连接WiFi: {conn_name}")
        result = subprocess.run(
            ['nmcli', 'connection', 'up', conn_name],
            capture_output=True, text=True, timeout=30
        )
        if '成功' in result.stdout or 'successfully' in result.stdout.lower():
            log.info("WiFi连接成功")
            return True
        return False
    except Exception as e:
        log.error(f"连接WiFi异常: {e}")
        return False


def wait_for_wifi():
    retries = 0
    while retries < MAX_WIFI_RETRIES:
        if is_wifi_connected():
            return True
        log.info(f"等待WiFi连接... (第{retries + 1}次)")
        connect_wifi()
        time.sleep(WIFI_RETRY_INTERVAL)
        retries += 1
    return False


def wait_for_drcom_server(max_wait=180):
    start = time.time()
    attempt = 0
    while time.time() - start < max_wait:
        attempt += 1
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(3)
            t = struct.pack("<H", int(time.time()) % 0xFFFF)
            packet = b"\x01\x02" + t + b"\x09" + b"\x00" * 15
            sock.sendto(packet, (DRCOM_SERVER, 61440))
            data, addr = sock.recvfrom(1024)
            sock.close()
            if data and (data[0] == 2 or data[0] == 7):
                log.info(f"DrCOM服务器可达 (第{attempt}次尝试)")
                return True
        except Exception as e:
            log.warning(f"DrCOM探测异常 (第{attempt}次): {e}")
        finally:
            try:
                sock.close()
            except Exception:
                pass
        time.sleep(3)
    return False


def _is_generate_204_check(url):
    return 'generate_204' in url


def check_real_online():
    if not ONLINE_CHECK_URLS:
        return True

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for url in ONLINE_CHECK_URLS:
        try:
            request = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'jlu-drcom-auth/1.0',
                    'Cache-Control': 'no-cache',
                },
                method='GET'
            )
            response = opener.open(request, timeout=ONLINE_CHECK_TIMEOUT)
            status = response.getcode()
            final_url = response.geturl()
            response.close()

            if _is_generate_204_check(url):
                if status == 204 and final_url == url:
                    return True
                log.warning(
                    f'[online-check] {url} 返回 status={status}, final_url={final_url}'
                )
                continue

            if 200 <= status < 400:
                return True
            log.warning(f'[online-check] {url} 返回 status={status}')
        except urllib.error.HTTPError as e:
            log.warning(f'[online-check] {url} HTTP错误: {e.code}')
        except Exception as e:
            log.warning(f'[online-check] {url} 探测失败: {e}')

    return False


class DrcomClient:
    def __init__(self, server, username, password, mac,
                 host_name=HOST_NAME, host_os=HOST_OS):
        self.server = server
        self.username = username
        self.password = password
        self.host_ip = '0.0.0.0'
        self.mac = mac
        self.host_name = host_name
        self.host_os = host_os
        self.salt = b''
        self.sock = None

    def _create_socket(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('0.0.0.0', 61440))
        self.sock.settimeout(SOCKET_TIMEOUT)

    def _udp_send_recv(self, packet, expect_from_server=True, retries=MAX_UDP_RETRIES):
        for attempt in range(retries):
            try:
                self.sock.sendto(packet, (self.server, 61440))
                data, address = self.sock.recvfrom(1024)
                if expect_from_server and address != (self.server, 61440):
                    log.warning(f'[UDP] 收到非预期地址: {address}')
                    continue
                return data, address
            except socket.timeout:
                if attempt < retries - 1:
                    log.debug(f'[UDP] 超时，重试 ({attempt + 1}/{retries})')
                    continue
                raise
        return None, None

    def challenge(self, ran):
        for attempt in range(10):
            t = struct.pack("<H", int(ran) % (0xFFFF))
            packet = b"\x01\x02" + t + b"\x09" + b"\x00" * 15
            try:
                data, address = self._udp_send_recv(packet, retries=3)
                if data and data[0] == 2:
                    salt = data[4:8]
                    if len(data) >= 24:
                        ip_bytes = data[20:24]
                        ip = '.'.join(str(b) for b in ip_bytes)
                        if re.match(r'\d+\.\d+\.\d+\.\d+', ip) and not ip.startswith('0.'):
                            self.host_ip = ip
                            save_cached_ip(ip)
                            log.info(f'[challenge] 成功, 获取IP: {ip}')
                        else:
                            log.warning(f'[challenge] 响应中IP无效: {ip}')
                    else:
                        log.warning(f'[challenge] 响应太短无法提取IP (len={len(data)})')
                    return salt
                log.warning(f'[challenge] 非预期响应 data[0]={data[0] if data else None}')
            except socket.timeout:
                log.info(f'[challenge] 超时，重试 ({attempt + 1}/10)')
                ran = time.time() + random.randint(0xF, 0xFF)
                continue
        raise Exception('[challenge] 多次尝试后仍失败')

    def mkpkt(self, salt):
        data = b'\x03\x01\x00' + (len(self.username) + 20).to_bytes(1, 'big')
        data += md5sum(b'\x03\x01' + salt + self.password)
        data += self.username.ljust(36, b'\x00')
        data += CONTROLCHECKSTATUS
        data += ADAPTERNUM
        data += dump(int(data[4:10].hex(), 16) ^ self.mac).rjust(6, b'\x00')
        data += md5sum(b"\x01" + self.password + salt + b'\x00' * 4)
        data += b'\x01'
        data += b''.join([int(x).to_bytes(1, 'big') for x in self.host_ip.split('.')])
        data += b'\x00' * 4
        data += b'\x00' * 4
        data += b'\x00' * 4
        data += md5sum(data + b'\x14\x00\x07\x0b')[:8]
        data += IPDOG
        data += b'\x00' * 4
        data += self.host_name.ljust(32, b'\x00')
        data += b''.join([int(i).to_bytes(1, 'big') for i in PRIMARY_DNS.split('.')])
        data += b''.join([int(i).to_bytes(1, 'big') for i in DHCP_SERVER.split('.')])
        data += b'\x00\x00\x00\x00'
        data += b'\x00' * 8
        data += b'\x94\x00\x00\x00'
        data += b'\x06\x00\x00\x00'
        data += b'\x02\x00\x00\x00'
        data += b'\xf0\x23\x00\x00'
        data += b'\x02\x00\x00\x00'
        data += b'\x44\x72\x43\x4f\x4d\x00\xcf\x07\x68'
        data += b'\x00' * 55
        data += b'\x33\x64\x63\x37\x39\x66\x35\x32\x31\x32\x65\x38\x31\x37\x30\x61\x63\x66\x61\x39\x65\x63\x39\x35\x66\x31\x64\x37\x34\x39\x31\x36\x35\x34\x32\x62\x65\x37\x62\x31'
        data += b'\x00' * 24
        data += AUTH_VERSION
        data += b'\x00' + len(self.password).to_bytes(1, 'big')
        data += ror(md5sum(b'\x03\x01' + salt + self.password), self.password)
        data += b'\x02\x0c'
        data += checksum(data + b'\x01\x26\x07\x11\x00\x00' + dump(self.mac))
        data += b'\x00\x00'
        data += dump(self.mac)
        if (len(self.password) / 4) != 4:
            data += b'\x00' * (len(self.password) // 4)
        data += b'\x60\xa2'
        data += b'\x00' * 28
        return data

    def web_logout(self):
        try:
            urllib.request.urlopen(f'http://{self.server}/F.htm', timeout=5)
            log.info('[web-logout] 已通过Web门户登出')
            time.sleep(2)
        except Exception as e:
            log.warning(f'[web-logout] Web登出失败: {e}')

    def login(self, do_logout=False):
        self._create_socket()
        if do_logout:
            self.web_logout()
        salt = self.challenge(time.time() + random.randint(0xF, 0xFF))
        self.salt = salt
        if self.host_ip == '0.0.0.0':
            cached = load_cached_ip()
            if cached:
                self.host_ip = cached
                log.info(f'[login] challenge未返回IP，使用缓存: {cached}')
            else:
                log.warning('[login] 无可用IP，使用0.0.0.0尝试登录')
        log.info(f'[login] 使用IP: {self.host_ip}')
        packet = self.mkpkt(salt)
        data, address = self._udp_send_recv(packet)
        if data is None:
            raise Exception('登录无响应')
        if data[0] == 4:
            log.info('[login] UDP认证登录成功！')
            return data[23:39]
        elif data[0] == 5:
            log.error('[login] 服务器拒绝(5): 密码错误/MAC不匹配/账号已在线')
            if not do_logout:
                log.info('[login] 尝试先登出再重登...')
                self.stop()
                return self.login(do_logout=True)
            raise Exception('登录被拒绝')
        else:
            log.error(f'[login] 未知响应 data[0]={data[0]}, 响应: {data.hex()[:100]}')
            raise Exception('登录失败')

    def keep_alive_package_builder(self, number, random_val, tail, ptype=1, first=False):
        data = b'\x07' + number.to_bytes(1, 'big') + b'\x28\x00\x0b' + ptype.to_bytes(1, 'big')
        if first:
            data += b'\x0f\x27'
        else:
            data += KEEP_ALIVE_VERSION
        data += b'\x2f\x12' + b'\x00' * 6
        data += tail
        data += b'\x00' * 4
        if ptype == 3:
            foo = b''.join([int(i).to_bytes(1, 'big') for i in self.host_ip.split('.')])
            crc = b'\x00' * 4
            data += crc + foo + b'\x00' * 8
        else:
            data += b'\x00' * 16
        return data

    def keep_alive2(self, tail):
        svr = self.server
        ran = random.randint(0, 0xFFFF)
        ran += random.randint(1, 10)
        svr_num = 0
        next_online_check = time.time() + ONLINE_CHECK_INTERVAL
        online_failures = 0

        packet = self.keep_alive_package_builder(svr_num, dump(ran), b'\x00' * 4, 1, True)
        while True:
            data, _ = self._udp_send_recv(packet)
            if data is None:
                raise Exception('keep-alive2 phase1 无响应')
            if data.startswith(b'\x07\x00\x28\x00') or \
               data.startswith(b'\x07' + svr_num.to_bytes(1, 'big') + b'\x28\x00'):
                break
            elif data[0] == 0x07 and data[2] == 0x10:
                svr_num += 1
                packet = self.keep_alive_package_builder(svr_num, dump(ran), b'\x00' * 4, 1, False)
            else:
                log.warning(f'[keep-alive2] phase1 非预期: {data.hex()[:40]}')

        ran += random.randint(1, 10)
        packet = self.keep_alive_package_builder(svr_num, dump(ran), b'\x00' * 4, 1, False)
        data, _ = self._udp_send_recv(packet)
        if data is None:
            raise Exception('keep-alive2 phase2 无响应')
        while data[0] != 7:
            data, _ = self._udp_send_recv(packet)
        svr_num += 1
        tail = data[16:20]

        ran += random.randint(1, 10)
        packet = self.keep_alive_package_builder(svr_num, dump(ran), tail, 3, False)
        data, _ = self._udp_send_recv(packet)
        if data is None:
            raise Exception('keep-alive2 phase3 无响应')
        while data[0] != 7:
            data, _ = self._udp_send_recv(packet)
        svr_num += 1
        tail = data[16:20]
        log.info("[keep-alive2] 心跳循环已启动")

        i = svr_num
        while True:
            try:
                ran += random.randint(1, 10)
                packet = self.keep_alive_package_builder(i, dump(ran), tail, 1, False)
                data, _ = self._udp_send_recv(packet)
                if data is None:
                    raise Exception('keep-alive type1 无响应')
                tail = data[16:20]

                ran += random.randint(1, 10)
                packet = self.keep_alive_package_builder(i + 1, dump(ran), tail, 3, False)
                data, _ = self._udp_send_recv(packet)
                if data is None:
                    raise Exception('keep-alive type3 无响应')
                tail = data[16:20]

                i = (i + 2) % 0xFF
                log.info(f'[keep-alive2] 心跳正常 (seq={i})')

                if ONLINE_CHECK_INTERVAL > 0 and time.time() >= next_online_check:
                    if check_real_online():
                        if online_failures:
                            log.info('[online-check] 真实联网已恢复')
                        online_failures = 0
                    else:
                        online_failures += 1
                        log.warning(
                            f'[online-check] 真实联网失败 '
                            f'({online_failures}/{ONLINE_CHECK_FAILS})'
                        )
                        if online_failures >= ONLINE_CHECK_FAILS:
                            raise ReauthRequired('真实联网探测连续失败，准备重新认证')
                    next_online_check = time.time() + ONLINE_CHECK_INTERVAL

                time.sleep(KEEP_ALIVE_INTERVAL)
            except Exception as e:
                log.warning(f"[keep-alive2] 心跳异常: {e}")
                raise

    def empty_socket_buffer(self):
        try:
            while True:
                self.sock.recvfrom(1024)
        except socket.timeout:
            pass

    def run(self):
        package_tail = self.login()
        log.info('[drcom] 登录成功，启动心跳...')
        self.empty_socket_buffer()
        self.keep_alive2(package_tail)

    def stop(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None


def main():
    log.info("=" * 50)
    log.info("JLU DrCOM 自动认证服务启动 (UDP协议)")
    log.info(f"WiFi: {WIFI_SSID}, 用户: {USERNAME.decode()}")
    log.info(f"心跳间隔: {KEEP_ALIVE_INTERVAL}s, Socket超时: {SOCKET_TIMEOUT}s")
    log.info("=" * 50)

    while True:
        client = None
        try:
            if not wait_for_wifi():
                log.error("无法连接WiFi，等待重试...")
                time.sleep(CHECK_INTERVAL)
                continue

            log.info("WiFi已连接，等待DrCOM服务器可达...")
            if not wait_for_drcom_server(max_wait=180):
                log.warning("DrCOM服务器不可达，等待重试...")
                time.sleep(CHECK_INTERVAL)
                continue

            client = DrcomClient(
                server=DRCOM_SERVER,
                username=USERNAME,
                password=PASSWORD,
                mac=REGISTERED_MAC
            )

            log.info("开始UDP认证...")
            client.run()

        except KeyboardInterrupt:
            log.info("收到中断信号，退出")
            if client:
                client.stop()
            break
        except ReauthRequired as e:
            log.error(f"认证异常: {e}")
            if client:
                client.stop()
            log.info("立即重新认证...")
        except Exception as e:
            log.error(f"认证异常: {e}")
            if client:
                client.stop()
            log.info(f"等待 {CHECK_INTERVAL} 秒后重试...")
            time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    main()
