"""shizhen 命令行入口。"""
import argparse
import getpass
import json
import os
import sys
import time

from . import __version__
from . import config, naming
from .api import Client
from .errors import (CliError, EXIT_AUTH, EXIT_INPUT, EXIT_OK, EXIT_UNAVAILABLE,
                     exit_code_for)

DEFAULT_TIMEOUT = 600
# 先 3 秒，逐步放宽到 15 秒
POLL_SCHEDULE = (3, 3, 3, 5, 5, 8, 10, 12, 15)
ACTIVE = ("queued", "processing")


class Ctx:
    def __init__(self, env, stdin, stdout, stderr, sleep, clock, json_mode):
        self.env, self.stdin, self.stdout, self.stderr = env, stdin, stdout, stderr
        self.sleep, self.clock, self.json_mode = sleep, clock, json_mode

    def say(self, text):
        print(text, file=self.stderr if self.json_mode else self.stdout)

    def progress(self, text):
        print(text, file=self.stderr)

    def client(self):
        token = config.load_token(self.env)
        if not token:
            raise CliError(EXIT_AUTH, "TOKEN_MISSING",
                           "未找到令牌：请先运行 shizhen login，或设置环境变量 SHIZHEN_TOKEN。")
        return Client(config.api_base(self.env), token)


def poll_delay(index):
    return POLL_SCHEDULE[min(index, len(POLL_SCHEDULE) - 1)]


def job_error(job):
    err = job.get("error") or {}
    code = str(err.get("code") or "JOB_" + str(job.get("state", "FAILED")).upper())
    retryable = bool(err.get("retryable"))
    message = err.get("message") or "任务未能完成（%s）。" % job.get("state")
    return CliError(exit_code_for(0, code, retryable), code, message, retryable,
                    extra={"jobId": job.get("jobId")})


def wait_for_job(ctx, client, job, timeout):
    start = ctx.clock()
    index = 0
    while True:
        state = job.get("state")
        if state == "ready":
            return job
        if state not in ACTIVE:
            raise job_error(job)
        if ctx.clock() - start >= timeout:
            raise CliError(EXIT_UNAVAILABLE, "WAIT_TIMEOUT",
                           "等待超过 %d 秒，任务仍在进行（任务 ID：%s），可稍后用 shizhen download 取回。"
                           % (timeout, job.get("jobId")),
                           True, extra={"jobId": job.get("jobId"), "state": state})
        ctx.progress("处理中（%s）…" % (job.get("stage") or state))
        ctx.sleep(poll_delay(index))
        index += 1
        job = client.job(job["jobId"])


def download_job(ctx, client, job_id, title, kind, outdir):
    grant = client.grant(job_id)
    url = grant.get("downloadUrl") or grant.get("externalDownloadUrl")
    if not url:
        raise CliError(EXIT_UNAVAILABLE, "BAD_RESPONSE", "服务未返回下载地址。", True)
    server_name = grant.get("fileName") or ""
    ext = os.path.splitext(server_name)[1] or (".m4a" if kind == "audio" else ".mp4")
    outdir = outdir or os.getcwd()
    try:
        os.makedirs(outdir, exist_ok=True)
    except OSError as exc:
        raise CliError(EXIT_INPUT, "BAD_OUTPUT_DIR", "无法使用输出目录：%s" % exc)
    if not title:
        title = os.path.splitext(server_name)[0]
    name = naming.file_name(title, kind, ext)
    path = naming.unique_path(outdir, name)
    part = path + ".part"
    size = client.fetch(url, part, grant.get("sizeBytes"))
    if os.path.exists(path):
        path = naming.unique_path(outdir, name)
    os.replace(part, path)
    return {"jobId": job_id, "file": os.path.abspath(path), "fileName": os.path.basename(path),
            "sizeBytes": size}


def lookup_title(client, job_id):
    try:
        for item in client.jobs().get("items", []):
            if item.get("jobId") == job_id:
                return (item.get("parseResult") or {}).get("title", "")
    except CliError:
        pass
    return ""


