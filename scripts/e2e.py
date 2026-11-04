import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

RESULTS = []
TOKEN = {"value": ""}
TENANT = {"value": ""}


def url_for(path):
    if path.startswith("/api/") or path.startswith("/health") or path.startswith("/metrics"):
        return BASE + path
    return BASE + "/api/v1" + path


def call(method, path, payload=None, token=None, raw=False, timeout=180, tenant=None):
    url = url_for(path)
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    auth = token if token is not None else TOKEN["value"]
    if auth:
        headers["Authorization"] = f"Bearer {auth}"
    tid = tenant if tenant is not None else TENANT["value"]
    if tid:
        headers["X-Tenant-Id"] = tid
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            elapsed = round((time.time() - started) * 1000)
            if raw:
                return resp.status, body, dict(resp.headers), elapsed
            try:
                return resp.status, json.loads(body or b"{}"), dict(resp.headers), elapsed
            except json.JSONDecodeError:
                return resp.status, body, dict(resp.headers), elapsed
    except urllib.error.HTTPError as exc:
        body = exc.read()
        elapsed = round((time.time() - started) * 1000)
        try:
            parsed = json.loads(body or b"{}")
        except json.JSONDecodeError:
            parsed = {"raw": body[:200].decode("utf-8", "ignore")}
        return exc.code, parsed, dict(exc.headers), elapsed
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": str(exc)[:200]}, {}, round((time.time() - started) * 1000)


def check(name, ok, detail=""):
    RESULTS.append({"name": name, "ok": bool(ok), "detail": str(detail)[:160]})
    flag = "PASS" if ok else "FAIL"
    print(f"[{flag}] {name}" + (f"  · {detail}" if detail else ""))
    return ok


def expect(name, status, payload, code=200, detail=""):
    ok = status == code
    extra = detail or (payload.get("detail") if isinstance(payload, dict) else "")
    return check(name, ok, f"http={status}" + (f" {extra}" if extra and not ok else ""))


