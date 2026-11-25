#!/usr/bin/env python3
"""Translate public procurement lists locally with MIT-licensed M2M100/CTranslate2."""
import argparse, json, os, pathlib, re, subprocess, time
from datetime import datetime,timezone
from collections import Counter
HANGUL=re.compile("[가-힣]")
LANGS=dict(GBR="en",CAN="en",AUT="de",BEL="fr",BGR="bg",HRV="hr",CYP="el",CZE="cs",DNK="da",EST="et",FIN="fi",FRA="fr",DEU="de",GRC="el",HUN="hu",IRL="en",ITA="it",LVA="lv",LTU="lt",LUX="fr",MLT="en",NLD="nl",POL="pl",PRT="pt",ROU="ro",SVK="sk",SVN="sl",ESP="es",SWE="sv")
MODEL="gn64/M2M100_418M_CTranslate2"
REVISION="18e406c"
PROVIDER="M2M100-418M-int8 (MIT)"
def title_text(r):
    t=r["title"]
    # TED English display prefix is metadata; translate the actual procurement title.
    parts=t.split(" – ",2)
    return parts[2] if r.get("source")=="eu" and len(parts)==3 and parts[2].strip() else t
def lang_for(r,text):
    import langid
    fallback=(r.get("detail") or {}).get("language") or LANGS.get(str(r.get("country","")).split(" | ")[0],"en")
    if fallback not in LANGS.values():fallback="en"
    if len(text)>=25:
        found,_=langid.classify(text)
        if found in LANGS.values():return found
    return fallback
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--notices",type=pathlib.Path,required=True)
    p.add_argument("--output",type=pathlib.Path,required=True)
    p.add_argument("--publish",type=pathlib.Path,required=True)
    p.add_argument("--max-batches",type=int,default=200)
    a=p.parse_args()
    source=json.loads(a.notices.read_text(encoding="utf-8"))
    cache=json.loads(a.output.read_text(encoding="utf-8"))
    cache.setdefault("titles",{});cache.setdefault("buyers",{})
    items=[];seen=set()
    for kind,field in [("titles","title"),("buyers","buyer")]:
        for r in source["notices"]:
            v=r.get(field)
            if not isinstance(v,str) or not v.strip() or v in cache[kind] or (kind,v) in seen:continue
            seen.add((kind,v))
            text=title_text(r) if kind=="titles" else v
            items.append((kind,v,text,r))
    def publish():
        cache["generatedAt"]=datetime.now(timezone.utc).isoformat()
        cache["provider"]=PROVIDER
        cache["modelRevision"]=REVISION
        tmp=a.output.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
        tmp.replace(a.output)
        subprocess.run(["bash",str(a.publish.resolve())],check=True)
    def coverage():
        return sum(bool(cache["titles"].get(r["title"])) for r in source["notices"])
    if not items:
        print("Korean title coverage",coverage(),"/",len(source["notices"]),flush=True)
        return 0
    import ctranslate2, sentencepiece
    from huggingface_hub import snapshot_download
    model=snapshot_download(MODEL,revision=REVISION,allow_patterns=["config.json","model.bin","sentencepiece.bpe.model","shared_vocabulary.json","README.md"])
    sp=sentencepiece.SentencePieceProcessor(model_file=str(pathlib.Path(model)/"sentencepiece.bpe.model"))
    tr=ctranslate2.Translator(model,device="cpu",compute_type="int8",inter_threads=2,intra_threads=2)
    def run(batch):
        src=[["__"+lang_for(r,text)+"__"]+sp.encode(text,out_type=str)+["</s>"] for kind,key,text,r in batch]
        result=tr.translate_batch(src,target_prefix=[["__ko__"]]*len(src),beam_size=2,max_batch_size=16,max_input_length=512,max_decoding_length=256)
        out=[]
        for x in result:
            tokens=x.hypotheses[0]
            out.append(sp.decode([t for t in tokens if t not in ("__ko__","</s>","<s>","<pad>")]).strip())
        return out
    smoke=run([("titles","test","Software development and maintenance",{"source":"uk","country":"GBR"})])
    if not smoke or not HANGUL.search(smoke[0]):raise RuntimeError("Korean model smoke test failed")
    print("Korean model smoke:",smoke[0],flush=True)
    completed=0;batch_count=0
    for offset in range(0,len(items),32):
        if batch_count>=a.max_batches:break
        batch=items[offset:offset+32]
        result=run(batch)
        for (kind,key,text,r),ko in zip(batch,result):
            if ko and (HANGUL.search(ko) or (kind=="buyers" and ko==text)):
                cache[kind][key]=ko;completed+=1
        batch_count+=1
        print("Korean title coverage",coverage(),"/",len(source["notices"]),"batch",batch_count,flush=True)
        if batch_count==1 or batch_count%4==0:publish()
    if completed:publish()
    print("Korean title coverage",coverage(),"/",len(source["notices"]),flush=True)
    return int(coverage()!=len(source["notices"]))
if __name__=="__main__":raise SystemExit(main())