def summarize_job(job):
    out = {"jobId": job.get("jobId"), "kind": job.get("kind"), "state": job.get("state"),
           "stage": job.get("stage"), "qualityId": job.get("qualityId")}
    asset = job.get("asset")
    if asset:
        out["fileName"] = asset.get("fileName")
        out["sizeBytes"] = asset.get("sizeBytes")
        out["expiresAt"] = asset.get("expiresAt")
    if job.get("error"):
        out["error"] = job["error"]
    title = (job.get("parseResult") or {}).get("title")
    if title:
        out["title"] = title
    return out


# ---- 命令 ----

def cmd_login(ctx, args):
    if ctx.stdin.isatty():
        token = getpass.getpass("粘贴令牌（输入不显示）：")
    else:
        token = ctx.stdin.readline()
    token = token.strip()
    if not token:
        raise CliError(EXIT_INPUT, "TOKEN_EMPTY", "没有从标准输入读到令牌。用法：echo 令牌 | shizhen login")
    Client(config.api_base(ctx.env), token).usage()  # 无效令牌会在这里以退出码 4 失败
    path = config.save_token(ctx.env, token)
    ctx.say("已保存令牌到 %s" % path)
    return {"configPath": path}


def cmd_logout(ctx, args):
    removed = config.delete_token(ctx.env)
    ctx.say("已删除本地令牌。服务端吊销请在小程序里操作。" if removed else "本地没有保存的令牌。")
    return {"removed": removed}


def cmd_parse(ctx, args):
    data = ctx.client().parse(args.url)
    out = {"platform": data.get("platform"), "title": data.get("title"), "author": data.get("author"),
           "duration": data.get("duration"), "isImage": bool(data.get("isImage")),
           "sourceUrl": data.get("sourceUrl"), "contentId": data.get("contentId"),
           "qualities": data.get("qualities") or []}
    duration = ("%s 秒" % out["duration"]) if out["duration"] is not None else "-"
    ctx.say("平台：%s\n标题：%s\n作者：%s\n时长：%s"
            % (out["platform"], out["title"], out["author"] or "-", duration))
    for q in out["qualities"]:
        ctx.say("  清晰度 %s  %s" % (q.get("qualityId"), q.get("label", "")))
    return out


def cmd_extract(ctx, args):
    client = ctx.client()
    parsed = client.parse(args.url)
    if parsed.get("isImage"):
        raise CliError(EXIT_INPUT, "IMAGE_NOT_SUPPORTED", "这是图集，命令行暂不支持图集下载。")
    kind = "audio" if args.audio else "video"
    quality = args.quality or "source"
    ctx.progress("已识别：%s" % parsed.get("title", ""))
    job = client.create_job(parsed.get("sourceUrl") or args.url, kind, quality, parsed.get("contentId", ""))
    if args.no_wait:
        ctx.say("已创建任务 %s（%s）" % (job.get("jobId"), job.get("state")))
        return {"jobId": job.get("jobId"), "state": job.get("state"), "kind": kind}
    job = wait_for_job(ctx, client, job, args.timeout)
    result = download_job(ctx, client, job["jobId"], parsed.get("title", ""), kind, args.output)
    result["state"] = "ready"
    ctx.say("已保存：%s" % result["file"])
    return result


def cmd_jobs(ctx, args):
    client = ctx.client()
    if args.job_id:
        out = summarize_job(client.job(args.job_id))
        ctx.say("%s  %s  %s" % (out["jobId"], out["kind"], out["state"]))
        return out
    items = [summarize_job(i) for i in client.jobs().get("items", [])]
    for i in items:
        ctx.say("%s  %-5s %-10s %s" % (i["jobId"], i["kind"], i["state"], i.get("title", "")))
    if not items:
        ctx.say("没有任务。")
    return {"jobs": items}


