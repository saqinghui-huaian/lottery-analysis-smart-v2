#!/usr/bin/env python3
"""
彩票数据验证工具
用于验证vision提取的数据和API数据的一致性
"""

import re
from typing import List, Dict, Tuple, Optional
from collections import Counter


def validate_vision_data(vision_text: str, expected_periods: int = 5) -> Dict:
    """
    验证vision提取的文本数据
    
    vision_text: vision返回的文本
    expected_periods: 期望提取的期数
    
    返回：{'valid': bool, 'data': list, 'issues': list, 'confidence': float}
    """
    issues = []
    data = []
    
    # 尝试解析期号和号码
    # 格式1: "189期 720" 或 "189 7 2 0"
    # 格式2: "2026189 7 2 0"
    patterns = [
        r'(\d{3,7})\s*期?\s*(\d)\s*(\d)\s*(\d)',  # "189期 720" 或 "189 7 2 0"
        r'(\d{3,7})\s+(\d{3})',  # "189 720"
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, vision_text)
        if matches:
            for match in matches:
                if len(match) == 4:
                    period, b, s, g = match
                    data.append({
                        'period': period,
                        'h': int(b),
                        't': int(s),
                        'u': int(g)
                    })
                elif len(match) == 2:
                    period, num_str = match
                    if len(num_str) == 3:
                        data.append({
                            'period': period,
                            'h': int(num_str[0]),
                            't': int(num_str[1]),
                            'u': int(num_str[2])
                        })
            break
    
    # 检查数据完整性
    if len(data) == 0:
        issues.append("无法解析任何数据")
        return {'valid': False, 'data': [], 'issues': issues, 'confidence': 0.0}
    
    if len(data) < expected_periods:
        issues.append(f"提取数据不足：期望{expected_periods}期，实际{len(data)}期")
    
    # 检查数字范围
    for i, d in enumerate(data):
        if not (0 <= d['h'] <= 9 and 0 <= d['t'] <= 9 and 0 <= d['u'] <= 9):
            issues.append(f"第{i+1}期数字超出0-9范围：{d['h']}{d['t']}{d['u']}")
    
    # 检查期号连续性
    if len(data) >= 2:
        periods = [int(d['period']) for d in data]
        for i in range(len(periods) - 1):
            if periods[i] - periods[i+1] > 3:
                issues.append(f"期号跳跃过大：{periods[i]} -> {periods[i+1]}")
    
    # 计算置信度
    confidence = 1.0
    if len(data) < expected_periods:
        confidence *= 0.7
    if any('超出范围' in issue for issue in issues):
        confidence *= 0.5
    if any('跳跃过大' in issue for issue in issues):
        confidence *= 0.8
    
    return {
        'valid': len(issues) == 0,
        'data': data,
        'issues': issues,
        'confidence': confidence
    }


def cross_validate_vision_api(vision_data: List[Dict], api_data: List[Dict]) -> Dict:
    """
    交叉验证vision数据和API数据
    
    vision_data: vision提取的数据
    api_data: API获取的数据
    
    返回：{'match': bool, 'mismatches': list, 'vision_only': list, 'api_only': list}
    """
    mismatches = []
    vision_only = []
    api_only = []
    
    # 创建期号到数据的映射
    vision_map = {d['period']: d for d in vision_data}
    api_map = {d['period']: d for d in api_data}
    
    # 检查匹配
    for period in vision_map:
        if period in api_map:
            v = vision_map[period]
            a = api_map[period]
            if v['h'] != a['h'] or v['t'] != a['t'] or v['u'] != a['u']:
                mismatches.append({
                    'period': period,
                    'vision': f"{v['h']}{v['t']}{v['u']}",
                    'api': f"{a['h']}{a['t']}{a['u']}"
                })
        else:
            vision_only.append(period)
    
    for period in api_map:
        if period not in vision_map:
            api_only.append(period)
    
    return {
        'match': len(mismatches) == 0,
        'mismatches': mismatches,
        'vision_only': vision_only,
        'api_only': api_only
    }


