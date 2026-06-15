"""CLI 子命令处理"""
import argparse
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import Config, BackupLogger
from core.engine import backup_all


def cmd_run(args):
    """立即执行一次备份"""
    config = Config()
    logger = BackupLogger()
    dest = config.destination
    sources = config.sources

    if not dest:
        print("错误：未设置备份存放位置，请先在 GUI 中设置。")
        return
    if not sources:
        print("没有待备份文件夹。")
        return

    print("正在备份...")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results = backup_all(sources, dest)

    success_count = 0
    for r in results:
        log_entry = {
            "path": r["path"],
            "time": now_str,
            "success": r["success"],
            "zip_path": r["zip_path"],
            "skipped": r["skipped"],
            "error": r.get("error", ""),
        }
        logger.add_entry(log_entry)

        if r["path"] and r["path"] != "(空路径)":
            fail_reason = ""
            if not r["success"]:
                fail_reason = r.get("error", "")
                skipped = r.get("skipped", [])
                if skipped:
                    fail_reason += f" 跳过 {len(skipped)} 个锁定文件"
            config.update_source_status(r["path"], r["success"], fail_reason)

        if r["success"]:
            success_count += 1

    config.save()

    fail_count = len(results) - success_count
    print(f"备份完成：成功 {success_count} 个", end="")
    if fail_count > 0:
        print(f"，失败 {fail_count} 个")
        for r in results:
            if not r["success"]:
                print(f"  - {r['path']}: {r.get('error', '')}")
                skipped = r.get("skipped", [])
                if skipped:
                    print(f"    跳过 {len(skipped)} 个锁定文件")
    else:
        print()


def cmd_status(args):
    """显示当前配置状态"""
    config = Config()
    data = config.to_dict()
    print(f"备份存放位置: {data['destination'] or '(未设置)'}")
    print(f"定时间隔: {data['interval_minutes']} 分钟")
    print(f"开机自动备份: {'是' if data['auto_backup_on_start'] else '否'}")
    print(f"开机自启动: {'是' if data['auto_start_with_system'] else '否'}")
    print(f"待备份文件夹 ({len(data['sources'])} 个):")
    for s in data["sources"]:
        status = "启用" if s.get("enabled", True) else "暂停"
        last = s.get("last_backup_time", "")
        last_str = f" (最近备份: {last})" if last else ""
        print(f"  [{status}] {s.get('path', '')}{last_str}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="AutoBackup", description="AutoBackup v1.0.2 自动备份工具")
    sub = parser.add_subparsers(dest="command", help="子命令")

    sub.add_parser("run", help="立即执行一次备份")
    sub.add_parser("status", help="查看当前配置状态")

    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.command == "run":
        cmd_run(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parse_args(["--help"])
