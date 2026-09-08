import os,sys,time,tiktoken
enc=tiktoken.get_encoding('o200k_base'); enc2=tiktoken.get_encoding('cl100k_base')
SRC={'.java','.scala','.py','.ts','.tsx','.js','.go','.kt','.groovy','.sh','.gradle'}
SKIP={'.git','node_modules','.venv','target','build','dist','.gradle'}
root=sys.argv[1]; t0=time.time(); chars=0; tok=0; tok2=0; n=0
for dp,dns,fns in os.walk(root):
    dns[:]=[d for d in dns if d not in SKIP]
    for f in fns:
        if os.path.splitext(f)[1] in SRC:
            try: s=open(os.path.join(dp,f),encoding='utf-8',errors='replace').read()
            except OSError: continue
            chars+=len(s); tok+=len(enc.encode(s,disallowed_special=())); tok2+=len(enc2.encode(s,disallowed_special=())); n+=1
print(f"{root}: files={n} chars={chars} o200k_tokens={tok} cl100k_tokens={tok2} chars_per_o200k_tok={chars/max(tok,1):.2f} chars_per_cl100k_tok={chars/max(tok2,1):.2f} secs={time.time()-t0:.1f}")