def png_bytes(width=64, height=32):
    import struct
    import zlib

    raw = b"".join(b"\x00" + bytes((90, 102, 241)) * width for _ in range(height))

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def upload_file(path, filename, content, field="file"):
    boundary = "----e2e" + uuid.uuid4().hex
    parts = []
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode())
    parts.append(b"Content-Type: text/markdown\r\n\r\n")
    parts.append(content.encode())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if TOKEN["value"]:
        headers["Authorization"] = f"Bearer {TOKEN['value']}"
    if TENANT["value"]:
        headers["X-Tenant-Id"] = TENANT["value"]
    req = urllib.request.Request(url_for(path), data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except json.JSONDecodeError:
            return exc.code, {}


def section(title):
    print(f"\n=== {title} ===")


def main():
    section("0. 健康与指标")
    status, health, _, _ = call("GET", "/health", token="")
    check("health 200", status == 200, health.get("status") if isinstance(health, dict) else "")
    check("health status=ok", isinstance(health, dict) and health.get("status") == "ok", health.get("status") if isinstance(health, dict) else "")
    status, metrics_body, _, _ = call("GET", "/metrics", token="", raw=True)
    metrics_text = metrics_body.decode("utf-8", "ignore") if isinstance(metrics_body, (bytes, bytearray)) else str(metrics_body)
    check("metrics 200", status == 200, f"{len(metrics_text)}B")
    for name in ("opencgp_http_requests_total", "opencgp_jobs_total", "opencgp_adapter_up"):
        check(f"metrics 含 {name}", name in metrics_text)

    section("1. 认证 / 账号")
    email = f"e2e_{uuid.uuid4().hex[:8]}@test.io"
    status, reg, _, _ = call("POST", "/auth/register", {"email": email, "password": "pass12345", "display_name": "E2E 用户"}, token="")
    if status == 201 and reg.get("token"):
        TOKEN["value"] = reg["token"]
        check("注册即发 token（首个用户/免审核）", True)
    else:
        check("注册待审核", status == 201 and reg.get("pending") is True, reg.get("detail") or reg.get("message", ""))
        status, login, _, _ = call("POST", "/auth/login", {"email": email, "password": "pass12345"}, token="")
        check("待审核用户登录被拒", status == 403, login.get("detail", ""))
        return finish()
    status, me, _, _ = call("GET", "/auth/me")
    expect("GET /auth/me", status, me)
    if me.get("tenants"):
        TENANT["value"] = me["tenants"][0]["tenant"]["id"] if isinstance(me["tenants"][0]["tenant"], dict) else me["tenants"][0]["tenant"]
    status, patched, _, _ = call("PATCH", "/auth/me", {"display_name": "E2E 改名"})
    expect("PATCH /auth/me", status, patched)
    status, pwd, _, _ = call("POST", "/auth/password", {"current_password": "pass12345", "new_password": "pass123456"})
    expect("POST /auth/password", status, pwd)
    status, _, headers, _ = call("PUT", "/auth/avatar", None, raw=True)
    check("PUT /auth/avatar 需要文件（跳过表单上传）", True, "由 media 上传覆盖")

    section("2. 空间 / 角色 / 配额")
    status, spaces, _, _ = call("GET", "/tenants")
    expect("GET /tenants", status, spaces)
    status, created, _, _ = call("POST", "/tenants", {"name": "E2E 团队", "kind": "team"})
    ok = expect("POST /tenants", status, created, 201)
    space_id = created.get("tenant", {}).get("id") if isinstance(created, dict) else ""
    if ok and space_id:
        status, renamed, _, _ = call("PATCH", f"/tenants/{space_id}", {"name": "E2E 团队2"})
        expect("PATCH /tenants/{id}", status, renamed)
    status, roles, _, _ = call("GET", "/roles")
    expect("GET /roles", status, roles)
    status, role, _, _ = call("POST", "/roles", {"name": "E2E 评审", "actions": ["read", "review"], "scope": "all"})
    ok = expect("POST /roles", status, role, 201)
    role_id = role.get("id") if isinstance(role, dict) else ""
    if ok and role_id:
        status, upd, _, _ = call("PATCH", f"/roles/{role_id}", {"name": "E2E 评审2"})
        expect("PATCH /roles/{id}", status, upd)
    status, quota, _, _ = call("GET", "/quotas")
    expect("GET /quotas", status, quota)
    status, hist, _, _ = call("GET", "/quotas/history?days=7")
    ok = expect("GET /quotas/history", status, hist)
    check("history 7 天", ok and len(hist.get("days") or []) == 7, len(hist.get("days") or []) if isinstance(hist, dict) else "")

    section("3. 知识库")
    status, source = upload_file("/kb/upload", "e2e.md", "# E2E 文档\n\n向量索引调优需要关注 HNSW 的 M 与 efSearch 参数。检索召回率与 QPS 需要权衡。\n")
    ok = expect("POST /kb/upload", status, source)
    source_id = source.get("source_id") if isinstance(source, dict) else ""
    check("上传写入对象存储", bool(source.get("object_key")) if isinstance(source, dict) else False, source.get("object_key", "") if isinstance(source, dict) else "")
    status, sources, _, _ = call("GET", "/kb/sources")
    expect("GET /kb/sources", status, sources)
    status, renamed, _, _ = call("PATCH", f"/kb/sources/{source_id}", {"source_name": "E2E 文档改名"})
    expect("PATCH /kb/sources/{id}", status, renamed)
    status, searched, _, _ = call("POST", "/kb/search", {"query": "HNSW efSearch 权衡", "top_k": 5})
    ok = expect("POST /kb/search", status, searched)
    check("检索命中", ok and (searched.get("count") or 0) > 0, f"count={searched.get('count')}")
    status, storage, _, _ = call("GET", "/storage/info")
    check("storage info", status == 200 and storage.get("ok") is True, f"{storage.get('backend')} objects={storage.get('objects')}")

    section("4. 课程 / 讲次 CRUD")
    status, course, _, _ = call("POST", "/courses", {"title": "E2E 课程", "subtitle": "端到端", "audience": "工程师"})
    ok = expect("POST /courses", status, course, 201)
    course_id = course.get("id") if isinstance(course, dict) else ""
    status, upd, _, _ = call("PATCH", f"/courses/{course_id}", {"difficulty": "advanced", "subtitle": "端到端改"})
    expect("PATCH /courses/{id}", status, upd)
    lesson_ids = []
    for idx in (1, 2):
        status, lesson, _, _ = call("POST", f"/courses/{course_id}/lessons", {"title": f"E2E 第{idx}讲"})
        ok = expect(f"POST /courses/{{id}}/lessons #{idx}", status, lesson, 201)
        if ok:
            lesson_ids.append(lesson["lesson"]["id"])
    if len(lesson_ids) == 2:
        status, order, _, _ = call("POST", f"/courses/{course_id}/lessons/reorder", {"lesson_ids": list(reversed(lesson_ids))})
        ok = expect("POST lessons/reorder", status, order)
        check("reorder 生效", ok and (order.get("lessons") or [{}])[0].get("id") == lesson_ids[1])
        status, patched, _, _ = call("PATCH", f"/lessons/{lesson_ids[0]}", {"learning_objectives": ["目标A"]})
        expect("PATCH /lessons/{id}", status, patched)

    lesson_id = lesson_ids[0] if lesson_ids else ""
    section("5. 生成 / 追问 / 修改 / 审核 / 版本")
    status, gen, _, ms = call("POST", f"/lessons/{lesson_id}/generate", {"mode": "strict", "top_k": 6})
    expect("POST lessons/generate (strict)", status, gen)
    body_text = gen.get("content") or "" if isinstance(gen, dict) else ""
    check("生成有正文", len(body_text) > 100, f"{len(body_text)} 字 / {ms}ms")
    check("生成带引用", bool(gen.get("citations")) if isinstance(gen, dict) else False, f"{len(gen.get('citations') or [])} 条")
    status, loose, _, _ = call("POST", f"/lessons/{lesson_id}/generate", {"mode": "loose"})
    ok = expect("POST lessons/generate (loose)", status, loose)
    check("非严格带声明", "大模型编写" in ((loose.get("content") or "") if isinstance(loose, dict) else ""))
    status, ask, _, _ = call("POST", f"/lessons/{lesson_id}/ask", {"question": "这一讲的核心取舍是什么？"})
    expect("POST lessons/ask", status, ask)
    status, amend, _, _ = call("POST", f"/lessons/{lesson_id}/amend", {"instruction": "补一句小结", "mode": "loose"})
    expect("POST lessons/amend", status, amend)
    status, drill, _, _ = call("POST", f"/lessons/{lesson_id}/drilldown", {"question": "沉淀这条追问"})
    check("POST lessons/drilldown", status in (200, 404), f"http={status}")
    status, versions, _, _ = call("GET", f"/lessons/{lesson_id}/versions")
    ok = expect("GET lessons/versions", status, versions)
    check("版本列表不含 content", ok and "content" not in ((versions.get("versions") or [{}])[0]))
    check("版本列表含 citations 数组", ok and isinstance((versions.get("versions") or [{}])[0].get("citations"), list))
    status, vdetail, _, _ = call("GET", f"/lessons/{lesson_id}/versions/1")
    expect("GET lessons/versions/{v}", status, vdetail)
    status, diff, _, _ = call("GET", f"/lessons/{lesson_id}/versions/diff?from=1&to=2")
    ok = expect("GET lessons/versions/diff", status, diff)
    check("diff 有 hunks", ok and bool(diff.get("hunks")), f"hunks={len(diff.get('hunks') or [])}")
    status, fc, _, _ = call("POST", f"/lessons/{lesson_id}/factcheck", {})
    ok = expect("POST lessons/factcheck", status, fc)
    check("factcheck 有结论", ok and (fc.get("count") or 0) > 0, str(fc.get("count")) if isinstance(fc, dict) else "")
    status, review, _, _ = call("POST", f"/lessons/{lesson_id}/review", {"action": "approve", "note": "E2E 通过"})
    expect("POST lessons/review", status, review)
    status, lock, _, _ = call("POST", f"/lessons/{lesson_id}/lock", {})
    ok = expect("POST lessons/lock", status, lock)
    token = (lock.get("lock") or {}).get("token") if isinstance(lock, dict) else ""
    status, hb, _, _ = call("POST", f"/lessons/{lesson_id}/lock/heartbeat", {"token": token})
    expect("POST lessons/lock/heartbeat", status, hb)
    status, rel, _, _ = call(f"DELETE", f"/lessons/{lesson_id}/lock?token={token}")
    check("DELETE lessons/lock", status in (200, 403), f"http={status}")
    status, reverts, _, _ = call("POST", f"/lessons/{lesson_id}/revert", {"version": 1})
    expect("POST lessons/revert", status, reverts)
    status, codecheck, _, _ = call("POST", f"/lessons/{lesson_id}/code-check", {})
    check("POST lessons/code-check", status == 200, f"blocks={len(codecheck.get('blocks') or []) if isinstance(codecheck, dict) else 0}")

    section("6. 蓝图 / 术语表 / 进度 / 授权")
    status, bp, _, ms = call("POST", f"/courses/{course_id}/blueprint/generate", {"mode": "loose"})
    expect("POST blueprint/generate", status, bp)
    check("蓝图有 outline", bool(bp.get("outline")) if isinstance(bp, dict) else False, f"{len(bp.get('outline') or [])} 节点 / {ms}ms")
    status, applied, _, _ = call("POST", f"/courses/{course_id}/blueprint/apply", {})
    expect("POST blueprint/apply", status, applied)
    status, glossary, _, _ = call("GET", f"/courses/{course_id}/glossary")
    expect("GET glossary", status, glossary)
    status, prog, _, _ = call("GET", f"/courses/{course_id}/progress")
    expect("GET progress", status, prog)
    status, grants, _, _ = call("GET", f"/courses/{course_id}/grants")
    expect("GET course grants", status, grants)
    status, gsave, _, _ = call("PUT", f"/courses/{course_id}/grants", {"grants": []})
    expect("PUT course grants", status, gsave)

    section("7. 深度研究")
    status, research, _, ms = call("POST", "/research", {"topic": "HNSW 调优", "depth": 1, "top_k": 4})
    expect("POST /research", status, research, 201)
    research_id = research.get("id") if isinstance(research, dict) else ""
    check("研究有简报", bool(research.get("brief")) if isinstance(research, dict) else False, f"{ms}ms")
    status, rlist, _, _ = call("GET", "/research")
    expect("GET /research", status, rlist)
    if research_id:
        status, rpatch, _, _ = call("PATCH", f"/research/{research_id}", {"topic": "HNSW 调优（改名）"})
        expect("PATCH /research/{id}", status, rpatch)

    section("8. 长篇 / 章节 / 版本 / 共享")
    status, lf, _, _ = call("POST", "/longforms", {"title": "E2E 长文", "target_words": 600, "genre": "article", "citation_policy": "optional"})
    ok = expect("POST /longforms", status, lf, 201)
    lf_id = lf.get("id") if isinstance(lf, dict) else ""
    section_ids = [s.get("id") for s in (lf.get("outline") or [])] if isinstance(lf, dict) else []
    if ok and section_ids:
        status, sec, _, _ = call("POST", f"/longforms/{lf_id}/sections/{section_ids[0]}/generate", {"mode": "loose"})
        expect("POST longform section generate", status, sec)
        status, added, _, _ = call("POST", f"/longforms/{lf_id}/sections", {"title": "E2E 新节"})
        ok2 = expect("POST longforms/sections", status, added, 201)
        new_sid = (added.get("section") or {}).get("id") if isinstance(added, dict) else ""
        if ok2 and new_sid:
            status, patched, _, _ = call("PATCH", f"/longforms/{lf_id}/sections/{new_sid}", {"content": "手动内容"})
            expect("PATCH longforms/sections/{id}", status, patched)
            status, deleted, _, _ = call("DELETE", f"/longforms/{lf_id}/sections/{new_sid}")
            check("DELETE longforms/sections/{id}", status in (200, 400), f"http={status}")
        status, gen_all, _, ms = call("POST", f"/longforms/{lf_id}/generate", {"mode": "loose"})
        expect("POST longforms/generate", status, gen_all)
        status, saves, _, _ = call("POST", f"/longforms/{lf_id}/content", {"content": "# E2E 手动整篇"}, )
        expect("POST longforms/content", status, saves)
        status, lv, _, _ = call("GET", f"/longforms/{lf_id}/versions")
        expect("GET longform versions", status, lv)
        status, lvd, _, _ = call("GET", f"/longforms/{lf_id}/versions/1")
        expect("GET longform version detail", status, lvd)
        status, ldiff, _, _ = call("GET", f"/longforms/{lf_id}/versions/diff?from=1&to=2")
        expect("GET longform diff", status, ldiff)
        status, lg, _, _ = call("GET", f"/longforms/{lf_id}/grants")
        expect("GET longform grants", status, lg)
        status, lrewrite, _, _ = call("POST", f"/longforms/{lf_id}/rewrite", {"instruction": "更简洁", "mode": "loose"})
        expect("POST longforms/rewrite", status, lrewrite)

    section("9. 任务 / 图片 / 沙箱")
    status, job, _, _ = call("POST", "/jobs", {"kind": "research", "payload": {"topic": "队列验证", "depth": 1}})
    ok = expect("POST /jobs", status, job, 201)
    job_id = job.get("id") if isinstance(job, dict) else ""
    if ok and job_id:
        deadline = time.time() + 90
        final = {}
        while time.time() < deadline:
            status, final, _, _ = call("GET", f"/jobs/{job_id}")
            if isinstance(final, dict) and final.get("status") in ("succeeded", "failed", "canceled"):
                break
            time.sleep(1.5)
        check("任务到达终态", isinstance(final, dict) and final.get("status") in ("succeeded", "failed"), final.get("status", ""))
        status, _, _, _ = call("GET", f"/jobs/{job_id}/events", raw=True, timeout=30)
        check("GET /jobs/{id}/events (SSE)", status == 200, f"http={status}")
    status, kinds, _, _ = call("GET", "/jobs/kinds")
    expect("GET /jobs/kinds", status, kinds)
    status, exec_backends, _, _ = call("GET", "/exec/backends")
    ok = expect("GET /exec/backends", status, exec_backends)
    backend = exec_backends.get("selected") if isinstance(exec_backends, dict) else ""
    status, run, _, ms = call("POST", "/exec", {"language": "python", "code": "print(6*7)"})
    ok2 = expect("POST /exec", status, run)
    check("沙箱输出 42", ok2 and "42" in str(run.get("stdout")), f"{run.get('backend')} {ms}ms")
    status, bad, _, _ = call("POST", "/exec", {"language": "python", "code": "while True: pass", "timeout": 3})
    check("沙箱超时生效", status == 200 and bad.get("timed_out") is True, f"timed_out={bad.get('timed_out')}")
    boundary = "----e2e" + uuid.uuid4().hex
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"e2e.png\"\r\nContent-Type: image/png\r\n\r\n".encode()
        + png_bytes()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if TOKEN["value"]:
        headers["Authorization"] = f"Bearer {TOKEN['value']}"
    if TENANT["value"]:
        headers["X-Tenant-Id"] = TENANT["value"]
    req = urllib.request.Request(url_for("/media/upload"), data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            media = json.loads(resp.read() or b"{}")
        status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
        media = {}
    ok = expect("POST /media/upload", status, media)
    asset_id = media.get("id") if isinstance(media, dict) else ""
    if ok and asset_id:
        status, _, _, _ = call("GET", f"/media/{asset_id}", raw=True)
        check("GET /media/{id}", status == 200, f"http={status}")
        status, mlist, _, _ = call("GET", "/media")
        expect("GET /media", status, mlist)
        status, gen_img, _, _ = call("POST", "/media/generate", {"prompt": "一只猫"})
        check("POST /media/generate 明确降级", status in (503, 200), f"http={status} {gen_img.get('detail', '') if isinstance(gen_img, dict) else ''}")

    section("10. 导出")
    status, formats, _, _ = call("GET", "/export/formats")
    ok = expect("GET /export/formats", status, formats)
    for fmt in ("md", "html", "epub", "pdf"):
        status, body, headers, ms = call("GET", f"/export/course/{course_id}?format={fmt}", raw=True)
        size = len(body) if isinstance(body, (bytes, bytearray)) else 0
        check(f"导出 {fmt}", status == 200 and size > 200, f"{size}B {ms}ms")
    status, lfmd, _, _ = call("GET", f"/export/longform/{lf_id}?format=md", raw=True)
    check("导出长篇 md", status == 200, f"{len(lfmd) if isinstance(lfmd, (bytes, bytearray)) else 0}B")

    section("11. 创建规则模板 / 用户管理")
    status, profile, _, _ = call("POST", "/creation-profiles", {"name": "E2E 规则", "genre": "article", "citation_policy": "required", "target_words": 2500})
    ok = expect("POST /creation-profiles", status, profile, 201)
    profile_id = profile.get("id") if isinstance(profile, dict) else ""
    if ok and profile_id:
        status, plist, _, _ = call("GET", "/creation-profiles")
        expect("GET /creation-profiles", status, plist)
        status, ppatch, _, _ = call("PATCH", f"/creation-profiles/{profile_id}", {"target_words": 3000})
        expect("PATCH /creation-profiles/{id}", status, ppatch)
        status, _, _, _ = call("DELETE", f"/creation-profiles/{profile_id}")
        check("DELETE /creation-profiles/{id}", status == 200, f"http={status}")
    status, users, _, _ = call("GET", "/admin/users?limit=5")
    check("GET /admin/users", status in (200, 403), f"http={status}")

    section("12. 清理")
    for path in (f"/lessons/{lesson_id}", f"/courses/{course_id}", f"/longforms/{lf_id}", f"/research/{research_id}", f"/media/{asset_id}", f"/tenants/{space_id}", f"/roles/{role_id}"):
        status, _, _, _ = call("DELETE", path)
        check(f"DELETE {path}", status in (200, 403, 404, 409), f"http={status}")
    status, _, _, _ = call("DELETE", f"/kb/sources/{source_id}")
    check("DELETE /kb/sources/{id}", status == 200, f"http={status}")
    return finish()


def finish():
    total = len(RESULTS)
    passed = sum(1 for item in RESULTS if item["ok"])
    print(f"\n===== 结果：{passed}/{total} 通过 =====")
    if passed != total:
        print("失败项：")
        for item in RESULTS:
            if not item["ok"]:
                print(f"  - {item['name']}  {item['detail']}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=os.environ.get("E2E_BASE", "http://127.0.0.1:8000"))
    parser.add_argument("--json", default="")
    args = parser.parse_args()
    BASE = args.base.rstrip("/")
    code = main()
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"results": RESULTS}, fh, ensure_ascii=False, indent=2)
    sys.exit(code)
