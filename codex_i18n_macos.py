#!/usr/bin/env python3
"""Seed the Codex Statsig i18n cache via a temporary local CDP connection."""
import argparse, base64, hashlib, json, os, socket, struct, subprocess, sys, time, urllib.request
from urllib.parse import urlsplit

EXPRESSION = r"""(async () => {
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
    const prefix = "statsig.cached.evaluations.";
    const targetLayer = "72216192";
    const targetLayerHash = "4269166702";
    const bootstrapMissing = __CODEX_I18N_BOOTSTRAP_MISSING__;
    const waitUntil = Date.now() + (bootstrapMissing ? 10000 : 45000);

    const getStatsigClient = () => {
        const root = window.__STATSIG__ || globalThis.__STATSIG__;
        if (!root) {
            return null;
        }
        return root.firstInstance ||
            (typeof root.instance === "function" ? root.instance() : null);
    };

    let seededFromMemory = false;
    const cacheKeys = () => {
        const keys = [];
        for (let index = 0; index < localStorage.length; index += 1) {
            const key = localStorage.key(index);
            if (key && key.startsWith(prefix)) {
                keys.push(key);
            }
        }

        if (keys.length === 0) {
            try {
                const client = getStatsigClient();
                if (client && client.dataAdapter) {
                    const context = client.getContext();
                    const user = context.user;
                    const cacheKey = client.dataAdapter._getCacheKey(user);
                    const currentData = client.dataAdapter.getDataSync(user);
                    if (currentData && currentData.data) {
                        localStorage.setItem(cacheKey, JSON.stringify(currentData));
                        seededFromMemory = true;
                        keys.push(cacheKey);
                    }
                    else if (
                        context.values &&
                        typeof context.values === "object" &&
                        context.values.has_updates === true
                    ) {
                        const cacheValue = {
                            source: "Memory",
                            data: JSON.stringify(context.values),
                            receivedAt: Date.now(),
                            stableID: context.stableID ?? null,
                            fullUserHash: null
                        };
                        localStorage.setItem(cacheKey, JSON.stringify(cacheValue));
                        seededFromMemory = true;
                        keys.push(cacheKey);
                    }
                }
            }
            catch {
                // The normal empty-cache diagnostic below is more useful.
            }
        }

        return keys;
    };

    let keys = cacheKeys();
    while (keys.length === 0 && Date.now() < waitUntil) {
        await sleep(250);
        keys = cacheKeys();
    }

    let bootstrapCreated = false;
    if (keys.length === 0 && bootstrapMissing) {
        try {
            const client = getStatsigClient();
            if (client && client.dataAdapter) {
                const context = client.getContext();
                const user = context.user;
                const cacheKey = client.dataAdapter._getCacheKey(user);
                const syntheticValues = {
                    has_updates: true,
                    response_format: "init-v2",
                    time: Date.now(),
                    feature_gates: {},
                    dynamic_configs: {},
                    layer_configs: {
                        [targetLayer]: {
                            v: "0",
                            r: "codex-i18n-cache-bootstrap",
                            s: [],
                            is_device_based: true
                        }
                    },
                    values: {
                        "0": {
                            enable_i18n: true,
                            locale_source: "SYSTEM"
                        }
                    },
                    param_stores: {},
                    sdk_flags: {},
                    exposures: {}
                };
                const cacheValue = {
                    source: "Bootstrap",
                    data: JSON.stringify(syntheticValues),
                    receivedAt: Date.now(),
                    stableID: context.stableID ?? null,
                    fullUserHash: null
                };
                localStorage.setItem(cacheKey, JSON.stringify(cacheValue));
                keys = [cacheKey];
                bootstrapCreated = true;
            }
        }
        catch {
            // The diagnostic below explains why bootstrap could not be created.
        }
    }

    if (keys.length === 0) {
        let totalStorageKeys = 0;
        for (let index = 0; index < localStorage.length; index += 1) {
            totalStorageKeys += 1;
        }
        const statsigRoot = window.__STATSIG__ || globalThis.__STATSIG__;
        const statsigClient = getStatsigClient();
        let statsigValues = null;
        let targetLayerState = null;
        try {
            if (statsigClient) {
                const context = statsigClient.getContext();
                statsigValues = context.values;
                const layer = statsigClient.getLayer(targetLayer, {
                    disableExposureLog: true
                });
                if (layer) {
                    targetLayerState = String(layer.get("enable_i18n", "missing"));
                }
            }
        }
        catch {
            // Diagnostics are best-effort.
        }
        return JSON.stringify({
            ok: false,
            error: "No Statsig evaluation cache was found in the Codex page within 45 seconds.",
            keys: [],
            entries: [],
            modified: 0,
            alreadyTrue: 0,
            cacheKeyCount: 0,
            seededFromMemory,
            bootstrapCreated,
            diagnostics: {
                origin: String(location.origin || ""),
                href: String(location.href || ""),
                totalStorageKeys,
                hasStatsigRoot: Boolean(statsigRoot),
                hasStatsigClient: Boolean(statsigClient),
                statsigStatus: statsigClient ? String(statsigClient.loadingStatus || "") : "",
                hasContextValues: Boolean(statsigValues),
                contextHasUpdates: Boolean(statsigValues && statsigValues.has_updates === true),
                targetLayerState
            }
        });
    }

    const hasOwn = (value, key) =>
        value !== null &&
        typeof value === "object" &&
        Object.prototype.hasOwnProperty.call(value, key);

    const valueAt = (values, index) => {
        if (values === null || values === undefined || index === null || index === undefined) {
            return undefined;
        }
        return values[String(index)] ?? values[index];
    };

    const patchPayload = payload => {
        const layerMap = payload && payload.layer_configs;
        const values = payload && payload.values;
        if (!layerMap || typeof layerMap !== "object") {
            return { found: false, changed: false, alreadyTrue: false };
        }

        const candidates = [];
        const targetCandidates = [];
        const seen = new Set();
        const addCandidate = (candidate, isTarget) => {
            if (
                candidate !== null &&
                typeof candidate === "object" &&
                !seen.has(candidate)
            ) {
                seen.add(candidate);
                candidates.push(candidate);
                if (isTarget) {
                    targetCandidates.push(candidate);
                }
            }
        };

        for (const [name, metadata] of Object.entries(layerMap)) {
            if (!metadata || typeof metadata !== "object") {
                continue;
            }

            const isTarget = name === targetLayer || name === targetLayerHash;
            if (metadata.v !== undefined) {
                addCandidate(valueAt(values, metadata.v), isTarget);
            }
            addCandidate(metadata.value, isTarget);

            if (isTarget) {
                addCandidate(metadata, true);
            }
        }

        let found = false;
        let changed = false;
        let alreadyTrue = false;

        for (const candidate of candidates) {
            if (hasOwn(candidate, "enable_i18n")) {
                found = true;
                if (candidate.enable_i18n === true) {
                    alreadyTrue = true;
                }
                else {
                    candidate.enable_i18n = true;
                    changed = true;
                }
            }
        }

        if (!found && targetCandidates.length > 0) {
            found = true;
            targetCandidates[0].enable_i18n = true;
            changed = true;
        }

        return { found, changed, alreadyTrue };
    };

    const processed = [];
    let modified = 0;
    let alreadyTrue = 0;

    for (const key of keys) {
        try {
            const raw = localStorage.getItem(key);
            if (raw === null) {
                continue;
            }

            const wrapper = JSON.parse(raw);
            if (!wrapper || !hasOwn(wrapper, "data")) {
                processed.push({ key, status: "not-a-statsig-cache-wrapper" });
                continue;
            }

            const dataWasString = typeof wrapper.data === "string";
            const payload = dataWasString ? JSON.parse(wrapper.data) : wrapper.data;
            const result = patchPayload(payload);

            if (!result.found) {
                processed.push({ key, status: "layer-not-found" });
                continue;
            }

            if (result.changed) {
                wrapper.data = dataWasString ? JSON.stringify(payload) : payload;
                localStorage.setItem(key, JSON.stringify(wrapper));
                modified += 1;
                processed.push({ key, status: "modified" });
            }
            else {
                if (result.alreadyTrue) {
                    alreadyTrue += 1;
                }
                processed.push({ key, status: "already-true" });
            }
        }
        catch (error) {
            processed.push({
                key,
                status: "error",
                error: String(error && error.message ? error.message : error)
            });
        }
    }

    return JSON.stringify({
        ok: modified > 0 || alreadyTrue > 0,
        modified,
        alreadyTrue,
        cacheKeyCount: keys.length,
        seededFromMemory,
        bootstrapCreated,
        entries: processed
    });
})()"""

