#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
带智能校验的导出系统
集成方案B智能校验功能到现有导出流程
"""

import os
import sys
import logging
from typing import Dict, List, Optional, Callable
from pathlib import Path

# 导入现有组件
try:
    from .smart_timeline_validator import smart_validator, SmartTimelineValidator
    SMART_VALIDATION_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] 智能校验模块导入失败: {e}")
    SMART_VALIDATION_AVAILABLE = False

logger = logging.getLogger(__name__)


class ValidationConfig:
    """校验配置"""
    
    def __init__(self):
        self.enabled = True                    # 是否启用智能校验
        self.auto_correct = True               # 是否自动修正
        self.backup_original = True            # 是否备份原文件
        self.validation_level = "standard"     # 校验级别: minimal, standard, thorough
        self.max_deviation_threshold = 5.0     # 最大允许偏差（秒）
        self.report_details = True             # 是否生成详细报告


class ExportWithValidation:
    """带智能校验的导出器"""
    
    def __init__(self, config: Optional[ValidationConfig] = None):
        self.config = config or ValidationConfig()
        self.validator = smart_validator if SMART_VALIDATION_AVAILABLE else None
        self.validation_results = []
        
    def export_with_smart_validation(self, video_path: str, subtitle_path: str, 
                                   output_dir: str, project_name: str,
                                   progress_callback: Optional[Callable] = None) -> Dict:
        """执行带智能校验的导出
        
        Args:
            video_path: 视频文件路径
            subtitle_path: 字幕文件路径
            output_dir: 输出目录
            project_name: 项目名称
            progress_callback: 进度回调函数
            
        Returns:
            导出结果
        """
        if not self.validator:
            return {
                'success': False,
                'error': '智能校验功能不可用',
                'fallback': True
            }
        
        try:
            # 第1步：准备输出路径
            if progress_callback:
                progress_callback(10, 100, "准备输出路径...")
            
            output_subtitle_path = os.path.join(output_dir, f"{project_name}_validated.srt")
            backup_path = os.path.join(output_dir, f"{project_name}_original.srt") if self.config.backup_original else None
            
            # 第2步：备份原文件（如果需要）
            if self.config.backup_original and backup_path:
                if progress_callback:
                    progress_callback(20, 100, "备份原始字幕文件...")
                self._backup_file(subtitle_path, backup_path)
            
            # 第3步：执行智能校验
            if progress_callback:
                progress_callback(30, 100, "执行智能时间轴校验...")
            
            validation_result = self.validator.validate_and_correct(
                video_path, subtitle_path, output_subtitle_path
            )
            
            # 记录校验结果
            self.validation_results.append(validation_result)
            
            # 第4步：分析校验结果
            if progress_callback:
                progress_callback(80, 100, "分析校验结果...")
            
            result = self._process_validation_result(
                validation_result, video_path, subtitle_path, output_subtitle_path, project_name
            )
            
            # 第5步：生成报告
            if self.config.report_details:
                if progress_callback:
                    progress_callback(90, 100, "生成校验报告...")
                report_path = self._generate_validation_report(result, output_dir, project_name)
                result['report_path'] = report_path
            
            if progress_callback:
                progress_callback(100, 100, "智能校验导出完成")
            
            return result
            
        except Exception as e:
            logger.error(f"智能校验导出失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'fallback': True
            }
    
    def batch_export_with_validation(self, export_tasks: List[Dict], 
                                   progress_callback: Optional[Callable] = None) -> Dict:
        """批量导出带智能校验
        
        Args:
            export_tasks: 导出任务列表，每个任务包含video_path, subtitle_path, output_dir, project_name
            progress_callback: 进度回调函数
            
        Returns:
            批量导出结果
        """
        results = []
        total_tasks = len(export_tasks)
        
        for i, task in enumerate(export_tasks):
            if progress_callback:
                overall_progress = int((i / total_tasks) * 100)
                progress_callback(overall_progress, 100, f"处理任务 {i+1}/{total_tasks}: {task.get('project_name', 'Unknown')}")
            
            # 为每个任务创建子进度回调
            def task_progress(current, total, message):
                if progress_callback:
                    # 将任务进度映射到总进度
                    task_weight = 100 / total_tasks
                    task_progress_percent = (current / total) * task_weight
                    overall_progress = int((i / total_tasks) * 100 + task_progress_percent)
                    progress_callback(overall_progress, 100, f"任务{i+1}: {message}")
            
            result = self.export_with_smart_validation(
                task['video_path'],
                task['subtitle_path'],
                task['output_dir'],
                task['project_name'],
                task_progress
            )
            
            result['task_index'] = i
            result['project_name'] = task['project_name']
            results.append(result)
        
        # 统计结果
        successful = sum(1 for r in results if r['success'])
        failed = total_tasks - successful
        
        return {
            'success': failed == 0,
            'total_tasks': total_tasks,
            'successful': successful,
            'failed': failed,
            'results': results,
            'summary': self._generate_batch_summary(results)
        }
    
    def _backup_file(self, source_path: str, backup_path: str):
        """备份文件"""
        try:
            import shutil
            shutil.copy2(source_path, backup_path)
        except Exception as e:
            logger.warning(f"备份文件失败: {e}")
    
    def _process_validation_result(self, validation_result: Dict, video_path: str, 
                                 subtitle_path: str, output_path: str, project_name: str) -> Dict:
        """处理校验结果"""
        result = {
            'success': validation_result['success'],
            'project_name': project_name,
            'video_path': video_path,
            'original_subtitle_path': subtitle_path,
            'output_subtitle_path': output_path,
            'validation': validation_result
        }
        
        if validation_result['success']:
            action = validation_result.get('action', 'unknown')
            
            if action == 'no_correction_needed':
                result['message'] = f"[OK] {project_name}: 时间轴精度良好，无需修正"
                result['status'] = 'perfect'
                # 如果不需要修正，复制原文件到输出路径
                if subtitle_path != output_path:
                    self._backup_file(subtitle_path, output_path)
                    
            elif action == 'corrected':
                strategy = validation_result.get('strategy', 'unknown')
                improvement = validation_result.get('improvement', 0)
                result['message'] = f"[OK] {project_name}: 应用{strategy}修正，改善{improvement:.3f}s"
                result['status'] = 'corrected'
                result['improvement'] = improvement
                result['strategy'] = strategy
                
            else:
                result['message'] = f"[WARN] {project_name}: 校验完成但状态未知"
                result['status'] = 'unknown'
        else:
            error = validation_result.get('error', '未知错误')
            result['message'] = f"[ERROR] {project_name}: 校验失败 - {error}"
            result['status'] = 'failed'
            result['error'] = error
            
            # 校验失败时，复制原文件作为回退
            if subtitle_path != output_path:
                self._backup_file(subtitle_path, output_path)
        
        return result
    
    def _generate_validation_report(self, result: Dict, output_dir: str, project_name: str) -> str:
        """生成校验报告"""
        report_path = os.path.join(output_dir, f"{project_name}_validation_report.json")
        
        try:
            import json
            
            report_data = {
                'project_name': project_name,
                'timestamp': self._get_timestamp(),
                'validation_config': {
                    'enabled': self.config.enabled,
                    'auto_correct': self.config.auto_correct,
                    'validation_level': self.config.validation_level,
                    'max_deviation_threshold': self.config.max_deviation_threshold
                },
                'result': result,
                'system_info': {
                    'smart_validation_available': SMART_VALIDATION_AVAILABLE,
                    'validator_version': '1.0.0'
                }
            }
            
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False)
            
            return report_path
            
        except Exception as e:
            logger.warning(f"生成校验报告失败: {e}")
            return ""
    
    def _generate_batch_summary(self, results: List[Dict]) -> Dict:
        """生成批量处理摘要"""
        summary = {
            'perfect_count': 0,      # 无需修正
            'corrected_count': 0,    # 已修正
            'failed_count': 0,       # 失败
            'total_improvement': 0.0, # 总改善时间
            'strategies_used': {},    # 使用的策略统计
            'common_issues': []       # 常见问题
        }
        
        for result in results:
            status = result.get('status', 'unknown')
            
            if status == 'perfect':
                summary['perfect_count'] += 1
            elif status == 'corrected':
                summary['corrected_count'] += 1
                summary['total_improvement'] += result.get('improvement', 0)
                
                strategy = result.get('strategy', 'unknown')
                summary['strategies_used'][strategy] = summary['strategies_used'].get(strategy, 0) + 1
            elif status == 'failed':
                summary['failed_count'] += 1
        
        return summary
    
    def _get_timestamp(self) -> str:
        """获取时间戳"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def get_validation_statistics(self) -> Dict:
        """获取校验统计信息"""
        if not self.validation_results:
            return {'message': '暂无校验数据'}
        
        stats = {
            'total_validations': len(self.validation_results),
            'successful_validations': sum(1 for r in self.validation_results if r['success']),
            'corrections_applied': sum(1 for r in self.validation_results if r.get('action') == 'corrected'),
            'perfect_timelines': sum(1 for r in self.validation_results if r.get('action') == 'no_correction_needed'),
            'average_improvement': 0.0
        }
        
        # 计算平均改善
        improvements = [r.get('improvement', 0) for r in self.validation_results if r.get('improvement')]
        if improvements:
            stats['average_improvement'] = sum(improvements) / len(improvements)
        
        return stats


# 创建全局实例
export_validator = ExportWithValidation() if SMART_VALIDATION_AVAILABLE else None


def create_validation_config(enabled: bool = True, auto_correct: bool = True, 
                           validation_level: str = "standard") -> ValidationConfig:
    """创建校验配置的便捷函数"""
    config = ValidationConfig()
    config.enabled = enabled
    config.auto_correct = auto_correct
    config.validation_level = validation_level
    return config
