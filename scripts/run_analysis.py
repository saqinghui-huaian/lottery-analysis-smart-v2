#!/usr/bin/env python3
"""
一体化分析脚本 — 数据获取 + 统计分析 + 推荐生成 + 格式化输出
=================================================================

解决的问题：context压缩后AI丢失skill指令，导致分析质量下降。
本脚本将所有分析逻辑和格式化自动化，AI只需执行脚本、原样输出结果。

Usage:
    python3 run_analysis.py --games 3d          # 只分析福彩3D
    python3 run_analysis.py --games 35          # 只分析排三
    python3 run_analysis.py --games 3d,35       # 3D+排三
    python3 run_analysis.py --games 85          # 大乐透
    python3 run_analysis.py --games 3d,35,85    # 全部分析

输出：完整的格式化文本，直接复制粘贴即可。

数学基础:
- 组六72%, 组三27%, 豹子1%
- 和值7-20占83.2%, 跨度4-7占56.4%
- 奇偶1:2或2:1各37.5%, 大小1:2或2:1各37.5%
- 遗漏期望E=9期, P(≥15)=20.6%, P(≥20)=12.2%
"""

import sys
import os
import json
import argparse
from collections import Counter
from datetime import datetime

# Add skill scripts directory to path
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SKILL_DIR)

from lottery_analysis import fetch_3d, fetch_pl3, fetch_dlt
from smart_selector import SmartNumberSelector


def compute_analysis_context(data):
    """
    计算完整分析上下文，用于生成所有分析逻辑bullet。
    返回一个字典，包含所有需要的统计数据。
    """
    ctx = {}
    n = len(data)
    
    # ── 各位频率（近20/50期）──
    ctx['freq20'] = [Counter(), Counter(), Counter()]
    ctx['freq50'] = [Counter(), Counter(), Counter()]
    for d in data[:20]:
        for pos, key in enumerate(['h', 't', 'u']):
            ctx['freq20'][pos][d[key]] += 1
    for d in data[:50]:
        for pos, key in enumerate(['h', 't', 'u']):
            ctx['freq50'][pos][d[key]] += 1
    
    # ── 遗漏值 ──
    ctx['miss'] = [{}, {}, {}]
    for digit in range(10):
        for pos, key in enumerate(['h', 't', 'u']):
            for i, d in enumerate(data):
                if d[key] == digit:
                    ctx['miss'][pos][digit] = i
                    break
            else:
                ctx['miss'][pos][digit] = n
    
    # ── 和值统计 ──
    sums = [d['h'] + d['t'] + d['u'] for d in data[:50]]
    ctx['hz_avg'] = sum(sums) / len(sums) if sums else 13.5
    
    # ── 和尾遗漏 ──
    ctx['sum_tail_miss'] = {}
    for tail in range(10):
        for i, d in enumerate(data):
            if (d['h'] + d['t'] + d['u']) % 10 == tail:
                ctx['sum_tail_miss'][tail] = i
                break
        else:
            ctx['sum_tail_miss'][tail] = n
    
    # ── 跨度统计 ──
    spans = [max(d['h'], d['t'], d['u']) - min(d['h'], d['t'], d['u']) for d in data[:50]]
    ctx['kd_avg'] = sum(spans) / len(spans) if spans else 4.5
    
    # ── 跨度遗漏 ──
    ctx['span_miss'] = {}
    for sp in range(10):
        for i, d in enumerate(data):
            kd = max(d['h'], d['t'], d['u']) - min(d['h'], d['t'], d['u'])
            if kd == sp:
                ctx['span_miss'][sp] = i
                break
        else:
            ctx['span_miss'][sp] = n
    
    # ── 形态统计（近50期）──
    ctx['shape_cnt'] = Counter()
    for d in data[:50]:
        unique = len(set([d['h'], d['t'], d['u']]))
        if unique == 1:
            ctx['shape_cnt']['豹子'] += 1
        elif unique == 2:
            ctx['shape_cnt']['组三'] += 1
        else:
            ctx['shape_cnt']['组六'] += 1
    
    # ── 奇偶比（近20期）──
    ctx['odd_even_cnt'] = Counter()
    for d in data[:20]:
        odd = sum(1 for x in [d['h'], d['t'], d['u']] if x % 2 == 1)
        ctx['odd_even_cnt'][f'{odd}:{3-odd}'] += 1
    
    # ── 大小比（近20期）──
    ctx['big_small_cnt'] = Counter()
    for d in data[:20]:
        big = sum(1 for x in [d['h'], d['t'], d['u']] if x >= 5)
        ctx['big_small_cnt'][f'{big}:{3-big}'] += 1
    
    return ctx