def recv_exact(s, count):
    data = b""
    while len(data) < count:
        chunk = s.recv(count - len(data))
        if not chunk: raise RuntimeError("调试连接意外关闭")
        data += chunk
    return data

def evaluate(url, expression, timeout):
    u = urlsplit(url)
    if u.scheme != 'ws' or u.hostname not in ('127.0.0.1', 'localhost'):
        raise RuntimeError('拒绝连接非本机调试地址')
    s = socket.create_connection(('127.0.0.1', u.port), timeout=timeout)
    s.settimeout(timeout)
    key = base64.b64encode(os.urandom(16)).decode()
    path = u.path + (('?' + u.query) if u.query else '')
    request = (f'GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{u.port}\r\n'
               f'Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n'
               'Sec-WebSocket-Version: 13\r\n\r\n')
    s.sendall(request.encode())
    header = b''
    while not header.endswith(b'\r\n\r\n'):
        header += recv_exact(s, 1)
        if len(header) > 16384: raise RuntimeError('WebSocket 响应过长')
    expected = base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
    if not header.startswith(b'HTTP/1.1 101') or expected.lower() not in header.decode('latin1').lower():
        raise RuntimeError('WebSocket 握手失败')
    def send(op, payload):
        n=len(payload); mask=os.urandom(4)
        length=bytes([0x80|n]) if n<126 else (bytes([0xfe])+struct.pack('!H',n) if n<65536 else bytes([0xff])+struct.pack('!Q',n))
        s.sendall(bytes([0x80|op])+length+mask+bytes(v^mask[i%4] for i,v in enumerate(payload)))
    msg=json.dumps({'id':1,'method':'Runtime.evaluate','params':{'expression':expression,'awaitPromise':True,'returnByValue':True}}).encode()
    send(1,msg); fragments=b''
    while True:
        a,b=recv_exact(s,2); n=b&127
        if n==126: n=struct.unpack('!H',recv_exact(s,2))[0]
        elif n==127: n=struct.unpack('!Q',recv_exact(s,8))[0]
        if n>16*1024*1024: raise RuntimeError('调试响应过大')
        mask=recv_exact(s,4) if b&128 else None
        data=recv_exact(s,n)
        if mask: data=bytes(v^mask[i%4] for i,v in enumerate(data))
        op=a&15
        if op==8: raise RuntimeError('调试连接已关闭')
        if op==9: send(10,data); continue
        if op not in (0,1): continue
        fragments+=data
        if not a&128: continue
        response=json.loads(fragments); fragments=b''
        if response.get('id') != 1: continue
        s.close()
        if 'error' in response: raise RuntimeError(str(response['error']))
        result=response['result']
        if 'exceptionDetails' in result: raise RuntimeError('页面脚本执行失败: '+str(result['exceptionDetails'].get('text')))
        return json.loads(result['result']['value'])

