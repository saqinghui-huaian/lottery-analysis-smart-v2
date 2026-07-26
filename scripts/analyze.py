#!/usr/bin/env python3
"""彩票数据统计分析脚本 - 排列三/福彩3D/试机号"""

import json
import sys
from collections import Counter
from openpyxl import load_workbook

GAME_CONFIG = {
    "pl3": {"name": "排列三", "cols": (1, 2, 3), "labels": ("bai", "shi", "ge")},
    "sj":  {"name": "试机号", "cols": (4, 5, 6), "labels": ("bai", "shi", "ge")},
    "d3":  {"name": "福彩3D", "cols": (7, 8, 9), "labels": ("bai", "shi", "ge")},
}


def load_data(filepath, game_type="pl3"):
    """从 Excel 加载数据，返回期号列表和三位数字列表"""
    cfg = GAME_CONFIG[game_type]
    wb = load_workbook(filepath, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    wb.close()

    periods = []
    digits = []  # [[b,s,g], ...]
    for row in rows:
        if row[0] is None:
            continue
        period = str(row[0])
        try:
            b = int(row[cfg["cols"][0]])
            s = int(row[cfg["cols"][1]])
            g = int(row[cfg["cols"][2]])
        except (TypeError, ValueError, IndexError):
            continue
        if not (0 <= b <= 9 and 0 <= s <= 9 and 0 <= g <= 9):
            continue
        periods.append(period)
        digits.append([b, s, g])
    return periods, digits


def frequency_analysis(digits):
    """各位置 0-9 出现次数"""
    result = {}
    for idx, label in enumerate(["bai", "shi", "ge"]):
        counter = Counter(d[idx] for d in digits)
        result[label] = {str(k): v for k in range(10) for v in [counter.get(k, 0)]}
    return result


def hot_cold(freq, top_n=3):
    """热号/冷号"""
    result = {}
    for pos, counts in freq.items():
        sorted_nums = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        result[pos] = {
            "hot": [int(x[0]) for x in sorted_nums[:top_n]],
            "cold": [int(x[0]) for x in sorted_nums[-top_n:]],
        }
    return result


def sum_value_analysis(digits):
    """和值分析"""
    sums = [d[0] + d[1] + d[2] for d in digits]
    counter = Counter(sums)
    return {str(k): v for k in range(28) for v in [counter.get(k, 0)]}


def span_analysis(digits):
    """跨度分析"""
    spans = [max(d) - min(d) for d in digits]
    counter = Counter(spans)
    return {str(k): v for k in range(10) for v in [counter.get(k, 0)]}


def parity_analysis(digits):
    """奇偶分析"""
    sums = [d[0] + d[1] + d[2] for d in digits]
    odd = sum(1 for s in sums if s % 2 == 1)
    return {"odd": odd, "even": len(sums) - odd}


def size_analysis(digits):
    """大小分析 (5-9大, 0-4小)"""
    big = sum(sum(1 for x in d if x >= 5) for d in digits)
    total = len(digits) * 3
    return {"big": big, "small": total - big}


def shape_analysis(digits):
    """形态分析: 豹子/组三/组六"""
    baozi = zhuanti = zuliu = 0
    for d in digits:
        s = set(d)
        if len(s) == 1:
            baozi += 1
        elif len(s) == 2:
            zhuanti += 1
        else:
            zuliu += 1
    return {"baozi": baozi, "zhuanti": zhuanti, "zuliu": zuliu}


def miss_analysis(digits):
    """遗漏值 - 各位置各号码未出现期数"""
    result = {}
    for idx, label in enumerate(["bai", "shi", "ge"]):
        miss = {}
        for num in range(10):
            for i, d in enumerate(digits):
                if d[idx] == num:
                    miss[str(num)] = i
                    break
            else:
                miss[str(num)] = len(digits)
        result[label] = miss
    return result


def miss_alert(miss_data, threshold=8):
    """遗漏警报 - 遗漏≥threshold的号码"""
    alerts = []
    for pos, nums in miss_data.items():
        for num, m in nums.items():
            if m >= threshold:
                alerts.append({"position": pos, "number": int(num), "miss": m})
    alerts.sort(key=lambda x: x["miss"], reverse=True)
    return alerts


def recent_numbers(digits, n=10):
    """最近n期号码"""
    return [d for d in digits[-n:]]


def analyze(filepath, game_type="pl3"):
    """完整分析"""
    periods, digits = load_data(filepath, game_type)
    if not digits:
        print(json.dumps({"error": "No valid data found"}, ensure_ascii=False))
        sys.exit(1)

    freq = frequency_analysis(digits)
    miss = miss_analysis(digits)

    result = {
        "game": game_type,
        "game_name": GAME_CONFIG[game_type]["name"],
        "total": len(digits),
        "range": f"{periods[0]} ~ {periods[-1]}",
        "frequency": freq,
        "hot_cold": hot_cold(freq),
        "sum_value": sum_value_analysis(digits),
        "span": span_analysis(digits),
        "parity": parity_analysis(digits),
        "size": size_analysis(digits),
        "shape": shape_analysis(digits),
        "miss": miss,
        "miss_alert": miss_alert(miss),
        "recent": recent_numbers(digits),
    }
    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze.py <数据文件.xlsx> [game_type]")
        print("game_type: pl3 (default), sj, d3")
        sys.exit(1)

    filepath = sys.argv[1]
    game_type = sys.argv[2] if len(sys.argv) > 2 else "pl3"

    if game_type not in GAME_CONFIG:
        print(f"Error: unknown game_type '{game_type}', use: pl3, sj, d3")
        sys.exit(1)

    result = analyze(filepath, game_type)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
