import json,sys
d=json.load(open(sys.argv[1]))
def fresh(source,predicate):
    return [r for r in d["notices"] if r["source"]==source and r["id"] in d["sources"].get(source,{}).get("freshIds",[]) and predicate(r)]
tuvalu=fresh("wb",lambda r:r["id"]=="OP00482505")
ungm=fresh("ungm",lambda r:r["id"]=="322032")
idlo=fresh("idlo",lambda r:"HQ-2026-000192" in (r["id"]+" "+r.get("reference","")) and "MDA" in r["countries"])
for source,rows in [("wb OP00482505",tuvalu),("ungm 322032",ungm),("idlo HQ-2026-000192",idlo)]:
    print(source,"PASS" if rows else "FAIL",flush=True)
    for r in rows:print(r["title"],r["url"],r["countries"],flush=True)
print("TWO_TARGETS_DISCOVERED", "PASS" if tuvalu and (ungm or idlo) else "FAIL",flush=True)
assert tuvalu and (ungm or idlo),"Live two-target discovery failed"
# Preserve the explicit UNGM coverage failure even if the same tender is found via IDLO.
assert ungm,"UNGM source coverage unresolved (IDLO is a separate official source)"
