import os, sys, uvicorn
os.chdir(r"C:\Users\hp\Downloads\STONIC_SAP-main")
sys.path.insert(0, r"C:\Users\hp\Downloads\STONIC_SAP-main")
uvicorn.run("api.index:app", host="0.0.0.0", port=8001, log_level="warning")