def find_strong_miss_signal(ctx, pos_key, label, threshold=15):
    """
    查找某位置最强的遗漏信号。
    返回 (digit, miss_periods, signal_strength) 或 None
    """
    pos_map = {'bai': 0, 'shi': 1, 'ge': 2}
    pos = pos_map[pos_key]
    
    max_miss = 0
    max_digit = -1
    for digit in range(10):
        m = ctx['miss'][pos].get(digit, 0)
        if m > max_miss:
            max_miss = m
            max_digit = digit
    
    if max_miss >= threshold:
        # 计算信号强度
        ratio = max_miss / 9.0  # 期望遗漏=9期
        if max_miss >= 25:
            strength = '极强信号'
        elif max_miss >= 20:
            strength = '强信号'
        elif max_miss >= 15:
            strength = '中等信号'
        else:
            strength = '弱信号'
        return (max_digit, max_miss, strength, ratio)
    return None


def find_strong_sum_tail_miss(ctx, threshold=10):
    """查找和尾最强遗漏信号"""
    max_miss = 0
    max_tail = -1
    for tail in range(10):
        m = ctx['sum_tail_miss'].get(tail, 0)
        if m > max_miss:
            max_miss = m
            max_tail = tail
    
    if max_miss >= threshold:
        ratio = max_miss / 9.0
        if max_miss >= 18:
            strength = '强信号'
        elif max_miss >= 14:
            strength = '中等信号'
        else:
            strength = '弱信号'
        return (max_tail, max_miss, strength, ratio)
    return None


def find_strong_span_miss(ctx, threshold=8):
    """查找跨度最强遗漏信号"""
    max_miss = 0
    max_span = -1
    for sp in range(10):
        m = ctx['span_miss'].get(sp, 0)
        if m > max_miss:
            max_miss = m
            max_span = sp
    
    if max_miss >= threshold:
        ratio = max_miss / 9.0
        if max_miss >= 15:
            strength = '强信号'
        elif max_miss >= 10:
            strength = '中等信号'
        else:
            strength = '弱信号'
        return (max_span, max_miss, strength, ratio)
    return None


def get_hot_numbers(ctx, top_n=3):
    """获取各位热号"""
    result = {}
    for pos, label in enumerate(['百位', '十位', '个位']):
        hot = [x[0] for x in ctx['freq20'][pos].most_common(top_n)]
        result[label] = '/'.join(str(x) for x in hot)
    return result


