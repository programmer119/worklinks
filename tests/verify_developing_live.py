import json,sys
d=json.load(open(sys.argv[1]))
checks={"ungm":"322032","wb":"OP00482505"}
for s,i in checks.items():
    fresh=d["sources"][s].get("freshIds",[])
    rows=[r for r in d["notices"] if r["source"]==s and r["id"]==i and i in fresh]
    print(s,i,"PASS" if rows else "FAIL",flush=True)
    if rows: print(rows[0]["title"],rows[0]["url"],rows[0]["countries"])
assert all(i in d["sources"][s].get("freshIds",[]) and any(r["source"]==s and r["id"]==i for r in d["notices"]) for s,i in checks.items()),"Live source acceptance gate failed"
