import subprocess,sys,time
t=float(sys.argv[1]); cmd=sys.argv[2:]; s=time.time()
try: r=subprocess.run(cmd,timeout=t); print(f"exit={r.returncode} secs={time.time()-s:.0f}")
except subprocess.TimeoutExpired: print(f"TIMEOUT after {t}s")