def format_3d_report(data, name, selector_output, analysis_ctx, gold_silver, include_header=True):
    """
    格式化3D/排三的完整分析报告。
    
    selector_output: SmartNumberSelector.analyze_and_recommend() 的返回值 (selected, ctx)
    analysis_ctx: compute_analysis_context() 的返回值（用于6个bullet）
    gold_silver: (gold_tuple, silver_tuple) 金码银码
    include_header: 是否包含header（多彩种时只在第一个彩种包含）
    """
    selected, _ = selector_output
    n = len(data)
    
    # 最新一期
    latest = data[0]
    latest_period = latest['period']
    latest_date = latest['date']
    latest_nums = f"{latest['h']}{latest['t']}{latest['u']}"
    
    # 计算待开期号
    try:
        latest_num = int(latest_period)
        next_period = str(latest_num + 1)
    except:
        next_period = '???'
    
    # 起始期号
    start_period = data[-1]['period']
    
    # 金码银码
    gold, silver = gold_silver
    gold_str = f"{gold[0]}{gold[1]}{gold[2]} / {silver[0]}{silver[1]}{silver[2]}"
    silver_str = f"{silver[0]}{silver[1]}{silver[2]} / {gold[0]}{gold[1]}{gold[2]}"
    
    # 使用 analysis_ctx
    ctx = analysis_ctx
    
    # Build report
    lines = []
    if include_header:
        lines.append(f"### 📊 {name}")
    else:
        lines.append(f"### 📊 {name}")
    lines.append(f"**最新开奖：{latest_period}期（{latest_date}）→ {latest_nums}**")
    lines.append(f"**待开：{next_period}期**")
    lines.append(f"**🥇 金码：{gold_str}**")
    lines.append(f"**🥈 银码：{silver_str}**")
    
    # 10注推荐表格
    lines.append(f"**📋 10注推荐：**")
    lines.append(f"| 序号 | 号码 | 和值 | 跨度 |")
    lines.append(f"|:---:|:---:|:---:|:---:|")
    
    for i, item in enumerate(selected[:10]):
        b, s, g = item['b'], item['s'], item['g']
        hz = item['hz']
        kd = item['kd']
        lines.append(f"| {i+1} | **{b}{s}{g}** | {hz} | {kd} |")
    
    # 分析逻辑（6个bullet，全部自动生成）
    lines.append(f"**分析逻辑：**")
    
    # Bullet 1: 遗漏回补
    miss_signals = []
    for pos_key, label in [('bai', '百位'), ('shi', '十位'), ('ge', '个位')]:
        sig = find_strong_miss_signal(ctx, pos_key, label, threshold=15)
        if sig:
            digit, miss, strength, ratio = sig
            miss_signals.append(f"{label}**{digit}**遗漏**{miss}期**（均值9期，{ratio:.1f}倍）→ {strength}")
    
    if miss_signals:
        lines.append(f"- 遗漏回补：{'；'.join(miss_signals)}")
    else:
        lines.append(f"- 遗漏回补：暂无强信号（各位置遗漏均在正常范围内）")
    
    # Bullet 2: 和尾遗漏
    sum_tail_sig = find_strong_sum_tail_miss(ctx, threshold=10)
    if sum_tail_sig:
        tail, miss, strength, ratio = sum_tail_sig
        lines.append(f"- 和尾遗漏：和尾**{tail}**遗漏**{miss}期**（均值9期，{ratio:.1f}倍）→ {strength}，回补方向")
    else:
        # 找出遗漏最大的和尾
        max_tail_miss = max(ctx['sum_tail_miss'].items(), key=lambda x: x[1])
        lines.append(f"- 和尾遗漏：和尾{max_tail_miss[0]}遗漏{max_tail_miss[1]}期，暂无强回补信号")
    
    # Bullet 3: 跨度遗漏
    span_sig = find_strong_span_miss(ctx, threshold=8)
    if span_sig:
        sp, miss, strength, ratio = span_sig
        lines.append(f"- 跨度遗漏：跨度**{sp}**遗漏**{miss}期**（均值9期，{ratio:.1f}倍）→ {strength}，回补方向")
    else:
        max_span_miss = max(ctx['span_miss'].items(), key=lambda x: x[1])
        lines.append(f"- 跨度遗漏：跨度{max_span_miss[0]}遗漏{max_span_miss[1]}期，暂无强回补信号")
    
    # Bullet 4: 热号支撑
    hot = get_hot_numbers(ctx, top_n=3)
    lines.append(f"- 热号支撑：百位{hot['百位']}，十位{hot['十位']}，个位{hot['个位']}")
    
    # Bullet 5: 形态统计
    zuliu = ctx['shape_cnt'].get('组六', 0)
    zusan = ctx['shape_cnt'].get('组三', 0)
    baozi = ctx['shape_cnt'].get('豹子', 0)
    lines.append(f"- 形态统计：组六{zuliu}次、组三{zusan}次、豹子{baozi}次")
    
    # Bullet 6: 奇偶比/大小比
    # 找最常见的奇偶比
    top_oe = ctx['odd_even_cnt'].most_common(1)[0] if ctx['odd_even_cnt'] else ('1:2', 0)
    top_bs = ctx['big_small_cnt'].most_common(1)[0] if ctx['big_small_cnt'] else ('1:2', 0)
    lines.append(f"- 奇偶比{top_oe[0]}（{top_oe[1]}次），大小比{top_bs[0]}（{top_bs[1]}次）")
    
    return '\n'.join(lines)


def format_dlt_report(data, selected, analyzer):
    """
    格式化大乐透的完整分析报告。
    使用 dlt_analysis.py 的 DLTAnalyzer 和 format_report。
    去掉原脚本自带的footer（由主脚本统一添加）。
    """
    from dlt_analysis import format_report
    raw = format_report(analyzer, selected)
    # 去掉末尾的 disclaimer 行（以 "> ⚠️" 或 "> 数据来源" 开头的行）
    lines = raw.split('\n')
    filtered = []
    for line in lines:
        if line.startswith('> ⚠️') or line.startswith('> 数据来源') or line.startswith('> 分析维度'):
            continue
        filtered.append(line)
    return '\n'.join(filtered).rstrip()


