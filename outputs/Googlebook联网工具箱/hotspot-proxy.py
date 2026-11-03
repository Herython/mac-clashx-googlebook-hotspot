#!/usr/bin/env python3
"""Temporary macOS hotspot TCP + DNS gateway via existing ClashX HTTP proxy."""
import socket,socketserver,threading,select,struct,fcntl,subprocess,signal,os,json,urllib.request,time,ipaddress
from pathlib import Path
BASE=Path(__file__).resolve().parent/'运行记录'
ANCHOR='com.apple/000.codex-googlebook'
GATEWAY='192.168.2.1'
PROXY=('127.0.0.1',7890)
stop=threading.Event()
log_lock=threading.Lock()
def log(message):
    with log_lock:
        line=time.strftime('%H:%M:%S ')+message
        print(line,flush=True)
        with (BASE/'hotspot-events.log').open('a') as f: f.write(line+'\n')
def pf(*args):
    return subprocess.run(['/sbin/pfctl',*args],capture_output=True,text=True,check=True)
def original(conn):
    src=conn.getpeername(); dst=conn.getsockname()
    fd=os.open('/dev/pf',os.O_RDONLY)
    try:
        for direction in (2,1):
            data=bytearray(84)
            data[0:4]=socket.inet_aton(src[0]); data[16:20]=socket.inet_aton(dst[0])
            data[64:66]=struct.pack('!H',src[1]);data[68:70]=struct.pack('!H',dst[1])
            data[80:84]=bytes((socket.AF_INET,socket.IPPROTO_TCP,0,direction))
            try:
                fcntl.ioctl(fd,0xc0544417,data,True)
                return socket.inet_ntoa(data[48:52]),struct.unpack('!H',data[76:78])[0]
            except OSError:
                if direction==1: raise
    finally: os.close(fd)
def tunnel(host,port):
    if port<1 or port>65535: raise ValueError('Invalid destination port')
    sock=socket.create_connection(PROXY,timeout=15)
    sock.sendall(f'CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n'.encode())
    head=bytearray()
    while not head.endswith(b'\r\n\r\n'):
        b=sock.recv(1)
        if not b or len(head)>16384: sock.close();raise OSError('Invalid proxy response')
        head.extend(b)
    if head.split(b' ',2)[1]!=b'200': sock.close();raise OSError('Proxy refused CONNECT')
    sock.settimeout(None)
    return sock
def pump(a,b):
    totals=[0,0]
    sockets=[a,b]
    while sockets and not stop.is_set():
        ready,_,_=select.select(sockets,[],[],60)
        if not ready: break
        for source in ready:
            data=source.recv(65536);target=b if source is a else a
            if not data:
                sockets.remove(source)
                try: target.shutdown(socket.SHUT_WR)
                except OSError: pass
            else:
                totals[0 if source is a else 1]+=len(data)
                if source is a and len(data)>=7 and data[0]==21 and data[3:5]==b'\x00\x02' and data[5] in (1,2):
                    log(f'TLS ALERT level={data[5]} description={data[6]}')
                target.sendall(data)
    return totals
def first_packet(conn,port):
    if port not in (80,443): return b'',None
    conn.settimeout(4)
    data=b''
    try:
        data=conn.recv(16384)
        if port==443 and data[:1]==b'\x16':
            while len(data)<5:
                part=conn.recv(5-len(data))
                if not part: return data,None
                data+=part
            needed=5+int.from_bytes(data[3:5],'big')
            if needed>65536: return data,None
            while len(data)<needed:
                part=conn.recv(needed-len(data))
                if not part: return data,None
                data+=part
            try:
                body=data[5:]
                if body[0]!=1: return data,None
                pos=38
                pos+=1+body[pos]
                pos+=2+int.from_bytes(body[pos:pos+2],'big')
                pos+=1+body[pos]
                end=min(len(body),pos+2+int.from_bytes(body[pos:pos+2],'big'));pos+=2
                while pos+4<=end:
                    typ=int.from_bytes(body[pos:pos+2],'big');length=int.from_bytes(body[pos+2:pos+4],'big');pos+=4
                    if typ==0:
                        ext=body[pos:pos+length];idx=2
                        while idx+3<=len(ext):
                            name_type=ext[idx];n=int.from_bytes(ext[idx+1:idx+3],'big');idx+=3
                            if name_type==0:
                                name=ext[idx:idx+n].decode('ascii')
                                if n==len(name) and all(c.isalnum() or c in '.-' for c in name) and len(name)<=253: return data,name
                            idx+=n
                    pos+=length
            except (IndexError,ValueError,UnicodeError): pass
        elif port==80:
            for line in data.split(b'\r\n')[1:]:
                if line.lower().startswith(b'host:'):
                    name=line[5:].strip().split(b':')[0].decode('ascii','ignore')
                    if name and len(name)<=253 and all(c.isalnum() or c in '.-' for c in name): return data,name
        return data,None
    except socket.timeout: return data,None
    finally: conn.settimeout(None)
class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address=True;daemon_threads=True
class TCP(socketserver.BaseRequestHandler):
    def handle(self):
        peer=self.client_address[0]
        if not ipaddress.ip_address(peer) in ipaddress.ip_network('192.168.2.0/24'): return
        try:
            host,port=original(self.request)
            initial,name=first_packet(self.request,port)
            destination=name or host
            with tunnel(destination,port) as upstream:
                log(f'TCP {peer} -> {destination}:{port} (original {host}, hello={len(initial)}) via ClashX')
                if initial: upstream.sendall(initial)
                totals=pump(self.request,upstream)
                log(f'CLOSE {destination}:{port} sent={totals[0]+len(initial)} received={totals[1]}')
        except Exception as e: log(f'TCP {peer}: {type(e).__name__}: {e}')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({'https':'http://127.0.0.1:7890'}))