def detect_vision_hallucination(vision_text: str) -> Dict:
    """
    检测vision是否产生幻觉数据
    
    常见幻觉模式：
    1. 所有数字出现次数过于均匀（标准差<2）
    2. 所有遗漏值都为0
    3. 数据明显不符合随机分布
    
    返回：{'hallucination_detected': bool, 'reasons': list, 'confidence': float}
    """
    reasons = []
    confidence = 1.0
    
    # 检测模式1：数字出现次数过于均匀
    # 提取频率数据
    freq_pattern = r'(\d)\s*[出现频率]*\s*[:：]\s*(\d+)'
    freq_matches = re.findall(freq_pattern, vision_text)
    
    if freq_matches:
        frequencies = [int(count) for _, count in freq_matches]
        if len(frequencies) >= 5:
            avg = sum(frequencies) / len(frequencies)
            std = (sum((f - avg)**2 for f in frequencies) / len(frequencies)) ** 0.5
            
            # 理论上，对于100期数据，每个数字期望出现10次，标准差约3
            if std < 2:
                reasons.append(f"数字频率过于均匀（标准差{std:.1f} < 2），可能是幻觉")
                confidence *= 0.3
    
    # 检测模式2：遗漏值全为0
    miss_pattern = r'遗漏\s*(\d+)\s*期'
    miss_matches = re.findall(miss_pattern, vision_text)
    
    if miss_matches:
        miss_values = [int(m) for m in miss_matches]
        if len(miss_values) >= 5 and all(m == 0 for m in miss_values):
            reasons.append("所有遗漏值都为0，明显不符合随机分布")
            confidence *= 0.2
    
    # 检测模式3：数据明显不符合随机分布
    # 例如：连续多期出现相同数字
    consecutive_pattern = r'(\d{3})\s*(\d{3})\s*(\d{3})'
    consecutive_matches = re.findall(consecutive_pattern, vision_text)
    
    if consecutive_matches:
        for i in range(len(consecutive_matches) - 2):
            nums = [consecutive_matches[i+j] for j in range(3)]
            if len(set(nums)) == 1:  # 连续3期相同
                reasons.append(f"连续3期出现相同号码{nums[0]}，概率极低")
                confidence *= 0.4
    
    return {
        'hallucination_detected': len(reasons) > 0,
        'reasons': reasons,
        'confidence': confidence
    }


def validate_api_data(api_data: List[Dict]) -> Dict:
    """
    验证API数据的完整性和合理性
    
    api_data: API返回的数据列表
    
    返回：{'valid': bool, 'issues': list, 'warnings': list, 'stats': dict}
    """
    issues = []
    warnings = []
    
    if not api_data:
        return {'valid': False, 'issues': ['数据为空'], 'warnings': [], 'stats': {}}
    
    # 检查数据格式
    for i, d in enumerate(api_data[:10]):
        if 'h' not in d or 't' not in d or 'u' not in d:
            issues.append(f"第{i}条数据缺少h/t/u字段")
        else:
            if not (0 <= d['h'] <= 9 and 0 <= d['t'] <= 9 and 0 <= d['u'] <= 9):
                issues.append(f"第{i}条数据数字超出0-9范围")
    
    # 检查期号连续性
    if len(api_data) >= 2 and 'period' in api_data[0]:
        try:
            p1 = int(api_data[0]['period'])
            p2 = int(api_data[1]['period'])
            if p1 - p2 > 5:
                warnings.append(f"期号跳跃较大：{p1} -> {p2}")
        except (ValueError, TypeError):
            pass
    
    # 检查数据量
    if len(api_data) < 20:
        warnings.append(f"数据量较少（{len(api_data)}期），统计结果可能不稳定")
    
    # 计算统计信息
    stats = {}
    if len(api_data) >= 10:
        sums = [d['h'] + d['t'] + d['u'] for d in api_data[:100]]
        stats['sum_avg'] = sum(sums) / len(sums)
        stats['sum_std'] = (sum((s - stats['sum_avg'])**2 for s in sums) / len(sums)) ** 0.5
        
        # 检查和值分布是否合理
        if stats['sum_std'] < 3:
            warnings.append(f"和值标准差过小（{stats['sum_std']:.1f}），可能数据异常")
    
    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'warnings': warnings,
        'stats': stats
    }


def create_validation_prompt(vision_text: str, api_data: List[Dict]) -> str:
    """
    创建验证提示，用于要求vision重新提取数据
    
    vision_text: 原始vision文本
    api_data: API数据（如有）
    
    返回：验证提示文本
    """
    prompt = f"""请仔细验证以下提取的数据是否正确：

原始提取文本：
{vision_text}

请检查：
1. 每个期号是否清晰可辨
2. 每个数字是否准确（0-9范围）
3. 期号是否连续
4. 是否有明显的识别错误

如有疑问，请重新提取最近3期的期号和号码，格式：
期号 百位 十位 个位

特别注意：
- 密集走势图中，数字可能重叠，需仔细分辨
- 统计表中的数字可能与走势图中的数字混淆
- 如有不确定，请标注"待确认"
"""
    
    if api_data:
        prompt += f"""
API数据（用于交叉验证）：
{api_data[:3]}

请对比API数据，确认提取的数据是否一致。
"""
    
    return prompt


if __name__ == '__main__':
    # 示例用法
    sample_vision = """
    189期 720
    188期 526
    187期 831
    186期 418
    185期 295
    """
    
    result = validate_vision_data(sample_vision, expected_periods=5)
    print("Vision数据验证：")
    print(f"  有效：{result['valid']}")
    print(f"  数据量：{len(result['data'])}期")
    print(f"  置信度：{result['confidence']:.2f}")
    if result['issues']:
        print(f"  问题：{result['issues']}")
    
    # 检测幻觉
    hallucination = detect_vision_hallucination(sample_vision)
    print(f"\n幻觉检测：")
    print(f"  检测到幻觉：{hallucination['hallucination_detected']}")
    if hallucination['reasons']:
        print(f"  原因：{hallucination['reasons']}")
