-- 添加双语字幕支持
-- 添加原文和译文字段

-- 添加新字段
ALTER TABLE subtitle_segments ADD COLUMN text_primary TEXT;
ALTER TABLE subtitle_segments ADD COLUMN text_secondary TEXT;

-- 迁移现有数据（将text内容复制到text_primary）
UPDATE subtitle_segments 
SET text_primary = text 
WHERE text_primary IS NULL OR text_primary = '';

-- 创建索引以提高查询性能
CREATE INDEX IF NOT EXISTS idx_segments_text_primary ON subtitle_segments(text_primary);
CREATE INDEX IF NOT EXISTS idx_segments_text_secondary ON subtitle_segments(text_secondary);