def resolve(data):
    if len(data)<12 or len(data)>4096: raise ValueError('Invalid DNS packet')
    r=urllib.request.Request('https://dns.google/dns-query',data=data,headers={'Content-Type':'application/dns-message','Accept':'application/dns-message'})
    with opener.open(r,timeout=15) as response: result=response.read(65536)
    if len(result)<12 or result[:2]!=data[:2]: raise ValueError('Invalid DNS response')
    labels=[];i=12
    while i<len(data) and 0<data[i]<64:
        n=data[i];labels.append(data[i+1:i+1+n].decode('ascii','replace'));i+=1+n
    log('DNS '+'.'.join(labels)+' via ClashX + encrypted Google DNS')
    return result
def recv_exact(sock,n):
    data=b''
    while len(data)<n:
        part=sock.recv(n-len(data))
        if not part: raise EOFError()
        data+=part
    return data
class DNSUDP(socketserver.BaseRequestHandler):
    def handle(self):
        if not ipaddress.ip_address(self.client_address[0]) in ipaddress.ip_network('192.168.2.0/24'): return
        try:
            data,sock=self.request;sock.sendto(resolve(data),self.client_address)
        except Exception as e: log(f'DNS: {type(e).__name__}: {e}')
class DNSTCP(socketserver.BaseRequestHandler):
    def handle(self):
        if not ipaddress.ip_address(self.client_address[0]) in ipaddress.ip_network('192.168.2.0/24'): return
        self.request.settimeout(20)
        try:
            n=struct.unpack('!H',recv_exact(self.request,2))[0]
            result=resolve(recv_exact(self.request,n));self.request.sendall(struct.pack('!H',len(result))+result)
        except Exception as e: log(f'DNS TCP: {type(e).__name__}: {e}')
def ntp_timestamp(now):
    seconds=int(now)+2208988800
    fraction=int((now-int(now))*(1<<32))
    return struct.pack('!II',seconds,fraction)
class NTP(socketserver.BaseRequestHandler):
    def handle(self):
        if not ipaddress.ip_address(self.client_address[0]) in ipaddress.ip_network('192.168.2.0/24'): return
        packet,sock=self.request;received=time.time()
        if len(packet)<48 or packet[0]&7!=3: return
        version=(packet[0]>>3)&7
        if version not in (3,4): return
        response=bytearray(48)
        response[:4]=bytes(((version<<3)|4,10,6,236))
        response[8:12]=struct.pack('!I',65536)
        response[12:16]=b'LOCL'
        response[16:24]=ntp_timestamp(received-1)
        response[24:32]=packet[40:48]
        response[32:40]=ntp_timestamp(received)
        response[40:48]=ntp_timestamp(time.time())
        sock.sendto(response,self.client_address)
        log(f'NTP time supplied to {self.client_address[0]}: '+time.strftime('%Y-%m-%d %H:%M:%S %z'))
class UDPServer(socketserver.ThreadingUDPServer):
    allow_reuse_address=True;daemon_threads=True
RULES='''# Scoped to the existing Apple Internet Sharing hotspot only.
rdr pass on bridge100 inet proto udp from 192.168.2.0/24 to any port 123 -> 192.168.2.1 port 1123
rdr pass on bridge100 inet proto { tcp udp } from 192.168.2.0/24 to any port 53 -> 192.168.2.1 port 1053
rdr pass on bridge100 inet proto tcp from 192.168.2.0/24 to ! 192.168.2.0/24 -> 192.168.2.1 port 12345
block drop in quick on bridge100 inet6 all
pass in quick on bridge100 inet proto udp from 192.168.2.0/24 to 192.168.2.1 port { 1053 1123 }
pass in quick on bridge100 inet proto udp from any port 68 to any port 67
block return in quick on bridge100 inet proto udp from 192.168.2.0/24 to any
'''
def main():
    if os.geteuid()!=0: raise SystemExit('Run using sudo in Terminal; no password is saved.')
    if '192.168.2.1' not in subprocess.check_output(['/sbin/ifconfig','bridge100'],text=True): raise SystemExit('Expected hotspot is not active.')
    # Refuse to overwrite any rules with the same anchor name.
    if pf('-a',ANCHOR,'-sr').stdout.strip() or pf('-a',ANCHOR,'-sn').stdout.strip(): raise SystemExit('Anchor already in use; stop existing relay first.')
    if 'Enabled' not in pf('-s','info').stdout: raise SystemExit('System PF is not enabled; enable Internet Sharing first.')
    test=socket.create_connection(PROXY,timeout=5);test.close()
    rules=BASE/'hotspot-pf.conf';rules.write_text(RULES)
    pf('-a',ANCHOR,'-nf',str(rules))
    servers=[Server((GATEWAY,12345),TCP),Server((GATEWAY,1053),DNSTCP),UDPServer((GATEWAY,1053),DNSUDP),UDPServer((GATEWAY,1123),NTP)]
    loaded=False
    try:
        for server in servers: threading.Thread(target=server.serve_forever,daemon=True).start()
        (BASE/'pf-before.txt').write_text(pf('-sa').stdout)
        pf('-a',ANCHOR,'-f',str(rules));loaded=True
        for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP): signal.signal(sig,lambda *_:stop.set())
        log('READY: hotspot TCP and DNS are routed through ClashX. Keep this window open; Ctrl+C restores direct sharing.')
        while not stop.wait(1): pass
    finally:
        if loaded:
            try: pf('-a',ANCHOR,'-F','all');log('Temporary rules removed. Internet Sharing remains available.')
            except Exception as e: log(f'Rollback requires attention: {e}')
        for server in servers: server.shutdown();server.server_close()
if __name__=='__main__': main()
