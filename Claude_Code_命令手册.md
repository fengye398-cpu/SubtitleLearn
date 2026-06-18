# Claude Code 命令手册
📊 完整的窗口管理策略

  | 窗口类型   | 模态/非模态 | 防止多开 | 状态     |
  |--------|--------|------|--------|
  | 帮助窗口   | 非模态    | ✅ 是  | ✅ 已实现  |
  | 导出对话框  | 非模态    | ✅ 是  | ✅ 已实现  |
  | 集成合并窗口 | 非模态    | ✅ 是  | ✅ 已实现  |
  | 简单合并窗口 | 模态     | 自动   | ✅ 保持原样 |
  | 导入对话框  | 模态     | 自动   | ✅ 保持原样 |


## 📋 目录
- [基础命令](#基础命令)
- [模型切换](#模型切换)
- [文件操作](#文件操作)
- [搜索功能](#搜索功能)
- [斜杠命令](#斜杠命令)
- [快捷操作](#快捷操作)

---

## 基础命令

### /help
显示帮助信息，查看所有可用命令

```bash
/help
```

### /clear
清除当前对话历史

```bash
/clear
```

### /exit
退出 Claude Code

```bash
/exit
```

---

## 模型切换

### 查看当前模型
在对话中询问 Claude 当前使用的模型

```
你现在使用什么模型？
```

### 可用模型

| 模型名称 | 代号 | 特点 | 适用场景 |
|---------|------|------|---------|
| **Claude Sonnet 4.5** | `claude-sonnet-4-5` | 最新最强，平衡性能和速度 | 复杂代码分析、大型项目 |
| **Claude Opus 4** | `claude-opus-4` | 最强推理能力 | 架构设计、复杂算法 |
| **Claude Sonnet 3.5** | `claude-sonnet-3-5` | 快速响应 | 日常开发、简单任务 |
| **Claude Haiku** | `claude-haiku` | 速度最快 | 快速问答、简单查询 |

### 如何切换模型

**方法1：配置文件**（推荐）

编辑配置文件：`~/.config/claude-code/config.json`

```json
{
  "model": "claude-sonnet-4-5"
}
```

**方法2：命令行参数**

```bash
claude-code --model claude-opus-4
```

**方法3：环境变量**

```bash
export CLAUDE_MODEL=claude-sonnet-3-5
claude-code
```

---

## 文件操作

### @ 符号 - 引用文件

```
@文件名.txt
```

**示例**：
```
@重复.txt 分析这个日志文件
@config.py 看看这个配置有什么问题
```

**支持的格式**：
- 文本文件：`.txt`, `.md`, `.log`
- 代码文件：`.py`, `.js`, `.java`, `.cpp`
- 配置文件：`.json`, `.yaml`, `.xml`
- 图片文件：`.png`, `.jpg`, `.jpeg`
- PDF 文件：`.pdf`

### 通配符引用

```
@src/**/*.py   # 引用 src 目录下所有 Python 文件
@*.md          # 引用当前目录所有 Markdown 文件
```

---

## 搜索功能

### 搜索代码

```
在项目中搜索 "function_name"
```

### 查找文件

```
找到所有包含 "config" 的文件
```

### 正则表达式搜索

```
搜索所有匹配 /def\s+\w+/ 的代码
```

---

## 斜杠命令

### 内置斜杠命令

```bash
/help          # 显示帮助
/clear         # 清除对话
/exit          # 退出程序
/model         # 查看当前模型
/tokens        # 查看token使用情况
```

### 自定义斜杠命令

在 `.claude/commands/` 目录下创建 Markdown 文件

**示例**：创建 `/review` 命令

文件：`.claude/commands/review.md`
```markdown
请审查以下代码：
1. 检查代码质量
2. 找出潜在bug
3. 提供优化建议
```

使用：
```
/review @main.py
```

---

## 快捷操作

### 代码分析

```
分析这个函数的时间复杂度 @algorithm.py
```

### Bug 诊断

```
@error.log 为什么会出现这个错误？
```

### 重构建议

```
@legacy_code.py 如何重构这段代码？
```

### 添加功能

```
在 @app.py 中添加用户认证功能
```

### 生成文档

```
为 @api.py 生成 API 文档
```

---

## 工作流程示例

### 1. Debug 流程

```markdown
1. @error_log.txt 分析错误日志
2. 找到相关代码文件
3. 定位问题
4. 提供修复方案
5. 我确认后再修改代码
```

### 2. 新功能开发

```markdown
1. 我需要添加一个用户登录功能
2. Claude 分析现有架构
3. 提出实现方案
4. 我确认方案
5. Claude 编写代码
6. 测试和优化
```

### 3. 代码审查

```markdown
1. /review @new_feature.py
2. Claude 审查代码
3. 指出问题和改进点
4. 我决定是否修改
```

---

## 高级技巧

### 1. 多文件对比

```
对比 @old_version.py 和 @new_version.py 的区别
```

### 2. 批量操作

```
检查所有 @src/**/*.py 文件的代码风格
```

### 3. 上下文引用

```
根据 @requirements.txt 检查 @app.py 是否缺少依赖
```

### 4. 图片分析

```
@screenshot.png 这个界面有什么问题？
```

---

## 注意事项

### ⚠️ 重要原则

1. **询问后再动手** - Claude 应该先分析，得到你的确认后再修改代码
2. **备份重要文件** - 修改代码前做好备份
3. **理解而非盲目应用** - 理解 Claude 的建议，不要直接复制粘贴
4. **保持系统稳定** - 修改时确保不破坏现有功能

### 💡 最佳实践

1. **清晰表达需求** - 说明你想要什么效果
2. **提供足够上下文** - 使用 @ 引用相关文件
3. **逐步推进** - 复杂任务分解为小步骤
4. **及时反馈** - 测试后告诉 Claude 结果

---

## 快速参考

### 常用命令速查

```bash
# 基础
/help                    # 帮助
/clear                   # 清除对话
/exit                    # 退出

# 文件操作
@文件名                  # 引用文件
@*.py                    # 引用所有Python文件
@src/**/*.js             # 递归引用JS文件

# 任务
分析 @code.py            # 代码分析
修复 @bug.py             # Bug修复
优化 @slow.py            # 性能优化
文档 @api.py             # 生成文档
测试 @function.py        # 编写测试

# 搜索
搜索 "关键词"            # 全项目搜索
查找包含 "TODO" 的文件   # 文件查找
```

---

## 配置示例

### .claude/config.json

```json
{
  "model": "claude-sonnet-4-5",
  "temperature": 0.7,
  "max_tokens": 4096,
  "context_window": 200000,
  "auto_save": true,
  "code_style": "pep8"
}
```

### .claude/commands/

自定义命令目录结构：

```
.claude/
  commands/
    review.md         # /review 命令
    test.md           # /test 命令
    deploy.md         # /deploy 命令
    refactor.md       # /refactor 命令
```

---

## 实用例子

### 例子1：分析日志重复问题

```
@重复.txt 分析为什么日志重复输出
```

### 例子2：添加功能

```
需要在导出窗口添加最小化按钮，先分析现有代码
@integrated_export_dialog.py
```

### 例子3：性能优化

```
@video_processor.py 这个文件处理大视频时很慢，如何优化？
```

### 例子4：Bug修复

```
程序运行时点击"显示桌面"后窗口无法恢复
@main_window.py 和 @export_dialog.py 看看是什么原因
```

---

## 学习资源

- 官方文档：https://docs.claude.com/claude-code
- GitHub：https://github.com/anthropics/claude-code
- 社区论坛：https://community.anthropic.com

---

**最后更新**：2025-01-11
**文档版本**：v1.0
**适用于**：Claude Code 最新版本
