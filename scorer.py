import pandas as pd, re, json
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def parse_rubric_from_excel(excel_path, sheet_name='Rubrics'):
    x = pd.read_excel(excel_path, sheet_name=sheet_name, header=None, dtype=str).fillna("")
    start = 25
    end = 60
    rows = x.iloc[start:end]
    criteria = {}
    current = None
    for idx, row in rows.iterrows():
        crit = str(row[1]).strip()
        metric = str(row[2]).strip()
        scoring = str(row[3]).strip()
        keywords_cell = str(row[4]).strip()
        score_attr = str(row[5]).strip()
        total_score = str(row[6]).strip()
        if crit and crit.lower()!="nan":
            current = crit
            if current not in criteria:
                criteria[current] = {"metrics": [], "total_possible": None}
        if current is None:
            continue
        try:
            s_attr = float(score_attr) if score_attr not in ("", "nan") else None
        except:
            s_attr = None
        try:
            t_score = float(total_score) if total_score not in ("", "nan") else None
        except:
            t_score = None
        criteria[current]["metrics"].append({
            "metric": metric,
            "scoring": scoring,
            "keywords_cell": keywords_cell,
            "score_attributed": s_attr,
            "total_score": t_score
        })
        if t_score is not None:
            criteria[current]["total_possible"] = t_score
    rubric = []
    for k,v in criteria.items():
        kws = []
        for m in v["metrics"]:
            cell = m["keywords_cell"]
            if cell and cell not in ("-","nan"):
                parts = re.split(r"[,\n]", cell)
                for p in parts:
                    p = p.strip()
                    if p and len(p.split())<=8:
                        cleaned = re.sub(r"[^\w\s]","",p).lower()
                        kws.append(cleaned)
        weight = v["total_possible"] if v["total_possible"] is not None else sum([m["score_attributed"] or 0 for m in v["metrics"]])
        rubric.append({
            "criterion": k,
            "description": " | ".join([m["scoring"] for m in v["metrics"] if m["scoring"] and m["scoring"]!="nan"]),
            "keywords": list(dict.fromkeys([kk for kk in kws if kk])),
            "weight": float(weight or 0)
        })
    total = sum([r['weight'] for r in rubric]) or 1.0
    for r in rubric:
        r['weight_norm'] = r['weight'] / total
    return rubric

def score_transcript(transcript, excel_path="Case study for interns.xlsx"):
    rubric = parse_rubric_from_excel(excel_path)
    texts = [transcript] + [r["description"] for r in rubric]
    vectorizer = TfidfVectorizer(stop_words='english').fit(texts)
    tvec = vectorizer.transform([transcript])
    results = []
    import re
    for r in rubric:
        kws = r.get("keywords", [])
        if not kws:
            kw_score = 1.0
            found = []
        else:
            found = []
            for k in kws:
                if re.search(r"\b" + re.escape(k) + r"\b", transcript, flags=re.I):
                    found.append(k)
            kw_score = len(found)/len(kws) if len(kws)>0 else 0.0
        desc_vec = vectorizer.transform([r["description"]])
        sem = float(cosine_similarity(tvec, desc_vec)[0,0])
        composite = 0.45*kw_score + 0.45*sem + 0.10*1.0
        results.append({
            "criterion": r["criterion"],
            "weight": r["weight"],
            "weight_norm": r["weight_norm"],
            "keyword_score": round(kw_score,3),
            "keywords_found": found,
            "semantic_similarity": round(sem,3),
            "composite_0_1": round(composite,4),
            "score_0_100": round(composite*100,2)
        })
    overall = sum([res["composite_0_1"] * res["weight_norm"] for res in results])
    overall_0_100 = round(overall*100,2)
    return {
        "transcript_length_words": len(re.findall(r"\w+", transcript)),
        "overall_score_0_100": overall_0_100,
        "per_criterion": results
    }
