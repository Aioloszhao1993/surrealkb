-- SurrealKB 数据库初始化
-- 若不需要自动建表，可手动执行本脚本
CREATE DATABASE IF NOT EXISTS `surrealkb`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE `surrealkb`;

-- 表结构由 SQLAlchemy 在应用启动时自动创建（Base.metadata.create_all）。
-- 如需手工建表，请启动一次后端后导出，或参照 app/models.py。

-- 参考结构（自动建表时可忽略）：
-- users(id, username, email, hashed_password, avatar, created_at)
-- videos(id, title, description, filename, original_name, cover, size, mime_type, views, owner_id, created_at)
-- likes(id, user_id, video_id, created_at)          UNIQUE(user_id, video_id)
-- favorites(id, user_id, video_id, created_at)      UNIQUE(user_id, video_id)
