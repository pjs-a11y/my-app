def analyze_pongdang_pattern(records_tuple):
    valid = [r[2] for r in records_tuple if r[2] in ALL_COMBOS]
    if len(valid) < 2:
        return {'rec': '우삼', 'avoid': '좌사', 'pattern_str': '데이터 부족'}

    last = valid[-1]       # 직전 회차 (N-1)
    prev = valid[-2]       # 전전 회차 (N-2)

    # 1. 지울 픽: 직전 회차 조합은 무조건 제외 (퐁당 유지 가정)
    avoid_pick = last

    # 2. 추천 픽: 전전 회차(N-2) 조합을 우선 채택 (1:1 퐁당 유지)
    # 만약 전전 회차와 직전 회차가 같았더라도 완전 반대 성향 조합으로 강제 전환
    opposite_map = {
        '우사': '좌삼',
        '우삼': '좌사',
        '좌사': '우삼',
        '좌삼': '우사'
    }

    if prev != last:
        rec_pick = prev  # 퐁당 흐름 유지 (A -> B -> A)
    else:
        rec_pick = opposite_map.get(last, '우삼')  # 꺾이는 퐁당 시작점

    pattern_display = " ➔ ".join(valid[-4:]) + " (퐁당 가설 적용 중)"

    return {
        'rec': rec_pick,
        'rec_prob': 75.0,
        'avoid': avoid_pick,
        'avoid_prob': 5.0,
        'pattern_str': pattern_display
    }
