#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频字幕定位应用
主程序入口

功能特性：
- 根据字幕文件切割视频为独立片段
- 支持快速播放和预览
- 支持批量导出和合并
- 本地数据库管理
- 关键词搜索和筛选
"""
#前端导入没问题了，但导出还要修复
#跨项目合并导出没有问题，但是导出顺序不对，需要在优化。
#导出成提示10秒后会关闭缺陷；导出窗口删除不需要的"片段合并"按钮
#修复导入成成功提示10S自动关闭窗口已修复；增加输入目录路径按钮
#修复了"打开输入目录"报错问题；单个项目数据删除；基本能凑合用了
#2.”视频字幕定位运用“主界面的”打开缓存目录“按钮移除
# 3.“存储管理”窗口中的”项目管理“栏增加滚条、参考”视频字幕定位运用“主界面的列表增加项目管理按页面显示及首页 、上页 、自动跳转第几页 、下页、末页，自定义页数相关功能
# 4.将”储存统计“栏中的”数据库大小： 412.0 KB 缓存大小： 14.5 KB“者两个数据单独在”管理操作“右侧在开一个栏，其余的参数及”整个“储存统计”栏移除，这样项目管理窗口就更大了
#跨项目生成合并片段问题已修复；数据库大小显示问题已修复，但是清完后最低都还有40KB而不是0KB
#单个项目和多个跨项目导出时间轴和闪轴基本可以用了
#跨项目输出srt修正输出，存在时间轴重大不对会停止输出，建议重新编码，只对跨项目修正
#单项目和跨项目增加输出SRT校验
import sys
import os
import traceback
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 早期FFmpeg检查，避免导入时错误
def early_ffmpeg_check():
    """在导入其他模块前进行FFmpeg检查"""
    try:
        import subprocess
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        # FFmpeg不可用，显示友好提示
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()

            result = messagebox.askyesno(
                "FFmpeg环境配置",
                "⚠️ 检测到FFmpeg未正确配置\n\n"
                "SubtitleLearn需要FFmpeg来处理视频和音频文件。\n\n"
                "请按照以下步骤配置FFmpeg：\n"
                "1. 下载FFmpeg并解压到任意目录\n"
                "2. 将FFmpeg的bin目录添加到系统环境变量PATH中\n"
                "3. 重启应用程序\n\n"
                "是否现在打开FFmpeg下载页面？",
                icon="warning"
            )

            if result:
                import webbrowser
                webbrowser.open("https://ffmpeg.org/download.html")

            root.destroy()

        except Exception:
            # 如果GUI不可用，使用控制台输出
            print("=" * 50)
            print("⚠️  FFmpeg环境配置错误")
            print("=" * 50)
            print("SubtitleLearn需要FFmpeg来处理视频和音频文件。")
            print()
            print("请按照以下步骤配置FFmpeg：")
            print("1. 下载FFmpeg: https://ffmpeg.org/download.html")
            print("2. 解压到任意目录（如：C:\\ffmpeg）")
            print("3. 将FFmpeg的bin目录添加到系统环境变量PATH中")
            print("4. 重启应用程序")
            print("=" * 50)
            input("按回车键退出...")

        return False

# 执行早期检查
if not early_ffmpeg_check():
    sys.exit(1)

try:
    import tkinter as tk
    from tkinter import messagebox

    # 导入应用模块
    from ui.main_window import MainWindow
    from config.settings import app_config
    from database.manager import db_manager

except ImportError as e:
    print(f"导入模块失败：{e}")
    print("请确保已安装所有依赖包：")
    print("pip install -r requirements.txt")
    sys.exit(1)

def check_dependencies():
    """检查依赖项"""
    missing_deps = []
    
    try:
        import pysrt
    except ImportError:
        missing_deps.append("pysrt")
    
    try:
        # 强制配置MoviePy使用系统FFmpeg，避免使用imageio_ffmpeg
        import os
        os.environ['FFMPEG_BINARY'] = 'ffmpeg'  # 设置环境变量
        os.environ['IMAGEIO_FFMPEG_EXE'] = 'ffmpeg'  # 防止imageio_ffmpeg查找内置二进制

        import moviepy.config as mp_config
        mp_config.FFMPEG_BINARY = "ffmpeg"  # 直接设置配置

        # 阻止MoviePy尝试导入imageio_ffmpeg
        import sys
        if 'imageio_ffmpeg' not in sys.modules:
            # 创建一个假的imageio_ffmpeg模块，防止MoviePy尝试导入
            class FakeImageIOFFmpeg:
                def get_ffmpeg_exe(self):
                    return 'ffmpeg'
            sys.modules['imageio_ffmpeg'] = FakeImageIOFFmpeg()

        import moviepy
    except ImportError:
        missing_deps.append("moviepy")
    
    # FFmpeg已在早期检查中验证，这里跳过

    # 检查其他依赖项
    if missing_deps:
        error_msg = "缺少以下依赖项：\n" + "\n".join(f"• {dep}" for dep in missing_deps)
        error_msg += "\n\n请安装缺少的依赖项后重试。"

        # 尝试显示图形界面错误
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("依赖项检查失败", error_msg)
            root.destroy()
        except:
            print(error_msg)

        return False
    
    return True

def setup_error_handling():
    """设置全局错误处理"""
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        print(f"未处理的异常：\n{error_msg}")
        
        # 尝试显示图形界面错误
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "程序错误",
                f"程序遇到未处理的错误：\n\n{exc_type.__name__}: {exc_value}\n\n"
                "详细错误信息已输出到控制台。"
            )
            root.destroy()
        except:
            pass
    
    sys.excepthook = handle_exception

def initialize_app():
    """初始化应用"""
    try:
        # 确保应用目录存在
        app_config.app_dir.mkdir(exist_ok=True)
        app_config.cache_dir.mkdir(exist_ok=True)
        
        # 初始化数据库
        db_manager.init_database()
        
        print(f"应用初始化完成")
        print(f"配置目录：{app_config.app_dir}")
        print(f"缓存目录：{app_config.cache_dir}")
        print(f"数据库文件：{app_config.db_file}")
        
        return True
        
    except Exception as e:
        error_msg = f"应用初始化失败：{e}"
        print(error_msg)
        
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("初始化失败", error_msg)
            root.destroy()
        except:
            pass
        
        return False

def main():
    """主函数"""
    print("=" * 50)
    print("SubtitleLearn - 外语学习字幕片段工具")
    print("版本：1.0.0")
    print("=" * 50)
    
    # 设置错误处理
    setup_error_handling()
    
    # 检查依赖项
    print("检查依赖项...")
    if not check_dependencies():
        return 1
    print("依赖项检查通过")
    
    # 初始化应用
    print("初始化应用...")
    if not initialize_app():
        return 1
    
    try:
        # 创建并运行主窗口
        print("启动主界面...")
        app = MainWindow()

        # 设置信号处理器，用于强制退出
        import signal
        def signal_handler(signum, frame):
            print(f"收到信号 {signum}，强制退出...")
            try:
                app.force_exit()
            except:
                import os
                os._exit(1)

        signal.signal(signal.SIGINT, signal_handler)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal_handler)

        app.run()

        print("应用正常退出")
        return 0
        
    except KeyboardInterrupt:
        print("\n用户中断程序")
        return 0
        
    except Exception as e:
        print(f"程序运行错误：{e}")
        traceback.print_exc()
        return 1
    
    finally:
        # 清理资源
        try:
            # 播放器资源由MainWindow.on_closing()负责清理
            # 这里无需额外清理
            print("应用程序资源清理完成")

        except Exception as e:
            print(f"清理资源时异常：{e}")

        print("程序清理完成")

if __name__ == "__main__":
    sys.exit(main())
