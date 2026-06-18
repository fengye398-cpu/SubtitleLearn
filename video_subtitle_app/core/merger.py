import os
import re
import subprocess
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Callable

# 简化版的 standalone_merge，参考 cut_video_audio_subs_v0.3.py
def _probe_duration(path: str) -> float:
    if not path:
        return 0.0
    try:
        r = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=nw=1:nk=1', path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
           creationflags=subprocess.CREATE_NO_WINDOW)
        return float((r.stdout or '0').strip())
    except Exception:
        return 0.0

_num_re = re.compile(r"(\d+)")

def _leading_num(s: str) -> int:
    m = _num_re.search(Path(s).stem)
    return int(m.group(1)) if m else 0


def _write_concat_list(paths: List[str]) -> str:
    import tempfile
    f = tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='w', encoding='utf-8')
    with f as fp:
        for p in paths:
            # 需要对路径中的反斜杠和单引号转义
            escaped = os.path.abspath(p).replace("\\", "\\\\").replace("'", "\\'")
            fp.write(f"file '{escaped}'\n")
    return f.name


def _concat_copy(paths: List[str], out_path: str) -> bool:
    if not paths:
        return False
    lst = _write_concat_list(paths)
    try:
        cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', out_path]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          creationflags=subprocess.CREATE_NO_WINDOW)
        return r.returncode == 0 and os.path.exists(out_path)
    finally:
        try:
            os.remove(lst)
        except Exception:
            pass


