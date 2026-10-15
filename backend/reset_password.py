"""管理员重置用户密码（忘记密码时用）。

为什么要这个脚本：本服务没有接短信 / 邮件，所以做不了「自助找回密码」。
按当前规模（小范围自用），最省事也最安全的做法就是管理员在服务器上重置。

用法（在服务器 backend 目录下、用后端自己的 venv python）：

    # 1) 让脚本生成一个随机强密码并打印给你，你再转告用户
    python reset_password.py alice

    # 2) 或者直接指定新密码（注意 shell 历史会留痕，尽量用方式 1）
    python reset_password.py alice 'MyNewPass123'

    # 3) 只列出所有用户（忘了用户名时用）
    python reset_password.py --list

说明：
- 脚本会做与注册一致的密码强度校验，弱密码会被拒绝。
- 重置后建议让用户在「账号菜单 → 修改密码」里自行改成自己记得住的密码。
- **已签发的 JWT 不会因此失效**（token 只带 sub/exp）。若怀疑账号被盗用，
  请同时更换 .env 里的 SECRET_KEY 并重启服务，这会让所有旧 token 立刻失效。
"""
from __future__ import annotations

import secrets
import string
import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models import User
from app.security import hash_password, password_error


def _random_password(length: int = 14) -> str:
    """生成易读、可手抄的随机密码：避免 0/O、1/l/I 这类容易看错的字符。"""
    alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _list_users(db) -> None:
    rows = db.scalars(select(User).order_by(User.id)).all()
    if not rows:
        print("（没有任何用户）")
        return
    print(f"{'id':>6}  {'用户名':<24} 角色")
    for u in rows:
        print(f"{u.id:>6}  {u.username:<24} {u.role or '-'}")


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] in ("--list", "-l", "list"):
        with SessionLocal() as db:
            _list_users(db)
        return 0

    if len(argv) < 2:
        print(__doc__)
        return 2

    username = argv[1].strip()
    new_password = argv[2] if len(argv) >= 3 else _random_password()
    generated = len(argv) < 3

    err = password_error(new_password, username)
    if err:
        print(f"[拒绝] 新密码不符合要求：{err}")
        return 1

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        if not user:
            print(f"[失败] 找不到用户：{username}")
            print("       可用 `python reset_password.py --list` 查看全部用户名。")
            return 1

        user.hashed_password = hash_password(new_password)
        db.commit()
        uid = user.id

    print(f"[成功] 已重置用户 {username} (id={uid}) 的密码")
    if generated:
        print(f"       新密码：{new_password}")
        print("       ↑ 这个密码只显示这一次，请立刻转告用户并在安全渠道传递。")
    print("       提醒：已登录的旧 token 仍然有效；如需立即失效，请更换 SECRET_KEY 后重启服务。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
