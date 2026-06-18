"""
波形生成器
用于生成音频波形图，支持时间轴编辑功能
"""

import os
import subprocess
import tempfile
from typing import Tuple, Optional
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
import io

class WaveformGenerator:
    """音频波形生成器"""

    def __init__(self):
        self.temp_dir = tempfile.gettempdir()

    def extract_waveform_data(self, video_path: str, start_time: float,
                            duration: float, width: int = 800,
                            height: int = 120) -> Optional[np.ndarray]:
        """
        从视频中提取音频波形数据

        Args:
            video_path: 视频文件路径
            start_time: 开始时间（秒）
            duration: 持续时间（秒）
            width: 波形图宽度
            height: 波形图高度

        Returns:
            波形数据数组或None
        """
        try:
            # 使用ffmpeg提取音频波形数据
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-ss', str(start_time),
                '-t', str(duration),
                '-filter_complex', f'showwavespic=s={width}x{height}:colors=0x3B82F6',
                '-frames:v', '1',
                '-f', 'image2pipe',
                '-vcodec', 'png',
                '-'
            ]

            result = subprocess.run(cmd, capture_output=True, timeout=30)

            if result.returncode != 0:
                print(f"FFmpeg错误: {result.stderr.decode()}")
                return None

            # 将PNG数据转换为PIL图像
            image = Image.open(io.BytesIO(result.stdout))

            # 转换为numpy数组
            waveform_data = np.array(image)

            return waveform_data

        except subprocess.TimeoutExpired:
            print("波形生成超时")
            return None
        except Exception as e:
            print(f"波形生成失败: {e}")
            return None

    def generate_waveform_image(self, video_path: str, start_time: float,
                              duration: float, width: int = 800,
                              height: int = 120) -> Optional[str]:
        """
        生成音频波形图并保存为临时文件

        Args:
            video_path: 视频文件路径
            start_time: 开始时间（秒）
            duration: 持续时间（秒）
            width: 波形图宽度
            height: 波形图高度

        Returns:
            波形图文件路径或None
        """
        try:
            # 生成临时文件路径
            temp_file = os.path.join(
                self.temp_dir,
                f"waveform_{start_time:.3f}_{duration:.3f}_{width}x{height}.png"
            )

            print(f"开始生成波形图: {video_path}, 开始时间: {start_time}, 持续时间: {duration}")

            # 使用ffmpeg生成波形图，使用更稳定的时间参数
            # 计算实际时间范围：提前1秒开始，增加2秒时长，保证至少3秒总时长
            actual_start = max(0, start_time - 1.0)
            actual_duration = max(duration + 2.0, 3.0)

            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-ss', str(actual_start),
                '-t', str(actual_duration),
                '-filter_complex', f'showwavespic=s={width}x{height}:colors=0x3B82F6',
                '-frames:v', '1',
                '-y',  # 覆盖输出文件
                temp_file
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            print(f"FFmpeg返回码: {result.returncode}")
            if result.stdout:
                print(f"FFmpeg标准输出: {result.stdout}")
            if result.stderr:
                print(f"FFmpeg错误输出: {result.stderr}")

            if result.returncode != 0:
                error_output = result.stderr
                print(f"FFmpeg错误: {error_output}")
                # 检查常见错误
                if "No such file or directory" in error_output:
                    print(f"视频文件不存在: {video_path}")
                elif "Invalid data found" in error_output:
                    print(f"无效的视频文件: {video_path}")
                elif "No audio stream" in error_output:
                    print(f"视频文件没有音频流: {video_path}")
                elif "ffmpeg: not found" in error_output or "is not recognized" in error_output:
                    print("FFmpeg未安装或不在PATH中")
                return None

            if os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
                return temp_file
            else:
                print("波形图文件未生成或为空，尝试备用方案...")
                return self._fallback_waveform_generation(video_path, start_time, duration, width, height, temp_file)

        except subprocess.TimeoutExpired:
            print("波形生成超时")
            return None
        except Exception as e:
            print(f"波形生成失败: {e}")
            return None

    def _fallback_waveform_generation(self, video_path: str, start_time: float,
                                    duration: float, width: int, height: int, temp_file: str):
        """
        备用波形生成方案：先转换为WAV，再生成波形
        """
        try:
            print("[备用方案] 开始WAV转换波形生成...")

            # 创建临时WAV文件
            wav_file = os.path.join(
                self.temp_dir,
                f"temp_audio_{start_time:.3f}_{duration:.3f}.wav"
            )

            # 步骤1：从视频提取音频为WAV
            ffmpeg_start = max(0, start_time - 0.5)
            ffmpeg_duration = max(duration + 1.0, 2.0)

            extract_cmd = [
                'ffmpeg',
                '-i', video_path,
                '-ss', str(ffmpeg_start),
                '-t', str(ffmpeg_duration),
                '-vn',  # 不包含视频
                '-acodec', 'pcm_s16le',  # 使用PCM格式
                '-ar', '44100',  # 标准采样率
                '-ac', '1',  # 单声道
                '-y',
                wav_file
            ]

            print(f"[备用方案] 提取音频: {' '.join(extract_cmd)}")
            extract_result = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=30)

            if extract_result.returncode != 0:
                print(f"[备用方案] 音频提取失败: {extract_result.stderr}")
                return None

            if not os.path.exists(wav_file):
                print("[备用方案] WAV文件未生成")
                return None

            # 步骤2：从WAV生成波形
            waveform_cmd = [
                'ffmpeg',
                '-i', wav_file,
                '-filter_complex', f'showwavespic=s={width}x{height}:colors=0x3B82F6',
                '-frames:v', '1',
                '-y',
                temp_file
            ]

            print(f"[备用方案] 生成波形图: {' '.join(waveform_cmd)}")
            waveform_result = subprocess.run(waveform_cmd, capture_output=True, text=True, timeout=30)

            # 清理临时WAV文件
            try:
                os.remove(wav_file)
                print(f"[备用方案] 已清理临时文件: {wav_file}")
            except OSError:
                pass

            # 检查结果
            if waveform_result.returncode == 0 and os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
                print(f"[备用方案] 波形图生成成功: {temp_file}")
                return temp_file
            else:
                print(f"[备用方案] 波形图生成失败: {waveform_result.stderr}")
                return None

        except Exception as e:
            print(f"[备用方案] 异常: {e}")
            return None

    def generate_multi_segment_waveform(self, video_path: str,
                                      segments: list, width: int = 800,
                                      height: int = 120) -> Optional[str]:
        """
        生成多片段组合波形图

        Args:
            video_path: 视频文件路径
            segments: 片段列表，每个片段包含 (start_time, duration, is_current)
            width: 波形图宽度
            height: 波形图高度

        Returns:
            波形图文件路径或None
        """
        try:
            if not segments:
                return None

            # 计算总时长
            total_duration = sum(duration for _, duration, _ in segments)

            # 生成基础波形图
            base_waveform = self.generate_waveform_image(
                video_path,
                segments[0][0],
                total_duration,
                width,
                height
            )

            if not base_waveform:
                return None

            # 打开基础波形图
            base_image = Image.open(base_waveform)
            draw = ImageDraw.Draw(base_image)

            # 为不同片段添加不同的视觉效果
            current_x = 0
            for start_time, duration, is_current in segments:
                segment_width = int(width * duration / total_duration)

                if not is_current:
                    # 非当前片段添加半透明灰色覆盖
                    overlay = Image.new('RGBA', (segment_width, height), (128, 128, 128, 64))
                    base_image.paste(overlay, (current_x, 0), overlay)

                current_x += segment_width

            # 保存修改后的波形图
            output_file = os.path.join(
                self.temp_dir,
                f"multi_waveform_{segments[0][0]:.3f}_{total_duration:.3f}_{width}x{height}.png"
            )
            base_image.save(output_file)

            return output_file

        except Exception as e:
            print(f"多片段波形生成失败: {e}")
            return None

    def cleanup_temp_files(self):
        """清理临时波形图文件"""
        try:
            temp_files = [
                f for f in os.listdir(self.temp_dir)
                if f.startswith('waveform_') and f.endswith('.png')
            ]

            for temp_file in temp_files:
                file_path = os.path.join(self.temp_dir, temp_file)
                try:
                    os.remove(file_path)
                except OSError:
                    pass

        except Exception as e:
            print(f"清理临时文件失败: {e}")

    def get_audio_duration(self, video_path: str) -> Optional[float]:
        """
        获取视频的音频时长

        Args:
            video_path: 视频文件路径

        Returns:
            音频时长（秒）或None
        """
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                duration = float(result.stdout.strip())
                return duration
            else:
                return None

        except Exception as e:
            print(f"获取音频时长失败: {e}")
            return None

# 全局波形生成器实例
waveform_generator = WaveformGenerator()