def _merge_subtitles_from_folder(srt_paths: List[str], durations: List[float], merged_srt: str, gap: float) -> bool:
    """将各段 srt 合并到一个 srt，使用真实时长推进时间轴，并添加最小间隔 gap
    参考 cut_video_audio_subs_v0.3.py 的实现逻辑"""
    try:
        import pysrt
        from datetime import timedelta

        def format_timedelta(td):
            """格式化时间差为SRT格式"""
            total_seconds = int(td.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            milliseconds = td.microseconds // 1000
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

        merged_subs = []
        current_time = timedelta(seconds=0)

        for idx, srt_path in enumerate(srt_paths):
            if not srt_path or not os.path.exists(srt_path):
                # 如果字幕文件不存在，仍然需要推进时间轴
                if idx < len(durations):
                    current_time += timedelta(seconds=durations[idx])
                continue

            subs = pysrt.open(srt_path, encoding='utf-8')
            for sub in subs:
                # 转换原始时间为timedelta
                sub_start = timedelta(
                    hours=sub.start.hours,
                    minutes=sub.start.minutes,
                    seconds=sub.start.seconds,
                    milliseconds=sub.start.milliseconds
                )
                sub_end = timedelta(
                    hours=sub.end.hours,
                    minutes=sub.end.minutes,
                    seconds=sub.end.seconds,
                    milliseconds=sub.end.milliseconds
                )

                # 计算新的时间轴
                new_start = current_time + sub_start
                new_end = current_time + sub_end

                # 防止重叠：确保与前一个字幕有足够间隔
                if merged_subs:
                    prev_end = merged_subs[-1]['end']
                    if new_start < prev_end + timedelta(seconds=gap):
                        new_start = prev_end + timedelta(seconds=gap)
                        if new_end < new_start:
                            new_end = new_start + timedelta(milliseconds=500)

                merged_subs.append({
                    'index': len(merged_subs) + 1,
                    'start': new_start,
                    'end': new_end,
                    'text': sub.text
                })

            # 用真实时长推进时间轴（参考外部脚本的逻辑）
            if idx < len(durations):
                current_time += timedelta(seconds=durations[idx])

        # 保存合并后的字幕
        with open(merged_srt, "w", encoding="utf-8") as f:
            for sub in merged_subs:
                f.write(f"{sub['index']}\n")
                f.write(f"{format_timedelta(sub['start'])} --> {format_timedelta(sub['end'])}\n")
                f.write(f"{sub['text']}\n\n")

        return True
    except Exception as e:
        print(f"合并字幕失败: {e}")
        return False


def standalone_merge(input_dir: str, output_dir: str, gap: float = 0.2,
                     progress: Optional[Callable[[str], None]] = None,
                     project_name: str = None) -> bool:
    """
    集成合并功能 - 统一双字幕文件生成逻辑：
    - 将 input_dir 下的片段视频/音频以"流复制"合并为单文件
    - 生成两个字幕文件（基于视频时长 + 基于音频时长）
    - 输出结构：
      * {project_name}.mp4 - 合并后的视频
      * {project_name}.srt - 视频字幕（基于视频时长）
      * {project_name}_audio.mp3 - 合并后的音频
      * {project_name}_audio.srt - 音频字幕（基于音频时长）
    - 清理原始字幕文件和临时文件（静默执行）
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    media_exts_video = {'.mp4', '.mkv', '.mov'}
    media_exts_audio = {'.mp3', '.wav', '.m4a', '.aac'}

    files = sorted([str(p) for p in Path(input_dir).glob('*') if p.is_file()], key=_leading_num)
    video_files = [f for f in files if Path(f).suffix.lower() in media_exts_video]
    audio_files = [f for f in files if Path(f).suffix.lower() in media_exts_audio]

    if not video_files and not audio_files:
        if progress: progress('未找到可合并的媒体文件')
        return False

    # 使用项目名称或默认名称
    base_name = project_name if project_name else "merged_project"

    # 分别合并视频和音频
    ok_video = True
    ok_audio = True

    if video_files:
        if progress: progress('开始合并视频文件...')
        merged_video = str(Path(output_dir) / f"{base_name}.mp4")
        ok_video = _concat_copy(video_files, merged_video)
        if not ok_video:
            if progress: progress('合并视频失败')
            return False

    if audio_files:
        if progress: progress('开始合并音频文件...')
        merged_audio = str(Path(output_dir) / f"{base_name}_audio.mp3")
        ok_audio = _concat_copy(audio_files, merged_audio)
        if not ok_audio:
            if progress: progress('合并音频失败')
            return False

    # 准备字幕文件列表
    srt_files: List[str] = []
    original_srt_files: List[str] = []  # 记录原始字幕文件用于后续清理

    # 根据视频文件或音频文件构建字幕列表
    media_files = video_files if video_files else audio_files
    for m in media_files:
        s = str(Path(m).with_suffix('.srt'))
        srt_files.append(s if os.path.exists(s) else '')
        if os.path.exists(s):
            original_srt_files.append(s)

    # 1️⃣ 生成视频字幕文件（基于视频时长）
    ok_video_srt = True
    if video_files:
        if progress: progress('开始合并视频字幕...')
        video_durations = [_probe_duration(p) for p in video_files]
        merged_video_srt = str(Path(output_dir) / f"{base_name}.srt")
        ok_video_srt = _merge_subtitles_from_folder(srt_files, video_durations, merged_video_srt, gap)
        if not ok_video_srt:
            if progress: progress('合并视频字幕失败')

    # 2️⃣ 生成音频字幕文件（基于音频时长）
    ok_audio_srt = True
    if audio_files:
        if progress: progress('开始合并音频字幕...')
        audio_durations = [_probe_duration(p) for p in audio_files]
        merged_audio_srt = str(Path(output_dir) / f"{base_name}_audio.srt")
        ok_audio_srt = _merge_subtitles_from_folder(srt_files, audio_durations, merged_audio_srt, gap)
        if not ok_audio_srt:
            if progress: progress('合并音频字幕失败')

    # 兼容性处理：如果只有视频或只有音频，ok_srt取对应的结果
    ok_srt = ok_video_srt and ok_audio_srt

    # 清理原始字幕文件和json文件（静默执行，不输出日志）
    if ok_srt:
        _cleanup_original_files(input_dir, original_srt_files, None)

    if progress:
        progress('合并完成！')
    return ok_video and ok_audio and ok_srt


def _cleanup_original_files(input_dir: str, original_srt_files: List[str],
                           progress: Optional[Callable[[str], None]] = None):
    """只清理临时文件，绝不删除任何输入文件（静默执行，不输出日志）"""
    try:
        # 静默执行清理，不输出任何日志
        input_path = Path(input_dir)
        cleaned_count = 0

        # 删除JSON配置文件（这些是临时文件）
        json_files = list(input_path.glob('*.json'))
        for json_file in json_files:
            try:
                json_file.unlink()
                cleaned_count += 1
            except Exception:
                pass  # 静默忽略错误

        # 删除明确的临时文件（带特殊后缀的）
        temp_patterns = ['*_original.srt', '*_backup.srt', '*_temp.srt', '*_validated.srt', '*concat*.txt', '*list*.txt']
        for pattern in temp_patterns:
            temp_files = list(input_path.glob(pattern))
            for temp_file in temp_files:
                try:
                    temp_file.unlink()
                    cleaned_count += 1
                except Exception:
                    pass  # 静默忽略错误

    except Exception:
        pass  # 静默忽略所有错误
