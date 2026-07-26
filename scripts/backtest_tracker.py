#!/usr/bin/env python3
"""
彩票回测追踪系统
记录推荐结果和实际结果，计算命中率
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from collections import Counter


class BacktestTracker:
    """回测追踪器"""
    
    def __init__(self, data_dir: str = None):
        """
        data_dir: 数据存储目录
        默认：~/AppData/Local/hermes/lottery_backtest/
        """
        if data_dir is None:
            data_dir = os.path.expanduser('~/AppData/Local/hermes/lottery_backtest')
        
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        
        self.records_file = os.path.join(data_dir, 'backtest_records.json')
        self.records = self._load_records()
    
    def _load_records(self) -> List[Dict]:
        """加载历史记录"""
        if os.path.exists(self.records_file):
            try:
                with open(self.records_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        return []
    
    def _save_records(self):
        """保存记录"""
        with open(self.records_file, 'w', encoding='utf-8') as f:
            json.dump(self.records, f, ensure_ascii=False, indent=2)
    
    def record_recommendation(self, 
                            game: str,
                            period: str,
                            recommendations: List[Tuple],
                            data_source: str = 'api',
                            vision_confidence: float = 1.0):
        """
        记录推荐结果
        
        game: 彩种（'3d' 或 'pl3'）
        period: 待开期号
        recommendations: [(score, b, s, g, hz, kd), ...]
        data_source: 数据来源（'api', 'vision', 'mixed'）
        vision_confidence: vision数据置信度（0-1）
        """
        record = {
            'timestamp': datetime.now().isoformat(),
            'game': game,
            'period': period,
            'recommendations': [
                {
                    'number': f"{b}{s}{g}",
                    'score': round(sc, 1),
                    'sum': hz,
                    'span': kd
                }
                for sc, b, s, g, hz, kd in recommendations[:10]
            ],
            'data_source': data_source,
            'vision_confidence': vision_confidence,
            'actual': None,  # 待开奖后填写
            'hit': None,
            'hit_rank': None
        }
        
        self.records.append(record)
        self._save_records()
        
        return len(self.records) - 1  # 返回记录索引
    
    def record_result(self, game: str, period: str, actual: Tuple[int, int, int]):
        """
        记录实际开奖结果
        
        game: 彩种
        period: 期号
        actual: (百位, 十位, 个位)
        """
        b, s, g = actual
        
        # 查找对应的推荐记录
        for record in reversed(self.records):
            if record['game'] == game and record['period'] == period and record['actual'] is None:
                record['actual'] = f"{b}{s}{g}"
                
                # 检查是否命中
                for i, rec in enumerate(record['recommendations']):
                    if rec['number'] == f"{b}{s}{g}":
                        record['hit'] = True
                        record['hit_rank'] = i + 1
                        break
                else:
                    record['hit'] = False
                    record['hit_rank'] = -1
                
                self._save_records()
                return True
        
        return False
    
    def get_statistics(self, game: str = None, last_n: int = None) -> Dict:
        """
        获取统计数据
        
        game: 彩种筛选（None表示全部）
        last_n: 最近N条记录（None表示全部）
        
        返回：统计数据字典
        """
        records = self.records
        
        if game:
            records = [r for r in records if r['game'] == game]
        
        if last_n:
            records = records[-last_n:]
        
        if not records:
            return {
                'total': 0,
                'completed': 0,
                'hit_count': 0,
                'hit_rate': 0,
                'avg_hit_rank': 0,
                'vision_accuracy': 0
            }
        
        completed = [r for r in records if r['actual'] is not None]
        hits = [r for r in completed if r.get('hit', False)]
        
        # 计算vision数据准确性
        vision_records = [r for r in completed if r['data_source'] == 'vision']
        vision_hits = [r for r in vision_records if r.get('hit', False)]
        
        stats = {
            'total': len(records),
            'completed': len(completed),
            'hit_count': len(hits),
            'hit_rate': len(hits) / len(completed) * 100 if completed else 0,
            'avg_hit_rank': sum(r['hit_rank'] for r in hits) / len(hits) if hits else 0,
            'vision_records': len(vision_records),
            'vision_hit_rate': len(vision_hits) / len(vision_records) * 100 if vision_records else 0
        }
        
        # 按数据来源统计
        for source in ['api', 'vision', 'mixed']:
            source_records = [r for r in completed if r['data_source'] == source]
            source_hits = [r for r in source_records if r.get('hit', False)]
            stats[f'{source}_total'] = len(source_records)
            stats[f'{source}_hit_rate'] = len(source_hits) / len(source_records) * 100 if source_records else 0
        
        return stats
    
    def get_recent_performance(self, game: str = None, days: int = 7) -> Dict:
        """
        获取最近N天的表现
        
        game: 彩种筛选
        days: 天数
        
        返回：表现统计
        """
        from datetime import timedelta
        
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        records = [r for r in self.records if r['timestamp'] >= cutoff]
        
        if game:
            records = [r for r in records if r['game'] == game]
        
        completed = [r for r in records if r['actual'] is not None]
        hits = [r for r in completed if r.get('hit', False)]
        
        return {
            'period': f"最近{days}天",
            'total': len(records),
            'completed': len(completed),
            'hit_count': len(hits),
            'hit_rate': len(hits) / len(completed) * 100 if completed else 0
        }
    
    def export_report(self, game: str = None, output_file: str = None) -> str:
        """
        导出报告
        
        game: 彩种筛选
        output_file: 输出文件路径
        
        返回：报告内容
        """
        stats = self.get_statistics(game)
        recent = self.get_recent_performance(game, days=7)
        
        report = f"""# 彩票推荐回测报告