def cmd_download(ctx, args):
    client = ctx.client()
    job = client.job(args.job_id)
    if job.get("state") in ACTIVE:
        raise CliError(EXIT_UNAVAILABLE, "JOB_NOT_READY", "任务还在处理中，请稍后再下载。", True,
                       extra={"jobId": args.job_id, "state": job.get("state")})
    if job.get("state") != "ready":
        raise job_error(job)
    result = download_job(ctx, client, args.job_id, lookup_title(client, args.job_id),
                          job.get("kind", "video"), args.output)
    ctx.say("已保存：%s" % result["file"])
    return result


def cmd_usage(ctx, args):
    data = ctx.client().usage()
    out = dict(data)
    if data.get("limited") is False:
        ctx.say("当前账号没有每日额度限制。")
        return out
    limit, remaining = data.get("dailyLimit"), data.get("remaining")
    if isinstance(limit, int) and isinstance(remaining, int):
        out["used"] = max(0, limit - remaining)
        ctx.say("今日已用 %d，剩余 %d（上限 %d），重置时间 %s"
                % (out["used"], remaining, limit, data.get("resetAt", "-")))
    else:
        ctx.say("额度：%s" % json.dumps(data, ensure_ascii=False))
    return out


def build_parser():
    parser = argparse.ArgumentParser(prog="shizhen", description="拾帧命令行：识别分享链接并提取视频/音频")
    parser.add_argument("--version", action="version", version="shizhen " + __version__)
    sub = parser.add_subparsers(dest="command", metavar="命令")
    sub.required = True

    def add(name, helptext):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--json", action="store_true", help="标准输出只输出一个 JSON 对象")
        return p

    add("login", "从标准输入读取令牌并保存")
    add("logout", "删除本地保存的令牌")
    p = add("parse", "识别链接或分享文本")
    p.add_argument("url", help="链接或整段分享文本")
    p = add("extract", "识别、创建任务、等待并下载")
    p.add_argument("url", help="链接或整段分享文本")
    p.add_argument("--audio", action="store_true", help="提取音频")
    p.add_argument("--quality", help="清晰度 ID（见 parse 输出），默认 source")
    p.add_argument("-o", "--output", help="保存目录，默认当前目录")
    p.add_argument("--no-wait", action="store_true", help="只创建任务并返回任务 ID")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="最长等待秒数，默认 600")
    p = add("jobs", "任务列表或单个任务状态")
    p.add_argument("job_id", nargs="?")
    p = add("download", "下载已完成任务的成品")
    p.add_argument("job_id")
    p.add_argument("-o", "--output", help="保存目录，默认当前目录")
    add("usage", "查看当日额度")
    return parser


COMMANDS = {"login": cmd_login, "logout": cmd_logout, "parse": cmd_parse, "extract": cmd_extract,
            "jobs": cmd_jobs, "download": cmd_download, "usage": cmd_usage}


def main(argv=None, env=None, stdin=None, stdout=None, stderr=None, sleep=time.sleep, clock=time.monotonic):
    env = os.environ if env is None else env
    stdin, stdout, stderr = stdin or sys.stdin, stdout or sys.stdout, stderr or sys.stderr
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else EXIT_INPUT
    ctx = Ctx(env, stdin, stdout, stderr, sleep, clock, args.json)
    try:
        result = COMMANDS[args.command](ctx, args)
    except CliError as exc:
        if args.json:
            body = {"ok": False, "code": exc.code, "message": exc.message, "retryable": exc.retryable}
            if exc.reset_at:
                body["resetAt"] = exc.reset_at
            body.update(exc.extra)
            print(json.dumps(body, ensure_ascii=False), file=stdout)
        else:
            print("错误：%s" % exc.message, file=stderr)
            if exc.reset_at:
                print("恢复时间：%s" % exc.reset_at, file=stderr)
        return exc.exit_code
    if args.json:
        print(json.dumps(dict(result, ok=True), ensure_ascii=False), file=stdout)
    return EXIT_OK


def run():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    try:
        return main()
    except KeyboardInterrupt:
        return 130