def main():
    ap=argparse.ArgumentParser(description='为 macOS Codex 写入中文功能开关缓存')
    ap.add_argument('--app', default='/Applications/ChatGPT.app', help='Codex 应用路径')
    ap.add_argument('--port', type=int, default=0, help='本机调试端口（默认随机空闲端口）')
    ap.add_argument('--timeout', type=int, default=60, help='等待应用启动的秒数（默认 60）')
    ap.add_argument('--bootstrap-missing', action='store_true', help='没有缓存时创建最小 i18n 缓存，其他功能使用默认行为')
    args=ap.parse_args()
    if sys.platform!='darwin': raise RuntimeError('此工具仅支持 macOS')
    if not 0<=args.port<=65535 or args.timeout<5: raise RuntimeError('端口或等待时间无效')
    app=os.path.realpath(os.path.expanduser(args.app))
    exe=os.path.join(app,'Contents/MacOS/ChatGPT')
    if not os.path.isfile(exe): raise RuntimeError('找不到 Codex 应用：'+exe)
    info=subprocess.run(['/usr/libexec/PlistBuddy','-c','Print :CFBundleIdentifier',os.path.join(app,'Contents/Info.plist')],capture_output=True,text=True)
    if info.stdout.strip()!='com.openai.codex': raise RuntimeError('应用的 Bundle ID 不是 com.openai.codex')
    processes=subprocess.check_output(['ps','-ax','-o','command='],text=True)
    if any(line.strip().startswith(exe) and '--type=' not in line for line in processes.splitlines()):
        raise RuntimeError('Codex 正在运行，请完全退出 Codex 后在外部终端运行此命令')
    if args.port: port=args.port
    else:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0)); port=probe.getsockname()[1]
    # Reject an existing listener; never send a patch to an unrelated application.
    with socket.socket() as probe:
        try: probe.bind(('127.0.0.1',port))
        except OSError: raise RuntimeError('调试端口已被占用')
    print(f'正在启动 Codex，调试端口 127.0.0.1:{port} ...',flush=True)
    subprocess.Popen(['/usr/bin/open','-a',app,'--args',f'--remote-debugging-port={port}',f'--remote-allow-origins=http://127.0.0.1:{port}'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    deadline=time.monotonic()+args.timeout; target=None
    while time.monotonic()<deadline:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list',timeout=2) as response: targets=json.load(response)
            pages=[x for x in targets if x.get('type')=='page' and x.get('url','').startswith('app://') and x.get('webSocketDebuggerUrl')]
            pages.sort(key=lambda x:not x['url'].startswith('app://-/index.html'))
            if pages: target=pages[0]; break
        except (OSError,ValueError): pass
        time.sleep(.5)
    if not target: raise RuntimeError('未发现 Codex 调试页面；请退出 Codex 后重试')
    expression=EXPRESSION.replace('__CODEX_I18N_BOOTSTRAP_MISSING__','true' if args.bootstrap_missing else 'false')
    result=evaluate(target['webSocketDebuggerUrl'],expression,max(args.timeout,60))
    if not result.get('ok'):
        print('诊断信息：',json.dumps(result.get('diagnostics',{}),ensure_ascii=False))
        raise RuntimeError(result.get('error','未找到可修改的 i18n Layer；如接受创建最小缓存可使用 --bootstrap-missing'))
    print(f"完成：修改 {result.get('modified',0)} 项，原本已启用 {result.get('alreadyTrue',0)} 项。")
    if result.get('bootstrapCreated'): print('已创建最小 i18n 缓存。')
    print('请完全退出 Codex，再正常启动并检查中文界面。调试端口会随退出关闭。')

if __name__=='__main__':
    try: main()
    except (Exception, KeyboardInterrupt) as e:
        print('错误：'+str(e),file=sys.stderr); sys.exit(1)