生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 总体统计
- 总记录数：{stats['total']}
- 已开奖：{stats['completed']}
- 命中次数：{stats['hit_count']}
- 命中率：{stats['hit_rate']:.1f}%
- 平均命中排名：{stats['avg_hit_rank']:.1f}

## 数据来源分析
- API数据：{stats.get('api_total', 0)}次，命中率{stats.get('api_hit_rate', 0):.1f}%
- Vision数据：{stats.get('vision_total', 0)}次，命中率{stats.get('vision_hit_rate', 0):.1f}%
- 混合数据：{stats.get('mixed_total', 0)}次，命中率{stats.get('mixed_hit_rate', 0):.1f}%

## 最近7天表现
- 记录数：{recent['total']}
- 已开奖：{recent['completed']}
- 命中次数：{recent['hit_count']}
- 命中率：{recent['hit_rate']:.1f}%

## 免责声明
⚠️ 彩票开奖为独立随机事件，历史命中率不能预测未来表现。
以上统计仅供参考，请理性投注。
"""
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)
        
        return report
    
    def analyze_mistakes(self, game: str = None, last_n: int = 20) -> Dict:
        """
        分析错误模式
        
        game: 彩种筛选
        last_n: 最近N条记录
        
        返回：错误分析
        """
        records = self.records
        
        if game:
            records = [r for r in records if r['game'] == game]
        
        if last_n:
            records = records[-last_n:]
        
        completed = [r for r in records if r['actual'] is not None]
        missed = [r for r in completed if not r.get('hit', False)]
        
        if not missed:
            return {'no_mistakes': True}
        
        # 分析未命中的号码特征
        actual_numbers = [r['actual'] for r in missed]
        actual_sums = [int(n[0]) + int(n[1]) + int(n[2]) for n in actual_numbers]
        actual_spans = [max(int(n[0]), int(n[1]), int(n[2])) - min(int(n[0]), int(n[1]), int(n[2])) for n in actual_numbers]
        
        # 分析推荐号码特征
        rec_numbers = []
        for r in missed:
            if r['recommendations']:
                rec_numbers.append(r['recommendations'][0]['number'])  # 取第一个推荐
        
        rec_sums = [int(n[0]) + int(n[1]) + int(n[2]) for n in rec_numbers]
        rec_spans = [max(int(n[0]), int(n[1]), int(n[2])) - min(int(n[0]), int(n[1]), int(n[2])) for n in rec_numbers]
        
        analysis = {
            'total_missed': len(missed),
            'actual_sum_avg': sum(actual_sums) / len(actual_sums) if actual_sums else 0,
            'rec_sum_avg': sum(rec_sums) / len(rec_sums) if rec_sums else 0,
            'actual_span_avg': sum(actual_spans) / len(actual_spans) if actual_spans else 0,
            'rec_span_avg': sum(rec_spans) / len(rec_spans) if rec_spans else 0,
            'sum_diff': abs(sum(actual_sums) / len(actual_sums) - sum(rec_sums) / len(rec_sums)) if actual_sums and rec_sums else 0,
            'span_diff': abs(sum(actual_spans) / len(actual_spans) - sum(rec_spans) / len(rec_spans)) if actual_spans and rec_spans else 0
        }
        
        # 判断是否有系统性偏差
        if analysis['sum_diff'] > 3:
            analysis['sum_bias'] = '实际和值偏大' if analysis['actual_sum_avg'] > analysis['rec_sum_avg'] else '实际和值偏小'
        
        if analysis['span_diff'] > 2:
            analysis['span_bias'] = '实际跨度偏大' if analysis['actual_span_avg'] > analysis['rec_span_avg'] else '实际跨度偏小'
        
        return analysis


if __name__ == '__main__':
    # 示例用法
    tracker = BacktestTracker()
    
    # 记录推荐
    sample_recommendations = [
        (85.5, 3, 7, 2, 12, 5),
        (82.3, 1, 5, 9, 15, 8),
        (80.1, 8, 2, 4, 14, 6),
    ]
    
    idx = tracker.record_recommendation(
        game='3d',
        period='2026001',
        recommendations=sample_recommendations,
        data_source='api'
    )
    
    print(f"记录索引：{idx}")
    
    # 记录开奖结果
    tracker.record_result('3d', '2026001', (3, 7, 2))
    
    # 获取统计
    stats = tracker.get_statistics()
    print(f"\n统计：{stats}")
    
    # 导出报告
    report = tracker.export_report()
    print(report)
