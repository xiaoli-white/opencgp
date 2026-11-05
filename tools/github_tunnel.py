import asyncio, socket

TARGETS = {"github.com": "140.82.112.3", "api.github.com": "140.82.112.6", "codeload.github.com": "140.82.112.9"}
LISTEN = ("127.0.0.1", 8899)

async def pipe(r, w):
    try:
        while True:
            data = await r.read(65536)
            if not data:
                break
            w.write(data)
            await w.drain()
    except Exception:
        pass
    finally:
        try:
            w.close()
        except Exception:
            pass

async def handle(reader, writer):
    try:
        head = await reader.readuntil(b"\r\n\r\n")
    except Exception:
        writer.close(); return
    line = head.split(b"\r\n")[0].decode("latin1")
    parts = line.split()
    if len(parts) < 2 or parts[0] != "CONNECT":
        writer.write(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n"); writer.close(); return
    host, _, port = parts[1].partition(":")
    ip = TARGETS.get(host, host)
    try:
        remote_r, remote_w = await asyncio.open_connection(ip, int(port or 443))
    except Exception as exc:
        writer.write(f"HTTP/1.1 502 Bad Gateway\r\n\r\n{exc}".encode()); writer.close(); return
    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    await writer.drain()
    await asyncio.gather(pipe(reader, remote_w), pipe(remote_r, writer))

async def main():
    server = await asyncio.start_server(handle, *LISTEN)
    print("proxy on", LISTEN, flush=True)
    async with server:
        await server.serve_forever()

asyncio.run(main())