def run_single_game(game_code, count=200):
    """
    运行单个彩种的完整分析流程。
    返回格式化的报告文本。
    """
    if game_code in ('3d', '3D'):
        name = '福彩3D'
        data = fetch_3d(count)
        print(f"[{name}] 获取到 {len(data)} 期数据", file=sys.stderr)
        
        # 分析上下文（用于6个bullet）
        analysis_ctx = compute_analysis_context(data)
        
        # 使用 SmartNumberSelector 生成推荐和金码银码
        smart = SmartNumberSelector()
        selected, sel_ctx = smart.analyze_and_recommend(data, style='balanced')
        gold_silver = smart.generate_gold_silver(data, sel_ctx, style='balanced')
        
        # 生成完整报告
        report = format_3d_report(data, name, (selected, sel_ctx), analysis_ctx, gold_silver)
        return report, data
        
    elif game_code == '35':
        name = '排列三'
        data = fetch_pl3('35', count)
        print(f"[{name}] 获取到 {len(data)} 期数据", file=sys.stderr)
        
        analysis_ctx = compute_analysis_context(data)
        
        smart = SmartNumberSelector()
        selected, sel_ctx = smart.analyze_and_recommend(data, style='balanced')
        gold_silver = smart.generate_gold_silver(data, sel_ctx, style='balanced')
        
        report = format_3d_report(data, name, (selected, sel_ctx), analysis_ctx, gold_silver)
        return report, data
        
    elif game_code == '85':
        name = '大乐透'
        data = fetch_dlt(count)
        print(f"[{name}] 获取到 {len(data)} 期数据", file=sys.stderr)
        
        from dlt_analysis import DLTAnalyzer
        analyzer = DLTAnalyzer(data, style='balanced')
        selected = analyzer.recommend(5)
        
        report = format_dlt_report(data, selected, analyzer)
        return report, data
        
    else:
        raise ValueError(f"不支持的彩种代码: {game_code}")


def main():
    parser = argparse.ArgumentParser(description='一体化彩票分析脚本')
    parser.add_argument('--games', type=str, required=True,
                        help='彩种列表，逗号分隔: 3d,35,85')
    parser.add_argument('--count', type=int, default=200,
                        help='获取数据期数 (默认200)')
    args = parser.parse_args()
    
    game_codes = [g.strip() for g in args.games.split(',')]
    
    # 按固定顺序排列: 3d -> 35 -> 85
    order = {'3d': 0, '3D': 0, '35': 1, '85': 2}
    game_codes.sort(key=lambda x: order.get(x, 99))
    
    reports = []
    all_data = {}
    name_map = {'3d': '福彩3D', '3D': '福彩3D', '35': '排列三', '85': '大乐透'}
    
    for code in game_codes:
        try:
            report, data = run_single_game(code, args.count)
            reports.append(report)
            all_data[code] = data
        except Exception as e:
            print(f"[ERROR] {code}: {e}", file=sys.stderr)
            reports.append(f"⚠️ {code} 分析失败: {e}")
    
    # 构建统一header
    header_parts = []
    for code in game_codes:
        if code in all_data:
            d = all_data[code]
            name = name_map.get(code, code)
            header_parts.append(f"{name} {d[-1]['period']}–{d[0]['period']}期")
    
    # 合并输出（所有彩种一条消息）
    now = datetime.now()
    output = f"分析完成，基于100期数据，多策略评分推荐如下：\n"
    output += "---\n"
    output += "## 🎰 金码银码推荐 & 10注精选\n"
    output += f"**{now.strftime('%Y-%m-%d %H:%M')} | {' | '.join(header_parts)}**\n"
    output += "---\n"
    output += "\n---\n".join(reports)
    
    # 添加统一footer
    output += "\n---\n"
    output += "> ⚠️ 仅供参考，请理性投注！\n"
    
    # 计算数据来源
    source_parts = []
    for code in game_codes:
        if code in all_data:
            d = all_data[code]
            source_parts.append(f"{d[-1]['period']}–{d[0]['period']}(各{len(d)}期)")
    output += f"> 数据来源：官方API {' | '.join(source_parts)}，智能选号系统V2.4\n"
    output += "> \n"
    output += "> 📊 选号说明：基于概率分布的智能选号，不是预测\n"
    output += "> - 和值7-20（占83.2%）、跨度4-7（占56.4%）、组六（占72%）\n"
    output += "> - 奇偶1:2或2:1（各37.5%）、大小1:2或2:1（各37.5%）\n"
    output += "> - 命中率≈1%（与随机选号相同），只提高选号质量\n"
    output += f"> ⏱️ 生成时间：{now.strftime('%Y-%m-%d %H:%M:%S')}（脚本实时生成，非缓存）\n"
    
    print(output)


if __name__ == '__main__':
    main()
