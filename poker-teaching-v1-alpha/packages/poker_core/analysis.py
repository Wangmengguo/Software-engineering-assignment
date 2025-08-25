from .cards import parse_card, get_rank_value

def classify_starting_hand(cards):
    r1,s1 = parse_card(cards[0])
    r2,s2 = parse_card(cards[1])
    v1, v2 = get_rank_value(r1), get_rank_value(r2)
    pair = r1 == r2
    suited = s1 == s2
    gap = abs(v1 - v2) - 1
    high = max(v1, v2)
    low = min(v1, v2)

    if pair and max(v1, v2) >= 11:
        cat = "premium_pair"
    elif (suited and high >= 13 and low >= 10) or (pair and max(v1, v2) >= 10):
        cat = "strong"
    elif suited and gap <= 1 and high >= 10:
        cat = "speculative"
    elif high >= 13 and low >= 10:
        cat = "broadway_offsuit"
    elif high < 10 and not suited and gap >= 3:
        cat = "weak_offsuit"
    else:
        cat = "weak"
    return {"pair": pair, "suited": suited, "gap": gap, "high": high, "low": low, "category": cat}

def annotate_player_hand(cards):
    info = classify_starting_hand(cards)
    notes = []
    if info["category"] == "weak":
        notes.append({"code":"E001","severity":"warn","msg":"Weak offsuit/unconnected. Consider folding preflop from early position."})
    if info["category"] == "weak_offsuit":
        notes.append({"code":"E002","severity":"warn","msg":"Very weak offsuit/unconnected. Consider folding preflop from early position."})
    if info["suited"] and info["gap"] <= 1 and info["low"] >= 9:
        notes.append({"code":"N101","severity":"info","msg":"Suited & relatively connected. Potential for draws."})
    if info["pair"] and info["high"] >= 11:
        notes.append({"code":"N102","severity":"info","msg":"Premium pair: raise or 3-bet in many spots."})
    return {"info": info, "notes": notes}
